"""ExamSkill — exam question generation (two-phase, code questions validated).

Pipeline: planner asks for a question TYPE distribution → worker generates
each question individually (short prompts, reasoning-model safe) → code
questions are sandbox-validated → near-duplicate questions are dropped →
returns the question list. Persistence (as drafts) stays with the caller.

User feedback 2026-09-17: per-question requests were generated with NO
awareness of each other, so the model kept repeating the same canonical
question 5-6 times. Two fixes: (1) every per-question prompt now lists the
questions already generated (negative examples); (2) a post-generation
similarity filter drops near-duplicates regardless of model behavior.
"""

import logging
import re

from difflib import SequenceMatcher

from ..harness import HarnessCore
from ..skill_config import skill_params
from .base import Skill

logger = logging.getLogger(__name__)

_QUESTION_SYSTEM = 'You are an expert examiner. Return JSON only.'

_WORD_RE = re.compile(r'[\W_]+', re.UNICODE)


def _plan_prompt(topic, difficulty, count) -> str:
    # NOTE: f-string, not str.format — the JSON braces would clash with
    # format placeholders (KeyError: '"types"').
    return (
        f"Plan a {difficulty} exam on '{topic}' with {count} questions. "
        f"Return JSON ONLY: "
        f'{{"types": ["multiple_choice", "code", "true_false", "essay", ...]}} '
        f"Exactly {count} entries. Mix: mostly multiple_choice/true_false, "
        f"at least one code and one essay. Order: easy first.")


_TYPE_CONTRACTS = {
    'multiple_choice': (
        '{"type": "multiple_choice", "text": "...", "points": 5, '
        '"options": {"A": "...", "B": "...", "C": "...", "D": "..."}, '
        '"correct_answer": "A", "explanation": "..."}\n'
        'correct_answer MUST be one of the option keys; the answer must be unambiguous.'),
    'true_false': (
        '{"type": "true_false", "text": "...", "points": 2, '
        '"correct_answer": true, "explanation": "..."}'),
    'code': (
        '{"type": "code", "text": "Write a function ...", "points": 10, '
        '"starter_code": "def f():\\n    pass", '
        '"solution_code": "def f():\\n    ...", '
        '"test_cases": [{"input": "f(1, 2)", "expected": 3, "is_hidden": false}], '
        '"explanation": "..."}\n'
        'test_cases are FUNCTION-BASED; solution_code must pass ALL of them.'),
    'essay': (
        '{"type": "essay", "text": "Explain ...", "points": 5, '
        '"word_limit": 200, "rubric": "...", "sample_answer": "..."}'),
}


def _normalize(text: str) -> str:
    """Lowercased alphanumeric tokens — similarity input."""
    return _WORD_RE.sub(' ', text or '').lower()


def _is_duplicate(candidate: dict, existing: list, threshold: float) -> bool:
    """True when the candidate's text is a near-duplicate of an accepted one."""
    cand = _normalize(candidate.get('text', ''))
    if not cand:
        return True  # empty question text is unusable
    for other in existing:
        ratio = SequenceMatcher(None, cand, _normalize(other.get('text', ''))).ratio()
        if ratio >= threshold:
            return True
    return False


def _already_generated_context(existing: list, limit: int = 10) -> str:
    """Negative-example list for the per-question prompt."""
    if not existing:
        return ''
    lines = []
    for question in existing[-limit:]:
        lines.append(f"- {question.get('text', '')[:80]}")
    return ('\n\nQuestions ALREADY generated for this exam (MUST NOT repeat '
            'or rephrase them):\n' + '\n'.join(lines))


class ExamSkill(Skill):
    name = 'exam_generation'
    description = 'AI 生成考题：题型分布(planner) → 逐题(worker) → 代码题沙箱验证 → 去重'

    def __init__(self):
        self.params = skill_params(self.name)

    def run(self, topic, difficulty='intermediate', count=10) -> dict:
        params = self.params
        count = max(1, min(count, params['max_questions']))

        # ---- Phase 1 (planner): question type distribution ----
        try:
            plan = HarnessCore.call(
                _plan_prompt(topic, difficulty, count),
                role='planner', system_prompt=_QUESTION_SYSTEM,
                temperature=params['plan_temperature'],
                max_tokens=params['plan_max_tokens'], json_mode=True)
            types = plan.get('types', []) if isinstance(plan, dict) else []
        except Exception as e:
            logger.warning('type planning failed (%s) — using default mix', e)
            types = ['multiple_choice'] * max(1, count - 2) + ['code', 'essay']
        types = [t for t in types[:count] if t in _TYPE_CONTRACTS]

        # ---- Phase 2 (worker): one short request per question ----
        questions = []
        duplicates_skipped = 0
        validated_code = 0
        code_total = 0
        for index, q_type in enumerate(types):
            question = self._generate_question(topic, difficulty, q_type, index,
                                               questions)
            if not question:
                continue
            if params['dedup_enabled'] and _is_duplicate(
                    question, questions, params['dedup_threshold']):
                logger.warning('question %d dropped as near-duplicate: %s',
                               index, question.get('text', '')[:60])
                duplicates_skipped += 1
                continue
            if q_type == 'code':
                code_total += 1
                ok, message = self._validate_code(question)
                question['_validated'] = ok
                question['_validation_message'] = message
                if ok:
                    validated_code += 1
            questions.append(question)

        return {
            'questions': questions,
            'duplicates_skipped': duplicates_skipped,
            'code_validated': f'{validated_code}/{code_total}',
            'all_code_valid': validated_code == code_total,
        }

    def validate(self, payload: dict) -> tuple[bool, str]:
        code_questions = [q for q in payload.get('questions', [])
                          if q.get('type') == 'code']
        for question in code_questions:
            ok, message = self._validate_code(question)
            if not ok:
                return False, f'代码题验证失败: {message}'
        return True, ''

    def _generate_question(self, topic, difficulty, q_type, index,
                           existing) -> dict:
        prompt = (
            f'Exam topic: {topic}（{difficulty}）. Create ONE {q_type} question '
            f'(#{index + 1}). Return JSON ONLY:\n{_TYPE_CONTRACTS[q_type]}'
            f'{_already_generated_context(existing)}')
        try:
            result = HarnessCore.call(
                prompt, role='worker', system_prompt=_QUESTION_SYSTEM,
                temperature=self.params['temperature'],
                max_tokens=self.params['max_tokens'], json_mode=True)
        except Exception as e:
            logger.warning('question %d (%s) failed: %s', index, q_type, e)
            return {}
        if isinstance(result, list):
            result = result[0] if result else {}
        return result if isinstance(result, dict) else {}

    def _validate_code(self, question) -> tuple[bool, str]:
        if not self.params['validate_code']:
            return True, '跳过沙箱验证（skill 参数）'
        from ..training_agent import validate_exercise
        ok, message, _detail = validate_exercise(
            question.get('solution_code', ''),
            question.get('test_cases', []))
        return ok, message

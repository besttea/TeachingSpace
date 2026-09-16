"""ExamSkill — exam question generation (two-phase, code questions validated).

Pipeline: planner asks for a question TYPE distribution → worker generates
each question individually (short prompts, reasoning-model safe) → code
questions are sandbox-validated → returns the question list. Persistence
(as drafts) stays with the caller.
"""

import json
import logging

from ..harness import HarnessCore
from .base import Skill

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 30

_QUESTION_SYSTEM = 'You are an expert examiner. Return JSON only.'


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


class ExamSkill(Skill):
    name = 'exam_generation'
    description = 'AI 生成考题：题型分布(planner) → 逐题(worker) → 代码题沙箱验证'

    def run(self, topic, difficulty='intermediate', count=10) -> dict:
        count = min(count, MAX_QUESTIONS)

        # ---- Phase 1 (planner): question type distribution ----
        try:
            plan = HarnessCore.call(
                _plan_prompt(topic, difficulty, count),
                role='planner', system_prompt=_QUESTION_SYSTEM,
                temperature=0.2, max_tokens=300, json_mode=True)
            types = plan.get('types', []) if isinstance(plan, dict) else []
        except Exception as e:
            logger.warning('type planning failed (%s) — using default mix', e)
            types = ['multiple_choice'] * max(1, count - 2) + ['code', 'essay']
        types = [t for t in types[:count] if t in _TYPE_CONTRACTS]

        # ---- Phase 2 (worker): one short request per question ----
        questions = []
        validated_code = 0
        code_total = 0
        for index, q_type in enumerate(types):
            question = self._generate_question(topic, difficulty, q_type, index)
            if not question:
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

    def _generate_question(self, topic, difficulty, q_type, index) -> dict:
        prompt = (
            f'Exam topic: {topic}（{difficulty}）. Create ONE {q_type} question '
            f'(#{index + 1}). Return JSON ONLY:\n{_TYPE_CONTRACTS[q_type]}')
        try:
            result = HarnessCore.call(
                prompt, role='worker', system_prompt=_QUESTION_SYSTEM,
                temperature=0.2, max_tokens=1200, json_mode=True)
        except Exception as e:
            logger.warning('question %d (%s) failed: %s', index, q_type, e)
            return {}
        if isinstance(result, list):
            result = result[0] if result else {}
        return result if isinstance(result, dict) else {}

    def _validate_code(self, question) -> tuple[bool, str]:
        from ..training_agent import validate_exercise
        ok, message, _detail = validate_exercise(
            question.get('solution_code', ''),
            question.get('test_cases', []))
        return ok, message

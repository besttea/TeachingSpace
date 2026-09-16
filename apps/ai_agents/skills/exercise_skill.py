"""ExerciseSkill — exercise generation with a sandbox validation fix-loop.

Pipeline: generate (worker) → validate in sandbox → on failure inject the
execution feedback and regenerate (max 2 fixes) → return the exercise dict
with its validation status. The caller persists.
"""

import json
import logging

from ..harness import HarnessCore
from .base import Skill

logger = logging.getLogger(__name__)

MAX_FIX_ATTEMPTS = 2

_CONTRACT = """
Return JSON ONLY with this exact structure:
{
    "title": "Exercise Title",
    "description": "Problem description...",
    "starter_code": "def function_name():\\n    pass",
    "solution_code": "def function_name():\\n    # solution",
    "test_cases": [
        {"input": "function_name(1, 2)", "expected": 3, "is_hidden": false}
    ],
    "hints": [
        {"order": 1, "content": "First hint...", "points_penalty": 2}
    ]
}

Test cases are FUNCTION-BASED: 'input' is a Python expression calling the
student's function; 'expected' is the EXACT return value. At least 3 cases.
"""


class ExerciseSkill(Skill):
    name = 'exercise_generation'
    description = 'AI 生成习题：生成 → 沙箱验证 → 反馈修复循环'

    def run(self, topic, difficulty='beginner') -> dict:
        exercise = self._generate(topic, difficulty)
        ok, message, detail = self.validate(exercise)
        attempts = 1

        while not ok and attempts <= MAX_FIX_ATTEMPTS:
            logger.warning('exercise failed validation (%s) — fix attempt %d',
                           message, attempts)
            exercise = self._fix(exercise, f'{message}: {detail.get("error") or ""}')
            ok, message, detail = self.validate(exercise)
            attempts += 1

        return {
            'exercise': exercise,
            'validated': ok,
            'validation_message': message,
            'attempts': attempts,
        }

    def validate(self, payload: dict) -> tuple[bool, str]:
        from ..training_agent import validate_exercise
        ok, message, detail = validate_exercise(
            payload.get('solution_code', ''), payload.get('test_cases', []))
        return ok, message, detail

    def _generate(self, topic, difficulty) -> dict:
        prompt = (
            f"Create a Python coding exercise on {topic} for {difficulty} level.\n"
            f"Requirements: clear problem statement; starter skeleton; a solution "
            f"that PASSES all test cases; ≥3 edge-case test cases; 3 progressive "
            f"hints.\n\n{_CONTRACT}")
        result = HarnessCore.call(
            prompt, role='worker',
            system_prompt='You are an expert Python coding interviewer. JSON only.',
            temperature=0.2, json_mode=True)
        if isinstance(result, list):
            result = result[0] if result else {}
        return result

    def _fix(self, previous, feedback) -> dict:
        prompt = (
            f"Your previous exercise draft was REJECTED by the sandbox executor:\n"
            f"{feedback}\n\nPrevious draft:\n{json.dumps(previous, ensure_ascii=False)[:3000]}"
            f"\n\nFix it so solution_code passes ALL test_cases. Return the corrected "
            f"full JSON.\n\n{_CONTRACT}")
        result = HarnessCore.call(
            prompt, role='worker',
            system_prompt='You are an expert Python coding interviewer. JSON only.',
            temperature=0.2, json_mode=True)
        if isinstance(result, list):
            result = result[0] if result else {}
        return result

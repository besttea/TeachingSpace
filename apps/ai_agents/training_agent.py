"""Training Agent — exercise generation & modification (skill mode).

Skill pattern (see .claude/skills/content-generator):
1. GENERATE: JSON contract (function-based test cases, `expected` not
   `expected_output`) → **sandbox validation**: the generated solution is
   executed against its test cases; on failure ONE retry is made with the
   execution feedback injected into the prompt; persistent failures are
   reported, never silently saved.
2. MODIFY: `modify_exercise` takes the current exercise + a natural-language
   instruction, returns an UPDATED full exercise dict (same contract), and
   the caller re-validates before applying.
"""

from .base_agent import BaseAgent

#: Prompt shared by generation and modification (single source of truth for
#: the exercise JSON contract).
_EXERCISE_CONTRACT = """
Output JSON ONLY with this exact structure:
{
    "title": "Exercise Title",
    "description": "Problem description...",
    "starter_code": "def function_name():\\n    pass",
    "solution_code": "def function_name():\\n    # solution",
    "test_cases": [
        {"input": "function_name(1, 2)", "expected": 3, "is_hidden": false},
        {"input": "function_name(-1, 1)", "expected": 0, "is_hidden": true}
    ],
    "hints": [
        {"order": 1, "content": "First hint...", "points_penalty": 2},
        {"order": 2, "content": "Second hint...", "points_penalty": 5}
    ]
}

Test cases are FUNCTION-BASED: 'input' is a Python expression calling the
student's function; 'expected' is the EXACT return value (a string only when
the function returns one). At least 3 test cases with edge cases.
"""


def validate_exercise(solution_code, test_cases):
    """Run the solution against the test cases in the sandbox.

    Returns (ok: bool, message: str, detail: dict). The authoritative check
    for AI-generated exercises — never trust the model's own claim.
    """
    from apps.code_runner.executor import CodeExecutor

    if not (solution_code or '').strip():
        return False, '参考答案为空', {}
    if not test_cases:
        return False, '测试用例为空', {}
    try:
        result = CodeExecutor().execute_with_tests(solution_code, test_cases, timeout=20)
    except TimeoutError:
        return False, '参考答案执行超时', {}
    passed = result.get('passed_tests', 0)
    total = result.get('total_tests', 0)
    ok = total > 0 and passed == total
    return ok, result.get('message', ''), result


class TrainingAgent(BaseAgent):
    """
    AI Agent for generating coding exercises, hints, and solutions.
    """

    def process_request(self, request_data):
        """
        Expected request_data: {'topic': str, 'difficulty': str, 'count': int}
        """
        topic = request_data.get('topic')
        difficulty = request_data.get('difficulty', 'beginner')
        return self.generate_exercise(topic, difficulty)

    def generate_exercise(self, topic, difficulty):
        """
        Generate a coding exercise with test cases and hints.
        """
        system_prompt = f"""
        You are an expert Python coding interviewer.
        Create a coding exercise on '{topic}' for {difficulty} level.

        {_EXERCISE_CONTRACT}
        """

        prompt = f"""
        Create a python coding exercise about {topic}.

        Requirements:
        1. Clear problem statement.
        2. {difficulty} difficulty level.
        3. Provide starter code skeleton.
        4. Provide working solution code that PASSES all test cases.
        5. Include at least 3 test cases (edge cases included).
        6. Provide 3 progressive hints.
        """

        result = self.generate_json(prompt, system_prompt)
        if isinstance(result, list):  # model dropped the outer wrapper
            result = result[0] if result else {}
        return result

    def generate_exercise_with_feedback(self, previous, feedback):
        """Retry generation with the sandbox failure feedback injected.

        Args:
            previous: the failed exercise dict from generate_exercise.
            feedback: human-readable failure description (executor output).
        """
        import json

        system_prompt = f"""
        You are an expert Python coding interviewer.

        {_EXERCISE_CONTRACT}
        """

        prompt = f"""
        Your previous exercise draft was REJECTED by the sandbox executor:
        {feedback}

        Previous draft:
        {json.dumps(previous, ensure_ascii=False)[:3000]}

        Fix the exercise so the solution_code passes ALL test_cases.
        Return the corrected full JSON.
        """

        result = self.generate_json(prompt, system_prompt)
        if isinstance(result, list):
            result = result[0] if result else {}
        return result

    def modify_exercise(self, exercise, instruction):
        """
        Modify an existing exercise per a natural-language instruction.

        Args:
            exercise: dict with the current exercise fields (title,
                description, starter_code, solution_code, test_cases, hints).
            instruction: what to change, e.g. "增加一个空列表的边界测试用例，
                并把提示改为更渐进".

        Returns the UPDATED full exercise dict (same contract as
        generate_exercise). The caller re-validates before applying.
        """
        import json

        current = json.dumps({
            k: exercise.get(k) for k in (
                'title', 'description', 'starter_code', 'solution_code',
                'test_cases', 'hints')
        }, ensure_ascii=False, indent=2)

        system_prompt = f"""
        You are an expert Python coding interviewer maintaining an exercise bank.

        {_EXERCISE_CONTRACT}
        """

        prompt = f"""
        Current exercise:
        {current}

        Instructor instruction:
        {instruction}

        Return the UPDATED exercise as JSON with the SAME structure.
        Rules:
        1. Keep unchanged parts exactly as they are.
        2. Apply the instruction precisely — do not redesign the exercise.
        3. If the instruction changes test cases, make sure the solution_code
           still passes ALL test cases.
        4. If it changes the difficulty, adjust description/test cases/hints
           accordingly.
        """

        result = self.generate_json(prompt, system_prompt)
        if isinstance(result, list):
            result = result[0] if result else {}
        return result

    def generate_hint(self, exercise_description, code_context):
        """
        Generate a specific hint based on current student code context.
        """
        prompt = f"""
        The student is stuck on this exercise:
        {exercise_description}

        Their current code:
        ```python
        {code_context}
        ```

        Provide a helpful hint without giving away the answer directly.
        """
        return self.generate(prompt, system_prompt="You are a helpful coding tutor.")

from .base_agent import BaseAgent

class TrainingAgent(BaseAgent):
    """
    AI Agent for generating coding exercises, hints, and solutions.
    """
    
    def process_request(self, request_data):
        """
        Process a request to generate an exercise.
        Expected request_data: {'topic': str, 'difficulty': str, 'count': int}
        """
        topic = request_data.get('topic')
        difficulty = request_data.get('difficulty', 'beginner')
        count = request_data.get('count', 1)
        
        # If count > 1, we might loop here, but for now let's generate one complex exercise
        # or return a list if the API supports it. The base agent generate_json returns one object.
        # We'll assume one exercise per request for simplicity in this method.
        return self.generate_exercise(topic, difficulty)

    def generate_exercise(self, topic, difficulty):
        """
        Generate a coding exercise with test cases and hints.
        """
        system_prompt = f"""
        You are an expert Python coding interviewer.
        Create a coding exercise on '{topic}' for {difficulty} level.
        
        Output JSON format:
        {{
            "title": "Exercise Title",
            "description": "Problem description...",
            "starter_code": "def function_name():\\n    pass",
            "solution_code": "def function_name():\\n    # solution",
            "test_cases": [
                {"input": "function_name(arg1, arg2)", "expected_output": "result", "is_hidden": false}
            ],
            "hints": [
                {"order": 1, "content": "First hint...", "points_penalty": 2},
                {"order": 2, "content": "Second hint...", "points_penalty": 5}
            ]
        }
        """
        
        prompt = f"""
        Create a python coding exercise about {topic}.
        
        Requirements:
        1. Clear problem statement.
        2. {difficulty} difficulty level.
        3. Provide starter code skeleton.
        4. Provide working solution code.
        5. Include at least 3 test cases (edge cases included). The 'input' field MUST be a valid python function call string (e.g. "my_func(1, 2)").
        6. Provide 3 progressive hints.
        """
        
        return self.generate_json(prompt, system_prompt)

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

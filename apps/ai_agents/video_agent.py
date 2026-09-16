import re

from .base_agent import BaseAgent


class VideoAgent(BaseAgent):
    """
    AI Agent for generating Manim animation scripts for educational videos.
    """

    def process_request(self, request_data):
        """
        Process request to generate a video script.
        """
        topic = request_data.get('topic')
        difficulty = request_data.get('difficulty', 'beginner')
        duration = request_data.get('duration', 60)
        return self.generate_video_script(topic, difficulty, duration)

    def generate_manim_script(self, topic, difficulty):
        """Generate a Manim script for the given topic (alias)."""
        return self.generate_video_script(topic, difficulty)

    def generate_video_script(self, topic, difficulty='beginner', duration=60):
        """
        Generate a Manim script for the given topic.

        Returns only the Python code (markdown fences stripped).
        """
        system_prompt = """
        You are an expert in Manim (Mathematical Animation Engine).
        Generate valid Python code using Manim Community Edition to visualize the given topic.

        Requirements:
        1. Import manim: `from manim import *`
        2. Create a class inheriting from `Scene`.
        3. Implement the `construct` method.
        4. Use clear animations (Write, FadeIn, Transform).
        5. Explain the concept visually with Text or Tex objects.
        6. Keep animations smooth and paced correctly.
        """

        prompt = f"""
        Create a Manim animation to explain the concept of '{topic}' for a {difficulty} level student.
        Keep the total animation around {duration} seconds.

        The script should:
        1. Show a title.
        2. Visualize the core concept (e.g., using shapes, graphs, or code snippets).
        3. Show a summary or key takeaway.

        Output ONLY the Python code, without markdown fences or explanations.
        """

        code = self.generate(prompt, system_prompt)
        return self._clean_script(code)

    @staticmethod
    def _clean_script(code: str) -> str:
        """Strip markdown fences/preamble and return just the Python code.

        The first fenced python block wins when present; otherwise the whole
        response is used as-is (the prompt asks for code only). Unlike the
        old ``replace('```', '')`` this never mangles backticks inside
        string literals.
        """
        if not code:
            return ''
        match = re.search(r'```(?:python)?\s*\n(.*?)```', code, re.DOTALL)
        if match:
            return match.group(1).strip()
        return code.strip()

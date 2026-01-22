from .base_agent import BaseAgent

class LearningAgent(BaseAgent):
    """
    AI Agent for generating educational content (lessons, explanations, examples).
    """
    
    def process_request(self, request_data):
        """
        Process a request to generate lesson content.
        Expected request_data: {'topic': str, 'difficulty': str, 'include_code': bool}
        """
        topic = request_data.get('topic')
        difficulty = request_data.get('difficulty', 'beginner')
        include_code = request_data.get('include_code', True)
        
        return self.generate_lesson_content(topic, difficulty, include_code)

    def generate_lesson_content(self, topic, difficulty, include_code=True):
        """
        Generate a structured lesson with text and code cells.
        """
        system_prompt = f"""
        You are an expert Python instructor creating a lesson on '{topic}' for {difficulty} level students.
        Your goal is to explain concepts clearly and provide practical code examples.
        
        Output Structure:
        Return a JSON object with a 'cells' key, containing a list of cell objects.
        Each cell object must have:
        - 'type': 'text' or 'code'
        - 'content': The markdown text or python code
        
        Example:
        {{
            "cells": [
                {{"type": "text", "content": "# Introduction\\n\\nHere is an explanation..."}},
                {{"type": "code", "content": "print('Hello World')"}}
            ]
        }}
        """
        
        prompt = f"""
        Create a comprehensive lesson on '{topic}'.
        
        Requirements:
        1. Start with a clear introduction and learning objectives.
        2. Break down the concept into logical sections.
        3. Use Markdown for text cells (headers, bold, lists).
        4. {'Include executable Python code examples.' if include_code else 'Focus on conceptual understanding.'}
        5. Conclude with a summary.
        6. Keep the tone encouraging and professional.
        """
        
        return self.generate_json(prompt, system_prompt)

    def generate_explanation(self, code_snippet):
        """
        Generate an explanation for a given code snippet.
        """
        prompt = f"Explain the following Python code step-by-step:\n\n```python\n{code_snippet}\n```"
        return self.generate(prompt, system_prompt="You are a helpful coding tutor.")

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
        return self.generate_manim_script(topic, difficulty)

    def generate_manim_script(self, topic, difficulty):
        """
        Generate a Manim script for the given topic.
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
        
        The script should:
        1. Show a title.
        2. Visualize the core concept (e.g., using shapes, graphs, or code snippets).
        3. Show a summary or key takeaway.
        """
        
        code = self.generate(prompt, system_prompt)
        
        # Clean up code blocks if present
        lines = code.split('\n')
        clean_lines = []
        in_code_block = False
        
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            
            # If we were in a code block, or if the model didn't use code blocks but just returned code
            # We try to heuristically detect if it's code. 
            # But simplest is to strip markdown fences.
            clean_lines.append(line)
            
        # Refined cleaning:
        cleaned_code = code.replace("```python", "").replace("```", "").strip()
        
        return cleaned_code

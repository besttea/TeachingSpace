from .base_agent import BaseAgent

import re


def _markdown_to_cells(text):
    """Fallback: split raw markdown into notebook cells.

    ```-fenced blocks become code cells; everything else becomes text
    cells (fence boundaries split the text). Used when a model ignores the
    JSON instruction but still produces a useful lesson.
    """
    cells = []
    buf = []
    mode = 'text'

    def flush():
        content = '\n'.join(buf).strip()
        if content:
            cells.append({'type': mode, 'content': content})
        buf.clear()

    for line in (text or '').split('\n'):
        if line.strip().startswith('```'):
            flush()
            mode = 'code' if mode == 'text' else 'text'
            continue
        buf.append(line)
    flush()
    return cells


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

    def generate_lesson_content(self, topic, difficulty, include_code=True,
                                source_material=''):
        """
        Generate a structured lesson with text and code cells.

        Two-phase design (robust against reasoning models like
        deepseek-flash, which burn thinking budget on long prompts):
        1. a tiny structure request (cell types + titles, small response);
        2. one short content request per cell.

        If phase 1 fails but produced usable text, the raw markdown is
        split into cells as a fallback.

        Args:
            source_material: optional teaching material (e.g. ClassLib
                notebook sections) the lesson must be grounded in.
        """
        structure_prompt = f"""
Lesson topic: {topic}（{difficulty}）

Plan a Jupyter-style lesson as 6-10 cells. Return JSON ONLY:
{{"cells": [{{"type": "text"|"code", "title": "short Chinese title"}}]}}

Order: intro → concept explanations → {'code examples interleaved' if include_code else 'concepts only'} → summary.
"""

        if source_material:
            structure_prompt += f"""

Ground the lesson in this teaching material (cover its key points):
{source_material[:3000]}
"""

        try:
            structure = self.generate_json(
                structure_prompt,
                system_prompt='You are a Python curriculum designer. Return JSON only.',
                max_tokens=800,
                role='planner')
            cells = structure.get('cells', []) if isinstance(structure, dict) else []
            if isinstance(structure, list):  # wrapper dropped
                cells = structure
            cells = [
                c for c in cells
                if c.get('type') in ('text', 'code') and c.get('title')
            ][:10]
            if not cells:
                raise ValueError('structure request returned no cells')
        except ValueError as e:
            # Fallback: one plain-content request, split markdown into cells
            raw_text = getattr(e, 'response_text', '')
            if raw_text.strip():
                cells = _markdown_to_cells(raw_text)
                if cells:
                    return {'cells': cells}
            fallback = self._generate_plain_lesson(topic, difficulty, source_material)
            return {'cells': _markdown_to_cells(fallback)}

        # Phase 2: one short request per cell
        result_cells = []
        for cell in cells:
            try:
                content = self._generate_cell_content(topic, cell, source_material)
                if content.strip():
                    result_cells.append({'type': cell['type'], 'content': content.strip()})
            except Exception as e:  # one bad cell must not sink the lesson
                logger.warning('cell %r generation failed: %s', cell.get('title'), e)
        return {'cells': result_cells}

    def _generate_cell_content(self, topic, cell, source_material):
        """One SHORT content request — small prompts keep reasoning models stable."""
        cell_type = cell['type']
        if cell_type == 'code':
            instruction = (
                f'Write ONLY the Python code for this cell (no fences, no '
                f'explanation). It must be runnable Python for beginners.')
        else:
            instruction = (
                f'Write ONLY the markdown content for this cell (no fences, '
                f'no HTML wrapper). Use headings, lists and inline code. '
                f'LaTeX via $...$ is allowed.')

        prompt = f'Lesson: {topic} | Cell type: {cell_type} | Cell title: {cell["title"]}\n\n{instruction}'
        if source_material:
            prompt += f'\n\nGround it in this material:\n{source_material[:2000]}'

        content = self.generate(
            prompt,
            system_prompt='You are a Python instructor writing notebook cells. '
                          'Output the cell content directly, nothing else.',
            temperature=0.3,
            max_tokens=1200,
        ).strip()
        if cell_type == 'code':
            # models sometimes wrap code in fences despite instructions
            content = content.replace('```python', '').replace('```', '').strip()
        return content

    def _generate_plain_lesson(self, topic, difficulty, source_material):
        """Last-resort single call: plain markdown lesson (no JSON demand)."""
        prompt = f"""
Write a complete lesson on {topic}（{difficulty}）in Chinese Markdown.
Structure: ## 学习目标, ## 讲解, {'## 代码示例 (with ```python fences)' if True else ''}, ## 小结.
"""
        if source_material:
            prompt += f'\n\nGround it in this material:\n{source_material[:2500]}'
        return self.generate(
            prompt,
            system_prompt='You are a Python instructor. Output markdown only.',
            temperature=0.5,
            max_tokens=3000,
        )

    def generate_explanation(self, code_snippet):
        """
        Generate an explanation for a given code snippet.
        """
        prompt = f"Explain the following Python code step-by-step:\n\n```python\n{code_snippet}\n```"
        return self.generate(prompt, system_prompt="You are a helpful coding tutor.")

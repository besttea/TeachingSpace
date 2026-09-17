"""Cell-level generation skills — the lesson editor's AI toolbar backend.

Four skills, one per cell type (user feedback 2026-09-17): text, code,
image (Manim still frame) and video (Manim animation). All follow the
Skill contract: produce content dicts, never persist; knobs live in
skill_config DEFAULTS (editable on the web settings page); every model
call goes through HarnessCore (role routing + fallback + audit).
"""

import logging

from ..harness import HarnessCore
from ..skill_config import skill_params
from .base import Skill

logger = logging.getLogger(__name__)


def _context_block(context: str, cap: int) -> str:
    """Optional grounding material (ClassLib/lesson text), truncated."""
    text = (context or '').strip()
    if not text:
        return ''
    return f'\n\nGround the content in this material (cover its key points):\n{text[:cap]}'


class TextSkill(Skill):
    """Generate markdown teaching content for one topic."""

    name = 'text_generation'
    description = 'AI 生成文本单元格：Markdown 教学内容（可接地素材）'

    def __init__(self):
        self.params = skill_params(self.name)

    def run(self, topic, context='') -> dict:
        params = self.params
        prompt = (
            f'Write a Markdown teaching section on "{topic}" for a Python '
            f'learning notebook: 2-4 paragraphs, clear headings (##), one '
            f'bullet list, inline code where useful; LaTeX $...$ allowed for '
            f'math. Chinese. Markdown ONLY — no fences around the whole '
            f'answer.\n\n{topic}{_context_block(context, params["context_char_cap"])}')
        try:
            result = HarnessCore.call(
                prompt, role='worker',
                system_prompt='You are a Python instructor writing notebook '
                              'text cells. Markdown only.',
                temperature=params['temperature'],
                max_tokens=params['max_tokens'])
        except Exception as e:
            logger.warning('text generation failed: %s', e)
            return {'content': '', 'error': str(e)[:200]}
        return {'content': (result or '').strip()}


class CodeSkill(Skill):
    """Generate a runnable Python snippet for one topic."""

    name = 'code_generation'
    description = 'AI 生成代码单元格：可运行的 Python 示例（可接地素材）'

    def __init__(self):
        self.params = skill_params(self.name)

    def run(self, topic, context='') -> dict:
        params = self.params
        prompt = (
            f'Write ONE runnable Python code cell teaching "{topic}": '
            f'5-15 lines, self-contained, with a short comment header and a '
            f'print that shows the result. No markdown fences, code only.'
            f'{_context_block(context, params["context_char_cap"])}')
        try:
            result = HarnessCore.call(
                prompt, role='worker',
                system_prompt='You write short, correct, runnable Python '
                              'notebook cells. Code only.',
                temperature=params['temperature'],
                max_tokens=params['max_tokens'])
        except Exception as e:
            logger.warning('code generation failed: %s', e)
            return {'content': '', 'error': str(e)[:200]}
        return {'content': (result or '').strip()}


class ImageSkill(Skill):
    """Generate a static-diagram Manim script (text-to-image)."""

    name = 'image_generation'
    description = 'AI 文生图：Manim 静帧脚本（渲染由调用方执行）'

    def __init__(self):
        self.params = skill_params(self.name)

    def run(self, description) -> dict:
        params = self.params
        prompt = (
            f'Create a Manim Community script that draws a STATIC diagram '
            f'illustrating: "{description}"\n\n'
            f'Requirements:\n'
            f'1. from manim import *; one Scene subclass; construct method\n'
            f'2. Build the shapes/text with no long animations — short FadeIn '
            f'is fine, the last frame must be the complete diagram\n'
            f'3. Use MathTex/Text with Chinese only via Text(font="Noto Sans CJK SC") '
            f'or avoid Chinese in labels; prefer English labels + simple shapes\n'
            f'4. No interactivity, no file IO, no imports beyond manim\n'
            f'Return ONLY the Python code, no fences.')
        try:
            result = HarnessCore.call(
                prompt, role='worker',
                system_prompt='You are an expert in Manim. Return Python code only.',
                temperature=params['temperature'],
                max_tokens=params['max_tokens'])
        except Exception as e:
            logger.warning('image script generation failed: %s', e)
            return {'script': '', 'error': str(e)[:200]}
        script = (result or '').strip()
        script = script.replace('```python', '').replace('```', '').strip()
        return {'script': script, 'description': description}


class VideoSkill(Skill):
    """Generate a Manim animation script (text-to-animation)."""

    name = 'video_generation'
    description = 'AI 文生动画：Manim 动画脚本（渲染由调用方异步执行）'

    def __init__(self):
        self.params = skill_params(self.name)

    def run(self, topic, difficulty='beginner', duration=60) -> dict:
        params = self.params
        prompt = (
            f'Create a Manim Community animation explaining "{topic}" for a '
            f'{difficulty} level student, paced for about {duration} seconds.\n\n'
            f'Requirements:\n'
            f'1. from manim import *; one Scene subclass; construct method\n'
            f'2. Clear animations: Write, FadeIn, Transform, Create\n'
            f'3. Visualize with shapes, axes, Text or MathTex (prefer English '
            f'labels for reliability)\n'
            f'4. No file IO, no network, no imports beyond manim\n'
            f'Return ONLY the Python code, no fences.')
        try:
            result = HarnessCore.call(
                prompt, role='worker',
                system_prompt='You are an expert in Manim. Return Python code only.',
                temperature=params['temperature'],
                max_tokens=params['max_tokens'])
        except Exception as e:
            logger.warning('video script generation failed: %s', e)
            return {'script': '', 'error': str(e)[:200]}
        script = (result or '').strip()
        script = script.replace('```python', '').replace('```', '').strip()
        return {'script': script, 'topic': topic}

"""CourseSkill — AI course generation pipeline (outline → per-lesson content).

Roles: planner (outline, chapter plans, cell structures) / worker (cell
content). Grounds in ClassLib material when ``source_material`` is provided
(callers obtain it via ``notebook_tools.find_related_sections``).
"""

import logging

from ..harness import HarnessCore
from .base import Skill

logger = logging.getLogger(__name__)

#: Hard cap on lessons generated in one run (cost control).
MAX_LESSONS = 30
MAX_CELLS_PER_LESSON = 10

_OUTLINE_SYSTEM = (
    'You are an expert curriculum designer for a Python teaching platform. '
    'Return JSON only.')

_OUTLINE_CONTRACT = """
Return JSON ONLY:
{"chapters": [{"title": "第1章 ...", "description": "one-line summary",
               "lessons": [{"title": "1.1 ...", "description": "one-line goal"}]}]}

Rules: lessons use X.Y numbering matching their chapter; 2-4 lessons per
chapter; progressive difficulty; Chinese titles.
"""

_STRUCTURE_PROMPT = """Plan a Jupyter lesson as 6-10 cells. Return JSON ONLY:
{"cells": [{"type": "text"|"code", "title": "short Chinese title"}]}
Order: intro → concepts → code examples interleaved → summary."""


class CourseSkill(Skill):
    name = 'course_generation'
    description = 'AI 生成完整课程：大纲 → 章节规划 → 逐单元两阶段内容'

    def run(self, topic, difficulty='beginner', chapter_count=3,
            source_material='', with_content=True) -> dict:
        """Generate a full course structure with optional lesson content.

        Returns:
            {'chapters': [{'title', 'description',
                           'lessons': [{'title', 'description', 'cells': [...]}]}]}
        """
        # ---- Phase 1 (planner): course outline ----
        prompt = (
            f"Design a {difficulty} level course outline on '{topic}' with "
            f"exactly {chapter_count} chapters. Focus on practical Python.\n\n"
            f"{_OUTLINE_CONTRACT}")
        if source_material:
            prompt += (
                "\n\nGround the outline in this teaching material (cover its "
                f"key points):\n{source_material[:3000]}")
        outline = HarnessCore.call(
            prompt, role='planner', system_prompt=_OUTLINE_SYSTEM,
            temperature=0.2, json_mode=True)
        if isinstance(outline, list):
            outline = {'chapters': outline}
        chapters = outline.get('chapters', [])[:chapter_count]

        result_chapters = []
        total_lessons = 0
        for chapter_index, chapter in enumerate(chapters):
            lessons = chapter.get('lessons', [])
            result_lessons = []
            for lesson_index, lesson in enumerate(lessons):
                if total_lessons >= MAX_LESSONS:
                    break
                cells = []
                if with_content:
                    cells = self._lesson_cells(
                        lesson.get('title') or f'{chapter_index + 1}.{lesson_index + 1}',
                        difficulty, source_material)
                result_lessons.append({
                    'title': lesson.get('title') or f'{chapter_index + 1}.{lesson_index + 1}',
                    'description': lesson.get('description', ''),
                    'cells': cells,
                })
                total_lessons += 1
            if result_lessons:
                result_chapters.append({
                    'title': chapter.get('title') or f'第{chapter_index + 1}章',
                    'description': chapter.get('description', ''),
                    'lessons': result_lessons,
                })
        return {'chapters': result_chapters, 'lesson_count': total_lessons}

    # -- lesson content: two-phase (structure → per-cell short requests) ----

    def _lesson_cells(self, lesson_title, difficulty, source_material) -> list:
        prompt = f"Lesson topic: {lesson_title}（{difficulty}）\n\n{_STRUCTURE_PROMPT}"
        try:
            structure = HarnessCore.call(
                prompt, role='worker',
                system_prompt=_OUTLINE_SYSTEM, temperature=0.2,
                max_tokens=800, json_mode=True)
        except Exception as e:
            logger.warning('cell structure request failed: %s — using markdown fallback', e)
            return self._fallback_cells(lesson_title, difficulty, source_material)

        if isinstance(structure, dict):
            structure = structure.get('cells', [])
        structure = [
            c for c in structure
            if isinstance(c, dict) and c.get('type') in ('text', 'code') and c.get('title')
        ][:MAX_CELLS_PER_LESSON]
        if not structure:
            return self._fallback_cells(lesson_title, difficulty, source_material)

        cells = []
        for cell in structure:
            content = self._cell_content(lesson_title, cell, source_material)
            if content:
                cells.append({'type': cell['type'], 'content': content})
        return cells

    def _cell_content(self, lesson_title, cell, source_material) -> str:
        if cell['type'] == 'code':
            instruction = ('Write ONLY the runnable Python code for this cell '
                           '(no fences, no explanation).')
        else:
            instruction = ('Write ONLY the markdown content (no fences): '
                           'headings, lists, inline code; LaTeX $...$ allowed.')
        prompt = (f'Lesson: {lesson_title} | Cell: {cell["title"]} ({cell["type"]})\n'
                  f'{instruction}')
        if source_material:
            prompt += f'\n\nGround it in:\n{source_material[:2000]}'
        try:
            content = HarnessCore.call(
                prompt, role='worker',
                system_prompt='You are a Python instructor writing notebook '
                              'cells. Output the cell content only.',
                temperature=0.3, max_tokens=1200)
        except Exception as e:
            logger.warning('cell %r failed: %s', cell.get('title'), e)
            return ''
        if cell['type'] == 'code':
            content = content.replace('```python', '').replace('```', '').strip()
        return content.strip()

    def _fallback_cells(self, lesson_title, difficulty, source_material) -> list:
        """One plain-markdown request split into cells (last resort)."""
        prompt = (
            f'Write a complete Chinese Markdown lesson on {lesson_title}'
            f'（{difficulty}）: ## 学习目标, ## 讲解, ## 代码示例 (```python '
            f'fences), ## 小结.')
        if source_material:
            prompt += f'\n\nGround it in:\n{source_material[:2500]}'
        try:
            text = HarnessCore.call(
                prompt, role='worker',
                system_prompt='You are a Python instructor. Markdown only.',
                temperature=0.5, max_tokens=3000)
        except Exception:
            return []
        return _markdown_to_cells(text)


def _markdown_to_cells(text: str) -> list:
    """Split markdown into cells on ``` fences (code vs text)."""
    cells, buf, mode = [], [], 'text'

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

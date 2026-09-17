"""KnowledgeSkill — extract structured knowledge points from teaching text.

Dual mode (user feedback 2026-09-17):
1. **grounded**: chapter teaching text and/or ClassLib material is present
   → the extraction is grounded in it;
2. **autonomous**: no material available → the prompt explicitly asks the
   model to outline the knowledge points from its own general knowledge of
   the topic (never fail or shrink because material is missing).

One worker call per chapter; defensive parsing — any failure returns []
without raising, so a broken chapter never aborts the whole extraction.
"""

import logging

from ..harness import HarnessCore
from ..skill_config import skill_params
from .base import Skill

logger = logging.getLogger(__name__)

_SYSTEM = 'You are an expert curriculum analyst. Return JSON only.'

_CONTRACT = (
    '{"points": [{"title": "知识点名称（简短，10 字内）", '
    '"description": "一句话说明该知识点涵盖什么", '
    '"difficulty": "beginner|intermediate|advanced"}]}')


class KnowledgeSkill(Skill):
    name = 'knowledge_extraction'
    description = 'AI 提炼知识点：从章节教学文本/ClassLib 素材提取结构化知识点（无素材时自主发挥）'

    def __init__(self):
        self.params = skill_params(self.name)

    def run(self, chapter_title, chapter_text='', source_material='') -> dict:
        """Skill contract wrapper around :meth:`extract`."""
        points = self.extract(chapter_title, chapter_text, source_material)
        return {'points': points, 'point_count': len(points)}

    def extract(self, chapter_title, chapter_text='', source_material='') -> list:
        """Extract the chapter's knowledge points. Never raises."""
        params = self.params
        cap = params['chapter_char_cap']
        text_block = (chapter_text or '').strip()[:cap]
        material_block = (source_material or '').strip()[:cap]

        if text_block:
            prompt = (
                f'章节：{chapter_title}\n\n以下是该章节的教学内容，请从中提炼'
                f'学生必须掌握的知识点（每条一句话，彼此独立、不重叠）：\n\n{text_block}')
        elif material_block:
            prompt = (
                f'章节：{chapter_title}\n\n以下是与该章节相关的教学素材，请从中提炼'
                f'学生必须掌握的知识点：\n\n{material_block}')
        else:
            # Autonomous mode: no local material — rely on the model's own
            # knowledge of the topic (explicit, so quality does not shrink).
            prompt = (
                f'章节：{chapter_title}\n\n该章节暂时没有现成教学素材。请基于你对'
                f'「{chapter_title}」这一主题的通识知识，列出该章节应覆盖的知识点'
                f'（由浅入深，彼此独立、不重叠）。')
        prompt += (
            f'\n\nReturn JSON ONLY:\n{_CONTRACT}\n'
            f'At most {params["max_points_per_chapter"]} points; '
            f'difficulty must be one of beginner/intermediate/advanced.')

        try:
            result = HarnessCore.call(
                prompt, role='worker', system_prompt=_SYSTEM,
                temperature=params['temperature'],
                max_tokens=params['max_tokens'], json_mode=True)
        except Exception as e:
            logger.warning('knowledge extraction failed for %r: %s', chapter_title, e)
            return []
        if isinstance(result, list):
            result = {'points': result}
        if not isinstance(result, dict):
            return []
        points = result.get('points', [])
        if not isinstance(points, list):
            return []
        cleaned = []
        for point in points:
            if not isinstance(point, dict):
                continue
            title = str(point.get('title', '')).strip()
            if not title:
                continue
            difficulty = point.get('difficulty', 'beginner')
            if difficulty not in ('beginner', 'intermediate', 'advanced'):
                difficulty = 'beginner'
            cleaned.append({
                'title': title[:200],
                'description': str(point.get('description', '')).strip()[:500],
                'difficulty': difficulty,
            })
        return cleaned[:params['max_points_per_chapter']]

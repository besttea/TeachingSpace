"""Celery tasks for the learning app — AI lesson generation off the request thread."""

import logging

from django.core.cache import cache

from celery import shared_task

logger = logging.getLogger(__name__)

_STATUS_TTL = 3600


def _status_key(lesson_id):
    return f'lesson_gen_status:{lesson_id}'


def lesson_gen_status(lesson_id) -> dict:
    return cache.get(_status_key(lesson_id)) or {'status': 'none'}


@shared_task
def generate_lesson_cells_task(lesson_id: int):
    """Generate a lesson's cells (two-phase harness pipeline) and save them.

    Progress is published to the cache for frontend polling; eager mode
    (dev default) runs this inline.
    """
    from apps.learning.models import Cell, Lesson

    lesson = Lesson.objects.filter(pk=lesson_id).first()
    if lesson is None:
        return

    cache.set(_status_key(lesson_id), {'status': 'running'}, _STATUS_TTL)
    try:
        from apps.ai_agents.learning_agent import LearningAgent
        from apps.chat.notebook_tools import find_related_sections

        query = f'{lesson.chapter.course.title} {lesson.title}'
        source_material = find_related_sections(query)
        generated = LearningAgent().generate_lesson_content(
            topic=lesson.title,
            difficulty=lesson.chapter.course.difficulty_level,
            include_code=True,
            source_material=source_material,
        )
        cells = generated.get('cells', [])

        from django.db import transaction
        with transaction.atomic():
            lesson.cells.all().delete()
            for order, cell in enumerate(cells):
                cell_type = cell.get('type')
                content = cell.get('content', '')
                if cell_type == 'code':
                    Cell.objects.create(
                        lesson=lesson, cell_type='code', order=order,
                        data={'source': content, 'output': '',
                              'execution_count': 0})
                else:
                    Cell.objects.create(
                        lesson=lesson, cell_type='text', order=order,
                        data={'markdown': content})

        cache.set(_status_key(lesson_id), {
            'status': 'done',
            'cell_count': len(cells),
            'grounded': bool(source_material),
        }, _STATUS_TTL)
    except Exception as e:
        logger.exception('lesson generation failed for lesson %s', lesson_id)
        cache.set(_status_key(lesson_id), {
            'status': 'error',
            'error': str(e)[:200],
        }, _STATUS_TTL)

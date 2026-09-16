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


def _design_status_key(course_id):
    return f'course_design_status:{course_id}'


def course_design_status(course_id) -> dict:
    return cache.get(_design_status_key(course_id)) or {'status': 'none'}


@shared_task
def design_course_outline_task(course_id: int):
    """AI-design a course outline (planner role) and create chapters+lessons.

    Runs after the course row exists; the create flow redirects to the
    outline page which polls course_design_status.
    """
    from apps.learning.models import Chapter, Course, Lesson

    course = Course.objects.filter(pk=course_id).first()
    if course is None:
        return

    cache.set(_design_status_key(course_id), {'status': 'running'}, _STATUS_TTL)
    try:
        from apps.ai_agents.skills import CourseSkill
        from apps.chat.notebook_tools import find_related_sections

        source_material = find_related_sections(course.title)
        outline = CourseSkill().run(
            topic=course.title,
            difficulty=course.difficulty_level,
            chapter_count=3,
            source_material=source_material,
            with_content=False,
        )

        created = 0
        for chapter_index, chapter_data in enumerate(outline.get('chapters', [])):
            chapter = Chapter.objects.create(
                course=course,
                title=chapter_data.get('title') or f'第{chapter_index + 1}章',
                description=chapter_data.get('description', ''),
                order=chapter_index,
            )
            for lesson_index, lesson_data in enumerate(chapter_data.get('lessons', [])):
                Lesson.objects.create(
                    chapter=chapter,
                    title=lesson_data.get('title') or f'课程单元 {lesson_index + 1}',
                    description=lesson_data.get('description', ''),
                    status='draft',
                    order=lesson_index,
                )
                created += 1

        cache.set(_design_status_key(course_id), {
            'status': 'done',
            'chapters': len(outline.get('chapters', [])),
            'lessons': created,
            'grounded': bool(source_material),
        }, _STATUS_TTL)
    except Exception as e:
        logger.exception('course design failed for course %s', course_id)
        cache.set(_design_status_key(course_id), {
            'status': 'error',
            'error': str(e)[:200],
        }, _STATUS_TTL)


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

        from apps.core.cache_utils import bump_content_version
        bump_content_version()

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

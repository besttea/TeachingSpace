"""Celery tasks for the learning app — AI lesson generation off the request thread."""

import logging

from django.core.cache import cache

from celery import shared_task

logger = logging.getLogger(__name__)

_STATUS_TTL = 3600
_MAX_RETRIES = 2  # OPTIMIZATION_PLAN 2.3: retry + exponential backoff


def _retry_countdown(retries: int) -> int:
    """Exponential backoff: 5s, 10s (capped at 120s)."""
    return min(120, 5 * 2 ** retries)


def _status_key(lesson_id):
    return f'lesson_gen_status:{lesson_id}'


def lesson_gen_status(lesson_id) -> dict:
    return cache.get(_status_key(lesson_id)) or {'status': 'none'}


def _design_status_key(course_id):
    return f'course_design_status:{course_id}'


def course_design_status(course_id) -> dict:
    return cache.get(_design_status_key(course_id)) or {'status': 'none'}


def _kp_status_key(course_id):
    return f'kp_extract_status:{course_id}'


def kp_extract_status(course_id) -> dict:
    return cache.get(_kp_status_key(course_id)) or {'status': 'none'}


@shared_task(bind=True, max_retries=_MAX_RETRIES)
def design_course_outline_task(self, course_id: int, chapter_count: int = 3):
    """AI-design a course outline (planner role) and create chapters+lessons.

    Runs after the course row exists; the create flow redirects to the
    outline page which polls course_design_status. The instructor picks
    the chapter count on the create form (1-10). Retried with exponential
    backoff on transient failures (OPTIMIZATION_PLAN 2.3).
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
            chapter_count=max(1, min(chapter_count, 10)),
            source_material=source_material,
            with_content=False,
        )

        created = 0
        # Atomic so a failed attempt cannot leave partial chapters behind
        # (retries would otherwise duplicate rows).
        from django.db import transaction
        with transaction.atomic():
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
        logger.warning('course design attempt %s failed: %s', self.request.retries + 1, e)
        # Eager mode has no broker: a retry would just propagate the Retry
        # exception into the calling view. Retries only exist with a broker.
        if self.request.retries < self.max_retries and not self.request.is_eager:
            cache.set(_design_status_key(course_id), {
                'status': 'retrying',
                'error': str(e)[:200],
            }, _STATUS_TTL)
            raise self.retry(exc=e, countdown=_retry_countdown(self.request.retries))
        logger.exception('course design failed for course %s after retries', course_id)
        cache.set(_design_status_key(course_id), {
            'status': 'error',
            'error': str(e)[:200],
        }, _STATUS_TTL)


@shared_task(bind=True, max_retries=_MAX_RETRIES)
def generate_lesson_cells_task(self, lesson_id: int):
    """Generate a lesson's cells (two-phase harness pipeline) and save them.

    Progress is published to the cache for frontend polling; eager mode
    (dev default) runs this inline. Retried with exponential backoff on
    transient failures (OPTIMIZATION_PLAN 2.3).
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
        logger.warning('lesson generation attempt %s failed: %s', self.request.retries + 1, e)
        # Eager mode has no broker: a retry would just propagate the Retry
        # exception into the calling view. Retries only exist with a broker.
        if self.request.retries < self.max_retries and not self.request.is_eager:
            cache.set(_status_key(lesson_id), {
                'status': 'retrying',
                'error': str(e)[:200],
            }, _STATUS_TTL)
            raise self.retry(exc=e, countdown=_retry_countdown(self.request.retries))
        logger.exception('lesson generation failed for lesson %s after retries', lesson_id)
        cache.set(_status_key(lesson_id), {
            'status': 'error',
            'error': str(e)[:200],
        }, _STATUS_TTL)


@shared_task(bind=True, max_retries=_MAX_RETRIES)
def extract_knowledge_points_task(self, course_id: int):
    """AI-extract knowledge points from a course's chapters (one worker
    request per chapter) and merge them into the knowledge-point DB.

    Grounding chain per chapter: lesson text cells → ClassLib related
    sections (find_related_sections) → autonomous model knowledge when
    neither exists (user feedback 2026-09-17: ClassLib + 自主发挥并重).
    Near-duplicates of existing points are skipped. Progress is published
    to the cache (kp_extract_status:<course_id>) for the instructor UI.
    """
    from apps.learning.models import Course, KnowledgePoint

    course = Course.objects.filter(pk=course_id).first()
    if course is None:
        return

    cache.set(_kp_status_key(course_id), {'status': 'running'}, _STATUS_TTL)
    try:
        from django.db import IntegrityError, transaction

        from apps.ai_agents.skills import KnowledgeSkill
        from apps.ai_agents.skill_config import skill_params
        from apps.ai_agents.skills.text_similarity import is_near_duplicate
        from apps.chat.notebook_tools import find_related_sections

        params = skill_params('knowledge_extraction')
        skill = KnowledgeSkill()
        chapters = list(course.chapters.all().prefetch_related('lessons__cells')
                        .order_by('order'))

        existing_titles = list(course.knowledge_points.values_list(
            'title', flat=True))
        created = 0
        duplicates = 0
        processed = 0

        for chapter in chapters:
            text_parts = []
            for lesson in chapter.lessons.all().order_by('order'):
                for cell in lesson.cells.all().order_by('order'):
                    if cell.cell_type == 'text':
                        markdown = cell.data.get('markdown', '')
                        if markdown:
                            text_parts.append(markdown)
            chapter_text = '\n\n'.join(text_parts).strip()

            source_material = ''
            if len(chapter_text) < 200:
                # thin or empty lesson content — ground in ClassLib first
                source_material = find_related_sections(
                    f'{course.title} {chapter.title}')

            try:
                points = skill.extract(
                    chapter.title, chapter_text, source_material)
            except Exception as e:
                logger.warning('chapter %r extraction failed: %s',
                               chapter.title, e)
                continue
            processed += 1

            for point in points:
                title = point['title']
                if params['dedup_enabled'] and is_near_duplicate(
                        title, existing_titles, params['dedup_threshold']):
                    duplicates += 1
                    continue
                try:
                    with transaction.atomic():
                        KnowledgePoint.objects.create(
                            course=course,
                            chapter=chapter,
                            title=title,
                            description=point['description'],
                            difficulty=point['difficulty'],
                            order=(course.knowledge_points.count()
                                   + created + duplicates + 1),
                            created_by=course.instructor,
                        )
                    created += 1
                    existing_titles.append(title)
                except IntegrityError:
                    duplicates += 1

        cache.set(_kp_status_key(course_id), {
            'status': 'done',
            'points_created': created,
            'chapters_processed': processed,
            'duplicates_skipped': duplicates,
        }, _STATUS_TTL)
    except Exception as e:
        logger.warning('kp extraction attempt %s failed: %s',
                       self.request.retries + 1, e)
        # Eager mode has no broker: a retry would just propagate the Retry
        # exception into the calling view. Retries only exist with a broker.
        if self.request.retries < self.max_retries and not self.request.is_eager:
            cache.set(_kp_status_key(course_id), {
                'status': 'retrying',
                'error': str(e)[:200],
            }, _STATUS_TTL)
            raise self.retry(exc=e, countdown=_retry_countdown(self.request.retries))
        logger.exception('kp extraction failed for course %s after retries',
                         course_id)
        cache.set(_kp_status_key(course_id), {
            'status': 'error',
            'error': str(e)[:200],
        }, _STATUS_TTL)

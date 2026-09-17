"""Celery tasks for the examination app — AI exam-question generation off
the request thread (web flow; eager inline in dev, like learning tasks).

OPTIMIZATION_PLAN 2.3: retried with exponential backoff on transient
failures; the final failure is published to the cache for the polling UI.
"""

import logging

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)

_STATUS_TTL = 3600
_MAX_RETRIES = 2


def _status_key(exam_id):
    return f'exam_gen_status:{exam_id}'


def exam_gen_status(exam_id) -> dict:
    return cache.get(_status_key(exam_id)) or {'status': 'none'}


def _retry_countdown(retries: int) -> int:
    """Exponential backoff: 5s, 10s (capped at 120s)."""
    return min(120, 5 * 2 ** retries)


@shared_task(bind=True, max_retries=_MAX_RETRIES)
def generate_exam_questions_task(self, exam_id: int, count: int = 10,
                                 difficulty: str = 'intermediate',
                                 topic: str = '',
                                 knowledge_points=None):
    """Two-phase AI generation of a full exam (ExamSkill) saved as questions.

    The exam row must already exist (created by the form or the manage
    page); this task fills it. When the exam is linked to a course with
    knowledge points, generation is knowledge-point-driven (one question
    per KP, distinct-first — no duplicates by construction); otherwise it
    falls back to autonomous topic generation. Progress is published to
    the cache under exam_gen_status:<id> for frontend polling.
    """
    from .models import Exam

    exam = Exam.objects.filter(pk=exam_id).first()
    if exam is None:
        return

    if knowledge_points is None and exam.course_id:
        knowledge_points = [
            {'id': kp.id, 'title': kp.title, 'description': kp.description}
            for kp in exam.course.knowledge_points.all()
        ]

    cache.set(_status_key(exam_id), {'status': 'running'}, _STATUS_TTL)
    try:
        from apps.ai_agents.skills import ExamSkill
        from .exam_assembly import save_generated_questions

        result = ExamSkill().run(
            topic or exam.title, difficulty, count,
            knowledge_points=knowledge_points)
        questions = result.get('questions', [])
        summary = save_generated_questions(exam, questions)
        summary['code_validated'] = result.get('code_validated', '0/0')
        summary['duplicates_skipped'] = result.get('duplicates_skipped', 0)

        cache.set(_status_key(exam_id), {
            'status': 'done',
            **summary,
        }, _STATUS_TTL)
    except Exception as e:
        logger.warning('exam generation attempt %s failed: %s',
                       self.request.retries + 1, e)
        # Eager mode has no broker: a retry would just propagate the Retry
        # exception into the calling view. Retries only exist with a broker.
        if self.request.retries < self.max_retries and not self.request.is_eager:
            cache.set(_status_key(exam_id), {
                'status': 'retrying',
                'error': str(e)[:200],
            }, _STATUS_TTL)
            raise self.retry(exc=e, countdown=_retry_countdown(self.request.retries))
        logger.exception('exam generation failed for exam %s after retries', exam_id)
        cache.set(_status_key(exam_id), {
            'status': 'error',
            'error': str(e)[:200],
        }, _STATUS_TTL)

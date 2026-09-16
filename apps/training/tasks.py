"""Celery tasks for the training app — grading outside the web request.

Without a Redis broker (CELERY_TASK_ALWAYS_EAGER=True, the dev default)
tasks run inline; with a broker, grading is queued and the submission
shows status 'running' until the worker processes it. If Celery itself is
not installed, grading degrades to a plain inline call.
"""

try:
    from celery import current_app, shared_task
    CELERY_AVAILABLE = True
except ImportError:
    current_app = None
    CELERY_AVAILABLE = False


def _grade(submission_id: int):
    from .models import Submission

    submission = Submission.objects.filter(pk=submission_id).first()
    if submission is None:
        return None
    return submission.grade()


if CELERY_AVAILABLE:

    @shared_task
    def grade_submission_task(submission_id: int):
        """Execute and grade a submission (sandboxed, may take seconds)."""
        return _grade(submission_id)

else:

    def grade_submission_task(submission_id: int):  # pragma: no cover
        return _grade(submission_id)


def grade_submission_async(submission_id: int) -> bool:
    """Queue grading; returns True when it ran inline (eager/no-Celery)."""
    if not CELERY_AVAILABLE:
        _grade(submission_id)
        return True
    grade_submission_task.delay(submission_id)
    return bool(current_app.conf.task_always_eager)

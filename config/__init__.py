# Import the Celery app so `celery -A config worker` finds it and so that
# tasks in the web process bind to the configured app (lazy config).
# Celery is OPTIONAL at runtime: without it, task calls degrade to inline
# execution (see apps/training/tasks.py), so startup must not fail here.
try:
    from .celery import app as celery_app
except ImportError:  # pragma: no cover - celery not installed
    celery_app = None

__all__ = ('celery_app',)

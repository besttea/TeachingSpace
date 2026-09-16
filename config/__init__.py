# Import the Celery app so `celery -A config worker` finds it and so that
# tasks in the web process bind to the configured app (lazy config).
from .celery import app as celery_app

__all__ = ('celery_app',)

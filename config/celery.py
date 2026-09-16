"""Celery application for teaching_space.

Usage:
    celery -A config worker -l info --pool=solo      (Windows dev)
    celery -A config worker -l info                  (Linux/prod)

Development: CELERY_TASK_ALWAYS_EAGER defaults to DEBUG, so tasks run
inline in the web process and no Redis broker is required. Set
CELERY_ALWAYS_EAGER=False (with a running Redis) to use the real queue.

Import-safety: ``config/__init__.py`` imports this module, so the app is
created very early during settings loading. ``config_from_object`` is lazy
(resolved on first task execution), and task autodiscovery is deferred to
the worker's process-init signal — task modules import Django models,
which must not happen before ``django.setup()``.
"""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('teaching_space')
app.config_from_object('django.conf:settings', namespace='CELERY')


def autodiscover():
    """Discover tasks.py modules of installed apps (worker only)."""
    app.autodiscover_tasks()


def _setup_worker(**kwargs):
    """Configure Django and discover tasks when a worker process boots."""
    import django

    django.setup()
    app.autodiscover_tasks()


if os.environ.get('CELERY_WORKER', '').lower() in ('1', 'true'):
    # In-process worker shortcut (e.g. Windows without the CLI):
    #   CELERY_WORKER=1 python -c "from config.celery import app; app.worker_main(['worker', '--pool=solo', '-l', 'info'])"
    pass
else:
    from celery.signals import worker_process_init

    worker_process_init.connect(_setup_worker)

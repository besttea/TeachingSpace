"""Pytest bootstrap: configure Django before test collection.

Works with plain pytest (no pytest-django required); if pytest-django is
installed later it reuses the same settings module.
"""

import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

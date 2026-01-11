"""
Django settings for teaching_space project - Development settings.
"""

from .base import *

# Development-specific settings
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*']

# Install django-debug-toolbar for development
# INSTALLED_APPS += [
#     'django_extensions',
# ]

# Use console email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# SQLite for development (easier setup)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Disable HTTPS redirect in development
SECURE_SSL_REDIRECT = False

# Allow all origins for development (CORS)
CORS_ALLOW_ALL_ORIGINS = True

"""
Django settings for teaching_space project - Base settings.
"""

import json
from pathlib import Path

from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-hj0w$la&3q1-st2s!u&36v5437w!hz7z^s8v&4l0kx)zrac8^*')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

# Hosts trusted for unsafe requests (CSRF). Needed when the site is reached
# through a different origin than the host header — e.g. LAN IP, a reverse
# proxy, or a custom domain. Comma-separated, with scheme:
#   CSRF_TRUSTED_ORIGINS=http://192.168.1.10:8000,http://example.com
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS', default='',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()])


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party apps
    "rest_framework",

    # Local apps
    "apps.accounts",
    "apps.learning",
    "apps.training",
    "apps.examination",
    "apps.chat",
    "apps.ai_agents",
    "apps.video_generator",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestLatencyMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / 'templates'],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": config('DB_ENGINE', default='django.db.backends.sqlite3'),
        "NAME": config('DB_NAME', default=str(BASE_DIR / "db.sqlite3")),
        "USER": config('DB_USER', default=''),
        "PASSWORD": config('DB_PASSWORD', default=''),
        "HOST": config('DB_HOST', default=''),
        "PORT": config('DB_PORT', default=''),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = "zh-hans"

TIME_ZONE = "Asia/Shanghai"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "accounts.User"

# Authentication URLs
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/dashboard/"
LOGOUT_REDIRECT_URL = "/"

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# Celery Configuration
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
# Run tasks inline when no Redis is available (default in dev); set
# CELERY_ALWAYS_EAGER=False once a broker is running.
CELERY_TASK_ALWAYS_EAGER = config('CELERY_ALWAYS_EAGER', default=DEBUG, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True
# T5/4.5: generation/render concurrency gates — expensive tasks are rate-limited
CELERY_ANNOTATIONS = {
    'apps.training.tasks.grade_submission_task': {'rate_limit': '120/m'},
    'apps.video_generator.tasks.render_video_task': {'rate_limit': '5/m'},
}

# Code Execution Settings
CODE_EXECUTION_TIMEOUT = 10  # seconds
CODE_EXECUTION_MEMORY_LIMIT = '128m'
CODE_EXECUTION_CPU_QUOTA = 50000  # 50% of one CPU
# Isolation backend: 'subprocess' (default) or 'docker' (full OS isolation,
# requires the sandbox image built — see docker/sandbox/Dockerfile)
CODE_EXECUTION_BACKEND = config('CODE_EXECUTION_BACKEND', default='subprocess')
SANDBOX_DOCKER_IMAGE = config('SANDBOX_DOCKER_IMAGE', default='teaching-space-sandbox')

# Jupyter kernel sessions (real notebook semantics for the learning class)
# 'local' = ipykernel subprocess (DEV ONLY — full Python, never expose to
# untrusted users); 'docker' = kernel inside the teaching-space-kernel
# container (loopback-only ports, resource caps) — production mode.
JUPYTER_KERNEL_BACKEND = config('JUPYTER_KERNEL_BACKEND', default='local')
JUPYTER_KERNEL_IMAGE = config('JUPYTER_KERNEL_IMAGE', default='teaching-space-kernel')
JUPYTER_KERNEL_IDLE_TIMEOUT = config('JUPYTER_KERNEL_IDLE_TIMEOUT', default=15 * 60, cast=int)
JUPYTER_MAX_KERNELS = config('JUPYTER_MAX_KERNELS', default=20, cast=int)
JUPYTER_MAX_KERNELS_PER_USER = config('JUPYTER_MAX_KERNELS_PER_USER', default=2, cast=int)
JUPYTER_EXECUTE_TIMEOUT = config('JUPYTER_EXECUTE_TIMEOUT', default=15, cast=int)

# Email Configuration
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

# AI/LLM Configuration — multi-provider support.
# Every provider below is Anthropic-API-compatible (DeepSeek exposes an
# Anthropic-compatible endpoint), so the same SDK client works for all.
# Switch the active provider with AI_PROVIDER (e.g. AI_PROVIDER=deepseek);
# optionally override the model with AI_MODEL.
AI_PROVIDERS = {
    'anthropic': {
        'api_key': config('ANTHROPIC_API_KEY', default=''),
        'base_url': config('ANTHROPIC_BASE_URL', default=''),
        'default_model': config('ANTHROPIC_MODEL', default='claude-sonnet-4-5-20250929'),
    },
    'deepseek': {
        'api_key': config('deepseek_Api', default=''),
        'base_url': config('DEEPSEEK_BASE_URL', default='https://api.deepseek.com/anthropic'),
        'default_model': config('DEEPSEEK_MODEL', default='deepseek-flash'),
    },
}
AI_PROVIDER = config('AI_PROVIDER', default='anthropic')
# App-specific active model — takes precedence over AI_MODEL and provider
# defaults, and is immune to host-harness environment variables (e.g. the
# Claude Code harness exporting AI_MODEL=... into the shell).
AI_ACTIVE_MODEL = config('AI_ACTIVE_MODEL', default='')
# Optional global model override (applies to whichever provider is active)
AI_MODEL = config('AI_MODEL', default='')

# AI Harness role→model routing (DeepSeek-harness pattern):
# planner = reasoning-heavy structure work, worker = bulk content,
# grader = evaluation. Empty values fall back to the active provider model.
AI_PLANNER_MODEL = config('AI_PLANNER_MODEL', default='deepseek-reasoner')
AI_WORKER_MODEL = config('AI_WORKER_MODEL', default='')
AI_GRADER_MODEL = config('AI_GRADER_MODEL', default='')
# Comma-separated fallback chain tried when a role's model fails.
AI_FALLBACK_MODELS = config('AI_FALLBACK_MODELS', default='')

# Legacy aliases (kept so existing call sites keep working)
ANTHROPIC_API_KEY = AI_PROVIDERS['anthropic']['api_key']
ANTHROPIC_MODEL = AI_PROVIDERS['anthropic']['default_model']
ANTHROPIC_API_BASE_URL = AI_PROVIDERS['anthropic']['base_url']
AI_MAX_TOKENS = config('AI_MAX_TOKENS', default=4096, cast=int)
AI_TEMPERATURE = config('AI_TEMPERATURE', default=0.7, cast=float)
AI_CACHE_ENABLED = config('AI_CACHE_ENABLED', default=True, cast=bool)
AI_COST_LIMIT_DAILY = config('AI_COST_LIMIT_DAILY', default=50.00, cast=float)
# Cost estimation prices (USD per 1M tokens) — used by AIGenerationHistory
AI_COST_INPUT_PER_MTOK = config('AI_COST_INPUT_PER_MTOK', default=3.0, cast=float)
AI_COST_OUTPUT_PER_MTOK = config('AI_COST_OUTPUT_PER_MTOK', default=15.0, cast=float)
# Skill-level tunable parameters (harness skills read these via
# apps.ai_agents.skill_config.skill_params). JSON object keyed by skill
# name, e.g. {"exam_generation": {"temperature": 0.5, "max_questions": 20}}.
# Per-knob env vars AI_SKILL_<NAME>_<KEY> take precedence.
AI_SKILL_PARAMS = config(
    'AI_SKILL_PARAMS', default='', cast=lambda v: json.loads(v) if v.strip() else {})

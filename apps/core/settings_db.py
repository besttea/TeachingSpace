"""DB-backed platform settings — the web-tunable layer above code defaults.

Layering (highest wins):
    PlatformSetting DB row  >  AI_SKILL_* env vars  >  settings/env  >  code default

The whole table is cached as one dict; writes invalidate the cache so the
next read sees fresh values (acceptable staleness window for tuning knobs).
"""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_KEY = 'platform_settings:all'
_CACHE_TTL = 300


def get_platform_settings() -> dict:
    """All DB settings as {key: value} (cached, 5 min).

    Defensive: when the DB is unavailable (SimpleTestCase, migration
    window), returns {} — callers fall back to their code defaults; rate
    limiting and skill params must never 500 because of a settings read.
    """
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached
    try:
        from apps.accounts.models import PlatformSetting
        settings = {row.key: row.value for row in PlatformSetting.objects.all()}
    except Exception as e:  # pragma: no cover — environment-dependent
        logger.warning('platform settings unavailable (%s) — using defaults', e)
        settings = {}
    cache.set(_CACHE_KEY, settings, _CACHE_TTL)
    return settings


def get_platform_setting(key, default=None):
    """One setting; ``default`` returned when unset."""
    return get_platform_settings().get(key, default)


def set_platform_setting(key, value, category='global', description=''):
    """Create/update a setting and invalidate the cache."""
    from apps.accounts.models import PlatformSetting
    row, _ = PlatformSetting.objects.update_or_create(
        key=key,
        defaults={'value': value, 'category': category, 'description': description})
    cache.delete(_CACHE_KEY)
    return row


def delete_platform_setting(key):
    """Remove a setting (falls back to the lower layers)."""
    from apps.accounts.models import PlatformSetting
    PlatformSetting.objects.filter(key=key).delete()
    cache.delete(_CACHE_KEY)

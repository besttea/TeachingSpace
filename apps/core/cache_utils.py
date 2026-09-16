"""Content-versioned page caching (plan 3.4).

Read-heavy pages (course list / course detail) are cached under a global
content version; ANY content mutation bumps the version, invalidating all
pages. Simple and correct — no per-key invalidation bookkeeping.
"""

from django.core.cache import cache

_VERSION_KEY = 'content_version'


def content_version() -> int:
    return cache.get(_VERSION_KEY, 1)


def bump_content_version():
    """Call after any course/lesson/exercise/exam content change."""
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 2)


def page_key(prefix: str, *parts) -> str:
    return f'{prefix}:v{content_version()}:{":".join(str(p) for p in parts)}'


def get_cached_page(key: str):
    return cache.get(key)


def set_cached_page(key: str, html: str, timeout: int = 300):
    cache.set(key, html, timeout)

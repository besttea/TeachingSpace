"""Per-user rate limiting decorator for expensive/abusive endpoints.

Cache-backed sliding window (per authenticated user). Applied to AI
generation endpoints, code submission and kernel execution — the platform's
expensive resources (see OPTIMIZATION_PLAN T5).
"""

import functools

from django.core.cache import cache
from django.http import JsonResponse


def rate_limit(key_prefix, limit=20, window_seconds=3600):
    """Allow at most ``limit`` requests per user per ``window_seconds``.

    Both numbers are overridable per endpoint from the web settings page
    (PlatformSetting key ``rate:<key_prefix>``, value
    ``{"limit": n, "window_seconds": n}`` — admin-editable).
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # DB override (cached whole-table read — cheap)
            try:
                from apps.core.settings_db import get_platform_setting
                override = get_platform_setting(f'rate:{key_prefix}', {}) or {}
                effective_limit = int(override.get('limit', limit))
                effective_window = int(override.get('window_seconds', window_seconds))
            except (TypeError, ValueError):
                effective_limit, effective_window = limit, window_seconds

            user_id = request.user.id if request.user.is_authenticated else 'anon'
            key = f'rate:{key_prefix}:{user_id}'
            count = cache.get(key, 0)
            if count >= effective_limit:
                return JsonResponse({
                    'error': f'操作过于频繁，请稍后再试'
                             f'（每 {max(1, effective_window // 60)} 分钟最多 {effective_limit} 次）'
                }, status=429)
            cache.add(key, 0, effective_window)  # establish the TTL window
            cache.incr(key)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator

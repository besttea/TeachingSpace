"""Per-user rate limiting decorator for expensive/abusive endpoints.

Cache-backed sliding window (per authenticated user). Applied to AI
generation endpoints, code submission and kernel execution — the platform's
expensive resources (see OPTIMIZATION_PLAN T5).
"""

import functools

from django.core.cache import cache
from django.http import JsonResponse


def rate_limit(key_prefix, limit=20, window_seconds=3600):
    """Allow at most ``limit`` requests per user per ``window_seconds``."""

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user_id = request.user.id if request.user.is_authenticated else 'anon'
            key = f'rate:{key_prefix}:{user_id}'
            count = cache.get(key, 0)
            if count >= limit:
                return JsonResponse({
                    'error': f'操作过于频繁，请稍后再试'
                             f'（每 {max(1, window_seconds // 60)} 分钟最多 {limit} 次）'
                }, status=429)
            cache.add(key, 0, window_seconds)  # establish the TTL window
            cache.incr(key)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator

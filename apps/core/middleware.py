"""Request latency logging middleware (6.4 observability).

Logs slow requests (>= threshold) at WARNING; sampled INFO for others in
production. Excludes static/media asset paths.
"""

import logging
import time

from django.conf import settings

logger = logging.getLogger('request.latency')

SLOW_MS = int(getattr(settings, 'SLOW_REQUEST_THRESHOLD_MS', 1000))
SKIP_PREFIXES = ('/static/', '/media/')


class RequestLatencyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(SKIP_PREFIXES):
            return self.get_response(request)

        start = time.time()
        response = self.get_response(request)
        duration_ms = int((time.time() - start) * 1000)

        if duration_ms >= SLOW_MS:
            logger.warning(
                'slow request: %s %s %dms',
                request.method, request.path, duration_ms)
        elif not getattr(settings, 'DEBUG', False) and duration_ms >= 500:
            logger.info(
                'request: %s %s %dms',
                request.method, request.path, duration_ms)
        return response

"""
Check AI connectivity and configuration (tiny prompt, ~1 token).

Usage:
    python manage.py test_ai_agents
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai_agents.base_agent import BaseAgent


class Command(BaseCommand):
    help = 'Test AI agent connectivity (key / base_url / model)'

    def handle(self, *args, **options):
        self.stdout.write(f'API key configured: {"yes" if settings.ANTHROPIC_API_KEY else "NO"}')
        self.stdout.write(f'Model: {settings.ANTHROPIC_MODEL}')
        self.stdout.write(f'Base URL: {settings.ANTHROPIC_API_BASE_URL or "(official endpoint)"}')
        self.stdout.write(f'Cache: {settings.AI_CACHE_ENABLED} | Daily cost limit: ${settings.AI_COST_LIMIT_DAILY}')

        if not settings.ANTHROPIC_API_KEY:
            raise CommandError('ANTHROPIC_API_KEY is not set — check .env')

        # Tiny probe call (one token of output, logged to AIGenerationHistory)
        try:
            result = BaseAgent().generate(
                'Reply with exactly: OK',
                system_prompt='You are a connectivity check.',
                max_tokens=4,
                temperature=0,
            )
        except Exception as e:
            raise CommandError(f'API call failed: {e}')

        self.stdout.write(self.style.SUCCESS(f'Connectivity OK — response: {result.strip()!r}'))

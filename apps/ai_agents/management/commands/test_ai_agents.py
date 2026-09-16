"""
Check AI connectivity and configuration (tiny prompt, ~1 token).

Usage:
    python manage.py test_ai_agents
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai_agents import ai_config
from apps.ai_agents.base_agent import BaseAgent


class Command(BaseCommand):
    help = 'Test AI agent connectivity (provider / key / base_url / model)'

    def handle(self, *args, **options):
        provider = ai_config.provider_name()
        configured = ai_config.is_configured()

        self.stdout.write(f'Active provider: {provider}')
        self.stdout.write(f'API key configured: {"yes" if configured else "NO"}')
        self.stdout.write(f'Model: {ai_config.model_name()}')
        self.stdout.write(f'Base URL: {ai_config.base_url() or "(official endpoint)"}')
        self.stdout.write(f'Cache: {settings.AI_CACHE_ENABLED} | Daily cost limit: ${settings.AI_COST_LIMIT_DAILY}')

        # Show the other available providers for convenience
        for name, conf in ai_config.providers().items():
            if name != provider:
                has_key = bool(conf.get('api_key'))
                self.stdout.write(
                    f'  (other) {name}: key={"yes" if has_key else "no"}, '
                    f'model={conf.get("default_model", "")}')

        if not configured:
            raise CommandError(
                f'No API key for provider "{provider}". Check .env '
                f'(e.g. ANTHROPIC_API_KEY / deepseek_Api) and AI_PROVIDER.')

        # Tiny probe call (logged to AIGenerationHistory). 64 output tokens:
        # reasoning models (deepseek-reasoner) spend early budget on thinking,
        # so 4 tokens is not enough for them to emit the final answer.
        try:
            from apps.ai_agents.learning_agent import LearningAgent
            result = LearningAgent().generate(
                'Reply with exactly: OK',
                system_prompt='You are a connectivity check.',
                max_tokens=64,
                temperature=0,
            )
            if not result.strip():
                raise CommandError(
                    'API responded but returned no text (reasoning model may '
                    'have consumed the output budget — try a non-reasoning '
                    'model like deepseek-chat for content generation)')
        except CommandError:
            raise
        except Exception as e:
            raise CommandError(f'API call failed: {e}')

        self.stdout.write(self.style.SUCCESS(f'Connectivity OK — response: {result.strip()!r}'))

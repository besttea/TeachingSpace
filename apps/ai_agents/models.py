"""AI generation tracking: audit history and cost control.

Every agent/chat call is recorded (prompt/response/tokens/cost), and the
daily cost limit (AI_COST_LIMIT_DAILY) is enforced before new calls.
"""

from django.conf import settings
from django.db import models


class AIGenerationHistory(models.Model):
    """Audit log of AI generation calls (prompt, response, tokens, cost)."""

    agent = models.CharField(max_length=50, help_text="调用方（Agent 类名或 chat）")
    model = models.CharField(max_length=100)
    prompt = models.TextField()
    response = models.TextField(blank=True)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    estimated_cost_usd = models.DecimalField(
        max_digits=10, decimal_places=6, default=0)
    duration_ms = models.IntegerField(default=0)
    success = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_generation_history'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['agent', '-created_at']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f'{self.agent}@{self.created_at:%Y-%m-%d %H:%M} ({self.estimated_cost_usd}$)'


def _truncate(text: str, limit: int = 4000) -> str:
    text = text or ''
    return text if len(text) <= limit else text[:limit] + '…(truncated)'


def _estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Cost estimate from token counts and configured per-1M-token prices.

    Defaults are Sonnet-class prices; adjust AI_COST_INPUT_PER_MTOK /
    AI_COST_OUTPUT_PER_MTOK for your provider (proxy pricing differs).
    """
    input_price = float(getattr(settings, 'AI_COST_INPUT_PER_MTOK', 3.0))
    output_price = float(getattr(settings, 'AI_COST_OUTPUT_PER_MTOK', 15.0))
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price


def record_generation(agent, model, prompt, response='', input_tokens=0,
                      output_tokens=0, duration_ms=0, success=True, error=''):
    """Record one AI call. Callers: BaseAgent.generate, ChatAIService."""
    return AIGenerationHistory.objects.create(
        agent=agent,
        model=model,
        prompt=_truncate(prompt),
        response=_truncate(response),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=_estimate_cost_usd(input_tokens, output_tokens),
        duration_ms=duration_ms,
        success=success,
        error=_truncate(error, 500),
    )


def daily_cost_exceeded() -> bool:
    """Whether today's recorded AI spend has hit the configured limit.

    The limit layers: DB PlatformSetting 'ai_cost_limit_daily' (web settings
    page, admin) over settings.AI_COST_LIMIT_DAILY (.env).
    """
    limit = float(getattr(settings, 'AI_COST_LIMIT_DAILY', 50.0))
    try:
        from apps.core.settings_db import get_platform_setting
        db_limit = get_platform_setting('ai_cost_limit_daily')
        if db_limit is not None:
            limit = float(db_limit)
    except (TypeError, ValueError):
        pass
    if limit <= 0:
        return False
    from django.utils import timezone
    # localdate() (NOT now().date()): the __date lookup interprets the value
    # in the current timezone, so a UTC date would miss rows near midnight.
    spent = AIGenerationHistory.objects.filter(
        created_at__date=timezone.localdate()
    ).aggregate(total=models.Sum('estimated_cost_usd'))['total'] or 0
    return float(spent) >= limit

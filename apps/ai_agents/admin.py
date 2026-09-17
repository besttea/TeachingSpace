"""Admin views for AI generation auditing (read-only)."""

from datetime import timedelta

from django.contrib import admin
from django.db.models import Sum
from django.utils import timezone

from .models import AIGenerationHistory


@admin.register(AIGenerationHistory)
class AIGenerationHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'agent', 'model', 'success', 'input_tokens', 'output_tokens',
        'estimated_cost_usd', 'duration_ms', 'created_at')
    list_filter = ('agent', 'model', 'success', 'created_at')
    search_fields = ('prompt', 'response', 'error')
    readonly_fields = [f.name for f in AIGenerationHistory._meta.fields]
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_per_page = 50
    change_list_template = 'admin/ai_agents/aigenerationhistory/change_list.html'

    def changelist_view(self, request, extra_context=None):
        """Attach a 24h health summary (OPTIMIZATION_PLAN 2.1: failure-rate
        visibility without querying the DB by hand)."""
        extra_context = extra_context or {}
        since = timezone.now() - timedelta(hours=24)
        recent = AIGenerationHistory.objects.filter(created_at__gte=since)
        total = recent.count()
        failed = recent.filter(success=False).count()
        extra_context['ai_24h_stats'] = {
            'total': total,
            'failed': failed,
            'failure_rate_pct': round(failed * 100 / total, 1) if total else 0,
            'cost_usd': round(recent.aggregate(cost=Sum('estimated_cost_usd'))['cost'] or 0, 4),
        }
        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

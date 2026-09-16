"""Admin views for AI generation auditing (read-only)."""

from django.contrib import admin

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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

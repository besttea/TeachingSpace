from django.contrib import admin
from .models import Exercise, Hint, Submission, HintUsage


class HintInline(admin.TabularInline):
    model = Hint
    extra = 1
    fields = ('content', 'order', 'points_penalty')


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ('title', 'difficulty', 'course', 'points', 'success_rate', 'total_submissions', 'created_at')
    list_filter = ('difficulty', 'course', 'created_at')
    search_fields = ('title', 'description', 'course__title')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [HintInline]
    readonly_fields = ('total_submissions', 'successful_submissions', 'success_rate', 'created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'description', 'difficulty', 'course')
        }),
        ('Code Requirements', {
            'fields': ('starter_code', 'solution_code', 'test_cases')
        }),
        ('Settings', {
            'fields': ('points', 'time_limit_seconds', 'created_by')
        }),
        ('Statistics', {
            'fields': ('total_submissions', 'successful_submissions', 'success_rate'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Hint)
class HintAdmin(admin.ModelAdmin):
    list_display = ('exercise', 'order', 'points_penalty', 'created_at')
    list_filter = ('exercise', 'created_at')
    search_fields = ('exercise__title', 'content')
    ordering = ('exercise', 'order')


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('student', 'exercise', 'status', 'tests_passed', 'tests_total', 'points_awarded', 'submitted_at')
    list_filter = ('status', 'submitted_at', 'exercise')
    search_fields = ('student__username', 'exercise__title')
    readonly_fields = ('test_results', 'output', 'error_message', 'execution_time_ms', 'tests_passed', 'tests_total', 'points_awarded', 'submitted_at')
    ordering = ('-submitted_at',)

    fieldsets = (
        ('Submission Info', {
            'fields': ('student', 'exercise', 'code', 'status')
        }),
        ('Execution Results', {
            'fields': ('test_results', 'output', 'error_message', 'execution_time_ms')
        }),
        ('Scoring', {
            'fields': ('tests_passed', 'tests_total', 'points_awarded', 'hints_used')
        }),
        ('Metadata', {
            'fields': ('submitted_at',),
            'classes': ('collapse',)
        }),
    )

    actions = ['regrade_submissions']

    def regrade_submissions(self, request, queryset):
        """Regrade selected submissions"""
        for submission in queryset:
            submission.grade()
        self.message_user(request, f"{queryset.count()} submissions regraded successfully.")
    regrade_submissions.short_description = "Regrade selected submissions"


@admin.register(HintUsage)
class HintUsageAdmin(admin.ModelAdmin):
    list_display = ('student', 'hint', 'viewed_at')
    list_filter = ('viewed_at',)
    search_fields = ('student__username', 'hint__exercise__title')
    readonly_fields = ('student', 'hint', 'viewed_at')
    ordering = ('-viewed_at',)

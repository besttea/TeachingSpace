from django.contrib import admin
from .models import (
    Cell, CellVersion, Chapter, Course, Enrollment, KnowledgePoint, Lesson,
    LessonProgress, Video,
)


class ChapterInline(admin.TabularInline):
    model = Chapter
    extra = 1
    fields = ('title', 'order')


@admin.register(KnowledgePoint)
class KnowledgePointAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'chapter', 'difficulty', 'order', 'created_by')
    list_filter = ('course', 'difficulty')
    search_fields = ('title', 'description', 'course__title')


class CellInline(admin.StackedInline):
    model = Cell
    extra = 0
    fields = ('cell_type', 'order', 'data')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'difficulty_level', 'instructor', 'is_published', 'created_at')
    list_filter = ('difficulty_level', 'is_published', 'created_at')
    search_fields = ('title', 'description', 'instructor__username')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ChapterInline]
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'description', 'difficulty_level')
        }),
        ('Settings', {
            'fields': ('instructor', 'thumbnail', 'is_published', 'estimated_duration_hours')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order', 'created_at')
    list_filter = ('course', 'created_at')
    search_fields = ('title', 'description', 'course__title')
    ordering = ('course', 'order')


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'chapter', 'status', 'order', 'duration_minutes', 'created_at')
    list_filter = ('status', 'created_at', 'chapter__course')
    search_fields = ('title', 'description', 'chapter__title')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [CellInline]
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('chapter', 'order')

    fieldsets = (
        ('Basic Information', {
            'fields': ('chapter', 'title', 'slug', 'description')
        }),
        ('Settings', {
            'fields': ('status', 'order', 'duration_minutes', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Cell)
class CellAdmin(admin.ModelAdmin):
    list_display = ('lesson', 'cell_type', 'order', 'created_by', 'updated_at')
    list_filter = ('cell_type', 'created_at')
    search_fields = ('lesson__title',)
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'last_edited_by')
    ordering = ('lesson', 'order')

    fieldsets = (
        ('Basic Information', {
            'fields': ('lesson', 'cell_type', 'order')
        }),
        ('Content', {
            'fields': ('data',),
            'description': 'Cell-specific data in JSON format'
        }),
        ('Metadata', {
            'fields': ('created_by', 'last_edited_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CellVersion)
class CellVersionAdmin(admin.ModelAdmin):
    list_display = ('cell', 'editor', 'change_description', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('cell__lesson__title', 'editor__username', 'change_description')
    readonly_fields = ('cell', 'snapshot', 'editor', 'created_at')
    ordering = ('-created_at',)


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'source_type', 'generation_status', 'duration_seconds', 'created_at')
    list_filter = ('source_type', 'generation_status', 'created_at')
    search_fields = ('title', 'lesson__title')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'lesson', 'cell', 'source_type')
        }),
        ('Video Source', {
            'fields': ('video_file', 'external_url', 'manim_script')
        }),
        ('Metadata', {
            'fields': ('thumbnail', 'duration_seconds', 'resolution_width', 'resolution_height', 'file_size_bytes')
        }),
        ('Status', {
            'fields': ('generation_status',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'progress_percentage', 'is_active', 'enrolled_at')
    list_filter = ('is_active', 'enrolled_at', 'course')
    search_fields = ('student__username', 'student__email', 'course__title')
    readonly_fields = ('enrolled_at', 'progress_percentage')
    ordering = ('-enrolled_at',)

    fieldsets = (
        ('Enrollment Info', {
            'fields': ('student', 'course', 'is_active')
        }),
        ('Progress', {
            'fields': ('progress_percentage', 'enrolled_at', 'completed_at')
        }),
    )


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'lesson', 'is_completed', 'time_spent_seconds', 'cells_executed', 'last_accessed')
    list_filter = ('is_completed', 'last_accessed')
    search_fields = ('enrollment__student__username', 'lesson__title')
    readonly_fields = ('last_accessed', 'completed_at')
    ordering = ('-last_accessed',)

    fieldsets = (
        ('Progress Info', {
            'fields': ('enrollment', 'lesson', 'is_completed', 'completed_at')
        }),
        ('Details', {
            'fields': ('time_spent_seconds', 'cells_executed', 'code_cells_run')
        }),
        ('Tracking', {
            'fields': ('last_accessed',),
            'classes': ('collapse',)
        }),
    )

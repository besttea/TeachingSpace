from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import PlatformSetting, StudentProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom User admin"""
    list_display = ('username', 'email', 'user_type', 'is_staff', 'created_at')
    list_filter = ('user_type', 'is_staff', 'is_active')
    search_fields = ('username', 'email')
    ordering = ('-created_at',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Additional Info', {
            'fields': ('user_type', 'bio', 'profile_picture')
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Additional Info', {
            'fields': ('user_type', 'email')
        }),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    """StudentProfile admin"""
    list_display = ('user', 'python_experience', 'total_points', 'total_exercises_completed', 'total_exams_passed')
    list_filter = ('python_experience',)
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('total_points', 'total_exercises_completed', 'total_exams_passed', 'current_streak_days', 'longest_streak_days')

    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Profile Info', {
            'fields': ('python_experience',)
        }),
        ('Statistics', {
            'fields': ('total_points', 'total_exercises_completed', 'total_exams_passed', 'current_streak_days', 'longest_streak_days', 'last_activity_date')
        }),
    )


@admin.register(PlatformSetting)
class PlatformSettingAdmin(admin.ModelAdmin):
    """Web-tunable platform parameters (usually edited via the settings page)."""
    list_display = ('key', 'category', 'value', 'updated_at')
    list_filter = ('category',)
    search_fields = ('key', 'description')

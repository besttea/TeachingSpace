from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model extending Django's AbstractUser"""
    USER_TYPE_CHOICES = (
        ('student', 'Student'),
        ('instructor', 'Instructor'),
        ('admin', 'Admin'),
    )
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default='student'
    )
    email = models.EmailField(unique=True)
    bio = models.TextField(blank=True)
    profile_picture = models.ImageField(
        upload_to='profile_pics/',
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Role-scoped personal preferences, editable on the web settings page
    # (e.g. instructor defaults: difficulty/chapter count/question count;
    # student toggles: heartbeat).
    preferences = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.username


class StudentProfile(models.Model):
    """Extended profile for students"""
    EXPERIENCE_CHOICES = (
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='student_profile'
    )
    python_experience = models.CharField(
        max_length=50,
        choices=EXPERIENCE_CHOICES,
        default='beginner'
    )
    total_points = models.IntegerField(default=0)
    total_exercises_completed = models.IntegerField(default=0)
    total_exams_passed = models.IntegerField(default=0)
    current_streak_days = models.IntegerField(default=0)
    longest_streak_days = models.IntegerField(default=0)
    last_activity_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'student_profiles'

    def __str__(self):
        return f"{self.user.username}'s Profile"


class PlatformSetting(models.Model):
    """Runtime-tunable platform parameter, editable from the web settings
    page (role-gated). Layered above code defaults and env config:
    DB > AI_SKILL_* env > settings > code defaults (see apps/core/settings_db.py).
    """

    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict)
    category = models.CharField(max_length=40, default='global')
    description = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'platform_settings'
        ordering = ['category', 'key']

    def __str__(self):
        return f'{self.key} = {self.value}'

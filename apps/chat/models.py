"""
Chat models for AI-powered learning assistant.
"""

from django.db import models
from django.conf import settings


class ChatConversation(models.Model):
    """A chat conversation session"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_conversations')
    title = models.CharField(max_length=200, blank=True, help_text="Auto-generated from first message")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'chat_conversations'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username} - {self.title or 'New Conversation'}"


class ChatMessage(models.Model):
    """Individual messages in a conversation"""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    conversation = models.ForeignKey(ChatConversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional data like suggested resources")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_messages'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class LearningResource(models.Model):
    """Available learning resources from Classlib"""
    title = models.CharField(max_length=300)
    filename = models.CharField(max_length=255, unique=True)
    file_path = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    topics = models.JSONField(default=list, help_text="List of topics covered")
    difficulty_level = models.CharField(max_length=20, default='beginner')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'learning_resources'
        ordering = ['title']

    def __str__(self):
        return self.title

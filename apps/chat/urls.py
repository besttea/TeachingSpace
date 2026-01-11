"""
Chat app URLs
"""

from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_interface, name='chat-interface'),
    path('api/send/', views.send_message, name='send-message'),
    path('api/conversation/<int:conversation_id>/', views.get_conversation_messages, name='get-messages'),
    path('api/conversation/new/', views.new_conversation, name='new-conversation'),
    path('api/conversation/<int:conversation_id>/delete/', views.delete_conversation, name='delete-conversation'),
]

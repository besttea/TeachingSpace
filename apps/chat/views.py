"""
Chat views for AI-powered learning assistant.
"""

import json
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import ChatConversation, ChatMessage
from .ai_service import ChatAIService


@login_required
def chat_interface(request):
    """Render the chat interface"""
    # Check if a specific conversation is requested
    conversation_id = request.GET.get('conversation')

    if conversation_id:
        # Load specific conversation
        conversation = get_object_or_404(
            ChatConversation,
            id=conversation_id,
            user=request.user
        )
    else:
        # Get or create most recent conversation for user
        conversation = ChatConversation.objects.filter(
            user=request.user
        ).first()

        if not conversation:
            conversation = ChatConversation.objects.create(
                user=request.user,
                title="新对话"
            )

    # Get recent conversations
    recent_conversations = ChatConversation.objects.filter(
        user=request.user
    )[:10]

    context = {
        'conversation': conversation,
        'recent_conversations': recent_conversations,
    }

    return render(request, 'chat/chat_interface.html', context)


@login_required
@require_http_methods(["POST"])
def send_message(request):
    """Handle sending a message and getting AI response"""
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')

        if not user_message:
            return JsonResponse({
                'success': False,
                'error': 'Message cannot be empty'
            }, status=400)

        # T17: server-side input length cap
        if len(user_message) > 4000:
            return JsonResponse({
                'success': False,
                'error': '消息过长（最多 4000 字符）'
            }, status=400)

        # Get or create conversation
        if conversation_id:
            conversation = get_object_or_404(
                ChatConversation,
                id=conversation_id,
                user=request.user
            )
        else:
            conversation = ChatConversation.objects.create(
                user=request.user,
                title=user_message[:50]  # Use first message as title
            )

        # Save user message
        user_msg = ChatMessage.objects.create(
            conversation=conversation,
            role='user',
            content=user_message
        )

        # Get conversation history (most recent 20 messages, chronological)
        history = []
        previous_messages = list(reversed(
            conversation.messages.order_by('-created_at')[:20]
        ))
        for msg in previous_messages:
            if msg.id != user_msg.id:  # Exclude the current message
                history.append({
                    'role': msg.role,
                    'content': msg.content
                })

        # Generate AI response
        ai_service = ChatAIService()
        result = ai_service.generate_response(user_message, history)

        # Save assistant response
        assistant_msg = ChatMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=result['response'],
            metadata={
                'suggested_resources': result.get('suggested_resources', []),
                'success': result.get('success', True)
            }
        )

        # Update conversation timestamp
        conversation.save()  # This updates updated_at

        return JsonResponse({
            'success': True,
            'conversation_id': conversation.id,
            'user_message': {
                'id': user_msg.id,
                'content': user_msg.content,
                'created_at': user_msg.created_at.isoformat()
            },
            'assistant_message': {
                'id': assistant_msg.id,
                'content': assistant_msg.content,
                'created_at': assistant_msg.created_at.isoformat(),
                'suggested_resources': result.get('suggested_resources', [])
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_conversation_messages(request, conversation_id):
    """Get all messages in a conversation"""
    conversation = get_object_or_404(
        ChatConversation,
        id=conversation_id,
        user=request.user
    )

    messages = []
    for msg in conversation.messages.all():
        messages.append({
            'id': msg.id,
            'role': msg.role,
            'content': msg.content,
            'created_at': msg.created_at.isoformat(),
            'metadata': msg.metadata
        })

    return JsonResponse({
        'success': True,
        'conversation_id': conversation.id,
        'conversation_title': conversation.title,
        'messages': messages
    })


@login_required
@require_http_methods(["POST"])
def new_conversation(request):
    """Create a new conversation"""
    conversation = ChatConversation.objects.create(
        user=request.user,
        title="New Chat"
    )

    return JsonResponse({
        'success': True,
        'conversation_id': conversation.id,
        'conversation_title': conversation.title
    })


@login_required
@require_http_methods(["DELETE"])
def delete_conversation(request, conversation_id):
    """Delete a conversation"""
    conversation = get_object_or_404(
        ChatConversation,
        id=conversation_id,
        user=request.user
    )

    conversation.delete()

    return JsonResponse({
        'success': True,
        'message': 'Conversation deleted'
    })

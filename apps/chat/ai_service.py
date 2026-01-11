"""
AI-powered chat service using Claude API to suggest learning materials.
"""

import os
import json
from typing import List, Dict, Any
from anthropic import Anthropic
from django.conf import settings
from .models import LearningResource


class ChatAIService:
    """Service for AI-powered chat responses"""

    def __init__(self):
        api_key = os.environ.get('ANTHROPIC_API_KEY') or settings.SECRET_KEY  # Fallback for demo
        self.client = Anthropic(api_key=api_key) if api_key else None
        self.model = "claude-3-5-sonnet-20241022"

    def get_available_resources(self) -> List[Dict[str, Any]]:
        """Get list of available learning resources from Classlib directory"""
        resources = []
        classlib_dir = os.path.join(settings.BASE_DIR, 'Classlib')

        if os.path.exists(classlib_dir):
            for filename in os.listdir(classlib_dir):
                if filename.endswith(('.ipynb', '.py', '.md')):
                    resources.append({
                        'filename': filename,
                        'path': os.path.join(classlib_dir, filename),
                        'type': filename.split('.')[-1]
                    })

        # Also get resources from database
        db_resources = LearningResource.objects.all()
        for resource in db_resources:
            resources.append({
                'title': resource.title,
                'filename': resource.filename,
                'description': resource.description,
                'topics': resource.topics,
                'difficulty': resource.difficulty_level
            })

        return resources

    def generate_response(self, user_message: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Generate AI response with learning material suggestions.

        Args:
            user_message: The user's question
            conversation_history: Previous messages in the conversation

        Returns:
            Dict containing response text and suggested resources
        """
        if conversation_history is None:
            conversation_history = []

        # Get available resources
        available_resources = self.get_available_resources()

        # Build system prompt
        system_prompt = f"""你是一个Python编程学习助手。你的任务是：
1. 理解学生想要学习什么内容
2. 根据可用的学习资源，向学生推荐最合适的学习材料
3. 用中文友好地回答学生的问题

可用的学习资源：
{json.dumps(available_resources, ensure_ascii=False, indent=2)}

当推荐学习资源时，请以如下格式提供：
- 资源标题
- 适合原因
- 难度等级
- 包含的主题

始终保持友好、鼓励和专业的语气。"""

        # If no API key, provide fallback response
        if not self.client:
            return self._fallback_response(user_message, available_resources)

        try:
            # Build message history
            messages = []
            for msg in conversation_history:
                messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })
            messages.append({
                "role": "user",
                "content": user_message
            })

            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt,
                messages=messages
            )

            # Extract response
            response_text = response.content[0].text

            # Extract suggested resources from response
            suggested_resources = self._extract_suggestions(response_text, available_resources)

            return {
                'response': response_text,
                'suggested_resources': suggested_resources,
                'success': True
            }

        except Exception as e:
            return {
                'response': f"抱歉，我在处理你的请求时遇到了问题：{str(e)}",
                'suggested_resources': [],
                'success': False,
                'error': str(e)
            }

    def _fallback_response(self, user_message: str, resources: List[Dict]) -> Dict[str, Any]:
        """Provide fallback response when API is not available"""
        # Simple keyword matching for demo
        keywords = user_message.lower()
        suggestions = []

        if '数据' in keywords or '列表' in keywords or 'list' in keywords:
            suggestions.append({
                'filename': '第一课_基本数据结构.ipynb',
                'title': 'Python基本数据结构',
                'reason': '这节课涵盖了Python的基本数据类型，包括列表、元组、字典和集合。'
            })

        response_text = f"你好！我注意到你对 {user_message} 感兴趣。"

        if suggestions:
            response_text += "\n\n我为你推荐以下学习资源：\n"
            for s in suggestions:
                response_text += f"\n📚 **{s['title']}** ({s['filename']})\n   {s['reason']}"
        else:
            response_text += "\n\n目前我们有以下学习资源可供学习：\n"
            for r in resources[:3]:  # Show first 3
                response_text += f"\n- {r.get('title', r.get('filename', ''))}"

        response_text += "\n\n请告诉我你想深入学习哪个方面，我会为你提供更具体的建议！"

        return {
            'response': response_text,
            'suggested_resources': suggestions,
            'success': True
        }

    def _extract_suggestions(self, response_text: str, resources: List[Dict]) -> List[Dict]:
        """Extract resource suggestions from AI response"""
        suggestions = []

        # Simple extraction - look for filenames mentioned in response
        for resource in resources:
            filename = resource.get('filename', '')
            if filename and filename in response_text:
                suggestions.append({
                    'filename': filename,
                    'title': resource.get('title', filename),
                    'description': resource.get('description', ''),
                    'topics': resource.get('topics', [])
                })

        return suggestions

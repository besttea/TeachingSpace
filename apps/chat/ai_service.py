"""
AI-powered chat service using Claude API to suggest learning materials.

The assistant can *use tools* (Anthropic tool-use) to read teaching
materials: list notebooks in ClassLib, fetch a notebook's structure, or
read one section's content. Tools are safe server-side functions in
``apps.chat.notebook_tools`` wrapping the shared parser in
``apps.core.notebook_parser`` — the model only picks tool + arguments.
"""

import json
import logging
import os
from typing import Any, Dict, List

from anthropic import Anthropic
from django.conf import settings

from .models import LearningResource
from .notebook_tools import MAX_RESULT_CHARS, TOOL_SCHEMAS, execute_tool

logger = logging.getLogger(__name__)

#: Maximum tool-use rounds per message (prevents runaway loops).
MAX_TOOL_ROUNDS = 3


class ChatAIService:
    """Service for AI-powered chat responses"""

    def __init__(self, client=None):
        # A client may be injected (tests); otherwise build it from the
        # multi-provider config (anthropic / deepseek / ...).
        if client is not None:
            self.client = client
            self.model = getattr(settings, 'AI_MODEL', '') or 'claude-sonnet-4-5-20250929'
        else:
            from apps.ai_agents.ai_config import api_key, base_url, is_configured, model_name

            if is_configured():
                client_kwargs = {'api_key': api_key()}
                if base_url():
                    client_kwargs['base_url'] = base_url()
                self.client = Anthropic(**client_kwargs)
            else:
                self.client = None

            self.model = model_name()

    def get_available_resources(self) -> List[Dict[str, Any]]:
        """Get list of available learning resources (no filesystem paths —
        filenames only, never sent to the LLM)."""
        resources = []
        classlib_dir = os.path.join(settings.BASE_DIR, 'ClassLib')

        if os.path.exists(classlib_dir):
            for filename in os.listdir(classlib_dir):
                if filename.endswith(('.ipynb', '.py', '.md')):
                    resources.append({
                        'filename': filename,
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

    def _build_system_prompt(self) -> str:
        return """你是一个Python编程学习助手，服务于一个 Python 教学平台。你的任务是：
1. 理解学生想要学习或询问的内容
2. 使用工具查询教学资料（notebook），基于资料的真实内容回答
3. 用中文友好地回答学生的问题

你可以使用以下工具（教学资料查询）：
- list_notebooks: 列出可用的 notebook 资料及其章节结构
- get_notebook_digest: 查看某个 notebook 的结构摘要
- get_notebook_section: 读取某个 notebook 中某一节的完整内容（含代码与运行输出）

工具使用规则：
- 回答具体知识点（概念、语法、示例、运行结果）前，先调用工具获取真实内容；不要凭记忆编造
- 回答"有什么资料/课程/目录"类问题，调用 list_notebooks
- 回答"某节讲了什么"类问题，调用 get_notebook_section 读取该节
- 回答时注明内容出处（如"根据《第一课》1.2 节"）
- 工具未找到内容时，如实告知学生，并建议用 list_notebooks 查看现有资料
- 代码相关回答中给出的示例代码应与资料风格一致

始终保持友好、鼓励和专业的语气。"""

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

        # If no API key, provide fallback response
        if not self.client:
            return self._fallback_response(user_message, available_resources)

        try:
            # Daily cost limit (optional, AI_COST_LIMIT_DAILY)
            from apps.ai_agents.models import daily_cost_exceeded
            if daily_cost_exceeded():
                return {
                    'response': '今日 AI 用量已达上限，请明天再试。',
                    'suggested_resources': [],
                    'success': False,
                    'error': 'daily cost limit reached',
                }

            # Long-conversation memory: beyond the recent 20 messages, older
            # turns are summarized once (cached) and injected into the system
            # prompt, so context is preserved instead of silently dropped.
            recent = conversation_history
            system_prompt = self._build_system_prompt()
            if len(conversation_history) > 20:
                older = conversation_history[:-20]
                recent = conversation_history[-20:]
                summary = self._summarize_history(older)
                if summary:
                    system_prompt += f'\n\n[更早对话的摘要]\n{summary}'

            # Build message history
            messages = []
            for msg in recent:
                messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })
            messages.append({
                "role": "user",
                "content": user_message
            })

            # Tool-use loop: let the model query materials, then answer.
            response_text = ""
            tool_used = False
            import time as _time
            _start = _time.time()
            for _ in range(MAX_TOOL_ROUNDS):
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2000,
                    system=system_prompt,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                )

                tool_uses = [b for b in response.content if b.type == 'tool_use']
                response_text += "".join(
                    b.text for b in response.content if b.type == 'text'
                )

                if not tool_uses:
                    break

                # Record the assistant turn (with its tool calls). Thinking
                # blocks (reasoning models) are replayed as-is — they carry
                # no 'id' and must not be treated as tool_use.
                assistant_content = []
                for b in response.content:
                    if b.type == 'text':
                        assistant_content.append({"type": "text", "text": b.text})
                    elif b.type == 'tool_use':
                        assistant_content.append({
                            "type": "tool_use",
                            "id": b.id, "name": b.name, "input": b.input,
                        })
                    elif b.type == 'thinking':
                        assistant_content.append({
                            "type": "thinking", "thinking": b.thinking,
                        })
                messages.append({
                    "role": "assistant",
                    "content": assistant_content,
                })
                # …and the tool results as a user turn.
                tool_results = []
                for block in tool_uses:
                    result = execute_tool(block.name, block.input or {})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False)[:MAX_RESULT_CHARS],
                    })
                    tool_used = True
                messages.append({"role": "user", "content": tool_results})

            if not response_text:
                response_text = "（未生成回答）"

            # Audit log (tokens/cost)
            from apps.ai_agents.models import record_generation
            record_generation(
                agent='chat',
                model=self.model,
                prompt=user_message,
                response=response_text,
                duration_ms=int((_time.time() - _start) * 1000),
                success=True,
            )

            # Extract suggested resources from response
            suggested_resources = self._extract_suggestions(response_text, available_resources)

            return {
                'response': response_text,
                'suggested_resources': suggested_resources,
                'success': True,
                'tools_used': tool_used,
            }

        except Exception as e:
            # Don't leak internal error details to students (except in DEBUG).
            logger.exception("Chat AI request failed")
            detail = str(e) if getattr(settings, 'DEBUG', False) else '请稍后再试'
            return {
                'response': f"抱歉，我在处理你的请求时遇到了问题：{detail}",
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

    def _summarize_history(self, older_messages: List[Dict[str, str]]) -> str:
        """Summarize conversation turns beyond the recent window.

        One harness call per conversation state (cached by content hash),
        so repeated messages in the same long session don't re-spend tokens.
        """
        import hashlib

        from django.core.cache import cache

        digest = hashlib.sha256(
            json.dumps(older_messages, ensure_ascii=False).encode('utf-8')
        ).hexdigest()
        cache_key = f'chat_summary:{digest}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        transcript = '\n'.join(
            f'{m["role"]}: {str(m["content"])[:200]}' for m in older_messages
        )
        try:
            from apps.ai_agents.harness import HarnessCore
            summary = HarnessCore.call(
                f'将以下对话历史压缩为 3 条以内的要点（中文）：\n{transcript}',
                role='worker',
                system_prompt='你是对话记忆压缩器。只输出要点，不输出其他内容。',
                temperature=0.2,
                max_tokens=300,
            ).strip()
        except Exception:
            logger.warning('history summarization failed — falling back to truncation')
            return ''
        cache.set(cache_key, summary, 86400)
        return summary

    def _extract_suggestions(self, response_text: str, resources: List[Dict]) -> List[Dict]:
        """Extract resource suggestions from the AI response.

        Matches notebook filenames AND section labels (e.g. '1.2 标准数据
        类型') mentioned in the answer — T18: structured-ish matching on
        the platform's real material registry.
        """
        suggestions = []
        seen = set()

        candidates = []  # (match_text, title, filename)
        for resource in resources:
            filename = resource.get('filename', '')
            if filename:
                candidates.append((filename, resource.get('title', filename), filename))
        # Notebook sections (from the shared material registry)
        try:
            from .notebook_tools import list_notebooks
            for notebook in list_notebooks().get('notebooks', []):
                for section in notebook.get('sections', []):
                    if section:
                        candidates.append(
                            (section, f'{notebook.get("title", notebook["filename"])} · {section}',
                             notebook['filename']))
        except Exception:
            pass  # suggestions are best-effort

        for match_text, title, filename in candidates:
            if match_text and match_text in response_text and filename not in seen:
                seen.add(filename)
                suggestions.append({
                    'filename': filename,
                    'title': title,
                    'description': '',
                    'topics': [],
                })
        return suggestions[:5]

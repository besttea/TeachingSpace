"""Tests for the chat AI service and its notebook tools.

Covers:
- notebook tool executors (listing, digest, section reading, path safety)
- the ChatAIService tool-use loop (with a mocked Anthropic client)
"""

import json
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User

from .ai_service import ChatAIService
from .notebook_tools import execute_tool, get_notebook_digest, get_notebook_section, list_notebooks


def _text_block(text):
    return SimpleNamespace(type='text', text=text)


def _tool_use_block(block_id, name, input_data):
    return SimpleNamespace(type='tool_use', id=block_id, name=name, input=input_data)


class _FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _FakeClient:
    def __init__(self, responses):
        self.messages = _FakeMessages(responses)


class NotebookToolsTests(SimpleTestCase):
    """Tool executors against the real ClassLib notebook."""

    def test_list_notebooks(self):
        result = list_notebooks()
        notebooks = result['notebooks']
        self.assertGreaterEqual(len(notebooks), 1)
        first = notebooks[0]
        self.assertEqual(first['filename'], '第一课_基本数据结构.ipynb')
        self.assertTrue(any(s.startswith('1.1') for s in first['sections']))

    def test_get_notebook_digest(self):
        result = get_notebook_digest('第一课_基本数据结构.ipynb')
        self.assertIn('digest', result)
        self.assertIn('1.1 数字常量', result['digest'])

    def test_get_notebook_section_by_number(self):
        result = get_notebook_section('第一课_基本数据结构.ipynb', '1.2')
        self.assertIn('section', result)
        self.assertIn('标准数据类型', result['section'])
        self.assertIn('代码', result['section'])

    def test_get_notebook_section_by_title(self):
        result = get_notebook_section('第一课_基本数据结构.ipynb', '数字常量')
        self.assertIn('1.1', result['section'])

    def test_get_notebook_section_missing(self):
        result = get_notebook_section('第一课_基本数据结构.ipynb', '不存在的节')
        self.assertIn('error', result)
        self.assertIn('available_sections', result)

    def test_filename_whitelist_blocks_traversal(self):
        result = get_notebook_section('../manage.py', '1.1')
        self.assertIn('error', result)
        result = get_notebook_digest('does_not_exist.ipynb')
        self.assertIn('error', result)

    def test_execute_tool_unknown(self):
        result = execute_tool('rm_rf', {})
        self.assertIn('error', result)


class ChatAIServiceToolLoopTests(TestCase):
    """Tool-use loop with a mocked Anthropic client."""

    def test_model_uses_tool_then_answers(self):
        fake = _FakeClient([
            # Round 1: model asks to list notebooks
            SimpleNamespace(content=[_tool_use_block('call_1', 'list_notebooks', {})]),
            # Round 2: model answers
            SimpleNamespace(content=[_text_block('根据资料，1.2 节讲的是标准数据类型。')]),
        ])
        service = ChatAIService(client=fake)
        result = service.generate_response('有哪些学习资料？')

        self.assertTrue(result['success'])
        self.assertTrue(result.get('tools_used'))
        self.assertIn('1.2 节', result['response'])

        # First API call must have advertised the tools
        first_call = fake.messages.calls[0]
        tool_names = {t['name'] for t in first_call['tools']}
        self.assertEqual(tool_names, {'list_notebooks', 'get_notebook_digest', 'get_notebook_section'})
        # Second call must carry the tool result back
        second_messages = fake.messages.calls[1]['messages']
        self.assertTrue(any(
            m['role'] == 'user' and any(
                isinstance(c, dict) and c.get('type') == 'tool_result'
                for c in m['content']
            )
            for m in second_messages
        ))

    def test_section_tool_result_reaches_model(self):
        fake = _FakeClient([
            SimpleNamespace(content=[
                _tool_use_block('call_1', 'get_notebook_section',
                                {'filename': '第一课_基本数据结构.ipynb', 'section': '1.1'}),
            ]),
            SimpleNamespace(content=[_text_block('1.1 节介绍了数字常量。')]),
        ])
        service = ChatAIService(client=fake)
        result = service.generate_response('1.1 节讲了什么？')

        self.assertTrue(result['success'])
        second_call = fake.messages.calls[1]['messages']
        tool_result_content = next(
            c['content'] for m in second_call
            if m['role'] == 'user'
            for c in m['content']
            if isinstance(c, dict) and c.get('type') == 'tool_result'
        )
        self.assertIn('数字常量', tool_result_content)  # real notebook content

    def test_api_error_is_sanitized_in_production(self):
        class _Boom:
            def __init__(self):
                self.messages = _BoomMessages()

        class _BoomMessages:
            def create(self, **kwargs):
                raise RuntimeError('secret internal detail')

        with override_settings(DEBUG=False):
            service = ChatAIService(client=_Boom())
            result = service.generate_response('你好')
        self.assertFalse(result['success'])
        self.assertNotIn('secret internal detail', result['response'])

    def test_api_error_detail_shown_in_debug(self):
        class _Boom:
            def __init__(self):
                self.messages = _BoomMessages()

        class _BoomMessages:
            def create(self, **kwargs):
                raise RuntimeError('secret internal detail')

        with override_settings(DEBUG=True):
            service = ChatAIService(client=_Boom())
            result = service.generate_response('你好')
        self.assertFalse(result['success'])
        self.assertIn('secret internal detail', result['response'])


class InputLimitAndSuggestionsTests(TestCase):
    """T17/T18: message length cap and section-aware suggestions."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='chat_limiter', email='cl@example.com',
            password='StrongPass123!', user_type='student')

    def test_long_message_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('chat:send-message'),
            data=json.dumps({'message': 'x' * 5000}),
            content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('过长', response.json()['error'])

    def test_section_label_suggestion(self):
        from .ai_service import ChatAIService
        service = ChatAIService(client='sentinel')  # bypass client build
        response_text = '根据《第一课》的 1.2 标准数据类型 一节，列表是可变的……'
        suggestions = service._extract_suggestions(response_text, [])
        self.assertTrue(any('1.2' in s['title'] for s in suggestions))
        self.assertEqual(suggestions[0]['filename'], '第一课_基本数据结构.ipynb')

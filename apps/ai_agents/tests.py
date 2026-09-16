"""Tests for AI generation tracking (history records + daily cost limit),
multi-provider model selection (ai_config), and the course design agent."""

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from . import ai_config
from .models import AIGenerationHistory, daily_cost_exceeded, record_generation


class CourseDesignAgentTests(SimpleTestCase):
    """Outline generation: structure contract + source-material grounding."""

    def _agent_with_output(self, output):
        from .course_design_agent import CourseDesignAgent

        agent = CourseDesignAgent.__new__(CourseDesignAgent)
        agent.api_key = 'test'
        agent.model = 'test'
        agent.generate_json = mock.Mock(return_value=output)
        return agent

    def test_outline_prompt_includes_source_material(self):
        agent = self._agent_with_output({'chapters': []})
        agent.design_course_outline(
            '数字常量', 'beginner', chapter_count=3,
            source_material='【素材：第一课 · 1.1 数字常量】\nint、float、bool……')
        _prompt, _system = agent.generate_json.call_args[0]
        self.assertIn('数字常量', _prompt)
        self.assertIn('素材', _prompt)
        self.assertIn('int、float', _prompt)

    def test_outline_without_material_has_no_material_section(self):
        agent = self._agent_with_output({'chapters': []})
        agent.design_course_outline('循环', 'beginner', chapter_count=2)
        prompt, _system = agent.generate_json.call_args[0]
        self.assertNotIn('素材', prompt)


class JSONExtractionTests(SimpleTestCase):
    """_extract_json must survive fences, prose, and trailing braces."""

    def _extract(self, text):
        from .base_agent import BaseAgent
        return BaseAgent._extract_json(text)

    def test_plain_json(self):
        self.assertEqual(self._extract('{"a": 1}'), {'a': 1})

    def test_fenced_with_prose(self):
        text = '好的，以下是结果：\n```json\n{"cells": [{"type": "text"}]}\n```\n希望对你有帮助！'
        self.assertEqual(self._extract(text), {'cells': [{'type': 'text'}]})

    def test_trailing_text_with_braces(self):
        # greedy regex would grab through the trailing {…} and corrupt the parse
        text = '{"score": 85}\n\n评分说明：分数范围 {0-100}，其中 {60} 为及格线。'
        self.assertEqual(self._extract(text), {'score': 85})

    def test_empty_raises(self):
        import json as _json
        with self.assertRaises(_json.JSONDecodeError):
            self._extract('')


class NotebookGroundingTests(SimpleTestCase):
    """find_related_sections returns real ClassLib content for a topic."""

    def test_finds_section_for_topic(self):
        from apps.chat.notebook_tools import find_related_sections

        material = find_related_sections('数字常量')
        self.assertTrue(material)
        self.assertIn('数字常量', material)

    def test_no_match_returns_empty(self):
        from apps.chat.notebook_tools import find_related_sections

        self.assertEqual(find_related_sections('量子引力波速算'), '')


class AIConfigTests(SimpleTestCase):
    """Provider selection: anthropic vs deepseek, model override."""

    @override_settings(
        AI_PROVIDER='deepseek',
        AI_PROVIDERS={
            'anthropic': {'api_key': 'sk-ant', 'base_url': '', 'default_model': 'claude-x'},
            'deepseek': {
                'api_key': 'sk-deep',
                'base_url': 'https://api.deepseek.com/anthropic',
                'default_model': 'deepseek-chat',
            },
        },
        AI_MODEL='',
    )
    def test_deepseek_provider_selected(self):
        self.assertEqual(ai_config.provider_name(), 'deepseek')
        self.assertEqual(ai_config.api_key(), 'sk-deep')
        self.assertEqual(ai_config.base_url(), 'https://api.deepseek.com/anthropic')
        self.assertEqual(ai_config.model_name(), 'deepseek-chat')
        self.assertTrue(ai_config.is_configured())

    @override_settings(
        AI_PROVIDER='deepseek',
        AI_PROVIDERS={
            'anthropic': {'api_key': 'sk-ant', 'base_url': '', 'default_model': 'claude-x'},
            'deepseek': {
                'api_key': 'sk-deep',
                'base_url': 'https://api.deepseek.com/anthropic',
                'default_model': 'deepseek-chat',
            },
        },
        AI_MODEL='deepseek-reasoner',
    )
    def test_model_override_wins(self):
        self.assertEqual(ai_config.model_name(), 'deepseek-reasoner')

    @override_settings(
        AI_PROVIDER='deepseek',
        AI_PROVIDERS={
            'anthropic': {'api_key': 'sk-ant', 'base_url': '', 'default_model': 'claude-x'},
            'deepseek': {'api_key': '', 'base_url': 'https://api.deepseek.com/anthropic',
                         'default_model': 'deepseek-chat'},
        },
        AI_MODEL='',
    )
    def test_missing_key_not_configured(self):
        self.assertFalse(ai_config.is_configured())

    @override_settings(
        AI_PROVIDER='deepseek',
        AI_PROVIDERS={
            'anthropic': {'api_key': 'sk-ant', 'base_url': '', 'default_model': 'claude-x'},
            'deepseek': {
                'api_key': 'sk-deep',
                'base_url': 'https://api.deepseek.com/anthropic',
                'default_model': 'deepseek-chat',
            },
        },
        AI_MODEL='',
    )
    def test_base_agent_uses_active_provider(self):
        from .learning_agent import LearningAgent

        agent = LearningAgent()  # concrete BaseAgent subclass
        self.assertEqual(agent.api_key, 'sk-deep')
        self.assertEqual(agent.model, 'deepseek-chat')
        self.assertEqual(str(agent.client.base_url), 'https://api.deepseek.com/anthropic/')


class CostTrackingTests(TestCase):
    def test_record_generation_creates_history(self):
        record_generation(
            agent='TestAgent', model='claude-test',
            prompt='hello', response='world',
            input_tokens=100, output_tokens=50,
        )
        row = AIGenerationHistory.objects.get()
        self.assertEqual(row.agent, 'TestAgent')
        self.assertGreater(float(row.estimated_cost_usd), 0)
        self.assertTrue(row.success)

    def test_failed_generation_recorded_with_error(self):
        record_generation(
            agent='TestAgent', model='claude-test',
            prompt='hello', success=False, error='boom',
        )
        row = AIGenerationHistory.objects.get()
        self.assertFalse(row.success)
        self.assertEqual(row.error, 'boom')

    def test_long_prompt_truncated(self):
        record_generation(
            agent='TestAgent', model='claude-test',
            prompt='x' * 10000, response='y' * 10000,
        )
        row = AIGenerationHistory.objects.get()
        self.assertLess(len(row.prompt), 5000)
        self.assertLess(len(row.response), 5000)

    @override_settings(AI_COST_LIMIT_DAILY=0.001)
    def test_daily_cost_limit_enforced(self):
        self.assertFalse(daily_cost_exceeded())
        # 0.001$ = 1000 input tokens at 3$/1M + overhead
        record_generation(
            agent='TestAgent', model='claude-test', prompt='x',
            input_tokens=1_000_000, output_tokens=0,
        )
        self.assertTrue(daily_cost_exceeded())

    @override_settings(AI_COST_LIMIT_DAILY=0)
    def test_zero_limit_means_disabled(self):
        record_generation(
            agent='TestAgent', model='claude-test', prompt='x',
            input_tokens=1_000_000,
        )
        self.assertFalse(daily_cost_exceeded())

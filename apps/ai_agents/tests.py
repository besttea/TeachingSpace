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
        AI_MODEL='', AI_ACTIVE_MODEL='',
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
        AI_MODEL='deepseek-reasoner', AI_ACTIVE_MODEL='',
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
        AI_MODEL='', AI_ACTIVE_MODEL='',
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
        AI_MODEL='', AI_ACTIVE_MODEL='',
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


class ExerciseValidationTests(SimpleTestCase):
    """validate_exercise: sandbox is the authority on AI-generated exercises."""

    def test_good_solution_validates(self):
        from .training_agent import validate_exercise
        ok, message, _detail = validate_exercise(
            'def add(a, b):\n    return a + b',
            [{'input': 'add(2, 3)', 'expected': 5},
             {'input': 'add(-1, 1)', 'expected': 0}])
        self.assertTrue(ok, message)

    def test_wrong_solution_rejected(self):
        from .training_agent import validate_exercise
        ok, _message, _detail = validate_exercise(
            'def add(a, b):\n    return a * b',
            [{'input': 'add(2, 3)', 'expected': 5}])
        self.assertFalse(ok)

    def test_empty_solution_rejected(self):
        from .training_agent import validate_exercise
        ok, _message, _detail = validate_exercise('', [{'input': 'x()', 'expected': 1}])
        self.assertFalse(ok)


class ModifyMethodTests(SimpleTestCase):
    """modify_exercise / modify_question: contract preservation + list normalization."""

    def _mock_agent(self, output):
        from unittest import mock as _mock
        agent = _mock.MagicMock()
        agent.api_key = 'x'
        agent.generate_json = _mock.Mock(return_value=output)
        return agent

    def test_modify_exercise_returns_updated_dict(self):
        from .training_agent import TrainingAgent
        agent = TrainingAgent.__new__(TrainingAgent)
        agent.api_key = 'x'
        agent.generate_json = mock.Mock(return_value={
            'title': 'T', 'test_cases': [{'input': 'f()', 'expected': 1}]})
        result = agent.modify_exercise(
            {'title': 'T', 'test_cases': []}, '增加边界用例')
        self.assertIsInstance(result, dict)
        self.assertEqual(result['title'], 'T')
        # the instruction is in the prompt
        prompt = agent.generate_json.call_args[0][0]
        self.assertIn('增加边界用例', prompt)
        self.assertIn('Current exercise', prompt)

    def test_modify_question_returns_updated_dict(self):
        from .examination_agent import ExaminationAgent
        agent = ExaminationAgent.__new__(ExaminationAgent)
        agent.api_key = 'x'
        agent.generate_json = mock.Mock(return_value={
            'type': 'multiple_choice', 'text': '新题干', 'options': {'A': 'x'}})
        result = agent.modify_question(
            {'type': 'multiple_choice', 'text': '旧题干'}, '更口语化')
        self.assertEqual(result['text'], '新题干')
        prompt = agent.generate_json.call_args[0][0]
        self.assertIn('更口语化', prompt)
        self.assertIn('SAME type', prompt)

    def test_generate_exercise_with_feedback_includes_feedback(self):
        from .training_agent import TrainingAgent
        agent = TrainingAgent.__new__(TrainingAgent)
        agent.api_key = 'x'
        agent.generate_json = mock.Mock(return_value={'title': 'T'})
        agent.generate_exercise_with_feedback(
            {'title': 'bad'}, 'IndexError: list index out of range')
        prompt = agent.generate_json.call_args[0][0]
        self.assertIn('REJECTED', prompt)
        self.assertIn('IndexError', prompt)


class HarnessTests(SimpleTestCase):
    """Role routing + fallback chain."""

    @override_settings(
        AI_PLANNER_MODEL='deepseek-reasoner', AI_WORKER_MODEL='deepseek-flash',
        AI_MODEL_ROLES={}, AI_FALLBACK_MODELS='',
        AI_PROVIDERS={'anthropic': {'api_key': 'k', 'base_url': '',
                                    'default_model': 'claude-x'}},
        AI_PROVIDER='anthropic', AI_MODEL='', AI_ACTIVE_MODEL='',
    )
    def test_role_model_routing(self):
        from .harness import HarnessCore
        self.assertEqual(HarnessCore.role_model('planner'), 'deepseek-reasoner')
        self.assertEqual(HarnessCore.role_model('worker'), 'deepseek-flash')
        self.assertEqual(HarnessCore.role_model('grader'), 'claude-x')  # provider default

    @override_settings(
        AI_PLANNER_MODEL='', AI_WORKER_MODEL='', AI_MODEL_ROLES={},
        AI_FALLBACK_MODELS='',
        AI_PROVIDERS={'anthropic': {'api_key': 'k', 'base_url': '',
                                    'default_model': 'm1'}},
        AI_PROVIDER='anthropic', AI_MODEL='', AI_ACTIVE_MODEL='',
    )
    def test_planner_defaults_to_provider_model(self):
        # no hardcoded reasoner default — unset planner follows the provider
        from .harness import HarnessCore
        self.assertEqual(HarnessCore.role_model('planner'), 'm1')
        self.assertEqual(HarnessCore.role_model('worker'), 'm1')

    @override_settings(
        AI_PLANNER_MODEL='', AI_WORKER_MODEL='', AI_MODEL_ROLES={},
        AI_FALLBACK_MODELS='',
        AI_PROVIDERS={'anthropic': {'api_key': 'k', 'base_url': '',
                                    'default_model': 'm1'}},
        AI_PROVIDER='anthropic', AI_MODEL='os-reasoner', AI_ACTIVE_MODEL='app-flash',
    )
    def test_active_model_beats_ai_model(self):
        from . import ai_config
        self.assertEqual(ai_config.model_name(), 'app-flash')

    @override_settings(
        AI_PLANNER_MODEL='', AI_WORKER_MODEL='', AI_MODEL_ROLES={},
        AI_FALLBACK_MODELS='m2,m3',
        AI_PROVIDERS={'anthropic': {'api_key': 'k', 'base_url': '',
                                    'default_model': 'm1'}},
        AI_PROVIDER='anthropic', AI_MODEL='', AI_ACTIVE_MODEL='',
    )
    def test_fallback_chain(self):
        from .harness import HarnessCore
        self.assertEqual(HarnessCore.fallback_chain('m1'), ['m1', 'm2', 'm3'])


class SkillPipelineTests(TestCase):
    """Exercise/Exam skills: harness-driven pipelines (mocked model calls)."""

    def test_exercise_skill_fix_loop(self):
        from unittest import mock as _mock
        from .skills import ExerciseSkill

        with _mock.patch('apps.ai_agents.skills.exercise_skill.HarnessCore.call') as call:
            # attempt 1: wrong solution → validation fails; attempt 2: fixed
            call.side_effect = [
                {'title': 'T', 'description': 'd',
                 'solution_code': 'def f():\n    return 999',
                 'test_cases': [{'input': 'f()', 'expected': 1}], 'hints': []},
                {'title': 'T', 'description': 'd',
                 'solution_code': 'def f():\n    return 1',
                 'test_cases': [{'input': 'f()', 'expected': 1}], 'hints': []},
            ]
            result = ExerciseSkill().run('测试', 'beginner')
            self.assertTrue(result['validated'])
            self.assertEqual(result['attempts'], 2)
            # the fix prompt carries the failure feedback
            self.assertIn('REJECTED', call.call_args_list[1].args[0])

    def test_exam_skill_plans_and_validates(self):
        from unittest import mock as _mock
        from .skills import ExamSkill

        good_code = {
            'type': 'code', 'text': '写 add', 'points': 10,
            'starter_code': 'def add(a, b):\n    pass',
            'solution_code': 'def add(a, b):\n    return a + b',
            'test_cases': [{'input': 'add(1, 2)', 'expected': 3}],
        }
        with _mock.patch('apps.ai_agents.skills.exam_skill.HarnessCore.call') as call:
            call.side_effect = [
                {'types': ['multiple_choice', 'code']},      # planner plan
                {'type': 'multiple_choice', 'text': 'Q1', 'points': 5,
                 'options': {'A': '1', 'B': '2'}, 'correct_answer': 'A'},  # worker Q1
                good_code,                                    # worker Q2 (code)
            ]
            result = ExamSkill().run('Python', 'beginner', count=2)
            self.assertEqual(len(result['questions']), 2)
            self.assertEqual(result['code_validated'], '1/1')
            self.assertTrue(result['all_code_valid'])
            # planner used for the plan, worker for questions
            self.assertEqual(call.call_args_list[0].kwargs['role'], 'planner')
            self.assertEqual(call.call_args_list[1].kwargs['role'], 'worker')


class LoggerHygieneTests(SimpleTestCase):
    """Static guard: modules referencing `logger` must define it.

    Regression for the 'name logger is not defined' generation failures
    (learning_agent.py referenced logger without defining it — surfaced
    only when a cell failed during generation).
    """

    def test_modules_referencing_logger_define_it(self):
        import pathlib

        pkg = pathlib.Path(__file__).parent
        for py in pkg.rglob('*.py'):
            src = py.read_text(encoding='utf-8')
            if 'logger.' in src:
                self.assertTrue(
                    'logger = logging.getLogger' in src,
                    f'{py.name} uses logger but never defines it')

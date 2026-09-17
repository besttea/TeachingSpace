"""Skill parameterization tests: layering (defaults → AI_SKILL_PARAMS →
env), exam near-duplicate filtering and negative-example context injection
(user feedback 2026-09-17: 考题重复 + skill 参数化可调机制)."""

import os
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from .skill_config import DEFAULTS, skill_params
from .skills.exam_skill import (
    ExamSkill, _already_generated_context, _is_duplicate,
)


class SkillParamsLayeringTests(SimpleTestCase):
    def test_defaults_returned_without_config(self):
        params = skill_params('exam_generation')
        self.assertEqual(params['temperature'], 0.2)
        self.assertEqual(params['max_questions'], 30)
        self.assertTrue(params['validate_code'])

    def test_settings_layer_overrides_defaults(self):
        with override_settings(AI_SKILL_PARAMS={
                'exam_generation': {'temperature': 0.6, 'max_questions': 12}}):
            params = skill_params('exam_generation')
        self.assertEqual(params['temperature'], 0.6)
        self.assertEqual(params['max_questions'], 12)
        self.assertEqual(params['plan_temperature'], 0.2)  # untouched knob

    def test_env_layer_wins_over_everything(self):
        with override_settings(AI_SKILL_PARAMS={
                'exam_generation': {'temperature': 0.6}}):
            with mock.patch.dict(os.environ, {
                    'AI_SKILL_EXAM_GENERATION_TEMPERATURE': '0.9',
                    'AI_SKILL_EXAM_GENERATION_DEDUP_ENABLED': 'false',
                    'AI_SKILL_EXAM_GENERATION_MAX_QUESTIONS': '7'}):
                params = skill_params('exam_generation')
        self.assertEqual(params['temperature'], 0.9)
        self.assertFalse(params['dedup_enabled'])  # bool cast
        self.assertEqual(params['max_questions'], 7)  # int cast

    def test_malformed_env_value_keeps_previous_layer(self):
        with mock.patch.dict(os.environ,
                             {'AI_SKILL_EXAM_GENERATION_MAX_QUESTIONS': 'not-an-int'}):
            params = skill_params('exam_generation')
        self.assertEqual(params['max_questions'], 30)

    def test_unknown_skill_returns_empty_dict(self):
        self.assertEqual(skill_params('nope'), {})

    def test_all_registered_skills_have_defaults(self):
        for name in DEFAULTS:
            params = skill_params(name)
            self.assertGreater(len(params), 0)
            # every skill carries at least one temperature/token knob
            self.assertTrue(any('temperature' in k or 'max_tokens' in k
                                for k in params), name)


class ExamSkillDedupTests(TestCase):
    def setUp(self):
        self.skill = ExamSkill()

    def test_is_duplicate_exact_and_near_text(self):
        existing = [{'text': '写一个函数计算两数之和并返回结果'}]
        self.assertTrue(_is_duplicate(
            {'text': '写一个函数计算两数之和并返回结果'}, existing, 0.85))
        # same question with trivial wording changes still caught
        self.assertTrue(_is_duplicate(
            {'text': '编写一个函数，计算两个数的和并返回结果'}, existing, 0.85))

    def test_distinct_questions_pass(self):
        existing = [{'text': '写一个函数计算两数之和'}]
        self.assertFalse(_is_duplicate(
            {'text': '列表推导式与 for 循环在性能上的区别是什么'}, existing, 0.85))

    def test_empty_text_is_duplicate(self):
        self.assertTrue(_is_duplicate({'text': ''}, [], 0.85))

    def test_context_injection_lists_existing_questions(self):
        context = _already_generated_context([
            {'text': '第一题'}, {'text': '第二题'}])
        self.assertIn('ALREADY generated', context)
        self.assertIn('第一题', context)
        self.assertIn('第二题', context)

    def test_run_drops_duplicates_and_injects_context(self):
        """Planner returns 4 types; the worker keeps returning the SAME
        question — exactly one question must survive (the user-reported
        'same question five times' bug)."""
        same = {'type': 'multiple_choice', 'text': 'Python 的列表是什么？',
                'points': 4, 'options': {'A': 'x', 'B': 'y', 'C': 'z', 'D': 'w'},
                'correct_answer': 'A'}
        prompts = []

        def fake_call(prompt, **kwargs):
            prompts.append(prompt)
            if 'Plan a' in prompt:
                return {'types': ['multiple_choice'] * 4}
            return dict(same)

        with mock.patch('apps.ai_agents.skills.exam_skill.HarnessCore.call',
                        side_effect=fake_call):
            result = self.skill.run('Python 基础', count=4)
        self.assertEqual(len(result['questions']), 1)
        self.assertEqual(result['duplicates_skipped'], 3)
        # prompts 2+ must carry the already-generated question as context
        worker_prompts = [p for p in prompts if 'Create ONE' in p]
        self.assertEqual(len(worker_prompts), 4)
        self.assertIn('ALREADY generated', worker_prompts[1])
        self.assertIn('Python 的列表是什么', worker_prompts[1])

    def test_run_planner_failure_uses_default_mix(self):
        def failing_planner(prompt, **kwargs):
            raise RuntimeError('planner down')
        with mock.patch('apps.ai_agents.skills.exam_skill.HarnessCore.call',
                        side_effect=failing_planner):
            result = self.skill.run('Python 基础', count=3)
        self.assertEqual(len(result['questions']), 0)
        self.assertEqual(result['code_validated'], '0/0')

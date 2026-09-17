"""KnowledgeSkill tests: grounded/autonomous dual mode, defensive parsing
and knob application (knowledge-point extraction, plan step 3)."""

from unittest import mock

from django.test import SimpleTestCase

from .skills.knowledge_skill import KnowledgeSkill


def _points(n=2):
    return {'points': [
        {'title': f'知识点{i}', 'description': f'说明{i}',
         'difficulty': 'beginner'} for i in range(1, n + 1)]}


class KnowledgeSkillTests(SimpleTestCase):
    def setUp(self):
        self.skill = KnowledgeSkill()
        self.patch = mock.patch(
            'apps.ai_agents.skills.knowledge_skill.HarnessCore.call',
            return_value=_points(2))
        self.mock_call = self.patch.start()
        self.addCleanup(self.patch.stop)

    def _prompt(self):
        return self.mock_call.call_args[0][0]

    def test_extract_from_chapter_text(self):
        points = self.skill.extract('第1章 列表', '列表是可变的……')
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]['title'], '知识点1')
        prompt = self._prompt()
        self.assertIn('第1章 列表', prompt)
        self.assertIn('列表是可变的', prompt)
        self.assertIn('提炼', prompt)

    def test_extract_from_source_material_when_text_empty(self):
        self.skill.extract('第2章 元组', '', '【素材：第一课 · 1.3 元组】\n元组不可变')
        prompt = self._prompt()
        self.assertIn('元组不可变', prompt)
        self.assertNotIn('没有现成教学素材', prompt)

    def test_autonomous_mode_without_any_material(self):
        self.skill.extract('第3章 装饰器', '', '')
        prompt = self._prompt()
        self.assertIn('没有现成教学素材', prompt)
        self.assertIn('第3章 装饰器', prompt)

    def test_garbage_payloads_return_empty(self):
        for garbage in ('not json', ['list', 'of', 'strings'],
                        {'points': 'nope'}, {'points': [42, None]},
                        {'points': [{'title': ''}]}):
            self.mock_call.return_value = garbage
            self.assertEqual(self.skill.extract('章', 'text'), [])

    def test_harness_failure_returns_empty(self):
        self.mock_call.side_effect = RuntimeError('boom')
        self.assertEqual(self.skill.extract('章', 'text'), [])

    def test_invalid_difficulty_normalized(self):
        self.mock_call.return_value = {'points': [
            {'title': 'x', 'difficulty': '超难'},
            {'title': 'y', 'difficulty': 'advanced'}]}
        points = self.skill.extract('章', 'text')
        self.assertEqual(points[0]['difficulty'], 'beginner')
        self.assertEqual(points[1]['difficulty'], 'advanced')

    def test_extra_points_capped(self):
        self.mock_call.return_value = {'points': [
            {'title': f'p{i}'} for i in range(20)]}
        points = self.skill.extract('章', 'text')
        self.assertEqual(len(points),
                         self.skill.params['max_points_per_chapter'])

"""Training knowledge-point integration tests: form binding, KP-driven
AI drafts and per-KP batch generation (plan step 11)."""

import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.learning.models import Chapter, Course, KnowledgePoint
from .models import Exercise


def _make_user(username, user_type='instructor'):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com',
        password='StrongPass123!', user_type=user_type)


def _make_course_kp(instructor, kp_title='列表推导式'):
    course = Course.objects.create(
        title='KP 课程', slug=f'kp-{kp_title[:2]}-{instructor.username}',
        instructor=instructor, difficulty_level='beginner', is_published=True)
    Chapter.objects.create(course=course, title='第1章', order=1)
    kp = KnowledgePoint.objects.create(course=course, title=kp_title,
                                       difficulty='intermediate')
    return course, kp


class ExerciseFormKPTests(TestCase):
    def setUp(self):
        self.instructor = _make_user('teacher')
        self.other = _make_user('other')
        self.course, self.kp = _make_course_kp(self.instructor)
        self.foreign_course, self.foreign_kp = _make_course_kp(self.other,
                                                               '别人的知识点')
        self.client.force_login(self.instructor)

    def _post(self, **overrides):
        data = dict(
            title='KP 练习', description='描述', difficulty='intermediate',
            points=10, starter_code='', solution_code='def f():\n    return 1',
            test_cases=json.dumps([{'input': 'f()', 'expected': 1}]),
        )
        data.update(overrides)
        return self.client.post(reverse('training:exercise-create'), data)

    def test_create_binds_kps(self):
        response = self._post(knowledge_points=[str(self.kp.id)])
        exercise = Exercise.objects.get(title='KP 练习')
        self.assertRedirects(response, reverse(
            'training:exercise-detail', args=[exercise.slug]))
        self.assertEqual(list(exercise.knowledge_points.all()), [self.kp])

    def test_foreign_kps_ignored_on_create(self):
        self._post(knowledge_points=[str(self.foreign_kp.id)])
        exercise = Exercise.objects.get(title='KP 练习')
        self.assertEqual(exercise.knowledge_points.count(), 0)

    def test_edit_binds_and_clears_kps(self):
        exercise = Exercise.objects.create(
            title='编辑我', slug='edit-me', description='x',
            difficulty='beginner', solution_code='def f():\n    return 1',
            test_cases=[{'input': 'f()', 'expected': 1}])
        url = reverse('training:exercise-edit', args=[exercise.id])
        data = {'title': '编辑我', 'description': 'x', 'difficulty': 'beginner',
                'points': 10, 'starter_code': '',
                'solution_code': 'def f():\n    return 1',
                'test_cases': json.dumps([{'input': 'f()', 'expected': 1}]),
                'knowledge_points': [str(self.kp.id)]}
        self.client.post(url, data)
        self.assertEqual(list(exercise.knowledge_points.all()), [self.kp])

        data['knowledge_points'] = []
        self.client.post(url, data)
        self.assertEqual(exercise.knowledge_points.count(), 0)

    def test_form_lists_own_kps_only(self):
        response = self.client.get(reverse('training:exercise-create'))
        self.assertContains(response, '列表推导式')
        self.assertNotContains(response, '别人的知识点')


class ExerciseAIDraftKPTests(TestCase):
    def setUp(self):
        self.instructor = _make_user('teacher')
        self.other = _make_user('other')
        self.course, self.kp = _make_course_kp(self.instructor)
        self.client.force_login(self.instructor)

    def _draft(self, **payload):
        data = dict(topic='', difficulty='beginner')
        data.update(payload)
        return self.client.post(
            reverse('training:exercise-ai-draft'),
            data=json.dumps(data), content_type='application/json')

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExerciseSkill')
    def test_kp_draft_uses_kp_topic_and_difficulty(self, skill_cls, _cfg):
        skill_cls.return_value.run.return_value = {
            'exercise': {'title': 'x', 'test_cases': []},
            'validated': True, 'validation_message': 'ok', 'attempts': 1}
        response = self._draft(knowledge_point_id=self.kp.id)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['knowledge_point_id'], self.kp.id)
        topic_arg = skill_cls.return_value.run.call_args.args[0]
        self.assertIn('列表推导式', topic_arg)
        self.assertEqual(skill_cls.return_value.run.call_args.args[1],
                         'intermediate')

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExerciseSkill')
    def test_foreign_kp_forbidden(self, skill_cls, _cfg):
        _, foreign_kp = _make_course_kp(self.other, '他人知识点')
        response = self._draft(knowledge_point_id=foreign_kp.id)
        self.assertEqual(response.status_code, 403)

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExerciseSkill')
    def test_unknown_kp_404(self, skill_cls, _cfg):
        response = self._draft(knowledge_point_id=9999)
        self.assertEqual(response.status_code, 404)

    def test_no_topic_and_no_kp_rejected(self):
        response = self._draft()
        self.assertEqual(response.status_code, 400)
        self.assertIn('主题不能为空', response.json()['error'])


class GenerateExercisesKPCommandTests(TestCase):
    def setUp(self):
        self.instructor = _make_user('teacher')
        self.course, self.kp1 = _make_course_kp(self.instructor, '列表')
        self.kp2 = KnowledgePoint.objects.create(
            course=self.course, title='元组', difficulty='beginner')

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExerciseSkill')
    def test_one_exercise_per_kp(self, skill_cls, _cfg):
        from django.core.management import call_command
        from io import StringIO
        skill_cls.return_value.run.return_value = {
            'exercise': {'title': 'x', 'test_cases': [
                {'input': 'f()', 'expected': 1}],
                'hints': []},
            'validated': True, 'validation_message': 'ok', 'attempts': 1}
        skill_cls.return_value.is_duplicate.return_value = False
        call_command('generate_exercises', topic='兜底主题',
                     course=self.course.slug, count=10,
                     creator=self.instructor.username, stdout=StringIO())
        exercises = list(self.course.exercises.all())
        self.assertEqual(len(exercises), 2)
        titles = skill_cls.return_value.run.call_args_list
        self.assertEqual([c.args[0] for c in titles], ['列表', '元组'])
        bound = set()
        for exercise in exercises:
            bound.update(exercise.knowledge_points.values_list('title',
                                                               flat=True))
        self.assertEqual(bound, {'列表', '元组'})

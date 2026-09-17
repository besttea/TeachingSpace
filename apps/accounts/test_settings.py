"""Web settings page tests: role-gated sections, persistence, and the
DB > env > defaults layering for rate limits / skill params / cost limit."""

import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import PlatformSetting, User
from apps.core.settings_db import (
    delete_platform_setting, get_platform_setting, set_platform_setting,
)


def _make_user(username, user_type='student', **extra):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com',
        password='StrongPass123!', user_type=user_type, **extra)


class SettingsPageRoleTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        PlatformSetting.objects.all().delete()

    def test_student_sees_personal_only(self):
        student = _make_user('student')
        self.client.force_login(student)
        response = self.client.get(reverse('accounts:settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '个人偏好')
        self.assertContains(response, '学习时长心跳')
        # section content (form fields), not labels — HTML comments carry
        # the section titles even when the section is not rendered
        self.assertNotContains(response, 'skill_exam_generation')
        self.assertNotContains(response, 'rate_limit_exercise_submit')

    def test_instructor_sees_ai_params_not_global(self):
        instructor = _make_user('teacher', 'instructor')
        self.client.force_login(instructor)
        response = self.client.get(reverse('accounts:settings'))
        self.assertContains(response, 'skill_exam_generation')
        self.assertContains(response, '默认章节数')
        self.assertNotContains(response, 'rate_limit_exercise_submit')
        self.assertNotContains(response, 'ai_cost_limit_daily')

    def test_admin_sees_everything(self):
        admin = _make_user('admin', 'admin', is_staff=True)
        self.client.force_login(admin)
        response = self.client.get(reverse('accounts:settings'))
        self.assertContains(response, 'skill_exam_generation')
        self.assertContains(response, 'rate_limit_exercise_submit')
        self.assertContains(response, 'ai_cost_limit_daily')

    def test_instructor_saves_skill_params(self):
        instructor = _make_user('teacher', 'instructor')
        self.client.force_login(instructor)
        response = self.client.post(reverse('accounts:settings'), {
            'default_difficulty': 'advanced',
            'default_chapter_count': '7',
            'default_exam_question_count': '15',
            'skill_exam_generation': '{"temperature": 0.6}',
            'skill_course_design': '',  # 留空 → 恢复默认
        })
        self.assertRedirects(response, reverse('accounts:settings'))
        instructor.refresh_from_db()
        self.assertEqual(instructor.preferences['default_difficulty'],
                         'advanced')
        self.assertEqual(instructor.preferences['default_chapter_count'], 7)
        stored = get_platform_setting('ai_skill_params:exam_generation')
        self.assertEqual(stored, {'temperature': 0.6})
        self.assertEqual(
            get_platform_setting('ai_skill_params:course_design', 'x'), {})

    def test_invalid_skill_json_rejected(self):
        instructor = _make_user('teacher', 'instructor')
        self.client.force_login(instructor)
        response = self.client.post(reverse('accounts:settings'), {
            'skill_exam_generation': 'not json{'})
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(
            get_platform_setting('ai_skill_params:exam_generation'))

    def test_admin_saves_rate_limits(self):
        admin = _make_user('admin', 'admin', is_staff=True)
        self.client.force_login(admin)
        self.client.post(reverse('accounts:settings'), {
            'rate_limit_exercise_submit': '100',
            'rate_window_exercise_submit': '600',
            'ai_cost_limit_daily': '12.5',
        })
        self.assertEqual(get_platform_setting('rate:exercise_submit'),
                         {'limit': 100, 'window_seconds': 600})
        self.assertEqual(get_platform_setting('ai_cost_limit_daily'), 12.5)

    def test_student_saves_heartbeat_preference(self):
        student = _make_user('student')
        self.client.force_login(student)
        self.client.post(reverse('accounts:settings'), {})
        student.refresh_from_db()
        self.assertFalse(student.preferences['heartbeat_enabled'])
        self.client.post(reverse('accounts:settings'),
                         {'heartbeat_enabled': 'on'})
        student.refresh_from_db()
        self.assertTrue(student.preferences['heartbeat_enabled'])


class SettingsLayeringTests(TestCase):
    """DB settings layer over code defaults / env / .env."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        PlatformSetting.objects.all().delete()

    def test_skill_params_db_layer_wins(self):
        from apps.ai_agents.skill_config import skill_params
        base = skill_params('exam_generation')
        self.assertNotEqual(base['temperature'], 0.9)
        set_platform_setting('ai_skill_params:exam_generation',
                             {'temperature': 0.9, 'max_questions': 5})
        overridden = skill_params('exam_generation')
        self.assertEqual(overridden['temperature'], 0.9)
        self.assertEqual(overridden['max_questions'], 5)
        # untouched knobs keep defaults
        self.assertEqual(overridden['dedup_threshold'],
                         base['dedup_threshold'])
        # cleanup returns to defaults (cache invalidation on delete)
        delete_platform_setting('ai_skill_params:exam_generation')
        restored = skill_params('exam_generation')
        self.assertEqual(restored['temperature'], base['temperature'])

    def test_rate_limit_db_override(self):
        from apps.core.rate_limit import rate_limit
        from django.http import JsonResponse

        captured = {}

        @rate_limit('test_setting_limit', limit=2, window_seconds=60)
        def fake_view(request):
            captured['called'] = captured.get('called', 0) + 1
            return JsonResponse({'ok': True})

        request = type('Req', (), {'user': type('U', (), {
            'is_authenticated': True, 'id': 777})()})()
        set_platform_setting('rate:test_setting_limit',
                             {'limit': 1, 'window_seconds': 60})
        first = fake_view(request)
        second = fake_view(request)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        body = json.loads(second.content)
        self.assertIn('最多 1 次', body['error'])

    def test_platform_setting_crud_and_cache(self):
        set_platform_setting('k', {'a': 1}, category='t', description='d')
        self.assertEqual(get_platform_setting('k'), {'a': 1})
        self.assertEqual(get_platform_setting('missing', 'fallback'),
                         'fallback')
        delete_platform_setting('k')
        self.assertIsNone(get_platform_setting('k'))

    def test_cost_limit_db_layer(self):
        from apps.ai_agents.models import AIGenerationHistory
        instructor = _make_user('teacher', 'instructor')
        self.client.force_login(instructor)
        AIGenerationHistory.objects.create(
            agent='x', model='m', success=True, input_tokens=1,
            output_tokens=1, estimated_cost_usd=5.0)
        set_platform_setting('ai_cost_limit_daily', 4.0)
        from apps.ai_agents.models import daily_cost_exceeded
        self.assertTrue(daily_cost_exceeded())
        set_platform_setting('ai_cost_limit_daily', 100.0)
        self.assertFalse(daily_cost_exceeded())

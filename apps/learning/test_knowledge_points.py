"""Knowledge-point endpoint tests: permissions, CRUD, duplicate handling
and the instructor-triggered AI extraction flow (plan step 5)."""

import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from .models import Chapter, Course, KnowledgePoint


def _make_user(username, user_type='instructor'):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com',
        password='StrongPass123!', user_type=user_type)


class KPEndpointSetup(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = _make_user('teacher')
        self.other_instructor = _make_user('teacher2')
        self.student = _make_user('student', 'student')
        self.course = Course.objects.create(
            title='知识点课程', slug='kp-course', instructor=self.instructor,
            difficulty_level='beginner')
        self.chapter = Chapter.objects.create(course=self.course,
                                              title='第1章', order=1)
        self.client.force_login(self.instructor)

    def _post(self, url_name, args, payload):
        return self.client.post(reverse(url_name, args=args),
                                data=json.dumps(payload),
                                content_type='application/json')


class KPPermissionTests(KPEndpointSetup):
    def test_student_forbidden_on_all_endpoints(self):
        self.client.force_login(self.student)
        kp = KnowledgePoint.objects.create(course=self.course, title='x')
        cases = [
            ('learning:course-kp-extract', [self.course.id]),
            ('learning:course-kp-add', [self.course.id]),
            ('learning:kp-update', [kp.id]),
            ('learning:kp-delete', [kp.id]),
        ]
        for name, args in cases:
            response = self._post(name, args, {})
            self.assertEqual(response.status_code, 403, name)
        status = self.client.get(reverse('learning:course-kp-status',
                                         args=[self.course.id]))
        self.assertEqual(status.status_code, 403)

    def test_other_instructor_forbidden(self):
        self.client.force_login(self.other_instructor)
        response = self._post('learning:course-kp-add', [self.course.id],
                              {'title': '越权'})
        self.assertEqual(response.status_code, 403)


class KPCRUDTests(KPEndpointSetup):
    def test_add_and_duplicate(self):
        response = self._post('learning:course-kp-add', [self.course.id], {
            'title': '列表推导式', 'description': '一句话',
            'difficulty': 'intermediate', 'chapter_id': self.chapter.id})
        self.assertEqual(response.status_code, 200)
        kp = KnowledgePoint.objects.get(course=self.course)
        self.assertEqual(kp.chapter, self.chapter)
        self.assertEqual(kp.difficulty, 'intermediate')
        self.assertEqual(kp.created_by, self.instructor)

        response = self._post('learning:course-kp-add', [self.course.id],
                              {'title': '列表推导式'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('已存在', response.json()['error'])

    def test_add_empty_title_rejected(self):
        response = self._post('learning:course-kp-add', [self.course.id],
                              {'title': '  '})
        self.assertEqual(response.status_code, 400)

    def test_add_invalid_difficulty_normalized(self):
        response = self._post('learning:course-kp-add', [self.course.id],
                              {'title': '元组', 'difficulty': '超难'})
        self.assertEqual(response.status_code, 200)
        kp = KnowledgePoint.objects.get(title='元组')
        self.assertEqual(kp.difficulty, 'beginner')

    def test_add_foreign_chapter_ignored(self):
        other_course = Course.objects.create(
            title='别人的课', slug='other-kp', instructor=self.other_instructor,
            difficulty_level='beginner')
        foreign = Chapter.objects.create(course=other_course, title='x',
                                         order=1)
        response = self._post('learning:course-kp-add', [self.course.id], {
            'title': '作用域', 'chapter_id': foreign.id})
        self.assertEqual(response.status_code, 200)
        kp = KnowledgePoint.objects.get(title='作用域')
        self.assertIsNone(kp.chapter)

    def test_update(self):
        kp = KnowledgePoint.objects.create(course=self.course, title='旧名')
        response = self._post('learning:kp-update', [kp.id], {
            'title': '新名', 'description': '更新', 'difficulty': 'advanced',
            'chapter_id': self.chapter.id})
        self.assertEqual(response.status_code, 200)
        kp.refresh_from_db()
        self.assertEqual(kp.title, '新名')
        self.assertEqual(kp.difficulty, 'advanced')
        self.assertEqual(kp.chapter, self.chapter)

    def test_update_to_duplicate_title_rejected(self):
        KnowledgePoint.objects.create(course=self.course, title='已存在')
        kp = KnowledgePoint.objects.create(course=self.course, title='另一个')
        response = self._post('learning:kp-update', [kp.id],
                              {'title': '已存在'})
        self.assertEqual(response.status_code, 400)

    def test_update_empty_title_rejected(self):
        kp = KnowledgePoint.objects.create(course=self.course, title='x')
        response = self._post('learning:kp-update', [kp.id], {'title': ''})
        self.assertEqual(response.status_code, 400)

    def test_delete(self):
        kp = KnowledgePoint.objects.create(course=self.course, title='删除我')
        response = self._post('learning:kp-delete', [kp.id], {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(KnowledgePoint.objects.filter(pk=kp.id).exists())


class KPExtractFlowTests(KPEndpointSetup):
    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.KnowledgeSkill')
    def test_eager_extraction_creates_points(self, skill_cls, _cfg):
        skill_cls.return_value.extract.return_value = [
            {'title': '变量', 'description': 'x', 'difficulty': 'beginner'}]
        response = self._post('learning:course-kp-extract', [self.course.id],
                              {})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertFalse(body['queued'])  # dev eager mode
        self.assertEqual(body['status']['status'], 'done')
        self.assertEqual(body['status']['points_created'], 1)
        self.assertEqual(self.course.knowledge_points.count(), 1)

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=False)
    def test_unconfigured_ai_rejected(self, _cfg):
        response = self._post('learning:course-kp-extract', [self.course.id],
                              {})
        self.assertEqual(response.status_code, 400)
        self.assertIn('AI 服务未配置', response.json()['error'])

    def test_status_endpoint(self):
        response = self.client.get(reverse('learning:course-kp-status',
                                           args=[self.course.id]))
        self.assertEqual(response.json()['status']['status'], 'none')
        KnowledgePoint.objects.create(course=self.course, title='已有')
        from django.core.cache import cache
        cache.set(f'kp_extract_status:{self.course.id}',
                  {'status': 'done', 'points_created': 1}, 3600)
        response = self.client.get(reverse('learning:course-kp-status',
                                           args=[self.course.id]))
        body = response.json()['status']
        self.assertEqual(body['status'], 'done')
        self.assertEqual(body['kp_count'], 1)

    def test_course_detail_shows_kp_section(self):
        KnowledgePoint.objects.create(course=self.course, title='列表推导式')
        response = self.client.get(reverse(
            'learning:instructor-course-manage', args=[self.course.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '知识点库')
        self.assertContains(response, '列表推导式')

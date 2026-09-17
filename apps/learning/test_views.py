"""View coverage for the learning app: course browsing/detail/enrollment,
lesson detail/edit, publishing, roster CSV, kernel endpoints, heartbeat and
completion tracking (OPTIMIZATION_PLAN 6.5 coverage gate)."""

import json
import unittest
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from .jupyter_kernel import HAS_JUPYTER
from .models import (
    Cell, Chapter, Course, Enrollment, Lesson, LessonProgress,
)


def _make_user(username, user_type='student'):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com',
        password='StrongPass123!', user_type=user_type)


def _make_course_lesson(instructor, **course_kwargs):
    defaults = dict(title='课程A', slug='course-a', instructor=instructor,
                    difficulty_level='beginner', is_published=True)
    defaults.update(course_kwargs)
    course = Course.objects.create(**defaults)
    chapter = Chapter.objects.create(course=course, title='第1章', order=1)
    lesson = Lesson.objects.create(chapter=chapter, title='单元1', order=1,
                                   status='published')
    Cell.objects.create(lesson=lesson, cell_type='text', order=0,
                        data={'markdown': '# 你好'})
    return course, lesson


class CourseBrowseTests(TestCase):
    def setUp(self):
        # course-list responses are cached (3.4) — isolate per test
        from django.core.cache import cache
        cache.clear()
        self.instructor = _make_user('teacher', 'instructor')
        self.student = _make_user('student')
        self.client.force_login(self.student)

    def test_list_filters_and_searches(self):
        _make_course_lesson(self.instructor, title='基础课', slug='base')
        _make_course_lesson(self.instructor, title='进阶课', slug='adv',
                            difficulty_level='advanced')
        url = reverse('learning:course-list')
        response = self.client.get(url, {'difficulty': 'advanced'})
        self.assertContains(response, '进阶课')
        self.assertNotContains(response, '基础课')

        response = self.client.get(url, {'search': '基础'})
        self.assertContains(response, '基础课')
        self.assertNotContains(response, '进阶课')

    def test_list_caches_and_serves_cache(self):
        # First hit fills the cache; second hit is served from it (3.4).
        _make_course_lesson(self.instructor)
        url = reverse('learning:course-list')
        first = self.client.get(url)
        self.assertEqual(first.status_code, 200)
        second = self.client.get(url)
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, '课程A')

    def test_detail_shows_progress_and_chapters(self):
        course, lesson = _make_course_lesson(self.instructor)
        enrollment = Enrollment.objects.create(student=self.student,
                                               course=course)
        LessonProgress.objects.create(enrollment=enrollment, lesson=lesson,
                                      is_completed=True)
        enrollment.calculate_progress()
        response = self.client.get(reverse('learning:course-detail',
                                           args=[course.slug]))
        context = response.context
        self.assertTrue(context['is_enrolled'])
        self.assertFalse(context['can_edit'])
        self.assertEqual(context['progress_percentage'], 100)
        self.assertEqual(len(context['chapters_data']), 1)
        self.assertEqual(context['chapters_data'][0]['lessons'][0]['cell_count'], 1)

    def test_detail_unpublished_visible_to_instructor_only(self):
        course, _ = _make_course_lesson(self.instructor, is_published=False,
                                        slug='draft-course')
        response = self.client.get(reverse('learning:course-detail',
                                           args=[course.slug]))
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.instructor)
        response = self.client.get(reverse('learning:course-detail',
                                           args=[course.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_edit'])

    def test_enroll_creates_then_reactivates(self):
        course, _ = _make_course_lesson(self.instructor)
        url = reverse('learning:course-enroll', args=[course.slug])
        response = self.client.post(url)
        self.assertRedirects(response, reverse('learning:course-detail',
                                               args=[course.slug]))
        enrollment = Enrollment.objects.get(student=self.student,
                                            course=course)
        self.assertTrue(enrollment.is_active)

        enrollment.is_active = False
        enrollment.save()
        self.client.post(url)
        enrollment.refresh_from_db()
        self.assertTrue(enrollment.is_active)
        self.assertEqual(Enrollment.objects.count(), 1)


class LessonViewTests(TestCase):
    def setUp(self):
        self.instructor = _make_user('teacher', 'instructor')
        self.student = _make_user('student')
        self.course, self.lesson = _make_course_lesson(self.instructor)
        self.client.force_login(self.student)

    def test_detail_creates_progress_for_enrolled(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        response = self.client.get(reverse('learning:lesson-detail',
                                           args=[self.lesson.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['progress'])
        self.assertFalse(response.context['can_edit'])

    def test_detail_draft_visible_to_instructor_only(self):
        self.lesson.status = 'draft'
        self.lesson.save()
        response = self.client.get(reverse('learning:lesson-detail',
                                           args=[self.lesson.id]))
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.instructor)
        response = self.client.get(reverse('learning:lesson-detail',
                                           args=[self.lesson.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_edit'])

    def test_edit_forbidden_for_student(self):
        response = self.client.get(reverse('learning:lesson-edit',
                                           args=[self.lesson.id]))
        self.assertEqual(response.status_code, 403)

    def test_edit_renders_cells_json_for_instructor(self):
        self.client.force_login(self.instructor)
        response = self.client.get(reverse('learning:lesson-edit',
                                           args=[self.lesson.id]))
        self.assertEqual(response.status_code, 200)
        cells = json.loads(response.context['cells_json'])
        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0]['cell_type'], 'text')


class InstructorPublishTests(TestCase):
    def setUp(self):
        self.instructor = _make_user('teacher', 'instructor')
        self.student = _make_user('student')
        self.course, self.lesson = _make_course_lesson(self.instructor)
        self.client.force_login(self.instructor)

    def test_publish_course_toggles(self):
        url = reverse('learning:instructor-course-publish',
                      args=[self.course.slug])
        response = self.client.post(url, {'action': 'unpublish'})
        self.assertFalse(response.json()['is_published'])
        self.course.refresh_from_db()
        self.assertFalse(self.course.is_published)

        response = self.client.post(url, {'action': 'publish'})
        self.assertTrue(response.json()['is_published'])
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_published)

    def test_publish_course_forbidden_for_student(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('learning:instructor-course-publish',
                    args=[self.course.slug]))
        self.assertEqual(response.status_code, 403)

    def test_publish_all_lessons(self):
        self.lesson.status = 'draft'
        self.lesson.save()
        Lesson.objects.create(chapter=self.lesson.chapter, title='单元2',
                              order=2, status='draft')
        response = self.client.post(
            reverse('learning:instructor-course-publish-all',
                    args=[self.course.slug]))
        self.assertEqual(response.json()['success'], True)
        self.assertEqual(Lesson.objects.filter(
            chapter__course=self.course, status='published').count(), 2)

    def test_roster_csv_export(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        response = self.client.get(
            reverse('learning:instructor-student-roster',
                    args=[self.course.slug]), {'export': 'csv'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        content = response.content.decode('utf-8-sig')
        self.assertIn('student', content)

    def test_roster_html_renders(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        response = self.client.get(reverse(
            'learning:instructor-student-roster', args=[self.course.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['roster']), 1)
        self.assertEqual(response.context['roster'][0]['student'],
                         self.student)


class ProgressEndpointTests(TestCase):
    def setUp(self):
        self.instructor = _make_user('teacher', 'instructor')
        self.student = _make_user('student')
        self.course, self.lesson = _make_course_lesson(self.instructor)
        self.client.force_login(self.student)

    def test_heartbeat_requires_enrollment(self):
        response = self.client.post(
            reverse('learning:lesson-heartbeat', args=[self.lesson.id]),
            data=json.dumps({'seconds': 30}),
            content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_heartbeat_accumulates_and_clamps(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        url = reverse('learning:lesson-heartbeat', args=[self.lesson.id])
        response = self.client.post(url, data=json.dumps({'seconds': 30}),
                                    content_type='application/json')
        self.assertEqual(response.json()['time_spent_seconds'], 30)
        # clamped to 300 per beat
        response = self.client.post(url, data=json.dumps({'seconds': 9999}),
                                    content_type='application/json')
        self.assertEqual(response.json()['time_spent_seconds'], 330)
        # malformed body → 0 increment
        response = self.client.post(url, data='not json',
                                    content_type='application/json')
        self.assertEqual(response.json()['time_spent_seconds'], 330)

    def test_mark_complete_updates_progress(self):
        enrollment = Enrollment.objects.create(student=self.student,
                                               course=self.course)
        response = self.client.post(
            reverse('learning:lesson-complete', args=[self.lesson.id]))
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['course_progress'], 100)
        progress = LessonProgress.objects.get(enrollment=enrollment,
                                              lesson=self.lesson)
        self.assertTrue(progress.is_completed)

    def test_mark_complete_unenrolled_404(self):
        response = self.client.post(
            reverse('learning:lesson-complete', args=[self.lesson.id]))
        self.assertEqual(response.status_code, 404)


class KernelEndpointTests(TestCase):
    def setUp(self):
        self.instructor = _make_user('teacher', 'instructor')
        self.student = _make_user('student')
        self.course, self.lesson = _make_course_lesson(self.instructor)
        self.client.force_login(self.student)

    def _execute(self, code='print(42)'):
        return self.client.post(
            reverse('learning:kernel-execute', args=[self.lesson.id]),
            data=json.dumps({'code': code}),
            content_type='application/json')

    def test_execute_unenrolled_forbidden(self):
        response = self._execute()
        self.assertEqual(response.status_code, 403)

    def test_execute_empty_code_rejected(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        response = self._execute('   ')
        self.assertEqual(response.status_code, 400)

    def test_execute_unknown_lesson_404(self):
        response = self.client.post(
            reverse('learning:kernel-execute', args=[9999]),
            data=json.dumps({'code': 'x'}),
            content_type='application/json')
        self.assertEqual(response.status_code, 404)

    @unittest.skipUnless(HAS_JUPYTER, 'jupyter_client/ipykernel not installed')
    def test_execute_runs_in_real_kernel(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        response = self._execute()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['success'])
        stream = ''.join(o['text'] for o in body['outputs']
                         if o['type'] == 'stream')
        self.assertIn('42', stream)

    def test_restart_unenrolled_forbidden(self):
        response = self.client.post(
            reverse('learning:kernel-restart', args=[self.lesson.id]))
        self.assertEqual(response.status_code, 403)

    @unittest.skipUnless(HAS_JUPYTER, 'jupyter_client/ipykernel not installed')
    def test_restart_instructor_ok(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:kernel-restart', args=[self.lesson.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])


class CellTypeConversionTests(TestCase):
    """Jupyter-style cell type conversion via update_cell (notebook polish)."""

    def setUp(self):
        self.instructor = _make_user('teacher', 'instructor')
        self.student = _make_user('student')
        self.course, self.lesson = _make_course_lesson(self.instructor)
        self.cell = Cell.objects.create(
            lesson=self.lesson, cell_type='code', order=1,
            data={'source': 'print(1)', 'output': '', 'execution_count': 0})
        self.client.force_login(self.instructor)

    def _update(self, payload):
        return self.client.post(
            reverse('learning:cell-update', args=[self.cell.id]),
            data=json.dumps(payload), content_type='application/json')

    def test_convert_code_to_text_resets_data(self):
        response = self._update({'cell_type': 'text',
                                 'change_description': '转换'})
        self.assertEqual(response.status_code, 200)
        self.cell.refresh_from_db()
        self.assertEqual(self.cell.cell_type, 'text')
        self.assertEqual(set(self.cell.data), {'markdown', 'rendered_html'})

    def test_convert_text_to_code_resets_data(self):
        self.cell.cell_type = 'text'
        self.cell.data = {'markdown': '旧内容'}
        self.cell.save()
        response = self._update({'cell_type': 'code'})
        self.assertEqual(response.status_code, 200)
        self.cell.refresh_from_db()
        self.assertEqual(self.cell.cell_type, 'code')
        self.assertIn('source', self.cell.data)

    def test_invalid_type_rejected(self):
        response = self._update({'cell_type': 'spreadsheet'})
        self.assertEqual(response.status_code, 400)
        self.cell.refresh_from_db()
        self.assertEqual(self.cell.cell_type, 'code')

    def test_snapshot_records_old_type(self):
        self._update({'cell_type': 'text'})
        version = self.cell.versions.latest('created_at')
        self.assertEqual(version.snapshot['cell_type'], 'code')

    def test_student_forbidden(self):
        self.client.force_login(self.student)
        response = self._update({'cell_type': 'text'})
        self.assertEqual(response.status_code, 403)


class CourseCreateChapterCountTests(TestCase):
    """The AI-assisted create flow must honor the form's chapter count."""

    def setUp(self):
        self.instructor = _make_user('teacher', 'instructor')
        self.client.force_login(self.instructor)

    def _create(self, **overrides):
        data = {'title': '新课程', 'description': '描述',
                'difficulty': 'beginner', 'ai_design': 'on',
                'chapter_count': '5'}
        data.update(overrides)
        return self.client.post(
            reverse('learning:instructor-course-create'), data)

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.learning.tasks.design_course_outline_task')
    def test_chapter_count_passed_to_task(self, task_mock, _cfg):
        response = self._create()
        course = Course.objects.get(title='新课程')
        self.assertRedirects(response, reverse(
            'learning:instructor-course-outline', args=[course.slug]))
        self.assertEqual(
            task_mock.delay.call_args.kwargs['chapter_count'], 5)

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.learning.tasks.design_course_outline_task')
    def test_invalid_count_defaults_to_three(self, task_mock, _cfg):
        self._create(chapter_count='abc')
        self.assertEqual(
            task_mock.delay.call_args.kwargs['chapter_count'], 3)

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.learning.tasks.design_course_outline_task')
    def test_count_clamped_to_ten(self, task_mock, _cfg):
        self._create(chapter_count='999')
        self.assertEqual(
            task_mock.delay.call_args.kwargs['chapter_count'], 10)

    def test_manual_flow_ignores_chapter_count(self):
        response = self._create(ai_design='')
        course = Course.objects.get(title='新课程')
        self.assertRedirects(response, reverse(
            'learning:instructor-course-manage', args=[course.slug]))
        self.assertEqual(course.chapters.count(), 0)

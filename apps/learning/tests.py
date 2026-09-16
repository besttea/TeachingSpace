"""Regression tests for P0-11 (cell reorder/create/delete unique-constraint
collisions) and P0-12 (execute_cell enrollment requirement)."""

import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from .models import Cell, Chapter, Course, Enrollment, Lesson, LessonProgress


class CellOrderingTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='Test Course', description='x', instructor=self.instructor)
        self.chapter = Chapter.objects.create(course=self.course, title='Ch1', order=0)
        self.lesson = Lesson.objects.create(
            chapter=self.chapter, title='L1', status='published', order=0)
        self.cells = [
            Cell.objects.create(lesson=self.lesson, cell_type='text',
                                order=i, data={'markdown': f'cell {i}'})
            for i in range(3)
        ]

    def test_reorder_swap_does_not_collide(self):
        """Swapping two adjacent cells must not hit the unique constraint."""
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:cells-reorder'),
            data=json.dumps({
                'lesson_id': self.lesson.id,
                'cell_orders': [
                    {'id': self.cells[0].id, 'order': 1},
                    {'id': self.cells[1].id, 'order': 0},
                    {'id': self.cells[2].id, 'order': 2},
                ],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        orders = dict(Cell.objects.filter(lesson=self.lesson).values_list('id', 'order'))
        self.assertEqual(orders[self.cells[0].id], 1)
        self.assertEqual(orders[self.cells[1].id], 0)
        self.assertEqual(orders[self.cells[2].id], 2)

    def test_reorder_rejects_partial_lists(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:cells-reorder'),
            data=json.dumps({
                'lesson_id': self.lesson.id,
                'cell_orders': [{'id': self.cells[0].id, 'order': 0}],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        # nothing changed
        orders = dict(Cell.objects.filter(lesson=self.lesson).values_list('id', 'order'))
        self.assertEqual(orders[self.cells[1].id], 1)

    def test_delete_cell_renumbers_without_collision(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:cell-delete', args=[self.cells[0].id]),
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        orders = sorted(
            Cell.objects.filter(lesson=self.lesson).values_list('order', flat=True))
        self.assertEqual(orders, [0, 1])

    def test_create_cell_insert_does_not_collide(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:cell-create'),
            data=json.dumps({
                'lesson_id': self.lesson.id,
                'cell_type': 'text',
                'order': 1,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        orders = sorted(
            Cell.objects.filter(lesson=self.lesson).values_list('order', flat=True))
        self.assertEqual(orders, [0, 1, 2, 3])

    def test_create_cell_rejects_unknown_type(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:cell-create'),
            data=json.dumps({'lesson_id': self.lesson.id, 'cell_type': 'evil', 'order': 0}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_restore_cell_version(self):
        """CellVersion snapshots can be restored (undo), and restore is undoable."""
        from .models import CellVersion

        cell = self.cells[0]
        # snapshot the original state
        original = CellVersion.objects.create(
            cell=cell, snapshot={'cell_type': 'text', 'data': {'markdown': 'original'}, 'order': 0},
            editor=self.instructor, change_description='v1')
        # change the cell
        cell.data = {'markdown': 'changed'}
        cell.save()

        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:cell-restore-version', args=[cell.id, original.id]),
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        cell.refresh_from_db()
        self.assertEqual(cell.data['markdown'], 'original')
        # the restore itself created a snapshot (undoable)
        self.assertTrue(CellVersion.objects.filter(
            cell=cell, change_description__startswith='Restore of version').exists())


class SlugNavigationAndProgressTests(TestCase):
    """P2-5 slug collisions, P2-6 dead template refs, P2-7 completed_at."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher3', email='t3@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student3', email='s3@example.com',
            password='StrongPass123!', user_type='student')

    def test_chinese_titles_get_unique_slugs(self):
        c1 = Course.objects.create(title='中文课程', description='x', instructor=self.instructor)
        c2 = Course.objects.create(title='中文课程', description='x', instructor=self.instructor)
        self.assertTrue(c1.slug and c2.slug)
        self.assertNotEqual(c1.slug, c2.slug)

    def test_lesson_prev_next_navigation(self):
        course = Course.objects.create(title='Nav', description='x', instructor=self.instructor)
        chapter = Chapter.objects.create(course=course, title='Ch', order=0)
        lessons = [
            Lesson.objects.create(chapter=chapter, title=f'L{i}', status='published', order=i)
            for i in range(3)
        ]
        self.assertIsNone(lessons[0].get_previous())
        self.assertEqual(lessons[0].get_next(), lessons[1])
        self.assertEqual(lessons[1].get_previous(), lessons[0])
        self.assertEqual(lessons[1].get_next(), lessons[2])
        self.assertIsNone(lessons[2].get_next())

    def test_completion_percentage(self):
        course = Course.objects.create(title='Pct', description='x', instructor=self.instructor)
        chapter = Chapter.objects.create(course=course, title='Ch', order=0)
        lesson = Lesson.objects.create(chapter=chapter, title='L', status='published', order=0)
        Cell.objects.create(lesson=lesson, cell_type='code', order=0, data={'source': 'x'})
        enrollment = Enrollment.objects.create(student=self.student, course=course)
        progress = LessonProgress.objects.create(enrollment=enrollment, lesson=lesson)
        self.assertEqual(progress.completion_percentage, 0)
        progress.mark_complete()
        self.assertEqual(progress.completion_percentage, 100)

    def test_enrollment_completed_at_set_on_100_percent(self):
        course = Course.objects.create(title='Done', description='x', instructor=self.instructor)
        chapter = Chapter.objects.create(course=course, title='Ch', order=0)
        lesson = Lesson.objects.create(chapter=chapter, title='L', status='published', order=0)
        enrollment = Enrollment.objects.create(student=self.student, course=course)
        progress = LessonProgress.objects.create(enrollment=enrollment, lesson=lesson)
        progress.mark_complete()
        enrollment.refresh_from_db()
        self.assertIsNotNone(enrollment.completed_at)
        self.assertEqual(enrollment.progress_percentage, 100)


class ExecuteCellPermissionTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher2', email='t2@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student2', email='s2@example.com',
            password='StrongPass123!', user_type='student')
        self.course = Course.objects.create(
            title='Test Course 2', description='x', instructor=self.instructor,
            is_published=True)
        self.chapter = Chapter.objects.create(course=self.course, title='Ch1', order=0)
        self.lesson = Lesson.objects.create(
            chapter=self.chapter, title='L1', status='published', order=0)
        self.code_cell = Cell.objects.create(
            lesson=self.lesson, cell_type='code', order=0,
            data={'source': 'print("hi")'})

    def test_unenrolled_student_cannot_execute(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('learning:cell-execute', args=[self.code_cell.id]))
        self.assertEqual(response.status_code, 403)

    def test_instructor_can_execute(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:cell-execute', args=[self.code_cell.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('hi', response.json()['output'])


class InstructorConsoleTests(TestCase):
    """Instructor console: course/chapter/lesson creation, publish, roster."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            username='console_teacher', email='ct@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='console_student', email='cs@example.com',
            password='StrongPass123!', user_type='student')

    def test_student_cannot_access_instructor_dashboard(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('learning:instructor-dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_instructor_dashboard_lists_own_courses(self):
        Course.objects.create(
            title='我的课程', description='x', instructor=self.instructor)
        self.client.force_login(self.instructor)
        response = self.client.get(reverse('learning:instructor-dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '我的课程')
        self.assertContains(response, '新建课程')

    def test_course_create_flow(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:instructor-course-create'),
            {'title': '新课程', 'description': '简介', 'difficulty': 'beginner'})
        self.assertEqual(response.status_code, 302)
        course = Course.objects.get(title='新课程')
        self.assertFalse(course.is_published)  # created as draft
        self.assertEqual(course.instructor, self.instructor)

    def test_chapter_and_lesson_create_flow(self):
        course = Course.objects.create(
            title='C', description='x', instructor=self.instructor)
        self.client.force_login(self.instructor)

        r = self.client.post(
            reverse('learning:instructor-chapter-create', args=[course.slug]),
            {'title': '第1章', 'description': ''})
        self.assertEqual(r.status_code, 302)
        chapter = Chapter.objects.get(course=course)

        r = self.client.post(
            reverse('learning:instructor-lesson-create', args=[course.slug]),
            {'title': '1.1 入门', 'chapter_id': chapter.id, 'description': ''})
        self.assertEqual(r.status_code, 302)
        lesson = Lesson.objects.get(chapter=chapter, title='1.1 入门')
        self.assertEqual(lesson.status, 'draft')
        # creating a lesson jumps straight into the notebook editor
        self.assertIn('/edit/', r['Location'])

    def test_lesson_publish_toggle(self):
        course = Course.objects.create(
            title='C2', description='x', instructor=self.instructor)
        chapter = Chapter.objects.create(course=course, title='Ch', order=0)
        lesson = Lesson.objects.create(
            chapter=chapter, title='L', status='draft', order=0)
        self.client.force_login(self.instructor)

        r = self.client.post(
            reverse('learning:lesson-publish', args=[lesson.pk]),
            data=json.dumps({'action': 'publish'}),
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, 'published')

    def test_student_roster_shows_progress(self):
        course = Course.objects.create(
            title='C3', description='x', instructor=self.instructor)
        chapter = Chapter.objects.create(course=course, title='Ch', order=0)
        lesson = Lesson.objects.create(
            chapter=chapter, title='L', status='published', order=0)
        enrollment = Enrollment.objects.create(student=self.student, course=course)
        LessonProgress.objects.create(enrollment=enrollment, lesson=lesson)

        self.client.force_login(self.instructor)
        response = self.client.get(
            reverse('learning:instructor-student-roster', args=[course.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'console_student')


class AICourseDesignFlowTests(TestCase):
    """AI-assisted course design: create-with-outline + per-lesson generation."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            username='ai_teacher', email='at@example.com',
            password='StrongPass123!', user_type='instructor')

    def _post_create(self, **extra):
        self.client.force_login(self.instructor)
        data = {
            'title': 'AI 课程',
            'description': 'x',
            'difficulty': 'beginner',
        }
        data.update(extra)
        return self.client.post(
            reverse('learning:instructor-course-create'), data)

    @override_settings(
        AI_PROVIDERS={
            'anthropic': {'api_key': '', 'base_url': '', 'default_model': 'x'},
        },
        AI_PROVIDER='anthropic',
    )
    def test_ai_design_without_key_falls_back_to_manual(self):
        response = self._post_create(ai_design='on', chapter_count='2')
        self.assertEqual(response.status_code, 302)
        course = Course.objects.get(title='AI 课程')
        self.assertEqual(course.chapters.count(), 0)  # no outline generated

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.CourseSkill')
    def test_ai_design_creates_outline(self, skill_cls, _configured):
        skill = skill_cls.return_value
        skill.run.return_value = {
            'chapters': [
                {'title': '第1章 入门', 'description': 'd1',
                 'lessons': [
                     {'title': '1.1 变量', 'description': 'l1'},
                     {'title': '1.2 类型', 'description': 'l2'},
                 ]},
            ]
        }
        response = self._post_create(
            ai_design='on', chapter_count='2', use_classlib='off')
        self.assertEqual(response.status_code, 302)
        course = Course.objects.get(title='AI 课程')
        self.assertEqual(course.chapters.count(), 1)
        self.assertEqual(course.lessons_count if hasattr(course, 'lessons_count') else
                         Lesson.objects.filter(chapter__course=course).count(), 2)
        # redirects to the outline review page
        self.assertIn('/outline/', response['Location'])

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.learning_agent.LearningAgent')
    def test_lesson_ai_generate_creates_cells(self, agent_cls, _configured):
        agent = agent_cls.return_value
        agent.generate_lesson_content.return_value = {
            'cells': [
                {'type': 'text', 'content': '# 介绍'},
                {'type': 'code', 'content': 'print("hi")'},
            ]
        }
        course = Course.objects.create(
            title='G', description='x', instructor=self.instructor)
        chapter = Chapter.objects.create(course=course, title='Ch', order=0)
        lesson = Lesson.objects.create(
            chapter=chapter, title='L', status='draft', order=0)

        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:lesson-ai-generate', args=[lesson.pk]),
            data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['cell_count'], 2)
        self.assertEqual(lesson.cells.count(), 2)
        # regeneration is idempotent (replaces cells)
        response = self.client.post(
            reverse('learning:lesson-ai-generate', args=[lesson.pk]),
            data=json.dumps({}), content_type='application/json')
        self.assertEqual(lesson.cells.count(), 2)

    def test_student_cannot_generate(self):
        student = User.objects.create_user(
            username='ai_student', email='as@example.com',
            password='StrongPass123!', user_type='student')
        course = Course.objects.create(
            title='G2', description='x', instructor=self.instructor)
        chapter = Chapter.objects.create(course=course, title='Ch', order=0)
        lesson = Lesson.objects.create(
            chapter=chapter, title='L', status='draft', order=0)
        self.client.force_login(student)
        response = self.client.post(
            reverse('learning:lesson-ai-generate', args=[lesson.pk]),
            data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.course_design_agent.CourseDesignAgent')
    def test_chapter_ai_plan_creates_lessons(self, agent_cls, _configured):
        agent = agent_cls.return_value
        agent.design_chapter_lessons.return_value = {
            'lessons': [
                {'title': '2.1 条件', 'description': 'd'},
                {'title': '2.2 循环', 'description': 'd'},
            ]
        }
        course = Course.objects.create(
            title='G3', description='x', instructor=self.instructor)
        chapter = Chapter.objects.create(course=course, title='第2章', order=0)

        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:chapter-ai-plan', args=[chapter.pk]),
            data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['lessons']), 2)
        self.assertEqual(chapter.lessons.count(), 2)
        self.assertEqual(chapter.lessons.first().status, 'draft')

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.course_design_agent.CourseDesignAgent')
    def test_chapter_ai_plan_denied_for_non_instructor(self, agent_cls, _configured):
        student = User.objects.create_user(
            username='ai_student2', email='as2@example.com',
            password='StrongPass123!', user_type='student')
        course = Course.objects.create(
            title='G4', description='x', instructor=self.instructor)
        chapter = Chapter.objects.create(course=course, title='Ch', order=0)
        self.client.force_login(student)
        response = self.client.post(
            reverse('learning:chapter-ai-plan', args=[chapter.pk]),
            data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(agent_cls.called)




class CellVersionListingTests(TestCase):
    """T11: version history listing endpoint (UI backend)."""

    def setUp(self):
        from .models import CellVersion

        self.instructor = User.objects.create_user(
            username='versions_teacher', email='vt@example.com',
            password='StrongPass123!', user_type='instructor')
        course = Course.objects.create(
            title='V', description='x', instructor=self.instructor)
        chapter = Chapter.objects.create(course=course, title='Ch', order=0)
        lesson = Lesson.objects.create(
            chapter=chapter, title='L', status='published', order=0)
        self.cell = Cell.objects.create(
            lesson=lesson, cell_type='text', order=0, data={'markdown': 'x'})
        CellVersion.objects.create(
            cell=self.cell,
            snapshot={'data': {'markdown': 'v1'}, 'order': 0, 'cell_type': 'text'},
            editor=self.instructor, change_description='v1')

    def test_listing_works_for_instructor(self):
        self.client.force_login(self.instructor)
        response = self.client.get(
            reverse('learning:cell-versions', args=[self.cell.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['versions']), 1)
        self.assertEqual(data['versions'][0]['change_description'], 'v1')

    def test_listing_forbidden_for_student(self):
        student = User.objects.create_user(
            username='versions_student', email='vs@example.com',
            password='StrongPass123!', user_type='student')
        self.client.force_login(student)
        response = self.client.get(
            reverse('learning:cell-versions', args=[self.cell.id]))
        self.assertEqual(response.status_code, 403)


class LessonHeartbeatTests(TestCase):
    """T10: study time accumulation endpoint."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            username='hb_teacher', email='hbt@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='hb_student', email='hbs@example.com',
            password='StrongPass123!', user_type='student')
        self.course = Course.objects.create(
            title='HB', description='x', instructor=self.instructor, is_published=True)
        self.chapter = Chapter.objects.create(course=self.course, title='Ch', order=0)
        self.lesson = Lesson.objects.create(
            chapter=self.chapter, title='L', status='published', order=0)
        self.enrollment = Enrollment.objects.create(student=self.student, course=self.course)

    def test_heartbeat_accumulates(self):
        self.client.force_login(self.student)
        url = reverse('learning:lesson-heartbeat', args=[self.lesson.id])
        for _ in range(3):
            response = self.client.post(
                url, data=json.dumps({'seconds': 60}), content_type='application/json')
            self.assertEqual(response.status_code, 200)
        progress = LessonProgress.objects.get(
            enrollment=self.enrollment, lesson=self.lesson)
        self.assertEqual(progress.time_spent_seconds, 180)

    def test_heartbeat_requires_enrollment(self):
        outsider = User.objects.create_user(
            username='hb_outsider', email='hbo@example.com',
            password='StrongPass123!', user_type='student')
        self.client.force_login(outsider)
        response = self.client.post(
            reverse('learning:lesson-heartbeat', args=[self.lesson.id]),
            data=json.dumps({'seconds': 60}), content_type='application/json')
        self.assertEqual(response.status_code, 403)


class LessonGenerateStatusTests(TestCase):
    """Async generation status polling (eager mode writes cache status)."""

    def setUp(self):
        from unittest import mock as _mock
        self.instructor = User.objects.create_user(
            username='genstatus_teacher', email='gst@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='GS', description='x', instructor=self.instructor)
        self.chapter = Chapter.objects.create(course=self.course, title='Ch', order=0)
        self.lesson = Lesson.objects.create(
            chapter=self.chapter, title='L', status='draft', order=0)

        patcher = _mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_agent = _mock.patch(
            'apps.ai_agents.learning_agent.LearningAgent.generate_lesson_content',
            return_value={'cells': [{'type': 'text', 'content': '# x'}]})
        self.mock_agent.start()
        self.addCleanup(self.mock_agent.stop)

        from django.core.cache import cache
        cache.clear()

    def test_status_none_before_generation(self):
        self.client.force_login(self.instructor)
        response = self.client.get(
            reverse('learning:lesson-generate-status', args=[self.lesson.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status']['status'], 'none')

    def test_eager_generation_publishes_done(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:lesson-ai-generate', args=[self.lesson.id]),
            data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['success'])

        status_resp = self.client.get(
            reverse('learning:lesson-generate-status', args=[self.lesson.id]))
        status = status_resp.json()['status']
        self.assertEqual(status['status'], 'done')
        self.assertGreaterEqual(status['cell_count'], 1)


class CourseListCacheTests(TestCase):
    """3.4: content-versioned course list caching with invalidation."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = User.objects.create_user(
            username='cache_teacher', email='cat@example.com',
            password='StrongPass123!', user_type='instructor')

    def _course(self, title):
        return Course.objects.create(
            title=title, description='x', instructor=self.instructor,
            is_published=True)

    def test_cache_serves_and_invalidates(self):
        from apps.core.cache_utils import bump_content_version
        from django.core.cache import cache

        self._course('缓存课程甲')
        first = self.client.get(reverse('learning:course-list'))
        self.assertEqual(first.status_code, 200)
        # cached now — adding a course WITHOUT bump keeps serving the old page
        self._course('缓存课程乙')
        second = self.client.get(reverse('learning:course-list'))
        self.assertNotContains(second, '缓存课程乙')

        # bump → fresh render includes the new course
        bump_content_version()
        third = self.client.get(reverse('learning:course-list'))
        self.assertContains(third, '缓存课程乙')
        cache.clear()

    def test_search_bypasses_cache(self):
        self._course('缓存课程甲')
        self.client.get(reverse('learning:course-list'))  # populate cache
        response = self.client.get(reverse('learning:course-list') + '?search=甲')
        self.assertContains(response, '缓存课程甲')




class RosterCsvExportTests(TestCase):
    """Roster CSV export (Excel-friendly UTF-8 BOM)."""

    def test_csv_export(self):
        instructor = User.objects.create_user(
            username='csv_teacher', email='csvt@example.com',
            password='StrongPass123!', user_type='instructor')
        student = User.objects.create_user(
            username='csv_student', email='csvs@example.com',
            password='StrongPass123!', user_type='student')
        course = Course.objects.create(
            title='CSV', description='x', instructor=instructor)
        Enrollment.objects.create(student=student, course=course)

        self.client.force_login(instructor)
        response = self.client.get(
            reverse('learning:instructor-student-roster',
                    args=[course.slug]) + '?export=csv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment', response['Content-Disposition'])
        content = response.content.decode('utf-8-sig')
        self.assertIn('csv_student', content)
        self.assertIn('用户名', content)


class CourseDesignStatusTests(TestCase):
    """Async course-outline design status endpoint (eager task writes cache)."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = User.objects.create_user(
            username='design_teacher', email='det@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='DS', description='x', instructor=self.instructor)

    def test_status_none_initially(self):
        self.client.force_login(self.instructor)
        response = self.client.get(
            reverse('learning:course-design-status', args=[self.course.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status']['status'], 'none')

    def test_eager_design_publishes_done(self):
        from unittest import mock as _mock
        with _mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True), \
             _mock.patch('apps.ai_agents.skills.CourseSkill.run', return_value={
                 'chapters': [{'title': '第1章', 'description': 'd',
                               'lessons': [{'title': '1.1 入门', 'description': 'l'}]}],
                 'lesson_count': 1}):
            self.client.force_login(self.instructor)
            response = self.client.post(
                reverse('learning:instructor-course-create'),
                {'title': 'DS2', 'description': 'x', 'difficulty': 'beginner',
                 'ai_design': 'on', 'chapter_count': '1', 'use_classlib': 'off'})
            self.assertEqual(response.status_code, 302)
        course2 = Course.objects.get(title='DS2')
        self.assertEqual(course2.chapters.count(), 1)

        self.client.force_login(self.instructor)
        status_resp = self.client.get(
            reverse('learning:course-design-status', args=[course2.id]))
        status = status_resp.json()['status']
        self.assertEqual(status['status'], 'done')
        self.assertEqual(status['chapter_count'], 1)


class PublishAllTests(TestCase):
    """D: publish every lesson of a course at once."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            username='puball_teacher', email='pat@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='PA', description='x', instructor=self.instructor)
        self.chapter = Chapter.objects.create(course=self.course, title='Ch', order=0)
        self.lessons = [
            Lesson.objects.create(chapter=self.chapter, title=f'L{i}',
                                 status='draft', order=i)
            for i in range(3)
        ]

    def test_publish_all(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('learning:instructor-course-publish-all', args=[self.course.slug]),
            data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('3', response.json()['message'])
        self.assertEqual(
            Lesson.objects.filter(chapter__course=self.course, status='published').count(), 3)

    def test_student_forbidden(self):
        student = User.objects.create_user(
            username='puball_student', email='pas@example.com',
            password='StrongPass123!', user_type='student')
        self.client.force_login(student)
        response = self.client.post(
            reverse('learning:instructor-course-publish-all', args=[self.course.slug]),
            data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 403)

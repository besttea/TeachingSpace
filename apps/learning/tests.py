"""Regression tests for P0-11 (cell reorder/create/delete unique-constraint
collisions) and P0-12 (execute_cell enrollment requirement)."""

import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StudentProfile, User
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

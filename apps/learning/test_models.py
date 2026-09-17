"""Model-layer misc coverage: __str__/save hooks, progress properties and
atomic cell-execution tracking (OPTIMIZATION_PLAN 6.5 coverage gate)."""

from django.test import TestCase

from apps.accounts.models import User
from .models import (
    Cell, CellVersion, Chapter, Course, Enrollment, Lesson,
    LessonProgress, Video,
)


class ModelMiscTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.course = Course.objects.create(
            title='模型课程', slug='model-course', instructor=self.instructor,
            difficulty_level='beginner')
        self.chapter = Chapter.objects.create(
            course=self.course, title='第1章', order=1)
        self.lesson = Lesson.objects.create(
            chapter=self.chapter, title='单元1', order=1, status='published')

    def test_str_representations(self):
        self.assertEqual(str(self.course), '模型课程')
        self.assertEqual(str(self.chapter), '模型课程 - 第1章')
        self.assertEqual(str(self.lesson), '单元1')
        cell = Cell.objects.create(lesson=self.lesson, cell_type='text',
                                   order=0, data={'markdown': 'x'})
        self.assertIn('text cell', str(cell))
        version = CellVersion.objects.create(
            cell=cell, snapshot={'data': {'markdown': '旧'}},
            editor=self.instructor, change_description='测试')
        self.assertIn('Version of', str(version))
        video = Video.objects.create(title='教学视频')
        self.assertEqual(str(video), '教学视频')

    def test_enrollment_str_and_completed_count(self):
        enrollment = Enrollment.objects.create(student=self.student,
                                               course=self.course)
        self.assertIn('student', str(enrollment))
        self.assertEqual(enrollment.completed_lessons_count, 0)
        LessonProgress.objects.create(enrollment=enrollment, lesson=self.lesson,
                                      is_completed=True)
        self.assertEqual(enrollment.completed_lessons_count, 1)

    def test_calculate_progress_zero_lessons(self):
        enrollment = Enrollment.objects.create(student=self.student,
                                               course=self.course)
        self.assertEqual(enrollment.calculate_progress(), 0.0)

    def test_calculate_progress_sets_and_clears_completed_at(self):
        enrollment = Enrollment.objects.create(student=self.student,
                                               course=self.course)
        LessonProgress.objects.create(enrollment=enrollment, lesson=self.lesson,
                                      is_completed=True)
        enrollment.calculate_progress()
        self.assertEqual(enrollment.progress_percentage, 100)
        self.assertIsNotNone(enrollment.completed_at)

        # a new lesson appears → progress drops below 100 → completed_at cleared
        Lesson.objects.create(chapter=self.chapter, title='单元2', order=2,
                              status='published')
        enrollment.calculate_progress()
        self.assertEqual(enrollment.progress_percentage, 50)
        self.assertIsNone(enrollment.completed_at)

    def test_lesson_progress_str_and_code_percentage(self):
        enrollment = Enrollment.objects.create(student=self.student,
                                               course=self.course)
        progress = LessonProgress.objects.create(
            enrollment=enrollment, lesson=self.lesson)
        self.assertIn('student', str(progress))

        # no code cells → 0
        self.assertEqual(progress.completion_percentage, 0)
        code_cell = Cell.objects.create(lesson=self.lesson, cell_type='code',
                                        order=1, data={'source': 'x'})
        progress.track_cell_execution(code_cell.id)
        progress.refresh_from_db()  # track_cell_execution re-selects the row
        self.assertEqual(progress.completion_percentage, 100)

    def test_track_cell_execution_deduplicates(self):
        enrollment = Enrollment.objects.create(student=self.student,
                                               course=self.course)
        progress = LessonProgress.objects.create(
            enrollment=enrollment, lesson=self.lesson)
        code_cell = Cell.objects.create(lesson=self.lesson, cell_type='code',
                                        order=1, data={'source': 'x'})
        progress.track_cell_execution(code_cell.id)
        progress.track_cell_execution(code_cell.id)  # duplicate → no-op
        progress.refresh_from_db()
        self.assertEqual(progress.cells_executed, 1)
        self.assertEqual(progress.code_cells_run, [code_cell.id])

    def test_mark_complete(self):
        enrollment = Enrollment.objects.create(student=self.student,
                                               course=self.course)
        progress = LessonProgress.objects.create(
            enrollment=enrollment, lesson=self.lesson)
        progress.mark_complete()
        self.assertTrue(progress.is_completed)
        self.assertIsNotNone(progress.completed_at)

    def test_add_time(self):
        enrollment = Enrollment.objects.create(student=self.student,
                                               course=self.course)
        progress = LessonProgress.objects.create(
            enrollment=enrollment, lesson=self.lesson)
        progress.add_time(30)
        progress.refresh_from_db()
        self.assertEqual(progress.time_spent_seconds, 30)

    def test_course_slug_fallback_for_chinese_title(self):
        course = Course.objects.create(title='中文课程', instructor=self.instructor,
                                       difficulty_level='beginner')
        self.assertTrue(course.slug)  # fallback slug assigned
        self.assertNotEqual(course.slug, '')

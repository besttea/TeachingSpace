"""Model-layer misc coverage: __str__/save hooks, progress properties and
atomic cell-execution tracking (OPTIMIZATION_PLAN 6.5 coverage gate)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import User
from .models import (
    Cell, CellVersion, Chapter, Course, Enrollment, KnowledgePoint, Lesson,
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


class KnowledgePointModelTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='知识点课程', slug='kp-course', instructor=self.instructor,
            difficulty_level='beginner')
        self.chapter = Chapter.objects.create(course=self.course,
                                              title='第1章', order=1)

    def _make(self, title='列表推导式', **kwargs):
        defaults = dict(course=self.course, chapter=self.chapter, title=title)
        defaults.update(kwargs)
        return KnowledgePoint.objects.create(**defaults)

    def test_duplicate_title_in_course_raises(self):
        self._make()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._make()

    def test_same_title_in_different_course_allowed(self):
        self._make()
        other_course = Course.objects.create(
            title='另一门课', slug='other-course', instructor=self.instructor,
            difficulty_level='beginner')
        kp = self._make(course=other_course)
        self.assertEqual(kp.title, '列表推导式')

    def test_course_delete_cascades(self):
        kp = self._make()
        self.course.delete()
        self.assertFalse(KnowledgePoint.objects.filter(pk=kp.id).exists())

    def test_chapter_delete_nulls_chapter(self):
        kp = self._make()
        self.chapter.delete()
        kp.refresh_from_db()
        self.assertIsNone(kp.chapter)
        self.assertEqual(kp.course, self.course)

    def test_default_ordering(self):
        second = self._make('变量作用域', order=2)
        first = self._make('print 函数', order=1)
        self.assertEqual(list(KnowledgePoint.objects.values_list('id', flat=True)),
                         [first.id, second.id])

    def test_str_and_reverse_relation(self):
        kp = self._make()
        self.assertEqual(str(kp), '知识点课程 - 列表推导式')
        self.assertIn(kp, list(self.course.knowledge_points.all()))

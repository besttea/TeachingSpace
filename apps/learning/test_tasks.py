"""Celery task tests for the learning app: early returns, success status
publishing and eager-mode failure handling (OPTIMIZATION_PLAN 2.3).

Tasks are invoked through their callable (eager dispatch) so ``self`` is
bound and ``request.is_eager`` behaves like the dev/prod default.
"""

from unittest import mock

from django.test import TestCase

from apps.accounts.models import User
from .models import Chapter, Course, Lesson
from .tasks import (
    course_design_status, design_course_outline_task,
    generate_lesson_cells_task, lesson_gen_status,
)


def _make_lesson(instructor):
    course = Course.objects.create(
        title='任务测试课程', slug='task-test', instructor=instructor,
        difficulty_level='beginner')
    chapter = Chapter.objects.create(course=course, title='第1章', order=1)
    return Lesson.objects.create(chapter=chapter, title='单元1', order=1)


class TaskEarlyReturnTests(TestCase):
    """Tasks on missing rows must be no-ops (async races are safe)."""

    def test_outline_task_missing_course(self):
        from django.core.cache import cache
        cache.clear()
        result = design_course_outline_task.delay(9999)
        self.assertIsNone(result.result)
        self.assertEqual(course_design_status(9999), {'status': 'none'})

    def test_lesson_task_missing_lesson(self):
        from django.core.cache import cache
        cache.clear()
        result = generate_lesson_cells_task.delay(9999)
        self.assertIsNone(result.result)
        self.assertEqual(lesson_gen_status(9999), {'status': 'none'})


class LessonGenTaskTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.lesson = _make_lesson(self.instructor)

    @mock.patch('apps.chat.notebook_tools.find_related_sections', return_value=[])
    @mock.patch('apps.ai_agents.learning_agent.LearningAgent')
    def test_success_publishes_done_status(self, agent_cls, _find):
        agent_cls.return_value.generate_lesson_content.return_value = {
            'cells': [
                {'type': 'text', 'content': '# 标题'},
                {'type': 'code', 'content': 'print(1)'},
            ]
        }
        generate_lesson_cells_task.delay(self.lesson.id)
        status = lesson_gen_status(self.lesson.id)
        self.assertEqual(status['status'], 'done')
        self.assertEqual(status['cell_count'], 2)
        self.assertEqual(self.lesson.cells.count(), 2)
        cell_types = sorted(self.lesson.cells.values_list('cell_type', flat=True))
        self.assertEqual(cell_types, ['code', 'text'])

    @mock.patch('apps.chat.notebook_tools.find_related_sections', return_value=[])
    @mock.patch('apps.ai_agents.learning_agent.LearningAgent')
    def test_failure_publishes_error_status(self, agent_cls, _find):
        agent_cls.return_value.generate_lesson_content.side_effect = RuntimeError('boom')
        generate_lesson_cells_task.delay(self.lesson.id)
        status = lesson_gen_status(self.lesson.id)
        self.assertEqual(status['status'], 'error')
        self.assertIn('boom', status['error'])
        self.assertEqual(self.lesson.cells.count(), 0)


class CourseDesignTaskTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='大纲任务课程', slug='outline-task', instructor=self.instructor,
            difficulty_level='beginner')

    @mock.patch('apps.chat.notebook_tools.find_related_sections', return_value=[])
    @mock.patch('apps.ai_agents.skills.CourseSkill')
    def test_success_creates_chapters_and_lessons(self, skill_cls, _find):
        skill_cls.return_value.run.return_value = {
            'chapters': [
                {'title': '第1章 基础',
                 'lessons': [{'title': '单元一'}, {'title': '单元二'}]},
                {'title': '第2章 进阶',
                 'lessons': [{'title': '单元三'}]},
            ]
        }
        design_course_outline_task.delay(self.course.id)
        status = course_design_status(self.course.id)
        self.assertEqual(status['status'], 'done')
        self.assertEqual(status['chapters'], 2)
        self.assertEqual(status['lessons'], 3)
        self.assertEqual(self.course.chapters.count(), 2)

    @mock.patch('apps.chat.notebook_tools.find_related_sections', return_value=[])
    @mock.patch('apps.ai_agents.skills.CourseSkill')
    def test_failure_publishes_error_and_leaves_no_partial_rows(self, skill_cls, _find):
        skill_cls.return_value.run.side_effect = RuntimeError('boom')
        design_course_outline_task.delay(self.course.id)
        status = course_design_status(self.course.id)
        self.assertEqual(status['status'], 'error')
        self.assertEqual(self.course.chapters.count(), 0)

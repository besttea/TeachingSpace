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


class KPExtractTaskTests(TestCase):
    """Knowledge-point extraction task: grounding chain, merge dedup,
    missing rows, failure atomicity."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='提炼课程', slug='kp-task', instructor=self.instructor,
            difficulty_level='beginner')

    def _add_chapter(self, title, order, markdown=''):
        from .models import Cell
        chapter = Chapter.objects.create(course=self.course, title=title,
                                         order=order)
        if markdown:
            lesson = Lesson.objects.create(chapter=chapter, title='单元',
                                           order=1, status='published')
            Cell.objects.create(lesson=lesson, cell_type='text', order=0,
                                data={'markdown': markdown})
        return chapter

    @mock.patch('apps.chat.notebook_tools.find_related_sections', return_value='')
    @mock.patch('apps.ai_agents.skills.KnowledgeSkill')
    def test_extract_merges_and_dedups_across_chapters(self, skill_cls, _find):
        from .tasks import extract_knowledge_points_task, kp_extract_status
        self._add_chapter('第1章 列表', 1, '列表是可变的，支持索引。' * 20)
        self._add_chapter('第2章 元组', 2, '元组是不可变的序列。' * 20)
        skill = skill_cls.return_value

        def fake_extract(chapter_title, chapter_text='', source_material=''):
            if chapter_title.startswith('第1章'):
                return [{'title': '列表', 'description': 'x',
                         'difficulty': 'beginner'},
                        {'title': '列表推导式', 'description': 'x',
                         'difficulty': 'intermediate'}]
            # 第2章: 一条与第1章重复, 一条新
            return [{'title': '列表', 'description': 'x',
                     'difficulty': 'beginner'},
                    {'title': '元组不可变性', 'description': 'x',
                     'difficulty': 'beginner'}]
        skill.extract.side_effect = fake_extract

        extract_knowledge_points_task.delay(self.course.id)
        status = kp_extract_status(self.course.id)
        self.assertEqual(status['status'], 'done')
        self.assertEqual(status['points_created'], 3)
        self.assertEqual(status['duplicates_skipped'], 1)
        self.assertEqual(status['chapters_processed'], 2)
        titles = set(self.course.knowledge_points.values_list('title', flat=True))
        self.assertEqual(titles, {'列表', '列表推导式', '元组不可变性'})

    @mock.patch('apps.chat.notebook_tools.find_related_sections', return_value='')
    @mock.patch('apps.ai_agents.skills.KnowledgeSkill')
    def test_thin_chapter_grounds_in_classlib(self, skill_cls, find_mock):
        from .tasks import extract_knowledge_points_task
        find_mock.return_value = '【素材：第一课 · 1.1】\n数字常量……'
        self._add_chapter('第1章 数字', 1, markdown='')  # no text cells
        skill = skill_cls.return_value
        skill.extract.return_value = [{'title': '数字常量', 'description': 'x',
                                       'difficulty': 'beginner'}]
        extract_knowledge_points_task.delay(self.course.id)
        # grounded call: find_related_sections was asked, and its result
        # reached the skill as source material
        self.assertTrue(find_mock.called)
        _title, _text, source_material = skill.extract.call_args[0]
        self.assertIn('数字常量', source_material)
        self.assertEqual(self.course.knowledge_points.count(), 1)

    @mock.patch('apps.ai_agents.skills.KnowledgeSkill')
    def test_missing_course_noop(self, skill_cls):
        from django.core.cache import cache
        from .tasks import extract_knowledge_points_task, kp_extract_status
        cache.clear()
        result = extract_knowledge_points_task.delay(9999)
        self.assertIsNone(result.result)
        self.assertEqual(kp_extract_status(9999), {'status': 'none'})
        self.assertFalse(skill_cls.return_value.extract.called)

    @mock.patch('apps.chat.notebook_tools.find_related_sections', return_value='')
    @mock.patch('apps.ai_agents.skills.KnowledgeSkill')
    def test_chapter_failure_skips_chapter_not_task(self, skill_cls, _find):
        """One broken chapter must not abort the whole extraction."""
        from .tasks import extract_knowledge_points_task, kp_extract_status
        self._add_chapter('第1章 列表', 1, '内容' * 100)
        skill_cls.return_value.extract.side_effect = RuntimeError('boom')
        extract_knowledge_points_task.delay(self.course.id)
        status = kp_extract_status(self.course.id)
        self.assertEqual(status['status'], 'done')
        self.assertEqual(status['chapters_processed'], 0)
        self.assertEqual(status['points_created'], 0)
        self.assertEqual(self.course.knowledge_points.count(), 0)


class CourseDesignChapterCountTests(TestCase):
    """The instructor picks the chapter count on the create form — the
    task must forward it (was hardcoded to 3)."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='章节数课程', slug='cc-course', instructor=self.instructor,
            difficulty_level='beginner')

    @mock.patch('apps.chat.notebook_tools.find_related_sections', return_value='')
    @mock.patch('apps.ai_agents.skills.CourseSkill')
    def test_task_forwards_chapter_count(self, skill_cls, _find):
        skill_cls.return_value.run.return_value = {'chapters': []}
        design_course_outline_task.delay(self.course.id, chapter_count=7)
        self.assertEqual(
            skill_cls.return_value.run.call_args.kwargs['chapter_count'], 7)

    @mock.patch('apps.chat.notebook_tools.find_related_sections', return_value='')
    @mock.patch('apps.ai_agents.skills.CourseSkill')
    def test_task_clamps_out_of_range(self, skill_cls, _find):
        skill_cls.return_value.run.return_value = {'chapters': []}
        design_course_outline_task.delay(self.course.id, chapter_count=99)
        self.assertEqual(
            skill_cls.return_value.run.call_args.kwargs['chapter_count'], 10)

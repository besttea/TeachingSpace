"""Management-command coverage: notebook export (json/md/ipynb/pdf),
notebook import, ClassLib loaders (OPTIMIZATION_PLAN 6.5 coverage gate)."""

import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import User
from .models import Cell, Chapter, Course, Lesson

_CLASSLIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'ClassLib')
NOTEBOOK_PATH = os.path.join(_CLASSLIB, '第一课_基本数据结构.ipynb')


def _make_instructor(username='teacher'):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com',
        password='StrongPass123!', user_type='instructor')


def _make_lesson(instructor):
    course = Course.objects.create(
        title='导出测试课程', slug='export-test', instructor=instructor,
        difficulty_level='beginner')
    chapter = Chapter.objects.create(course=course, title='第1章', order=1)
    lesson = Lesson.objects.create(
        chapter=chapter, title='导出测试单元', order=1)
    Cell.objects.create(lesson=lesson, cell_type='text', order=0,
                        data={'markdown': '# 标题\n正文'})
    Cell.objects.create(lesson=lesson, cell_type='code', order=1,
                        data={'source': 'print(1 + 1)', 'output': '2',
                              'execution_count': 1})
    return lesson


class ExportNotebookTests(TestCase):
    def setUp(self):
        self.instructor = _make_instructor()
        self.lesson = _make_lesson(self.instructor)
        self.tmp = tempfile.mkdtemp(prefix='export_test_')

    def _run(self, fmt, output='', out=None):
        call_command('export_notebook', lesson_id=self.lesson.id,
                     format=fmt, output=output, stdout=out)

    def test_json_to_stdout(self):
        out = StringIO()
        self._run('json', out=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload['lesson_title'], '导出测试单元')
        self.assertEqual(len(payload['cells']), 2)
        self.assertEqual(payload['cells'][0]['cell_type'], 'text')

    def test_json_to_file(self):
        path = os.path.join(self.tmp, 'out.json')
        self._run('json', output=path)
        with open(path, encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(len(payload['cells']), 2)

    def test_markdown_export(self):
        out = StringIO()
        self._run('md', out=out)
        text = out.getvalue()
        self.assertIn('# 导出测试单元', text)
        self.assertIn('```python', text)
        self.assertIn('print(1 + 1)', text)

    def test_ipynb_export(self):
        out = StringIO()
        self._run('ipynb', out=out)
        notebook = json.loads(out.getvalue())
        self.assertEqual(notebook['nbformat'], 4)
        self.assertEqual(len(notebook['cells']), 2)
        self.assertEqual(notebook['cells'][0]['cell_type'], 'markdown')
        self.assertEqual(notebook['cells'][1]['cell_type'], 'code')
        self.assertEqual(notebook['cells'][1]['source'], ['print(1 + 1)'])

    def test_pdf_export(self):
        path = os.path.join(self.tmp, 'out.pdf')
        self._run('pdf', output=path)
        with open(path, 'rb') as f:
            self.assertTrue(f.read().startswith(b'%PDF'))

    def test_pdf_requires_output_path(self):
        with self.assertRaises(CommandError):
            self._run('pdf', out=StringIO())

    def test_unknown_lesson_raises(self):
        with self.assertRaises(CommandError):
            call_command('export_notebook', lesson_id=9999,
                         format='json', stdout=StringIO())


class ImportNotebookTests(TestCase):
    def setUp(self):
        self.instructor = _make_instructor('importer')

    def test_import_creates_course_lessons_cells(self):
        call_command('import_notebook', NOTEBOOK_PATH,
                     course_name='导入课程', instructor=self.instructor.username)
        course = Course.objects.get(title='导入课程')
        lessons = course.chapters.first().lessons.all()
        self.assertGreater(course.chapters.count(), 0)
        self.assertGreater(lessons.count(), 0)
        self.assertGreater(Cell.objects.filter(
            lesson__chapter__course=course).count(), 0)

    def test_import_idempotent(self):
        call_command('import_notebook', NOTEBOOK_PATH,
                     course_name='导入课程2', instructor=self.instructor.username)
        first = Cell.objects.filter(
            lesson__chapter__course__title='导入课程2').count()
        call_command('import_notebook', NOTEBOOK_PATH,
                     course_name='导入课程2', instructor=self.instructor.username)
        second = Cell.objects.filter(
            lesson__chapter__course__title='导入课程2').count()
        self.assertEqual(first, second)

    def test_missing_file_errors_gracefully(self):
        out = StringIO()
        call_command('import_notebook', os.path.join(self.tmp_dir(), 'nope.ipynb'),
                     stdout=out)
        self.assertIn('File not found', out.getvalue())

    def tmp_dir(self):
        # plain temp dir (no cleanup concerns in tests)
        return tempfile.mkdtemp(prefix='import_test_')


class LoadNotebookDataTests(TestCase):
    def test_load_creates_course_chapter_lesson_and_cells(self):
        out = StringIO()
        call_command('load_notebook_data', instructor='admin',
                     password='TempPass123!', stdout=out)
        course = Course.objects.get(title='Python编程基础')
        self.assertTrue(course.is_published)
        chapter = course.chapters.get(title='第1章 Python基本数据结构')
        lesson = chapter.lessons.get(title='第一讲 基本数据结构')
        self.assertGreater(lesson.cells.count(), 0)
        admin = User.objects.get(username='admin')
        self.assertTrue(admin.check_password('TempPass123!'))

    def test_reload_is_idempotent(self):
        call_command('load_notebook_data', instructor='admin2',
                     password='TempPass123!', stdout=StringIO())
        lesson = Lesson.objects.get(title='第一讲 基本数据结构')
        first = lesson.cells.count()
        call_command('load_notebook_data', instructor='admin2',
                     password='TempPass123!', stdout=StringIO())
        lesson = Lesson.objects.get(title='第一讲 基本数据结构')
        self.assertEqual(lesson.cells.count(), first)

    def test_missing_notebook_errors(self):
        out = StringIO()
        call_command('load_notebook_data', notebook='不存在.ipynb',
                     instructor='admin3', password='TempPass123!', stdout=out)
        self.assertIn('Notebook not found', out.getvalue())


class LoadAdditionalContentTests(TestCase):
    def test_requires_admin_first(self):
        out = StringIO()
        call_command('load_additional_content', stdout=out)
        self.assertIn('not found', out.getvalue())

    def test_loads_lessons_and_is_idempotent(self):
        # load_notebook_data creates the 'admin' instructor that
        # load_additional_content looks up
        call_command('load_notebook_data', instructor='admin',
                     password='TempPass123!', stdout=StringIO())
        call_command('load_additional_content', stdout=StringIO())
        self.assertTrue(Lesson.objects.filter(
            title='第二讲 流程控制').exists())
        self.assertTrue(Lesson.objects.filter(title='第三讲 函数').exists())
        oop_chapter = Chapter.objects.get(course__title='Python编程基础',
                                          title='第2章 面向对象编程')
        self.assertTrue(oop_chapter.lessons.filter(
            title='第一讲 类与对象').exists())

        lesson = Lesson.objects.get(title='第二讲 流程控制')
        first = lesson.cells.count()
        call_command('load_additional_content', stdout=StringIO())
        lesson = Lesson.objects.get(title='第二讲 流程控制')
        self.assertEqual(lesson.cells.count(), first)

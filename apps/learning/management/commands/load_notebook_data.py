"""
Management command to load a Jupyter notebook from the ClassLib directory
into the database as a single lesson (all cells, in original order).

Shares the notebook parser with the ``notebook-reader`` Claude Code skill
(apps.core.notebook_parser). Re-running the command clears and rebuilds
the lesson's cells, so it is idempotent.
"""

import os
import secrets

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.core.notebook_parser import cell_payload, parse_notebook
from apps.learning.models import Cell, Chapter, Course, Lesson


class Command(BaseCommand):
    help = 'Load Jupyter notebook data from ClassLib directory into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--notebook',
            type=str,
            default='Python基础程序设计/第一课_基本数据结构.ipynb',
            help='Notebook path inside ClassLib (category/name.ipynb)'
        )
        parser.add_argument(
            '--instructor',
            type=str,
            default='admin',
            help='Username of the instructor (default: admin)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default='',
            help='Password for a newly created instructor (default: random, printed once)'
        )

    def handle(self, *args, **options):
        notebook_file = options['notebook']
        instructor = self._get_or_create_instructor(options)

        # Path to notebook
        notebook_path = os.path.join(settings.BASE_DIR, 'ClassLib', notebook_file)

        if not os.path.exists(notebook_path):
            self.stdout.write(self.style.ERROR(f'Notebook not found: {notebook_path}'))
            return

        self.stdout.write(f'Loading notebook: {notebook_file}')
        doc = parse_notebook(notebook_path)

        # Parse notebook metadata to extract course info
        # For this example, we'll use the filename and first cell content
        course_title = "Python编程基础"
        course_description = "通过Jupyter风格的交互式笔记本学习Python编程基础知识"

        # Create or get course
        course, created = Course.objects.get_or_create(
            title=course_title,
            defaults={
                'slug': 'python-basics',
                'description': course_description,
                'instructor': instructor,
                'difficulty_level': 'beginner',
                'is_published': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created course: {course_title}'))
        else:
            self.stdout.write(f'Using existing course: {course_title}')

        # Create or get chapter
        chapter_title = "第1章 Python基本数据结构"
        chapter, created = Chapter.objects.get_or_create(
            course=course,
            title=chapter_title,
            defaults={
                'description': '学习Python的六种标准数据类型及其操作',
                'order': 1,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created chapter: {chapter_title}'))

        # Create or get lesson
        lesson_title = "第一讲 基本数据结构"
        lesson, created = Lesson.objects.get_or_create(
            chapter=chapter,
            title=lesson_title,
            defaults={
                'description': '介绍Python的数字常量、标准数据类型、字符串操作和LaTeX公式编辑',
                'order': 1,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created lesson: {lesson_title}'))
        else:
            # Clear existing cells if lesson already exists
            lesson.cells.all().delete()
            self.stdout.write(f'Cleared existing cells for lesson: {lesson_title}')

        # Parse and create cells
        cells_created = 0
        for order, item in enumerate(doc.cells):
            payload = cell_payload(item)
            if payload is None:
                continue
            Cell.objects.create(
                lesson=lesson,
                cell_type=payload['cell_type'],
                order=order,
                data=payload['data'],
                created_by=instructor,
            )
            cells_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Successfully loaded {cells_created} cells from {notebook_file}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'\nCourse: {course.title}'
            f'\nChapter: {chapter.title}'
            f'\nLesson: {lesson.title}'
            f'\nCells: {cells_created}'
        ))

    def _get_or_create_instructor(self, options):
        """Get the instructor, or create one with an explicit/random password
        — never a hardcoded one."""
        username = options['instructor']
        user = User.objects.filter(username=username).first()
        if user:
            return user

        password = options['password'] or secrets.token_urlsafe(12)
        user = User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password=password,
            user_type='instructor',
            is_staff=True,
        )
        self.stdout.write(self.style.WARNING(
            f'Created instructor "{username}" with generated password: {password} '
            f'(keep it safe and change it soon)'
        ))
        return user

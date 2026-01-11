"""
Management command to load Jupyter notebook data from Classlib directory into the database.
"""

import json
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.accounts.models import User
from apps.learning.models import Course, Chapter, Lesson, Cell


class Command(BaseCommand):
    help = 'Load Jupyter notebook data from Classlib directory into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--notebook',
            type=str,
            default='第一课_基本数据结构.ipynb',
            help='Notebook filename in Classlib directory'
        )
        parser.add_argument(
            '--instructor',
            type=str,
            default='admin',
            help='Username of the instructor (default: admin)'
        )

    def handle(self, *args, **options):
        notebook_file = options['notebook']
        instructor_username = options['instructor']

        # Get or create instructor user
        instructor, created = User.objects.get_or_create(
            username=instructor_username,
            defaults={
                'email': f'{instructor_username}@example.com',
                'user_type': 'instructor',
                'is_staff': True,
            }
        )
        if created:
            instructor.set_password('admin123')
            instructor.save()
            self.stdout.write(self.style.SUCCESS(f'Created instructor: {instructor_username}'))

        # Path to notebook
        notebook_path = os.path.join(settings.BASE_DIR, 'Classlib', notebook_file)

        if not os.path.exists(notebook_path):
            self.stdout.write(self.style.ERROR(f'Notebook not found: {notebook_path}'))
            return

        # Load notebook
        self.stdout.write(f'Loading notebook: {notebook_file}')
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook_data = json.load(f)

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
        for idx, cell_data in enumerate(notebook_data.get('cells', [])):
            cell_type = cell_data.get('cell_type', 'markdown')
            source = cell_data.get('source', [])

            # Join source lines if it's a list
            if isinstance(source, list):
                source_text = ''.join(source)
            else:
                source_text = source

            # Skip empty cells
            if not source_text.strip():
                continue

            # Map Jupyter cell types to our cell types
            if cell_type == 'markdown':
                our_cell_type = 'text'
                cell_content = {
                    'markdown': source_text,
                }
            elif cell_type == 'code':
                our_cell_type = 'code'
                # Get output if available
                outputs = cell_data.get('outputs', [])
                output_text = self._extract_output(outputs)

                cell_content = {
                    'source': source_text,
                    'output': output_text,
                    'language': 'python',
                    'status': 'success' if output_text else 'pending',
                }
            else:
                # Unknown cell type, treat as text
                our_cell_type = 'text'
                cell_content = {
                    'markdown': source_text,
                }

            # Create cell
            Cell.objects.create(
                lesson=lesson,
                cell_type=our_cell_type,
                order=idx,
                data=cell_content,
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

    def _extract_output(self, outputs):
        """Extract text output from notebook cell outputs."""
        if not outputs:
            return ''

        output_parts = []
        for output in outputs:
            if 'text' in output:
                text = output['text']
                if isinstance(text, list):
                    output_parts.append(''.join(text))
                else:
                    output_parts.append(text)
            elif 'data' in output:
                # Handle data outputs (e.g., text/plain)
                data = output['data']
                if 'text/plain' in data:
                    text = data['text/plain']
                    if isinstance(text, list):
                        output_parts.append(''.join(text))
                    else:
                        output_parts.append(text)

        return '\n'.join(output_parts)

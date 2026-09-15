"""
Imports a Jupyter notebook (.ipynb) as a Course, splitting content into
lessons at ``X.Y`` section headings (e.g. ``## 1.1 数字常量``).

Shares the notebook parser with the ``notebook-reader`` Claude Code skill
(apps.core.notebook_parser), so database imports match what AI-side
tooling sees. Re-running the command is safe: existing cells of a target
lesson are cleared before re-import.
"""

import os
import secrets

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.core.notebook_parser import cell_payload, parse_notebook
from apps.learning.models import Cell, Chapter, Course, Lesson


class Command(BaseCommand):
    help = 'Imports a Jupyter Notebook as a Course (lessons split at X.Y sections)'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the .ipynb file')
        parser.add_argument('--course-name', type=str, default='Python Basic Structures',
                            help='Name of the course')
        parser.add_argument('--instructor', type=str, default='',
                            help='Username of an existing instructor (default: first superuser)')
        parser.add_argument('--instructor-password', type=str, default='',
                            help='Password for a newly created instructor (default: random, printed once)')

    def handle(self, *args, **options):
        file_path = options['file_path']

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        doc = parse_notebook(file_path)
        stats = doc.stats()
        self.stdout.write(
            f'Notebook: {doc.title} | {stats["total"]} cells '
            f'({stats["markdown"]} text, {stats["code"]} code), {len(doc.sections)} sections'
        )

        instructor = self._resolve_instructor(options)

        # Create Course
        course, created = Course.objects.get_or_create(
            title=options['course_name'],
            defaults={
                'description': 'Imported from Jupyter Notebook',
                'instructor': instructor,
                'is_published': True,
                'difficulty_level': 'beginner'
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created course: {course.title}'))
        else:
            self.stdout.write(f'Using existing course: {course.title}')

        # Create Chapter (title from the notebook's 第X章 heading)
        chapter_title = doc.chapters[0] if doc.chapters else 'Chapter 1'
        chapter, created = Chapter.objects.get_or_create(
            course=course,
            title=chapter_title,
            defaults={'order': 1}
        )
        self.stdout.write(self.style.SUCCESS(f'Target Chapter: {chapter.title}'))

        # Create lessons from sections; the intro section (cells before the
        # first X.Y heading) becomes the "Introduction" lesson.
        for idx, section in enumerate(doc.sections):
            lesson_title = section.label if section.number else 'Introduction'
            lesson, _ = Lesson.objects.get_or_create(
                chapter=chapter,
                title=lesson_title,
                defaults={
                    'order': idx,
                    'status': 'published',
                    'created_by': instructor
                }
            )
            # Re-import safety: wipe existing cells so order never collides.
            removed, _ = lesson.cells.all().delete()
            if removed:
                self.stdout.write(f'Cleared {removed} existing cells from lesson: {lesson_title}')

            for order, item in enumerate(section.cells):
                payload = cell_payload(item)
                if payload is None:
                    continue
                Cell.objects.create(
                    lesson=lesson,
                    cell_type=payload['cell_type'],
                    order=order,
                    data=payload['data'],
                    created_by=instructor
                )

            self.stdout.write(self.style.SUCCESS(
                f'Lesson "{lesson_title}": {len(section.cells)} cells'
            ))

        if stats['noise']:
            self.stdout.write(self.style.WARNING(
                f'{stats["noise"]} noise cells (symbol tables / TOC / README pages / setup) '
                f'were imported as-is; trim them in the lesson editor if needed.'
            ))
        self.stdout.write(self.style.SUCCESS(
            f'Successfully imported notebook into {len(doc.sections)} lessons of "{chapter.title}"'
        ))

    def _resolve_instructor(self, options):
        """Pick an instructor account; create one only with an explicit or
        randomly generated password — never a hardcoded one."""
        username = options['instructor']
        user = User.objects.filter(username=username).first() if username else None
        if not user:
            user = User.objects.filter(is_superuser=True).first()
        if user:
            return user

        username = username or 'admin'
        password = options['instructor_password'] or secrets.token_urlsafe(12)
        user = User.objects.create_superuser(username, f'{username}@example.com', password)
        self.stdout.write(self.style.WARNING(
            f'Created instructor "{username}" with generated password: {password} '
            f'(keep it safe and change it soon)'
        ))
        return user

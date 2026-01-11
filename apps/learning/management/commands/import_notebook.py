import json
import re
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.learning.models import Course, Chapter, Lesson, Cell
from apps.accounts.models import User

class Command(BaseCommand):
    help = 'Imports a Jupyter Notebook as a Course'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the .ipynb file')
        parser.add_argument('--course-name', type=str, default='Python Basic Structures', help='Name of the course')

    def handle(self, *args, **options):
        file_path = options['file_path']
        course_name = options['course_name']

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            notebook_data = json.load(f)

        # Get or create instructor (admin)
        instructor = User.objects.filter(username='admin').first()
        if not instructor:
            instructor = User.objects.filter(is_superuser=True).first()
        
        if not instructor:
            self.stdout.write(self.style.WARNING('No admin or superuser found. Creating a default instructor.'))
            try:
                instructor = User.objects.create_superuser('admin', 'admin@example.com', 'adminpass')
            except Exception as e:
                # Fallback if email exists or other error
                self.stdout.write(self.style.WARNING(f'Failed to create admin: {e}. Trying to get any user.'))
                instructor = User.objects.first()
                if not instructor:
                     self.stdout.write(self.style.ERROR('No users found and cannot create one. Aborting.'))
                     return

        # Create Course
        course, created = Course.objects.get_or_create(
            title=course_name,
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

        # Determine Chapter Title from Content
        chapter_title = "Chapter 1" # Default
        # Scan for "第*章" pattern
        for cell in notebook_data.get('cells', []):
            if cell.get('cell_type') == 'markdown':
                source_text = ''.join(cell.get('source', [])).strip()
                # Check for HTML H1 containing 第*章
                h1_match = re.search(r'<h1[^>]*>.*(第.+章.*)</h1>', source_text, re.IGNORECASE)
                if h1_match:
                    chapter_title = h1_match.group(1).strip()
                    break
                # Check for Markdown headers containing 第*章
                md_match = re.search(r'^#{1,3}\s+.*(第.+章.*)', source_text, re.MULTILINE)
                if md_match:
                    chapter_title = md_match.group(1).strip()
                    break

        # Create Chapter
        chapter, created = Chapter.objects.get_or_create(
            course=course,
            title=chapter_title,
            defaults={'order': 1}
        )
        self.stdout.write(self.style.SUCCESS(f'Target Chapter: {chapter.title}'))

        # Process Cells
        cells = notebook_data.get('cells', [])
        
        # Create an initial lesson for intro content (before 1.1)
        current_lesson, _ = Lesson.objects.get_or_create(
            chapter=chapter,
            title="Introduction",
            defaults={
                'order': 0,
                'status': 'published',
                'created_by': instructor
            }
        )
        
        lesson_order = 1
        cell_order = 1

        for cell in cells:
            cell_type = cell.get('cell_type')
            source_lines = cell.get('source', [])
            source_text = ''.join(source_lines) if isinstance(source_lines, list) else source_lines

            # Check for Section Headers 1.x to start new Lesson
            is_new_lesson = False
            lesson_title = ""

            if cell_type == 'markdown':
                lines = source_text.strip().split('\n')
                # Iterate through lines to find the header
                for line in lines:
                    line = line.strip()
                    # Match headers that start with "1.x " (e.g., "### 1.1 数字常量")
                    # Exclude 1.5.1 (Level 3 numbering)
                    # Regex: start with #s, whitespace, then "1.", then digits, then space or end of line.
                    match = re.match(r'^(#{1,6})\s+(1\.\d+\s+.*)', line)
                    if match:
                        lesson_title = match.group(2).strip()
                        is_new_lesson = True
                        break # Found the header for this cell
                    else:
                        # Also check HTML headers if they contain "1.x "
                        html_match = re.match(r'^<h[1-6][^>]*>\s*(1\.\d+\s+.*)</h[1-6]>', line, re.IGNORECASE)
                        if html_match:
                            lesson_title = html_match.group(1).strip()
                            is_new_lesson = True
                            break

            if is_new_lesson:
                # Create new lesson
                current_lesson, created = Lesson.objects.get_or_create(
                    chapter=chapter,
                    title=lesson_title,
                    defaults={
                        'order': lesson_order,
                        'status': 'published',
                        'created_by': instructor
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'Created lesson: {lesson_title}'))
                    lesson_order += 1
                else:
                    self.stdout.write(f'Using existing lesson: {lesson_title}')
                
                cell_order = 1 # Reset cell order for new lesson

            # Prepare Cell Data
            db_cell_type = 'text'
            cell_data = {}

            if cell_type == 'markdown':
                db_cell_type = 'text'
                cell_data = {'markdown': source_text}
            elif cell_type == 'code':
                db_cell_type = 'code'
                outputs = cell.get('outputs', [])
                output_text = ''
                for output in outputs:
                    if 'text' in output:
                        output_text += ''.join(output['text'])
                    elif 'data' in output and 'text/plain' in output['data']:
                        output_text += ''.join(output['data']['text/plain'])
                
                cell_data = {
                    'source': source_text,
                    'output': output_text,
                    'execution_count': cell.get('execution_count') or 0
                }

            # Create Cell
            Cell.objects.create(
                lesson=current_lesson,
                cell_type=db_cell_type,
                order=cell_order,
                data=cell_data,
                created_by=instructor
            )
            cell_order += 1

        self.stdout.write(self.style.SUCCESS('Successfully imported notebook content'))

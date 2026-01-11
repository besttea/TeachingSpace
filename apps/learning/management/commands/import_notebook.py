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

        # Determine Chapter Title from Content (First H1) or Filename
        chapter_title = os.path.splitext(os.path.basename(file_path))[0]
        # Try to find H1 in first few cells
        for i in range(min(5, len(notebook_data.get('cells', [])))):
            cell = notebook_data['cells'][i]
            if cell.get('cell_type') == 'markdown':
                source_text = ''.join(cell.get('source', [])).strip()
                # Check for HTML H1
                h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', source_text, re.IGNORECASE)
                if h1_match:
                    chapter_title = h1_match.group(1).strip()
                    break
                # Check for Markdown H1
                md_h1_match = re.match(r'^#\s+(.*)', source_text)
                if md_h1_match:
                    chapter_title = md_h1_match.group(1).strip()
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
        
        # We need a default lesson if the file doesn't start with a header
        # Or we can treat the Chapter Title as the first Lesson Title
        current_lesson = None
        lesson_order = 1
        cell_order = 1
        
        # Initial scan to see if first cell is a header
        first_cell_is_header = False
        if cells:
            first_cell = cells[0]
            if first_cell.get('cell_type') == 'markdown':
                src = ''.join(first_cell.get('source', [])).strip()
                if re.match(r'^(#{1,3})\s+(.*)', src) or re.match(r'^(#{1,3})[^#]', src):
                     first_cell_is_header = True

        if not first_cell_is_header:
            # Create a "Overview" lesson or use Chapter title
            current_lesson, _ = Lesson.objects.get_or_create(
                chapter=chapter,
                title="Introduction", # Default if no header
                defaults={
                    'order': 0,
                    'status': 'published',
                    'created_by': instructor
                }
            )

        for cell in cells:
            cell_type = cell.get('cell_type')
            source_lines = cell.get('source', [])
            source_text = ''.join(source_lines) if isinstance(source_lines, list) else source_lines

            # Check for Section Headers in Markdown to start new Lesson
            # We treat H1, H2, H3 as Lesson delimiters to strictly follow content structure
            is_new_lesson = False
            lesson_title = ""

            if cell_type == 'markdown':
                # Iterate through lines to find a header at the START of the cell
                # If a cell starts with a header, it's a new lesson.
                # If a header is in the middle, we might split? 
                # For simplicity and robustness, we assume headers starting a section are usually at the start of a cell in notebooks.
                # But we can also check line by line if we want to split cells (complex).
                # Let's stick to "Cell starting with Header starts a new Lesson".
                
                # Check first line for header
                lines = source_text.strip().split('\n')
                if lines:
                    first_line = lines[0].strip()
                    # Match #, ##, ###
                    match = re.match(r'^(#{1,3})\s+(.*)', first_line)
                    if match:
                        lesson_title = match.group(2).strip()
                        # If title is empty (just ###), use placeholder
                        if not lesson_title:
                            lesson_title = f"Section {lesson_order}"
                        is_new_lesson = True
                    else:
                        # Check for HTML headers <h1>, <h2>, <h3>
                        html_match = re.match(r'^<h[1-3][^>]*>(.*?)</h[1-3]>', first_line, re.IGNORECASE)
                        if html_match:
                            lesson_title = html_match.group(1).strip()
                            is_new_lesson = True

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
            
            # If still no current lesson (e.g. first cell was not header and we skipped default), create one now
            if not current_lesson:
                 current_lesson, _ = Lesson.objects.get_or_create(
                    chapter=chapter,
                    title="Introduction",
                    defaults={
                        'order': 0,
                        'status': 'published',
                        'created_by': instructor
                    }
                )

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

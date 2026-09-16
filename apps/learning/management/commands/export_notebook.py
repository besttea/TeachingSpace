"""
Export a lesson's cells to JSON (cell-payload format, readable by the
shared notebook parser) or Markdown.

Usage:
    python manage.py export_notebook --lesson-id 1 --format json [--output path]
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.learning.models import Lesson


class Command(BaseCommand):
    help = 'Export a lesson to JSON or Markdown'

    def add_arguments(self, parser):
        parser.add_argument('--lesson-id', type=int, required=True)
        parser.add_argument('--format', choices=['json', 'md'], default='json')
        parser.add_argument('--output', type=str, default='',
                            help='Output file path (default: print to stdout)')

    def handle(self, *args, **options):
        lesson = Lesson.objects.filter(pk=options['lesson_id']).first()
        if lesson is None:
            raise CommandError(f'Lesson not found: {options["lesson_id"]}')

        cells = list(lesson.cells.all().order_by('order'))

        if options['format'] == 'json':
            payloads = []
            for cell in cells:
                if cell.cell_type == 'text':
                    payloads.append({'cell_type': 'text', 'data': {
                        'markdown': cell.data.get('markdown', '')}})
                elif cell.cell_type == 'code':
                    payloads.append({'cell_type': 'code', 'data': {
                        'source': cell.data.get('source', ''),
                        'output': cell.data.get('output', ''),
                        'execution_count': cell.data.get('execution_count', 0)}})
            output = json.dumps({
                'lesson_title': lesson.title,
                'chapter': lesson.chapter.title,
                'cells': payloads,
            }, ensure_ascii=False, indent=2)
        else:
            lines = [f'# {lesson.title}', '']
            for cell in cells:
                if cell.cell_type == 'text':
                    lines.append(cell.data.get('markdown', ''))
                    lines.append('')
                elif cell.cell_type == 'code':
                    lines.append('```python')
                    lines.append(cell.data.get('source', ''))
                    lines.append('```')
                    lines.append('')
            output = '\n'.join(lines)

        if options['output']:
            with open(options['output'], 'w', encoding='utf-8') as f:
                f.write(output)
            self.stdout.write(self.style.SUCCESS(f'Exported to {options["output"]}'))
        else:
            self.stdout.write(output)

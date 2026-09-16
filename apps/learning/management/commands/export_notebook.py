"""
Export a lesson's cells to JSON (cell-payload format), Markdown, Jupyter
notebook (.ipynb) or PDF (T22).

Usage:
    python manage.py export_notebook --lesson-id 1 --format json [--output path]
"""

import json
from io import BytesIO

from django.core.management.base import BaseCommand, CommandError

from apps.learning.models import Lesson


def _cells_to_payloads(cells) -> list:
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
    return payloads


def _to_ipynb(lesson, cells) -> str:
    nb_cells = []
    for cell in cells:
        if cell.cell_type == 'text':
            nb_cells.append({
                'cell_type': 'markdown',
                'metadata': {},
                'source': cell.data.get('markdown', '').splitlines(keepends=True),
            })
        elif cell.cell_type == 'code':
            nb_cells.append({
                'cell_type': 'code',
                'metadata': {},
                'execution_count': cell.data.get('execution_count') or None,
                'source': cell.data.get('source', '').splitlines(keepends=True),
                'outputs': [],
            })
    notebook = {
        'nbformat': 4,
        'nbformat_minor': 5,
        'metadata': {'language_info': {'name': 'python'}},
        'cells': nb_cells,
    }
    return json.dumps(notebook, ensure_ascii=False, indent=1)


def _to_pdf_bytes(lesson, cells) -> bytes:
    """Plain-layout PDF: text cells as CJK paragraphs, code cells in blocks."""
    import re

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 60

    c.setFont('STSong-Light', 20)
    c.drawString(50, y, lesson.title)
    y -= 30

    def new_page():
        nonlocal y
        c.showPage()
        y = height - 60

    for cell in cells:
        if y < 80:
            new_page()
        if cell.cell_type == 'text':
            c.setFont('STSong-Light', 11)
            for line in cell.data.get('markdown', '').split('\n'):
                line = re.sub(r'[#*`>]', '', line).strip()
                if not line:
                    y -= 6
                    continue
                # simple wrapping at ~90 CJK chars
                while line:
                    chunk, line = line[:88], line[88:]
                    c.drawString(50, y, chunk)
                    y -= 16
                    if y < 60:
                        new_page()
            y -= 10
        elif cell.cell_type == 'code':
            c.setFont('Courier', 9)
            for line in cell.data.get('source', '').split('\n'):
                if not line:
                    y -= 5
                    continue
                c.drawString(50, y, line[:100])
                y -= 12
                if y < 60:
                    new_page()
            y -= 8
    c.save()
    return buf.getvalue()


class Command(BaseCommand):
    help = 'Export a lesson to JSON / Markdown / ipynb / PDF'

    def add_arguments(self, parser):
        parser.add_argument('--lesson-id', type=int, required=True)
        parser.add_argument('--format', choices=['json', 'md', 'ipynb', 'pdf'],
                            default='json')
        parser.add_argument('--output', type=str, default='',
                            help='Output file path (default: print to stdout)')

    def handle(self, *args, **options):
        lesson = Lesson.objects.filter(pk=options['lesson_id']).first()
        if lesson is None:
            raise CommandError(f'Lesson not found: {options["lesson_id"]}')

        cells = list(lesson.cells.all().order_by('order'))
        fmt = options['format']

        if fmt == 'json':
            output = json.dumps({
                'lesson_title': lesson.title,
                'chapter': lesson.chapter.title,
                'cells': _cells_to_payloads(cells),
            }, ensure_ascii=False, indent=2)
            mode = 'w'
        elif fmt == 'md':
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
            mode = 'w'
        elif fmt == 'ipynb':
            output = _to_ipynb(lesson, cells)
            mode = 'w'
        else:  # pdf
            output = _to_pdf_bytes(lesson, cells)
            mode = 'wb'

        if options['output']:
            with open(options['output'], mode, encoding=None if mode == 'wb' else 'utf-8') as f:
                f.write(output)
            self.stdout.write(self.style.SUCCESS(f'Exported to {options["output"]}'))
        else:
            if mode == 'wb':
                raise CommandError('PDF 导出必须指定 --output 文件路径')
            self.stdout.write(output)

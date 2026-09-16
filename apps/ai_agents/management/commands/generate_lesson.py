"""
Generate a lesson with the Learning Agent and save it as
Course → Chapter → Lesson → Cells.

Usage:
    python manage.py generate_lesson "Variables and Data Types" \
        --difficulty beginner \
        [--course "Python Basics"] \
        [--notebook 第一课_基本数据结构.ipynb] [--section 1.2] \
        [--instructor admin] [--publish]

Optional --notebook/--section grounds the generation in real ClassLib
material: the section content is fetched via the shared notebook tools and
handed to the agent as source material.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.learning.models import Cell, Chapter, Course, Lesson


class Command(BaseCommand):
    help = 'Generate a lesson (with AI) and save it into the learning app'

    def add_arguments(self, parser):
        parser.add_argument('topic', type=str, help='Lesson topic')
        parser.add_argument('--difficulty', type=str, default='beginner',
                            choices=['beginner', 'intermediate', 'advanced'])
        parser.add_argument('--course', type=str, default='',
                            help='Existing course title (default: derived from topic)')
        parser.add_argument('--instructor', type=str, default='',
                            help='Username of the course instructor (default: first superuser)')
        parser.add_argument('--notebook', type=str, default='',
                            help='Optional ClassLib notebook to ground the lesson in')
        parser.add_argument('--section', type=str, default='',
                            help='Section (e.g. 1.2) of --notebook to use as source material')
        parser.add_argument('--publish', action='store_true',
                            help='Publish the lesson immediately (default: draft)')

    def handle(self, *args, **options):
        topic = options['topic']
        difficulty = options['difficulty']

        instructor = self._resolve_instructor(options)

        # Optional grounding material from ClassLib
        source_material = ''
        if options['notebook']:
            from apps.chat.notebook_tools import get_notebook_section
            section = options['section'] or ''
            result = get_notebook_section(options['notebook'], section)
            if 'error' in result:
                self.stdout.write(self.style.WARNING(
                    f'Notebook material not available: {result["error"]}'))
            else:
                source_material = result['section']
                self.stdout.write(self.style.SUCCESS(
                    f'Using notebook "{options["notebook"]}" section "{section}" as source material'))

        self.stdout.write(f'Generating lesson: {topic} ({difficulty})...')
        from apps.ai_agents import ai_config
        if not ai_config.is_configured():
            raise CommandError('ANTHROPIC_API_KEY is not configured — cannot generate content')

        from apps.ai_agents.skills import CourseSkill
        generated = CourseSkill().run(
            topic, difficulty, chapter_count=1,
            source_material=source_material, with_content=True)
        chapters = generated.get('chapters', [])
        cells = []
        if chapters:
            lessons = chapters[0].get('lessons', [])
            if lessons:
                cells = lessons[0].get('cells', [])
        if not cells:
            raise CommandError('The AI returned no lesson cells')

        # Course → Chapter → Lesson
        course, _ = Course.objects.get_or_create(
            title=options['course'] or f'{topic} 课程',
            defaults={
                'description': f'AI 生成的 {topic} 课程',
                'instructor': instructor,
                'is_published': False,
                'difficulty_level': difficulty,
            },
        )
        chapter, _ = Chapter.objects.get_or_create(
            course=course, title=f'第1章 {topic}', defaults={'order': 0},
        )
        last_order = Lesson.objects.filter(chapter=chapter).count()
        lesson = Lesson.objects.create(
            chapter=chapter,
            title=topic,
            description=f'AI 生成课程单元（{difficulty}）',
            status='published' if options['publish'] else 'draft',
            order=last_order,
            created_by=instructor,
        )

        # Cells
        for order, cell in enumerate(cells):
            cell_type = cell.get('type')
            content = cell.get('content', '')
            if cell_type == 'code':
                Cell.objects.create(
                    lesson=lesson, cell_type='code', order=order,
                    data={'source': content, 'output': '', 'execution_count': 0},
                    created_by=instructor,
                )
            else:
                Cell.objects.create(
                    lesson=lesson, cell_type='text', order=order,
                    data={'markdown': content},
                    created_by=instructor,
                )

        self.stdout.write(self.style.SUCCESS(
            f'Created lesson "{lesson.title}" ({len(cells)} cells) in course "{course.title}"'
            f' — status: {lesson.status}'
        ))

    def _resolve_instructor(self, options):
        username = options['instructor']
        user = User.objects.filter(username=username).first() if username else None
        if not user:
            user = User.objects.filter(is_superuser=True).first()
        if not user:
            raise CommandError(
                'No instructor found. Create a user first, or pass --instructor <username>.'
            )
        return user

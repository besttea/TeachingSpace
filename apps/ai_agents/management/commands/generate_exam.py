"""
Generate an exam through the ExamSkill (harness pipeline: type distribution
→ per-question generation → code questions sandbox-validated) and save it
as DRAFT — instructor review required before publishing.

Usage:
    python manage.py generate_exam --course python-basics --question-count 20 \
        [--difficulty intermediate] [--title "期中考试"] [--duration 60]
"""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.examination.exam_assembly import save_generated_questions
from apps.examination.models import Exam
from apps.learning.models import Course


class Command(BaseCommand):
    help = 'Generate an exam (with AI) and save it as a draft for review'

    def add_arguments(self, parser):
        parser.add_argument('--course', type=str, required=True,
                            help='Course slug (topic source)')
        parser.add_argument('--question-count', type=int, default=10,
                            help='Number of questions')
        parser.add_argument('--difficulty', type=str, default='intermediate',
                            choices=['beginner', 'intermediate', 'advanced'])
        parser.add_argument('--title', type=str, default='',
                            help='Exam title (default: "<course> 测验")')
        parser.add_argument('--duration', type=int, default=60,
                            help='Exam duration in minutes')
        parser.add_argument('--creator', type=str, default='',
                            help='Username of the creator (default: first superuser)')

    def handle(self, *args, **options):
        course = Course.objects.filter(slug=options['course']).first()
        if course is None:
            raise CommandError(f'Course not found: {options["course"]}')

        creator = self._resolve_creator(options)
        from apps.ai_agents import ai_config
        if not ai_config.is_configured():
            raise CommandError('AI API key is not configured — cannot generate content')

        self.stdout.write(
            f'Generating {options["question_count"]} questions on "{course.title}"...')
        from apps.ai_agents.skills import ExamSkill

        skill = ExamSkill()
        result = skill.run(
            course.title, options['difficulty'], options['question_count'])
        questions = result.get('questions', [])
        if not questions:
            raise CommandError('The AI returned no questions')
        self.stdout.write(self.style.SUCCESS(
            f'代码题沙箱验证: {result.get("code_validated", "0/0")}'))

        exam = Exam.objects.create(
            title=options['title'] or f'{course.title} 测验',
            description=f'AI 生成的 {course.title} 测验（{options["difficulty"]}）',
            duration_minutes=options['duration'],
            passing_score=60,
            max_attempts=3,
            is_published=False,  # critical content: instructor review required
            created_by=creator,
        )

        summary = save_generated_questions(exam, questions)
        self.stdout.write(self.style.SUCCESS(
            f'Created exam "{exam.title}" (id={exam.id}) with '
            f'{summary["saved"]} questions ({summary["skipped"]} skipped) — '
            f'status: DRAFT. Review and publish it in the admin.'
        ))

    def _resolve_creator(self, options):
        username = options['creator']
        user = User.objects.filter(username=username).first() if username else None
        if not user:
            user = User.objects.filter(is_superuser=True).first()
        if not user:
            raise CommandError(
                'No user found to mark as creator. Create a user first, '
                'or pass --creator <username>.'
            )
        return user

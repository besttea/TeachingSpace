"""
Generate an exam with the Examination Agent and save it (as DRAFT for
instructor review — critical content must be approved before publishing).

Usage:
    python manage.py generate_exam --course python-basics --question-count 20 \
        [--difficulty intermediate] [--title "期中考试"] [--duration 60]
"""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.ai_agents.examination_agent import ExaminationAgent
from apps.examination.models import (
    CodeQuestion, EssayQuestion, Exam, MultipleChoiceQuestion,
    Question, TrueFalseQuestion,
)
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
        agent = ExaminationAgent()
        if not agent.api_key:
            raise CommandError('ANTHROPIC_API_KEY is not configured — cannot generate content')

        self.stdout.write(
            f'Generating {options["question_count"]} questions on "{course.title}"...')
        data = agent.generate_exam_questions(
            course.title, options['difficulty'], options['question_count'])
        questions = data.get('questions', [])
        if not questions:
            raise CommandError('The AI returned no questions')

        exam = Exam.objects.create(
            title=options['title'] or f'{course.title} 测验',
            description=f'AI 生成的 {course.title} 测验（{options["difficulty"]}）',
            duration_minutes=options['duration'],
            passing_score=60,
            max_attempts=3,
            is_published=False,  # critical content: instructor review required
            created_by=creator,
        )

        saved = 0
        for i, q in enumerate(questions):
            q_type = q.get('type')
            if q_type not in dict(Question.QUESTION_TYPES):
                self.stdout.write(self.style.WARNING(
                    f'Question {i + 1}: unknown type {q_type!r} — skipped'))
                continue
            try:
                question = Question.objects.create(
                    exam=exam,
                    question_type=q_type,
                    question_text=q.get('text', ''),
                    points=int(q.get('points', 10)),
                    difficulty='medium',
                    order=i,
                )
                if q_type == 'multiple_choice':
                    MultipleChoiceQuestion.objects.create(
                        question=question,
                        options=q.get('options', {}),
                        correct_answer=q.get('correct_answer', 'A'),
                        explanation=q.get('explanation', ''),
                    )
                elif q_type == 'true_false':
                    TrueFalseQuestion.objects.create(
                        question=question,
                        correct_answer=bool(q.get('correct_answer', False)),
                        explanation=q.get('explanation', ''),
                    )
                elif q_type == 'code':
                    CodeQuestion.objects.create(
                        question=question,
                        starter_code=q.get('starter_code', ''),
                        solution_code=q.get('solution_code', ''),
                        test_cases=q.get('test_cases', []),
                        explanation=q.get('explanation', ''),
                    )
                elif q_type == 'essay':
                    EssayQuestion.objects.create(
                        question=question,
                        word_limit=int(q.get('word_limit') or 0),
                        rubric=q.get('rubric', ''),
                        sample_answer=q.get('sample_answer', ''),
                    )
                saved += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Question {i + 1} failed: {e}'))

        self.stdout.write(self.style.SUCCESS(
            f'Created exam "{exam.title}" (id={exam.id}) with {saved} questions — '
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

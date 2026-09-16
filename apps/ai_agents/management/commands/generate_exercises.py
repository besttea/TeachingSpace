"""
Generate coding exercises with the Training Agent and save them.

Usage:
    python manage.py generate_exercises --topic "Functions" --count 5 \
        --difficulty intermediate [--course python-basics] [--creator admin]
"""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.ai_agents.training_agent import TrainingAgent
from apps.learning.models import Course
from apps.training.models import Exercise, Hint


class Command(BaseCommand):
    help = 'Generate coding exercises (with AI) and save them into the training app'

    def add_arguments(self, parser):
        parser.add_argument('--topic', type=str, required=True, help='Exercise topic')
        parser.add_argument('--count', type=int, default=1, help='Number of exercises')
        parser.add_argument('--difficulty', type=str, default='intermediate',
                            choices=['beginner', 'intermediate', 'advanced'])
        parser.add_argument('--course', type=str, default='',
                            help='Course slug to attach the exercises to (optional)')
        parser.add_argument('--creator', type=str, default='',
                            help='Username of the creator (default: first superuser)')

    def handle(self, *args, **options):
        topic = options['topic']
        difficulty = options['difficulty']
        count = options['count']

        creator = self._resolve_creator(options)
        course = None
        if options['course']:
            course = Course.objects.filter(slug=options['course']).first()
            if course is None:
                raise CommandError(f'Course not found: {options["course"]}')

        agent = TrainingAgent()
        if not agent.api_key:
            raise CommandError('ANTHROPIC_API_KEY is not configured — cannot generate content')

        created = 0
        for i in range(count):
            self.stdout.write(f'Generating exercise {i + 1}/{count} on "{topic}"...')
            try:
                data = agent.generate_exercise(topic, difficulty)
                test_cases = data.get('test_cases') or []
                if not test_cases:
                    self.stdout.write(self.style.WARNING(
                        f'Exercise {i + 1} has no test cases — skipped'))
                    continue

                exercise = Exercise.objects.create(
                    title=data.get('title', f'{topic} 练习 {i + 1}'),
                    description=data.get('description', ''),
                    difficulty=difficulty,
                    course=course,
                    starter_code=data.get('starter_code', ''),
                    solution_code=data.get('solution_code', ''),
                    test_cases=test_cases,
                    created_by=creator,
                )

                for hint in data.get('hints', []):
                    Hint.objects.create(
                        exercise=exercise,
                        content=hint.get('content', ''),
                        order=hint.get('order', 0),
                        points_penalty=hint.get('points_penalty', 2),
                    )

                created += 1
                self.stdout.write(self.style.SUCCESS(
                    f'Created exercise: {exercise.title} ({len(test_cases)} test cases, '
                    f'{len(data.get("hints", []))} hints)'
                ))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Exercise {i + 1} failed: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Done. {created}/{count} exercises created.'))

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

"""
Batch-generate content for a course: coding exercises (published) and an
exam (draft) grounded in the course title/topic.

Usage:
    python manage.py batch_generate_content --course-id 1 \
        [--exercises 5] [--exam-questions 10] [--difficulty intermediate]
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai_agents.examination_agent import ExaminationAgent
from apps.ai_agents.training_agent import TrainingAgent
from apps.examination.models import Exam
from apps.learning.models import Course


class Command(BaseCommand):
    help = 'Batch-generate exercises + an exam draft for a course'

    def add_arguments(self, parser):
        parser.add_argument('--course-id', type=int, required=True)
        parser.add_argument('--exercises', type=int, default=5)
        parser.add_argument('--exam-questions', type=int, default=10)
        parser.add_argument('--difficulty', type=str, default='intermediate',
                            choices=['beginner', 'intermediate', 'advanced'])

    def handle(self, *args, **options):
        course = Course.objects.filter(pk=options['course_id']).first()
        if course is None:
            raise CommandError(f'Course not found: {options["course_id"]}')

        # Exercises — reuse the generate_exercises command logic
        from django.core.management import call_command
        call_command('generate_exercises',
                     topic=course.title,
                     count=options['exercises'],
                     difficulty=options['difficulty'],
                     course=course.slug,
                     verbosity=1)

        # Exam draft — reuse the generate_exam command logic
        call_command('generate_exam',
                     course=course.slug,
                     question_count=options['exam_questions'],
                     difficulty=options['difficulty'],
                     verbosity=1)

        self.stdout.write(self.style.SUCCESS(
            f'Batch generation for "{course.title}" done. '
            f'Review the exam draft in admin before publishing.'
        ))

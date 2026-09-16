"""
Export an exam's questions to JSON (portable question bank format).

Usage:
    python manage.py export_exam_questions --exam-id 3 [--output bank.json]
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.examination.models import Exam
from apps.examination.question_ai import question_to_dict


class Command(BaseCommand):
    help = '导出一场考试的全部题目为 JSON 题库文件'

    def add_arguments(self, parser):
        parser.add_argument('--exam-id', type=int, required=True)
        parser.add_argument('--output', type=str, default='')

    def handle(self, *args, **options):
        exam = Exam.objects.filter(pk=options['exam_id']).first()
        if exam is None:
            raise CommandError(f'考试不存在: {options["exam_id"]}')

        questions = []
        for question in exam.questions.all().order_by('order'):
            questions.append(question_to_dict(question))

        payload = {
            'exported_from': {'exam_id': exam.id, 'title': exam.title},
            'questions': questions,
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)

        if options['output']:
            with open(options['output'], 'w', encoding='utf-8') as f:
                f.write(output)
            self.stdout.write(self.style.SUCCESS(
                f'已导出 {len(questions)} 道题到 {options["output"]}'))
        else:
            self.stdout.write(output)

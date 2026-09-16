"""
Assemble an exam from a question bank: pull N questions per type from
source exams and clone them into a target exam (draft).

Usage:
    python manage.py assemble_exam --exam-id 9 --source-exams 1,2,3 \
        --distribution '{"multiple_choice": 10, "true_false": 5, "code": 3, "essay": 2}'

Code questions are sandbox-validated before cloning; invalid ones are skipped.
"""

import json
import random

from django.core.management.base import BaseCommand, CommandError

from apps.examination.models import Exam, Question
from apps.examination.question_ai import clone_question, question_to_dict, validate_code_question


class Command(BaseCommand):
    help = '按题型配比从题库（源考试）自动组卷到目标考试'

    def add_arguments(self, parser):
        parser.add_argument('--exam-id', type=int, required=True, help='目标考试 ID')
        parser.add_argument('--source-exams', type=str, required=True,
                            help='源考试 ID，逗号分隔，如 1,2,3')
        parser.add_argument('--distribution', type=str, required=True,
                            help='题型配比 JSON，如 {"multiple_choice": 10, "code": 3}')
        parser.add_argument('--seed', type=int, default=0,
                            help='随机种子（0 = 随机）')

    def handle(self, *args, **options):
        target = Exam.objects.filter(pk=options['exam_id']).first()
        if target is None:
            raise CommandError(f'目标考试不存在: {options["exam_id"]}')

        try:
            distribution = json.loads(options['distribution'])
        except json.JSONDecodeError as e:
            raise CommandError(f'配比 JSON 格式错误: {e}')

        source_ids = [int(s) for s in options['source_exams'].split(',') if s.strip()]
        sources = list(Exam.objects.filter(pk__in=source_ids))
        if not sources:
            raise CommandError('没有找到源考试')

        rng = random.Random(options['seed'] or None)
        order = target.questions.count()
        saved = skipped = 0

        for q_type, wanted in distribution.items():
            if wanted <= 0:
                continue
            pool = list(
                Question.objects.filter(
                    exam__in=sources, question_type=q_type
                ).select_related(
                    'multiplechoicequestion', 'codequestion',
                    'essayquestion', 'truefalsequestion'))
            if len(pool) < wanted:
                self.stdout.write(self.style.WARNING(
                    f'{q_type}: 题库只有 {len(pool)} 道，需要 {wanted} 道'))
            rng.shuffle(pool)
            taken = 0
            for question in pool:
                if taken >= wanted:
                    break
                data = question_to_dict(question)
                data.pop('_validated', None)
                data.pop('_validation_message', None)
                if q_type == 'code':
                    ok, message = validate_code_question(data)
                    if not ok:
                        skipped += 1
                        continue
                clone_question(question, target, order)
                order += 1
                saved += 1
                taken += 1

        self.stdout.write(self.style.SUCCESS(
            f'组卷完成：成功 {saved} 道（跳过 {skipped} 道未通过沙箱验证的代码题）。'
            f'目标考试《{target.title}》现共 {target.questions.count()} 道题，请在管理页审核发布。'))

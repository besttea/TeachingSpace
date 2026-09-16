"""
Import questions from a JSON question-bank file into an existing exam
(created as draft questions, code questions sandbox-validated).

Usage:
    python manage.py import_exam_questions --exam-id 3 --file bank.json
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.examination.models import (
    CodeQuestion, EssayQuestion, Exam, MultipleChoiceQuestion,
    Question, TrueFalseQuestion,
)
from apps.examination.question_ai import validate_code_question


class Command(BaseCommand):
    help = '从 JSON 题库文件导入题目到一场考试（代码题会做沙箱验证）'

    def add_arguments(self, parser):
        parser.add_argument('--exam-id', type=int, required=True)
        parser.add_argument('--file', type=str, required=True)

    def handle(self, *args, **options):
        exam = Exam.objects.filter(pk=options['exam_id']).first()
        if exam is None:
            raise CommandError(f'考试不存在: {options["exam_id"]}')

        try:
            payload = json.loads(
                open(options['file'], encoding='utf-8').read())
        except (OSError, json.JSONDecodeError) as e:
            raise CommandError(f'读取题库文件失败: {e}')

        questions = payload.get('questions', [])
        if not questions:
            raise CommandError('题库文件没有题目')

        base_order = exam.questions.count()
        saved = rejected = 0
        for index, data in enumerate(questions):
            q_type = data.get('type')
            if q_type not in dict(Question.QUESTION_TYPES):
                self.stdout.write(self.style.WARNING(
                    f'题目 {index + 1}: 未知类型 {q_type!r} — 跳过'))
                rejected += 1
                continue

            # Code questions must pass the sandbox before import
            if q_type == 'code':
                ok, message = validate_code_question(data)
                if not ok:
                    self.stdout.write(self.style.WARNING(
                        f'题目 {index + 1}（代码题）验证失败（{message}）— 跳过'))
                    rejected += 1
                    continue

            try:
                question = Question.objects.create(
                    exam=exam,
                    question_type=q_type,
                    question_text=data.get('text', ''),
                    points=int(data.get('points', 10)),
                    difficulty=data.get('difficulty', 'medium'),
                    order=base_order + saved,
                )
                # create the specific record (apply_question only updates)
                if q_type == 'multiple_choice':
                    MultipleChoiceQuestion.objects.create(
                        question=question,
                        options=data.get('options', {}),
                        correct_answer=data.get('correct_answer', 'A'),
                        explanation=data.get('explanation', ''))
                elif q_type == 'true_false':
                    TrueFalseQuestion.objects.create(
                        question=question,
                        correct_answer=bool(data.get('correct_answer', False)),
                        explanation=data.get('explanation', ''))
                elif q_type == 'code':
                    CodeQuestion.objects.create(
                        question=question,
                        starter_code=data.get('starter_code', ''),
                        solution_code=data.get('solution_code', ''),
                        test_cases=data.get('test_cases', []),
                        explanation=data.get('explanation', ''))
                elif q_type == 'essay':
                    EssayQuestion.objects.create(
                        question=question,
                        word_limit=int(data.get('word_limit') or 0),
                        rubric=data.get('rubric', ''),
                        sample_answer=data.get('sample_answer', ''))
                saved += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'题目 {index + 1} 导入失败: {e}'))
                rejected += 1

        self.stdout.write(self.style.SUCCESS(
            f'导入完成：{saved} 道成功，{rejected} 道跳过/失败。'
            f'请在考试管理页审核后发布。'))

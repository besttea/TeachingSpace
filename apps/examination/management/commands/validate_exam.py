"""
Validate an exam's code questions in the sandbox: run each solution against
its test cases and report per-question pass/fail. Part of the exam review
workflow (skill mode: the sandbox is the authority).

Usage:
    python manage.py validate_exam --id 3
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai_agents.training_agent import validate_exercise
from apps.examination.models import CodeQuestion, Exam, Question


class Command(BaseCommand):
    help = '在沙箱中验证一场考试的全部编程题（参考答案 vs 测试用例）'

    def add_arguments(self, parser):
        parser.add_argument('--id', type=int, required=True, help='考试 ID')

    def handle(self, *args, **options):
        exam = Exam.objects.filter(pk=options['id']).first()
        if exam is None:
            raise CommandError(f'考试不存在: {options["id"]}')

        code_questions = Question.objects.filter(
            exam=exam, question_type='code').select_related('codequestion')

        if not code_questions.count():
            self.stdout.write(self.style.SUCCESS('本考试没有编程题。'))
            return

        passed = failed = 0
        self.stdout.write(f'验证《{exam.title}》的 {code_questions.count()} 道编程题…\n')
        for question in code_questions:
            specific = question.get_specific_question()
            if not isinstance(specific, CodeQuestion):
                continue
            ok, message, _detail = validate_exercise(
                specific.solution_code, specific.test_cases)
            status = self.style.SUCCESS('PASS') if ok else self.style.ERROR('FAIL')
            if ok:
                passed += 1
            else:
                failed += 1
            self.stdout.write(
                f'  [{status}] 题目 #{question.id} {question.question_text[:40]} — {message}')

        self.stdout.write('')
        if failed:
            self.stdout.write(self.style.ERROR(
                f'结果: {passed} 通过 / {failed} 失败 —— 发布前请修复失败的题目'))
            raise CommandError(f'{failed} 道编程题验证失败')
        self.stdout.write(self.style.SUCCESS(f'结果: {passed} 道编程题全部通过'))

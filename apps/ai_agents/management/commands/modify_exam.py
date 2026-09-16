"""
AI-assisted exam question modification (skill mode: dry-run by default).

Usage:
    python manage.py modify_exam --question 42 --instruction "题干更口语化"
    python manage.py modify_exam --question 42 --instruction "..." --apply

Code questions are re-validated (solution vs test cases in the sandbox)
before applying.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.ai_agents.examination_agent import ExaminationAgent
from apps.examination.models import Question
from apps.examination.question_ai import apply_question, question_to_dict, validate_code_question


class Command(BaseCommand):
    help = 'AI 修改一道考试题（默认只预览，--apply 才保存）'

    def add_arguments(self, parser):
        parser.add_argument('--question', type=int, required=True, help='题目 ID')
        parser.add_argument('--instruction', type=str, required=True,
                            help='修改指令（自然语言）')
        parser.add_argument('--apply', action='store_true', help='保存修改')

    def handle(self, *args, **options):
        question = Question.objects.filter(pk=options['question']).first()
        if question is None:
            raise CommandError(f'题目不存在: {options["question"]}')

        agent = ExaminationAgent()
        if not agent.api_key:
            raise CommandError('AI 密钥未配置')

        current = question_to_dict(question)
        self.stdout.write(f'正在为题目 #{question.id}（{question.get_question_type_display()}）生成修改…')
        updated = agent.modify_question(current, options['instruction'])

        if not isinstance(updated, dict) or not updated.get('text'):
            raise CommandError('AI 返回的修改结果无效，请重试')

        self.stdout.write(self.style.SUCCESS('=== 修改预览 ==='))
        self.stdout.write(f'题干: {updated.get("text")[:150]}')
        if updated.get('options'):
            self.stdout.write(f'选项: {json.dumps(updated["options"], ensure_ascii=False)[:200]}')
            self.stdout.write(f'答案: {updated.get("correct_answer")}')
        if updated.get('test_cases') is not None:
            self.stdout.write(f'测试用例数: {len(updated.get("test_cases") or [])}')

        if options['apply']:
            # Sandbox validation BEFORE saving (skill-mode hard rule)
            ok, message = validate_code_question(updated)
            if not ok:
                raise CommandError(
                    f'修改后参考答案未通过测试用例（{message}）——未保存，请调整指令重试')
            apply_question(question, updated)
            self.stdout.write(self.style.SUCCESS(f'已保存修改：题目 #{question.id}'))
        else:
            self.stdout.write(self.style.WARNING(
                '未保存（干跑）。确认无误后加 --apply 应用。'))

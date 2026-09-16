"""
AI-assisted exercise modification (skill mode: dry-run by default).

Usage:
    python manage.py modify_exercises --id 3 --instruction "增加一个空列表的边界测试用例"
    python manage.py modify_exercises --id 3 --instruction "..." --apply

The proposed changes are printed for review; nothing is saved without
--apply. Before applying, the updated solution is re-validated against the
updated test cases in the sandbox (never trust the model).
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai_agents.training_agent import TrainingAgent, validate_exercise
from apps.training.models import Exercise


class Command(BaseCommand):
    help = 'AI 修改一个练习题（默认只预览，--apply 才保存）'

    def add_arguments(self, parser):
        parser.add_argument('--id', type=int, required=True, help='练习 ID')
        parser.add_argument('--instruction', type=str, required=True,
                            help='修改指令（自然语言），如"增加空列表边界用例"')
        parser.add_argument('--apply', action='store_true', help='保存修改')

    def handle(self, *args, **options):
        exercise = Exercise.objects.filter(pk=options['id']).first()
        if exercise is None:
            raise CommandError(f'练习不存在: {options["id"]}')

        agent = TrainingAgent()
        if not agent.api_key:
            raise CommandError('AI 密钥未配置')

        current = {
            'title': exercise.title,
            'description': exercise.description,
            'starter_code': exercise.starter_code,
            'solution_code': exercise.solution_code,
            'test_cases': exercise.test_cases,
            'hints': [
                {'order': h.order, 'content': h.content, 'points_penalty': h.points_penalty}
                for h in exercise.hints.all().order_by('order')
            ],
        }

        self.stdout.write(f'正在为《{exercise.title}》生成修改…')
        updated = agent.modify_exercise(current, options['instruction'])

        if not isinstance(updated, dict) or not updated.get('title'):
            raise CommandError('AI 返回的修改结果无效，请重试')

        self.stdout.write(self.style.SUCCESS('=== 修改预览 ==='))
        self.stdout.write(f'标题: {updated.get("title")}')
        self.stdout.write(f'描述: {(updated.get("description") or "")[:120]}…')
        self.stdout.write(f'测试用例数: {len(updated.get("test_cases") or [])}')
        for tc in (updated.get('test_cases') or [])[:5]:
            self.stdout.write(f'  - {tc.get("input")} → {tc.get("expected")}')
        self.stdout.write(f'提示数: {len(updated.get("hints") or [])}')

        if options['apply']:
            # Sandbox validation BEFORE saving (skill-mode hard rule)
            ok, message, _detail = validate_exercise(
                updated.get('solution_code', ''),
                updated.get('test_cases', []))
            if not ok:
                raise CommandError(f'修改后参考答案未通过测试用例（{message}）——未保存，请调整指令重试')

            exercise.title = updated.get('title', exercise.title)
            exercise.description = updated.get('description', exercise.description)
            exercise.starter_code = updated.get('starter_code', exercise.starter_code)
            exercise.solution_code = updated.get('solution_code', exercise.solution_code)
            exercise.test_cases = updated.get('test_cases', exercise.test_cases)
            exercise.save()

            exercise.hints.all().delete()
            for hint in updated.get('hints', []):
                from apps.training.models import Hint
                Hint.objects.create(
                    exercise=exercise,
                    content=hint.get('content', ''),
                    order=hint.get('order', 0),
                    points_penalty=hint.get('points_penalty', 2),
                )
            self.stdout.write(self.style.SUCCESS(
                f'已保存修改：{exercise.title}（测试用例 {message}）'))
        else:
            self.stdout.write(self.style.WARNING(
                '未保存（干跑）。确认无误后加 --apply 应用。'))

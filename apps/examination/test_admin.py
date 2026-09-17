"""Admin smoke tests: registered changelists render, the AI audit banner
shows 24h stats, and grading via admin recomputes attempt scores (T6)."""

import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from .models import (
    EssayQuestion, Exam, ExamAnswer, Question, StudentExam,
)


def _admin_url(app, model):
    return reverse(f'admin:{app}_{model}_changelist')


class AdminSmokeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            'root', 'root@example.com', 'StrongPass123!')
        self.client.force_login(self.admin)

    def test_exam_changelists_render(self):
        instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        exam = Exam.objects.create(
            title='管理测试', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, created_by=instructor)
        Question.objects.create(exam=exam, question_type='essay',
                                question_text='简述', points=5, order=0)
        for model in ('exam', 'question', 'examanswer', 'certificate',
                      'studentexam'):
            response = self.client.get(_admin_url('examination', model))
            self.assertEqual(response.status_code, 200, model)

    def test_ai_audit_changelist_shows_stats_banner(self):
        from apps.ai_agents.models import AIGenerationHistory
        AIGenerationHistory.objects.create(
            agent='test_agent', model='test-model', success=True,
            input_tokens=10, output_tokens=20, duration_ms=100)
        AIGenerationHistory.objects.create(
            agent='test_agent', model='test-model', success=False,
            input_tokens=10, output_tokens=0, duration_ms=50,
            error='boom')
        response = self.client.get(_admin_url('ai_agents', 'aigenerationhistory'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '近 24 小时调用')
        stats = response.context['ai_24h_stats']
        self.assertEqual(stats['total'], 2)
        self.assertEqual(stats['failed'], 1)
        self.assertEqual(stats['failure_rate_pct'], 50.0)

    def test_admin_has_no_write_permissions_on_ai_history(self):
        from django.contrib import admin
        from apps.ai_agents.models import AIGenerationHistory
        model_admin = admin.site._registry[AIGenerationHistory]
        self.assertFalse(model_admin.has_add_permission(request=None))
        self.assertFalse(model_admin.has_change_permission(request=None))
        self.assertFalse(model_admin.has_delete_permission(request=None))


class AdminGradingRecomputeTests(TestCase):
    """T6: saving an ExamAnswer through the admin recomputes attempt scores."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            'root2', 'root2@example.com', 'StrongPass123!')
        instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = Exam.objects.create(
            title='评阅重算', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, created_by=instructor)
        self.question = Question.objects.create(
            exam=self.exam, question_type='essay',
            question_text='简述区别', points=10, order=0)
        EssayQuestion.objects.create(question=self.question)
        self.attempt = StudentExam.objects.create(
            student=self.student, exam=self.exam, attempt_number=1,
            time_remaining_seconds=1800, score=0, is_submitted=True)
        self.answer = ExamAnswer.objects.create(
            student_exam=self.attempt, question=self.question,
            answer_data={'text': '我的答案'}, status='needs_review')
        self.client.force_login(self.admin)

    def test_grade_via_admin_save_recomputes_score(self):
        url = reverse('admin:examination_examanswer_change',
                      args=[self.answer.id])
        response = self.client.post(url, {
            'student_exam': self.attempt.id,
            'question': self.question.id,
            'answer_data': json.dumps({'text': '我的答案'}),
            'is_correct': 'on',
            'points_awarded': 10,
            'feedback': '很好',
            'graded_by': self.admin.id,
            'status': 'graded',
            '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302, response.content[:400])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, 100)

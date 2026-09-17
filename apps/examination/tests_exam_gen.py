"""Tests for the exam web flow: manual creation form and AI whole-exam
generation (task + polling endpoints + shared save helper)."""

import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from .exam_assembly import save_generated_questions
from .models import (
    CodeQuestion, EssayQuestion, Exam, MultipleChoiceQuestion, Question,
    TrueFalseQuestion,
)


def _make_user(username, user_type='instructor'):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com',
        password='StrongPass123!', user_type=user_type)


def _make_exam(creator, **kwargs):
    defaults = dict(title='AI 卷', description='x', duration_minutes=30,
                    passing_score=60, max_attempts=3, created_by=creator)
    defaults.update(kwargs)
    return Exam.objects.create(**defaults)


SAMPLE_QUESTIONS = [
    {'type': 'multiple_choice', 'text': 'Python 关键字?', 'points': 4,
     'options': {'A': 'if', 'B': 'no', 'C': 'yes', 'D': 'maybe'},
     'correct_answer': 'A', 'explanation': 'if 是关键字'},
    {'type': 'true_false', 'text': 'Python 支持多继承。', 'points': 2,
     'correct_answer': True, 'explanation': ''},
    {'type': 'code', 'text': '写函数 f', 'points': 10,
     'starter_code': '', 'solution_code': 'def f():\n    return 1',
     'test_cases': [{'input': 'f()', 'expected': 1}],
     'explanation': '', '_validated': True},
    {'type': 'essay', 'text': '描述列表与元组的区别', 'points': 6,
     'word_limit': 100, 'rubric': '准确', 'sample_answer': 'x'},
]


class ExamCreateFormTests(TestCase):
    def setUp(self):
        self.instructor = _make_user('teacher')
        self.client.force_login(self.instructor)

    def test_student_forbidden(self):
        student = _make_user('student', 'student')
        self.client.force_login(student)
        response = self.client.get(reverse('examination:exam-create'))
        self.assertEqual(response.status_code, 403)

    def test_get_renders_form(self):
        response = self.client.get(reverse('examination:exam-create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '新建考试')

    def test_post_creates_draft_exam(self):
        response = self.client.post(reverse('examination:exam-create'), {
            'title': '期中考试', 'description': '说明',
            'duration_minutes': 45, 'passing_score': 70, 'max_attempts': 2,
            'show_results_immediately': 'on',
        })
        self.assertRedirects(response, reverse('examination:exam-manage'))
        exam = Exam.objects.get(title='期中考试')
        self.assertFalse(exam.is_published)
        self.assertEqual(exam.duration_minutes, 45)
        self.assertEqual(exam.passing_score, 70)
        self.assertEqual(exam.max_attempts, 2)
        self.assertTrue(exam.show_results_immediately)
        self.assertFalse(exam.randomize_questions)  # unchecked
        self.assertEqual(exam.created_by, self.instructor)

    def test_post_missing_title_rejected(self):
        response = self.client.post(reverse('examination:exam-create'), {
            'title': '', 'duration_minutes': 45,
            'passing_score': 70, 'max_attempts': 2,
        })
        self.assertRedirects(response, reverse('examination:exam-create'))
        self.assertEqual(Exam.objects.count(), 0)

    def test_post_out_of_range_values_rejected(self):
        response = self.client.post(reverse('examination:exam-create'), {
            'title': 'x', 'duration_minutes': 9999,
            'passing_score': 150, 'max_attempts': 0,
        })
        self.assertRedirects(response, reverse('examination:exam-create'))
        self.assertEqual(Exam.objects.count(), 0)


class ExamAIGenerateTests(TestCase):
    def setUp(self):
        # The task publishes status to the shared cache — isolate per test
        # (Django TestCase rolls back the DB but not the cache).
        from django.core.cache import cache
        cache.clear()
        self.instructor = _make_user('teacher')
        self.client.force_login(self.instructor)
        self.exam = _make_exam(self.instructor)

    def _post(self, exam_id=None, **payload):
        data = dict(count=10, difficulty='intermediate')
        data.update(payload)
        return self.client.post(
            reverse('examination:exam-ai-generate',
                    args=[exam_id or self.exam.id]),
            data=json.dumps(data), content_type='application/json')

    def test_student_forbidden(self):
        student = _make_user('student', 'student')
        self.client.force_login(student)
        response = self._post()
        self.assertEqual(response.status_code, 403)

    def test_other_instructor_forbidden(self):
        other = _make_user('teacher2')
        self.client.force_login(other)
        response = self._post()
        self.assertEqual(response.status_code, 403)

    def test_non_empty_exam_rejected(self):
        Question.objects.create(exam=self.exam, question_type='true_false',
                                question_text='已有题', points=2, order=0)
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertIn('已有题目', response.json()['error'])

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=False)
    def test_unconfigured_ai_rejected(self, _mock_cfg):
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertIn('AI 服务未配置', response.json()['error'])

    def test_bad_params_rejected(self):
        response = self._post(count='not-a-number')
        self.assertEqual(response.status_code, 400)

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExamSkill')
    def test_eager_generation_saves_questions(self, mock_skill, _mock_cfg):
        mock_skill.return_value.run.return_value = {
            'questions': SAMPLE_QUESTIONS,
            'code_validated': '1/1',
        }
        response = self._post(count=4)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertFalse(body['queued'])  # dev eager mode
        self.assertEqual(body['status']['status'], 'done')
        self.assertEqual(body['status']['saved'], 4)

        self.assertEqual(self.exam.questions.count(), 4)
        self.assertEqual(MultipleChoiceQuestion.objects.count(), 1)
        self.assertEqual(TrueFalseQuestion.objects.count(), 1)
        self.assertEqual(CodeQuestion.objects.count(), 1)
        self.assertEqual(EssayQuestion.objects.count(), 1)

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExamSkill')
    def test_eager_generation_failure_publishes_error(self, mock_skill, _mock_cfg):
        mock_skill.return_value.run.side_effect = RuntimeError('boom')
        response = self._post()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['status']['status'], 'error')
        self.assertIn('boom', body['status']['error'])
        self.assertEqual(self.exam.questions.count(), 0)

    def test_status_endpoint_permission(self):
        student = _make_user('student', 'student')
        self.client.force_login(student)
        response = self.client.get(reverse(
            'examination:exam-ai-status', args=[self.exam.id]))
        self.assertEqual(response.status_code, 403)

    def test_status_endpoint_none_state(self):
        response = self.client.get(reverse(
            'examination:exam-ai-status', args=[self.exam.id]))
        self.assertEqual(response.json()['status']['status'], 'none')

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExamSkill')
    def test_status_endpoint_after_done_reports_count(self, mock_skill, _mock_cfg):
        mock_skill.return_value.run.return_value = {
            'questions': SAMPLE_QUESTIONS,
            'code_validated': '1/1',
        }
        self._post(count=4)
        response = self.client.get(reverse(
            'examination:exam-ai-status', args=[self.exam.id]))
        body = response.json()
        self.assertEqual(body['status']['status'], 'done')
        self.assertEqual(body['status']['question_count'], 4)


class SaveGeneratedQuestionsTests(TestCase):
    def setUp(self):
        self.instructor = _make_user('teacher')
        self.exam = _make_exam(self.instructor)

    def test_saves_all_four_types(self):
        summary = save_generated_questions(self.exam, SAMPLE_QUESTIONS)
        self.assertEqual(summary['saved'], 4)
        self.assertEqual(summary['skipped'], 0)
        self.assertEqual(summary['code_validated'], '1/1')
        self.assertEqual(self.exam.questions.count(), 4)

    def test_skips_bad_rows_without_raising(self):
        summary = save_generated_questions(self.exam, [
            {'type': 'nonsense', 'text': 'x', 'points': 1},
            {'type': 'multiple_choice', 'text': 'ok?', 'points': 'not-int'},
        ])
        self.assertEqual(summary['saved'], 0)
        self.assertEqual(summary['skipped'], 2)
        self.assertEqual(self.exam.questions.count(), 0)

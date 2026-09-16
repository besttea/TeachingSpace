"""Tests for the examination app: true/false question accessor (P0-10)
and the certificate flow (download / verification / failed attempts)."""

import json
import tempfile

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from .models import (
    Certificate, CodeQuestion, Exam, MultipleChoiceQuestion, Question,
    StudentExam, TrueFalseQuestion,
)

_MEDIA_TMP = tempfile.mkdtemp(prefix='cert_test_')


class TrueFalseAccessorTests(TestCase):
    """P0-10 regression: get_specific_question() must find T/F questions."""

    def setUp(self):
        instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.exam = Exam.objects.create(
            title='TF 测试', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, is_published=True,
            created_by=instructor)

    def test_truefalse_accessor_returns_specific_question(self):
        q = Question.objects.create(
            exam=self.exam, question_type='true_false',
            question_text='Python 是动态类型语言。', points=2, order=0)
        tf = TrueFalseQuestion.objects.create(question=q, correct_answer=True)
        self.assertEqual(q.get_specific_question(), tf)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class CertificateTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher2', email='t2@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = Exam.objects.create(
            title='Python 基础测验', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, is_published=True,
            created_by=self.instructor)
        self.client.force_login(self.student)

    def _attempt(self, score):
        return StudentExam.objects.create(
            student=self.student, exam=self.exam, attempt_number=1,
            time_remaining_seconds=1800, score=score, is_submitted=True)

    def test_passing_attempt_downloads_pdf(self):
        attempt = self._attempt(score=85)
        response = self.client.get(
            reverse('examination:exam-certificate', args=[attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        # FileResponse streams — join the streamed chunks to check the PDF magic
        body = b''.join(response.streaming_content)
        self.assertTrue(body.startswith(b'%PDF'))

        certificate = Certificate.objects.get(student_exam=attempt)
        self.assertEqual(len(certificate.verification_code), 32)
        self.assertTrue(certificate.certificate_pdf.name.startswith('certificates/'))

    def test_verification_page_shows_student(self):
        attempt = self._attempt(score=85)
        self.client.get(reverse('examination:exam-certificate', args=[attempt.id]))
        certificate = Certificate.objects.get(student_exam=attempt)

        response = self.client.get(
            reverse('examination:certificate-verify',
                    args=[certificate.verification_code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '证书验证通过')
        self.assertContains(response, 'student')

    def test_invalid_code_shows_failure(self):
        response = self.client.get(
            reverse('examination:certificate-verify', args=['0' * 32]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '证书验证失败')

    def test_failed_attempt_cannot_download(self):
        attempt = self._attempt(score=45)
        response = self.client.get(
            reverse('examination:exam-certificate', args=[attempt.id]))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Certificate.objects.filter(student_exam=attempt).exists())

    def test_certificate_is_reused_on_second_download(self):
        attempt = self._attempt(score=90)
        url = reverse('examination:exam-certificate', args=[attempt.id])
        first = self.client.get(url)
        second = self.client.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        # one certificate, one stable verification code
        self.assertEqual(Certificate.objects.filter(student_exam=attempt).count(), 1)


class QuestionAIModifyAndValidateTests(TestCase):
    """AI question modification endpoint + validate_exam command."""

    def setUp(self):
        from unittest import mock as _mock
        self.instructor = User.objects.create_user(
            username='exam_mod_teacher', email='emt@example.com',
            password='StrongPass123!', user_type='instructor')
        self.other = User.objects.create_user(
            username='exam_mod_other', email='emo@example.com',
            password='StrongPass123!', user_type='instructor')
        self.exam = Exam.objects.create(
            title='修改测试', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, is_published=False,
            created_by=self.instructor)
        self.question = Question.objects.create(
            exam=self.exam, question_type='multiple_choice',
            question_text='旧题干', points=5, order=0)
        MultipleChoiceQuestion.objects.create(
            question=self.question,
            options={'A': '1', 'B': '2'}, correct_answer='A')

        patcher = _mock.patch('apps.ai_agents.examination_agent.ExaminationAgent.modify_question')
        self.mock_modify = patcher.start()
        self.addCleanup(patcher.stop)
        patcher2 = _mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
        patcher2.start()
        self.addCleanup(patcher2.stop)

    def test_preview_and_apply(self):
        self.mock_modify.return_value = {
            'type': 'multiple_choice', 'text': '新题干', 'points': 5,
            'options': {'A': '1', 'B': '2'}, 'correct_answer': 'A',
        }
        self.client.force_login(self.instructor)
        url = reverse('examination:question-ai-modify', args=[self.question.id])
        response = self.client.post(
            url, data=json.dumps({'instruction': '更口语化', 'apply': False}),
            content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()['applied'])
        self.assertIn('新题干', response.json()['preview']['text'])

        response = self.client.post(
            url, data=json.dumps({'instruction': '更口语化', 'apply': True}),
            content_type='application/json')
        self.assertTrue(response.json()['applied'])
        self.question.refresh_from_db()
        self.assertEqual(self.question.question_text, '新题干')

    def test_non_creator_forbidden(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('examination:question-ai-modify', args=[self.question.id]),
            data=json.dumps({'instruction': 'x', 'apply': False}),
            content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_validate_exam_command(self):
        from django.core.management import call_command
        from io import StringIO

        code_q = Question.objects.create(
            exam=self.exam, question_type='code', question_text='写 add', points=10, order=1)
        CodeQuestion.objects.create(
            question=code_q,
            solution_code='def add(a, b):\n    return a + b',
            test_cases=[{'input': 'add(1, 2)', 'expected': 3}])

        # valid exam → no exception
        out = StringIO()
        call_command('validate_exam', id=self.exam.id, stdout=out)
        self.assertIn('全部通过', out.getvalue())

        # broken solution → CommandError
        code_q.codequestion.solution_code = 'def add(a, b):\n    return 0'
        code_q.codequestion.save()
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('validate_exam', id=self.exam.id)

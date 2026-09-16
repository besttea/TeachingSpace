"""Tests for the examination app: true/false question accessor (P0-10)
and the certificate flow (download / verification / failed attempts)."""

import tempfile

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from .models import Certificate, Exam, Question, StudentExam, TrueFalseQuestion

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

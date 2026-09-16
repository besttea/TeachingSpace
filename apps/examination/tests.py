"""Tests for the examination app: true/false question accessor (P0-10)
and the certificate flow (download / verification / failed attempts)."""

import json
import tempfile

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from .models import (
    Certificate, CodeQuestion, Exam, ExamAnswer, MultipleChoiceQuestion,
    Question, StudentExam, TrueFalseQuestion,
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


class ScoreRecomputeTests(TestCase):
    """T6: recompute_exam_scores updates submitted attempts after grading changes."""

    def test_recompute_updates_scores(self):
        from .question_ai import recompute_exam_scores

        instructor = User.objects.create_user(
            username='recalc_teacher', email='rt@example.com',
            password='StrongPass123!', user_type='instructor')
        student = User.objects.create_user(
            username='recalc_student', email='rs@example.com',
            password='StrongPass123!', user_type='student')
        exam = Exam.objects.create(
            title='重算测试', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, is_published=True,
            created_by=instructor)
        question = Question.objects.create(
            exam=exam, question_type='multiple_choice',
            question_text='Q', points=10, order=0)
        attempt = StudentExam.objects.create(
            student=student, exam=exam, attempt_number=1,
            time_remaining_seconds=100, score=100, is_submitted=True)
        answer = ExamAnswer.objects.create(
            student_exam=attempt, question=question,
            answer_data={'selected': 'A'}, points_awarded=10, is_correct=True)

        # manual regrade: award only 5 points → score must change from 100 to 50
        answer.points_awarded = 5
        answer.save()
        updated = recompute_exam_scores(exam)
        self.assertEqual(updated, 1)
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 50)


class EssayReviewTests(TestCase):
    """T16: instructor essay grading endpoint with score recompute."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            username='review_teacher', email='rvt@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='review_student', email='rvs@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = Exam.objects.create(
            title='评阅测试', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, is_published=True,
            created_by=self.instructor)
        self.essay_q = Question.objects.create(
            exam=self.exam, question_type='essay',
            question_text='解释列表与元组的区别', points=10, order=0)
        self.attempt = StudentExam.objects.create(
            student=self.student, exam=self.exam, attempt_number=1,
            time_remaining_seconds=100, score=0, is_submitted=True)
        self.answer = ExamAnswer.objects.create(
            student_exam=self.attempt, question=self.essay_q,
            answer_data={'text': '列表可变，元组不可变'},
            status='needs_review', points_awarded=None)

    def test_grade_answer_recomputes_score(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('examination:answer-grade', args=[self.answer.id]),
            data=json.dumps({'points': 8, 'feedback': '答到要点'}),
            content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.answer.refresh_from_db()
        self.assertEqual(self.answer.points_awarded, 8)
        self.assertEqual(self.answer.status, 'graded')
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, 80)  # 8/10

    def test_points_beyond_max_rejected(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('examination:answer-grade', args=[self.answer.id]),
            data=json.dumps({'points': 99}),
            content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_non_creator_forbidden(self):
        other = User.objects.create_user(
            username='review_other', email='rvo@example.com',
            password='StrongPass123!', user_type='instructor')
        self.client.force_login(other)
        response = self.client.post(
            reverse('examination:answer-grade', args=[self.answer.id]),
            data=json.dumps({'points': 5}),
            content_type='application/json')
        self.assertEqual(response.status_code, 403)


class QuestionEditTests(TestCase):
    """Manual question editing form (all four types route through apply_question)."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            username='qedit_teacher', email='qet@example.com',
            password='StrongPass123!', user_type='instructor')
        self.exam = Exam.objects.create(
            title='编辑测试', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, is_published=False,
            created_by=self.instructor)
        self.question = Question.objects.create(
            exam=self.exam, question_type='multiple_choice',
            question_text='旧题干', points=5, order=0)
        MultipleChoiceQuestion.objects.create(
            question=self.question,
            options={'A': '1', 'B': '2', 'C': '3', 'D': '4'}, correct_answer='A')

    def test_edit_page_renders_with_prefill(self):
        self.client.force_login(self.instructor)
        response = self.client.get(
            reverse('examination:question-edit', args=[self.question.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '旧题干')
        self.assertContains(response, '选项 A')

    def test_edit_updates_question(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('examination:question-edit', args=[self.question.id]),
            {'text': '新题干', 'points': '8',
             'option_a': '甲', 'option_b': '乙', 'option_c': '丙', 'option_d': '丁',
             'correct_answer': 'B', 'explanation': '解析'})
        self.assertEqual(response.status_code, 302)
        self.question.refresh_from_db()
        self.assertEqual(self.question.question_text, '新题干')
        self.assertEqual(self.question.points, 8)
        specific = self.question.get_specific_question()
        self.assertEqual(specific.options['B'], '乙')
        self.assertEqual(specific.correct_answer, 'B')

    def test_invalid_answer_key_rejected(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('examination:question-edit', args=[self.question.id]),
            {'text': 'x', 'points': '5',
             'option_a': '1', 'option_b': '2', 'option_c': '3', 'option_d': '4',
             'correct_answer': 'Z'})
        self.assertEqual(response.status_code, 302)  # back to form with error
        self.question.refresh_from_db()
        self.assertEqual(self.question.question_text, '旧题干')  # unchanged

    def test_student_forbidden(self):
        student = User.objects.create_user(
            username='qedit_student', email='qes@example.com',
            password='StrongPass123!', user_type='student')
        self.client.force_login(student)
        response = self.client.get(
            reverse('examination:question-edit', args=[self.question.id]))
        self.assertEqual(response.status_code, 403)


class ExamSubmissionIntegrationTests(TestCase):
    """End-to-end: attempt → answers → submit → grading (real sandbox) → score."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            username='flow_teacher', email='flt@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='flow_student', email='fls@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = Exam.objects.create(
            title='全流程测试', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, is_published=True,
            created_by=self.instructor, show_results_immediately=True)

        mc_q = Question.objects.create(
            exam=self.exam, question_type='multiple_choice',
            question_text='2+2=?', points=20, order=0)
        MultipleChoiceQuestion.objects.create(
            question=mc_q, options={'A': '3', 'B': '4', 'C': '5', 'D': '6'},
            correct_answer='B')
        self.mc_q = mc_q

        code_q = Question.objects.create(
            exam=self.exam, question_type='code',
            question_text='写 add', points=80, order=1)
        CodeQuestion.objects.create(
            question=code_q,
            solution_code='def add(a, b):\n    return a + b',
            test_cases=[{'input': 'add(1, 2)', 'expected': 3}])
        self.code_q = code_q

    def _start_attempt(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse('examination:exam-start', args=[self.exam.id]))
        self.assertEqual(response.status_code, 302)
        attempt = StudentExam.objects.get(
            student=self.student, exam=self.exam, is_submitted=False)
        return attempt

    def _save_answer(self, attempt, question, answer_data):
        return self.client.post(
            reverse('examination:save-answer'),
            data=json.dumps({
                'student_exam_id': attempt.id,
                'question_id': question.id,
                'answer_data': answer_data,
            }), content_type='application/json')

    def test_full_flow_grades_and_scores(self):
        attempt = self._start_attempt()

        self._save_answer(attempt, self.mc_q, {'selected': 'B'})
        self._save_answer(attempt, self.code_q,
                          {'code': 'def add(a, b):\n    return a + b'})

        response = self.client.post(
            reverse('examination:submit-exam'),
            data=json.dumps({'student_exam_id': attempt.id}),
            content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['score'], 100)  # 20 (MC) + 80 (code, 1/1 tests)
        self.assertTrue(data['is_passing'])

        attempt.refresh_from_db()
        self.assertTrue(attempt.is_submitted)
        # code answer graded with the real sandbox
        code_answer = ExamAnswer.objects.get(
            student_exam=attempt, question=self.code_q)
        self.assertEqual(code_answer.status, 'graded')
        self.assertEqual(code_answer.points_awarded, 80)

    def test_resubmit_blocked(self):
        attempt = self._start_attempt()
        self.client.post(
            reverse('examination:submit-exam'),
            data=json.dumps({'student_exam_id': attempt.id}),
            content_type='application/json')
        response = self.client.post(
            reverse('examination:submit-exam'),
            data=json.dumps({'student_exam_id': attempt.id}),
            content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('已提交', response.json()['error'])

    def test_wrong_code_solution_scores_zero(self):
        attempt = self._start_attempt()
        self._save_answer(attempt, self.code_q, {'code': 'def add(a, b):\n    return 0'})
        response = self.client.post(
            reverse('examination:submit-exam'),
            data=json.dumps({'student_exam_id': attempt.id}),
            content_type='application/json')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['score'], 0)


class QuestionBankImportExportTests(TestCase):
    """Round-trip: export exam questions to JSON, import into another exam."""

    def setUp(self):
        from django.core.management import call_command
        from io import StringIO

        self.call_command = call_command
        self.out = StringIO

    def test_round_trip(self):
        instructor = User.objects.create_user(
            username='bank_teacher', email='bkt@example.com',
            password='StrongPass123!', user_type='instructor')
        exam_a = Exam.objects.create(
            title='题库A', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, is_published=False,
            created_by=instructor)
        q = Question.objects.create(
            exam=exam_a, question_type='multiple_choice',
            question_text='1+1=?', points=5, order=0)
        MultipleChoiceQuestion.objects.create(
            question=q, options={'A': '1', 'B': '2', 'C': '3', 'D': '4'},
            correct_answer='B', explanation='基础')
        code_q = Question.objects.create(
            exam=exam_a, question_type='code',
            question_text='写 add', points=10, order=1)
        CodeQuestion.objects.create(
            question=code_q,
            solution_code='def add(a, b):\n    return a + b',
            test_cases=[{'input': 'add(1, 2)', 'expected': 3}])

        exam_b = Exam.objects.create(
            title='题库B', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, is_published=False,
            created_by=instructor)

        import json as _json
        import tempfile
        import os

        bank = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8')
        bank.close()
        self.call_command('export_exam_questions', exam_id=exam_a.id,
                          output=bank.name, stdout=self.out())

        self.call_command('import_exam_questions', exam_id=exam_b.id,
                          file=bank.name, stdout=self.out())
        os.unlink(bank.name)

        self.assertEqual(exam_b.questions.count(), 2)
        imported_mc = Question.objects.get(exam=exam_b, question_type='multiple_choice')
        self.assertEqual(imported_mc.get_specific_question().correct_answer, 'B')
        imported_code = Question.objects.get(exam=exam_b, question_type='code')
        self.assertEqual(
            imported_code.get_specific_question().test_cases,
            [{'input': 'add(1, 2)', 'expected': 3}])

    def test_import_rejects_broken_code_question(self):
        import json as _json
        import tempfile
        import os

        instructor = User.objects.create_user(
            username='bank_teacher2', email='bkt2@example.com',
            password='StrongPass123!', user_type='instructor')
        exam = Exam.objects.create(
            title='题库C', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, is_published=False,
            created_by=instructor)
        bank = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8')
        _json.dump({'questions': [{
            'type': 'code', 'text': 'bad', 'points': 10,
            'solution_code': 'def f():\n    return 0',
            'test_cases': [{'input': 'f()', 'expected': 1}],
        }]}, bank)
        bank.close()

        self.call_command('import_exam_questions', exam_id=exam.id,
                          file=bank.name, stdout=self.out())
        os.unlink(bank.name)
        self.assertEqual(exam.questions.count(), 0)  # rejected by sandbox

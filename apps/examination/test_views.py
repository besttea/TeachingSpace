"""View coverage for the examination app: list/detail/start/take/save/submit
flows, publish controls and results (OPTIMIZATION_PLAN 6.5 coverage gate)."""

import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentProfile, User
from .models import (
    CodeQuestion, EssayQuestion, Exam, ExamAnswer, MultipleChoiceQuestion,
    Question, StudentExam, TrueFalseQuestion,
)


def _make_exam(instructor, **kwargs):
    defaults = dict(title='视图测试考试', description='x', duration_minutes=30,
                    passing_score=60, max_attempts=3, is_published=True,
                    created_by=instructor)
    defaults.update(kwargs)
    return Exam.objects.create(**defaults)


def _make_attempt(student, exam, **kwargs):
    defaults = dict(student=student, exam=exam, attempt_number=1,
                    time_remaining_seconds=1800)
    defaults.update(kwargs)
    return StudentExam.objects.create(**defaults)


def _add_mc(exam, order=0, points=4):
    q = Question.objects.create(exam=exam, question_type='multiple_choice',
                                question_text='MC?', points=points, order=order)
    MultipleChoiceQuestion.objects.create(
        question=q, options={'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd'},
        correct_answer='A')
    return q


def _add_tf(exam, order=1, points=2):
    q = Question.objects.create(exam=exam, question_type='true_false',
                                question_text='TF?', points=points, order=order)
    TrueFalseQuestion.objects.create(question=q, correct_answer=True)
    return q


def _add_code(exam, order=2, points=10):
    q = Question.objects.create(exam=exam, question_type='code',
                                question_text='CODE?', points=points, order=order)
    CodeQuestion.objects.create(
        question=q, starter_code='', solution_code='',
        test_cases=[{'input': 'f()', 'expected': 1}])
    return q


def _add_essay(exam, order=3, points=5):
    q = Question.objects.create(exam=exam, question_type='essay',
                                question_text='ESSAY?', points=points, order=order)
    EssayQuestion.objects.create(question=q, word_limit=100,
                                 rubric='准确', sample_answer='x')
    return q


class ExamBrowseTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.published = _make_exam(self.instructor, title='已发布')
        self.draft = _make_exam(self.instructor, title='草稿', is_published=False)
        _add_mc(self.published)

    def test_list_shows_only_published_for_student(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('examination:exam-list'))
        self.assertContains(response, '已发布')
        self.assertNotContains(response, '草稿')

    def test_list_includes_attempt_counts(self):
        self.client.force_login(self.student)
        _make_attempt(self.student, self.published, is_submitted=True)
        response = self.client.get(reverse('examination:exam-list'))
        exam_row = response.context['exams'][0]
        self.assertEqual(exam_row.user_attempts, 1)
        self.assertTrue(exam_row.can_attempt)

    def test_detail_hides_draft_from_student(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('examination:exam-detail',
                                           args=[self.draft.id]))
        self.assertEqual(response.status_code, 404)

    def test_detail_visible_to_creator(self):
        self.client.force_login(self.instructor)
        response = self.client.get(reverse('examination:exam-detail',
                                           args=[self.draft.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '草稿')

    def test_detail_draft_hidden_from_other_instructor(self):
        stranger = User.objects.create_user(
            username='stranger', email='str@example.com',
            password='StrongPass123!', user_type='instructor')
        self.client.force_login(stranger)
        response = self.client.get(reverse('examination:exam-detail',
                                           args=[self.draft.id]))
        self.assertEqual(response.status_code, 404)

    def test_detail_context_sums_points_and_attempts(self):
        self.client.force_login(self.student)
        _add_tf(self.published)
        response = self.client.get(reverse('examination:exam-detail',
                                           args=[self.published.id]))
        context = response.context
        self.assertEqual(context['total_points'], 6)
        self.assertEqual(context['question_count'], 2)
        self.assertEqual(context['attempt_count'], 0)
        self.assertTrue(context['can_attempt'])

    def test_detail_shows_ongoing_attempt(self):
        self.client.force_login(self.student)
        ongoing = _make_attempt(self.student, self.published)
        response = self.client.get(reverse('examination:exam-detail',
                                           args=[self.published.id]))
        self.assertEqual(response.context['ongoing_attempt'], ongoing)


class StartExamTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = _make_exam(self.instructor)
        self.client.force_login(self.student)

    def test_start_creates_attempt_and_redirects(self):
        response = self.client.post(reverse('examination:exam-start',
                                            args=[self.exam.id]))
        attempt = StudentExam.objects.get(student=self.student, exam=self.exam)
        self.assertRedirects(response, reverse(
            'examination:exam-take',
            args=[self.exam.id, attempt.id]), fetch_redirect_response=False)
        self.assertEqual(attempt.time_remaining_seconds, 30 * 60)

    def test_start_respects_max_attempts(self):
        _make_attempt(self.student, self.exam, attempt_number=1, is_submitted=True)
        _make_attempt(self.student, self.exam, attempt_number=2, is_submitted=True)
        _make_attempt(self.student, self.exam, attempt_number=3, is_submitted=True)
        response = self.client.post(reverse('examination:exam-start',
                                            args=[self.exam.id]))
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {
            'success': False,
            'error': '您已达到最大尝试次数 (3)',
        })

    def test_start_resumes_ongoing_attempt(self):
        ongoing = _make_attempt(self.student, self.exam)
        response = self.client.post(reverse('examination:exam-start',
                                            args=[self.exam.id]))
        self.assertRedirects(response, reverse(
            'examination:exam-take', args=[self.exam.id, ongoing.id]),
            fetch_redirect_response=False)
        self.assertEqual(StudentExam.objects.count(), 1)

    def test_start_unpublished_404(self):
        self.exam.is_published = False
        self.exam.save()
        response = self.client.post(reverse('examination:exam-start',
                                            args=[self.exam.id]))
        self.assertEqual(response.status_code, 404)


class TakeExamTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = _make_exam(self.instructor, randomize_questions=True)
        _add_mc(self.exam, order=0)
        _add_tf(self.exam, order=1)
        _add_code(self.exam, order=2)
        _add_essay(self.exam, order=3)
        self.client.force_login(self.student)
        self.attempt = _make_attempt(self.student, self.exam)

    def test_interface_renders_all_question_types(self):
        response = self.client.get(reverse(
            'examination:exam-take', args=[self.exam.id, self.attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'MC?')
        self.assertContains(response, 'TF?')
        self.assertContains(response, 'CODE?')
        self.assertContains(response, 'ESSAY?')

    def test_take_draft_404_for_student(self):
        self.exam.is_published = False
        self.exam.save()
        response = self.client.get(reverse(
            'examination:exam-take', args=[self.exam.id, self.attempt.id]))
        self.assertEqual(response.status_code, 404)

    def test_take_draft_allowed_for_staff(self):
        self.exam.is_published = False
        self.exam.save()
        admin = User.objects.create_user(
            username='admin2', email='a2@example.com',
            password='StrongPass123!', user_type='admin', is_staff=True)
        self.client.force_login(admin)
        response = self.client.get(reverse(
            'examination:exam-take', args=[self.exam.id, self.attempt.id]))
        self.assertEqual(response.status_code, 200)

    def test_submitted_attempt_redirects_to_results(self):
        self.attempt.is_submitted = True
        self.attempt.save()
        response = self.client.get(reverse(
            'examination:exam-take', args=[self.exam.id, self.attempt.id]))
        self.assertRedirects(response, reverse(
            'examination:exam-results', args=[self.attempt.id]),
            fetch_redirect_response=False)

    def test_randomization_is_stable_per_attempt(self):
        url = reverse('examination:exam-take',
                      args=[self.exam.id, self.attempt.id])
        first = self.client.get(url)
        second = self.client.get(url)
        ids_first = [q['question'].id for q in first.context['questions']]
        ids_second = [q['question'].id for q in second.context['questions']]
        self.assertEqual(ids_first, ids_second)
        self.assertEqual(sorted(ids_first),
                         list(Question.objects.values_list('id', flat=True)))

    def test_existing_answers_passed_to_context(self):
        mc = Question.objects.get(question_text='MC?')
        ExamAnswer.objects.create(
            student_exam=self.attempt, question=mc,
            answer_data={'selected': 'A'})
        response = self.client.get(reverse(
            'examination:exam-take', args=[self.exam.id, self.attempt.id]))
        by_id = {q['question'].id: q['existing_answer']
                 for q in response.context['questions']}
        self.assertIsNotNone(by_id[mc.id])


class SaveAnswerTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.other = User.objects.create_user(
            username='other', email='o@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = _make_exam(self.instructor)
        self.question = _add_mc(self.exam)
        self.client.force_login(self.student)
        self.attempt = _make_attempt(self.student, self.exam)

    def _post(self, **payload):
        return self.client.post(
            reverse('examination:save-answer'),
            data=json.dumps(payload), content_type='application/json')

    def test_save_creates_and_updates_answer(self):
        response = self._post(student_exam_id=self.attempt.id,
                              question_id=self.question.id,
                              answer_data={'selected': 'B'})
        self.assertEqual(response.status_code, 200)
        answer = ExamAnswer.objects.get(student_exam=self.attempt)
        self.assertEqual(answer.answer_data, {'selected': 'B'})

        response = self._post(student_exam_id=self.attempt.id,
                              question_id=self.question.id,
                              answer_data={'selected': 'C'})
        self.assertEqual(response.status_code, 200)
        answer.refresh_from_db()
        self.assertEqual(answer.answer_data, {'selected': 'C'})
        self.assertEqual(ExamAnswer.objects.count(), 1)

    def test_save_rejects_non_dict_payload(self):
        response = self._post(student_exam_id=self.attempt.id,
                              question_id=self.question.id,
                              answer_data='not-a-dict')
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {
            'success': False, 'error': '答案格式无效'})

    def test_save_rejects_oversized_payload(self):
        response = self._post(student_exam_id=self.attempt.id,
                              question_id=self.question.id,
                              answer_data={'blob': 'x' * 110_000})
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {
            'success': False, 'error': '答案内容过长'})

    def test_save_after_timeout_rejected(self):
        StudentExam.objects.filter(pk=self.attempt.pk).update(
            start_time=timezone.now() - timedelta(hours=1))
        response = self._post(student_exam_id=self.attempt.id,
                              question_id=self.question.id,
                              answer_data={'selected': 'A'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('考试时间已结束', response.json()['error'])

    def test_save_wrong_student_404(self):
        self.client.force_login(self.other)
        response = self._post(student_exam_id=self.attempt.id,
                              question_id=self.question.id,
                              answer_data={'selected': 'A'})
        self.assertEqual(response.status_code, 404)

    def test_save_wrong_question_404(self):
        other_exam = _make_exam(self.instructor, title='别的考试')
        foreign = _add_mc(other_exam, order=9)
        response = self._post(student_exam_id=self.attempt.id,
                              question_id=foreign.id,
                              answer_data={'selected': 'A'})
        self.assertEqual(response.status_code, 404)


class SubmitExamTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = _make_exam(self.instructor)
        _add_mc(self.exam, points=4)
        _add_tf(self.exam, points=2)
        _add_essay(self.exam, points=5)
        self.client.force_login(self.student)
        self.attempt = _make_attempt(self.student, self.exam)

    def _submit(self, attempt_id=None):
        return self.client.post(
            reverse('examination:submit-exam'),
            data=json.dumps({'student_exam_id': attempt_id or self.attempt.id}),
            content_type='application/json')

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=False)
    def test_submit_grades_mc_tf_and_essay_needs_review(self, _mock_cfg):
        mc = Question.objects.get(question_text='MC?')
        tf = Question.objects.get(question_text='TF?')
        essay = Question.objects.get(question_text='ESSAY?')
        ExamAnswer.objects.create(student_exam=self.attempt, question=mc,
                                  answer_data={'selected': 'A'})
        ExamAnswer.objects.create(student_exam=self.attempt, question=tf,
                                  answer_data={'selected': True})
        ExamAnswer.objects.create(student_exam=self.attempt, question=essay,
                                  answer_data={'text': '我的答案'})

        response = self._submit()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['score'], 54)  # (4 + 2 + 0) / 11
        self.assertFalse(body['is_passing'])
        self.attempt.refresh_from_db()
        self.assertTrue(self.attempt.is_submitted)
        self.assertEqual(self.attempt.score, 54)

        mc_answer = ExamAnswer.objects.get(student_exam=self.attempt,
                                           question=mc)
        self.assertTrue(mc_answer.is_correct)
        essay_answer = ExamAnswer.objects.get(student_exam=self.attempt,
                                              question=essay)
        self.assertEqual(essay_answer.status, 'needs_review')

    def test_submit_unknown_attempt_400(self):
        response = self._submit(attempt_id=9999)
        self.assertEqual(response.status_code, 400)

    def test_submit_someone_elses_attempt_400(self):
        other = User.objects.create_user(
            username='other2', email='o2@example.com',
            password='StrongPass123!', user_type='student')
        attempt = _make_attempt(other, self.exam)
        response = self._submit(attempt_id=attempt.id)
        self.assertEqual(response.status_code, 400)

    def test_passing_submit_updates_student_profile(self):
        profile = StudentProfile.objects.create(user=self.student)
        mc = Question.objects.get(question_text='MC?')
        tf = Question.objects.get(question_text='TF?')
        ExamAnswer.objects.create(student_exam=self.attempt, question=mc,
                                  answer_data={'selected': 'A'})
        ExamAnswer.objects.create(student_exam=self.attempt, question=tf,
                                  answer_data={'selected': True})
        # essay is left ungraded (0), so 6/11 < 60 — make it pass instead
        exam = _make_exam(self.instructor, title='能过', passing_score=50)
        _add_mc(exam, points=4)
        _add_tf(exam, points=2)
        attempt = _make_attempt(self.student, exam, attempt_number=2)
        for question in exam.questions.all():
            ExamAnswer.objects.create(
                student_exam=attempt, question=question,
                answer_data={'selected': 'A'}
                if question.question_type == 'multiple_choice'
                else {'selected': True})

        response = self._submit(attempt_id=attempt.id)
        self.assertTrue(response.json()['is_passing'])
        profile.refresh_from_db()
        self.assertEqual(profile.total_exams_passed, 1)


class ExamResultsTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = _make_exam(self.instructor)
        _add_mc(self.exam)
        self.client.force_login(self.student)

    def test_unsubmitted_attempt_404(self):
        attempt = _make_attempt(self.student, self.exam)
        response = self.client.get(reverse('examination:exam-results',
                                           args=[attempt.id]))
        self.assertEqual(response.status_code, 404)

    def test_results_compute_points_and_hide_details(self):
        self.exam.show_results_immediately = False
        self.exam.save()
        attempt = _make_attempt(self.student, self.exam, score=80,
                                is_submitted=True)
        question = Question.objects.get(question_text='MC?')
        ExamAnswer.objects.create(
            student_exam=attempt, question=question, is_correct=True,
            points_awarded=4, status='graded',
            answer_data={'selected': 'A'})
        response = self.client.get(reverse('examination:exam-results',
                                           args=[attempt.id]))
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertEqual(context['total_points'], 4)
        self.assertEqual(context['earned_points'], 4)
        self.assertTrue(context['is_passing'])
        self.assertFalse(context['show_details'])
        self.assertIsNone(context['certificate'])

    def test_results_show_details_when_allowed(self):
        attempt = _make_attempt(self.student, self.exam, score=80,
                                is_submitted=True)
        response = self.client.get(reverse('examination:exam-results',
                                           args=[attempt.id]))
        self.assertTrue(response.context['show_details'])


class InstructorConsoleTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = _make_exam(self.instructor)

    def test_console_forbids_students(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('examination:exam-manage'))
        self.assertEqual(response.status_code, 403)

    def test_console_lists_own_exams(self):
        self.client.force_login(self.instructor)
        response = self.client.get(reverse('examination:exam-manage'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.exam, response.context['exams'])

    def test_publish_toggles_state(self):
        self.client.force_login(self.instructor)
        url = reverse('examination:exam-publish', args=[self.exam.id])
        response = self.client.post(url, {'action': 'unpublish'})
        self.assertJSONEqual(response.content, {
            'success': True, 'is_published': False, 'message': '考试已下线为草稿'})
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_published)
        response = self.client.post(url, {'action': 'publish'})
        self.assertTrue(response.json()['is_published'])
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.is_published)

    def test_publish_forbidden_for_non_creator(self):
        other = User.objects.create_user(
            username='other3', email='o3@example.com',
            password='StrongPass123!', user_type='instructor')
        self.client.force_login(other)
        response = self.client.post(reverse('examination:exam-publish',
                                            args=[self.exam.id]))
        self.assertEqual(response.status_code, 403)

    def test_publish_unknown_404(self):
        self.client.force_login(self.instructor)
        response = self.client.post(reverse('examination:exam-publish',
                                            args=[9999]))
        self.assertEqual(response.status_code, 404)

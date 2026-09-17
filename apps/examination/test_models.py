"""Model-layer misc coverage for examination: __str__ hooks, remaining-time
end_time branch, auto-grade branches (MC wrong answer, TF string forms,
essay needs_review) and certificate validation (OPTIMIZATION_PLAN 6.5)."""

from django.test import TestCase

from apps.accounts.models import User
from .models import (
    Certificate, Exam, ExamAnswer, MultipleChoiceQuestion, Question,
    StudentExam, TrueFalseQuestion,
)


def _setup():
    instructor = User.objects.create_user(
        username='teacher', email='t@example.com',
        password='StrongPass123!', user_type='instructor')
    student = User.objects.create_user(
        username='student', email='s@example.com',
        password='StrongPass123!', user_type='student')
    exam = Exam.objects.create(
        title='模型测试考试', description='x', duration_minutes=30,
        passing_score=60, max_attempts=3, created_by=instructor)
    return instructor, student, exam


class ExamModelTests(TestCase):
    def setUp(self):
        self.instructor, self.student, self.exam = _setup()

    def _attempt(self, **kwargs):
        defaults = dict(student=self.student, exam=self.exam,
                        attempt_number=1, time_remaining_seconds=1800)
        defaults.update(kwargs)
        return StudentExam.objects.create(**defaults)

    def test_exam_and_attempt_str(self):
        self.assertEqual(str(self.exam), '模型测试考试')
        attempt = self._attempt()
        self.assertIn('student', str(attempt))
        self.assertIn('模型测试考试', str(attempt))

    def test_remaining_seconds_zero_after_end_time(self):
        from django.utils import timezone
        attempt = self._attempt()
        attempt.end_time = timezone.now()
        attempt.save()
        self.assertEqual(attempt.remaining_seconds(), 0)

    def test_is_passing_none_score(self):
        attempt = self._attempt(score=None)
        self.assertFalse(attempt.is_passing())

    def test_mc_auto_grade_wrong_answer(self):
        question = Question.objects.create(
            exam=self.exam, question_type='multiple_choice',
            question_text='MC?', points=4, order=0)
        MultipleChoiceQuestion.objects.create(
            question=question, options={'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd'},
            correct_answer='A')
        answer = ExamAnswer.objects.create(
            student_exam=self._attempt(), question=question,
            answer_data={'selected': 'B'})
        answer.auto_grade()
        self.assertFalse(answer.is_correct)
        self.assertEqual(answer.points_awarded, 0)
        self.assertEqual(answer.status, 'graded')

    def test_tf_auto_grade_string_forms(self):
        question = Question.objects.create(
            exam=self.exam, question_type='true_false',
            question_text='TF?', points=2, order=0)
        TrueFalseQuestion.objects.create(question=question, correct_answer=True)
        answer = ExamAnswer.objects.create(
            student_exam=self._attempt(), question=question,
            answer_data={'selected': 'true'})
        answer.auto_grade()
        self.assertTrue(answer.is_correct)
        self.assertEqual(answer.points_awarded, 2)

        answer2 = ExamAnswer.objects.create(
            student_exam=self._attempt(attempt_number=2), question=question,
            answer_data={'selected': 'false'})
        answer2.auto_grade()
        self.assertFalse(answer2.is_correct)

    def test_essay_auto_grade_marks_needs_review(self):
        from .models import EssayQuestion
        question = Question.objects.create(
            exam=self.exam, question_type='essay',
            question_text='ESSAY?', points=5, order=0)
        EssayQuestion.objects.create(question=question)
        answer = ExamAnswer.objects.create(
            student_exam=self._attempt(), question=question,
            answer_data={'text': 'x'})
        answer.auto_grade()
        self.assertEqual(answer.status, 'needs_review')
        self.assertIsNone(answer.points_awarded)  # manual grading pending

    def test_auto_grade_missing_specific_is_noop(self):
        # a question with no typed record: auto_grade must not crash
        question = Question.objects.create(
            exam=self.exam, question_type='true_false',
            question_text='孤儿?', points=2, order=9)
        answer = ExamAnswer.objects.create(
            student_exam=self._attempt(), question=question,
            answer_data={'selected': True})
        answer.auto_grade()  # no exception
        self.assertEqual(answer.status, 'pending')

    def test_certificate_str_and_unique_code(self):
        attempt = self._attempt(score=90, is_submitted=True)
        certificate = Certificate.objects.create(student_exam=attempt)
        self.assertEqual(len(certificate.verification_code), 32)
        self.assertIn('student', str(certificate))

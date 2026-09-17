"""Knowledge-point mastery tests (plan v3 2.1): signal mapping from
exercise submissions + exam answers, state boundaries, page rendering, and
weak-point practice entry (2.2: list filter + form preselect)."""


from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.learning.models import Chapter, Course, Enrollment, KnowledgePoint
from apps.examination.models import (
    Exam, ExamAnswer, Question, StudentExam, TrueFalseQuestion,
)
from .mastery import kp_mastery
from .models import Exercise, Submission


class MasterySetup(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.course = Course.objects.create(
            title='掌握度课程', slug='mastery-course',
            instructor=self.instructor, difficulty_level='beginner')
        Chapter.objects.create(course=self.course, title='第1章', order=1)
        Enrollment.objects.create(student=self.student, course=self.course)
        self.kp = KnowledgePoint.objects.create(course=self.course, title='列表')
        self.client.force_login(self.student)

    def _exercise(self, kp, slug='ex'):
        exercise = Exercise.objects.create(
            title=slug, slug=slug, description='x', difficulty='beginner',
            solution_code='def f():\n    return 1',
            test_cases=[{'input': 'f()', 'expected': 1}])
        exercise.knowledge_points.add(kp)
        return exercise

    def _exam_question(self, kp):
        exam = Exam.objects.create(
            title='掌握度卷', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, course=self.course,
            created_by=self.instructor)
        question = Question.objects.create(
            exam=exam, question_type='true_false', question_text='TF?',
            points=2, order=0)
        TrueFalseQuestion.objects.create(question=question, correct_answer=True)
        question.knowledge_points.add(kp)
        return exam, question

    def _exam_answer(self, kp, is_correct):
        exam, question = self._exam_question(kp)
        attempt = StudentExam.objects.create(
            student=self.student, exam=exam, attempt_number=1,
            time_remaining_seconds=1800, is_submitted=True)
        ExamAnswer.objects.create(
            student_exam=attempt, question=question, is_correct=is_correct,
            points_awarded=2 if is_correct else 0, status='graded',
            answer_data={'selected': is_correct})
        return exam, question


class MasteryComputationTests(MasterySetup):
    def test_no_signals_is_unstarted(self):
        rows = kp_mastery(self.student, self.course)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['state'], '未开始')
        self.assertIsNone(rows[0]['score'])

    def test_passed_exercise_counts(self):
        exercise = self._exercise(self.kp)
        Submission.objects.create(exercise=exercise, student=self.student,
                                  code='x', status='passed', tests_passed=1,
                                  tests_total=1)
        rows = kp_mastery(self.student, self.course)
        self.assertEqual(rows[0]['state'], '已掌握')
        self.assertEqual(rows[0]['score'], 100)
        self.assertEqual(rows[0]['exercise_passed'], 1)

    def test_latest_attempt_only_counts(self):
        exercise = self._exercise(self.kp)
        Submission.objects.create(exercise=exercise, student=self.student,
                                  code='x', status='failed')
        Submission.objects.create(exercise=exercise, student=self.student,
                                  code='y', status='passed', tests_passed=1,
                                  tests_total=1)
        rows = kp_mastery(self.student, self.course)
        self.assertEqual(rows[0]['exercise_total'], 1)
        self.assertEqual(rows[0]['state'], '已掌握')

    def test_exam_signals_merge(self):
        # 1 exercise pass + 1 exam wrong → 50% → 学习中
        exercise = self._exercise(self.kp)
        Submission.objects.create(exercise=exercise, student=self.student,
                                  code='x', status='passed', tests_passed=1,
                                  tests_total=1)
        self._exam_answer(self.kp, is_correct=False)
        rows = kp_mastery(self.student, self.course)
        self.assertEqual(rows[0]['score'], 50)
        self.assertEqual(rows[0]['state'], '学习中')
        self.assertEqual(rows[0]['exam_correct'], 0)
        self.assertEqual(rows[0]['exam_total'], 1)

    def test_boundary_at_70(self):
        # 3 passed + 1 failed exercise signals = 75% → 已掌握
        for i in range(3):
            exercise = self._exercise(self.kp, slug=f'ex{i}')
            Submission.objects.create(exercise=exercise, student=self.student,
                                      code='x', status='passed',
                                      tests_passed=1, tests_total=1)
        exercise = self._exercise(self.kp, slug='exfail')
        Submission.objects.create(exercise=exercise, student=self.student,
                                  code='x', status='failed')
        rows = kp_mastery(self.student, self.course)
        self.assertEqual(rows[0]['score'], 75)
        self.assertEqual(rows[0]['state'], '已掌握')

    def test_other_students_do_not_contaminate(self):
        other = User.objects.create_user(
            username='other', email='o@example.com',
            password='StrongPass123!', user_type='student')
        exercise = self._exercise(self.kp)
        Submission.objects.create(exercise=exercise, student=other,
                                  code='x', status='passed', tests_passed=1,
                                  tests_total=1)
        rows = kp_mastery(self.student, self.course)
        self.assertEqual(rows[0]['state'], '未开始')


class MasteryPageTests(MasterySetup):
    def test_progress_page_renders_mastery(self):
        exercise = self._exercise(self.kp)
        Submission.objects.create(exercise=exercise, student=self.student,
                                  code='x', status='passed', tests_passed=1,
                                  tests_total=1)
        response = self.client.get(reverse('training:my-progress'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '知识点掌握度')
        self.assertContains(response, '列表')
        self.assertContains(response, '已掌握')

    def test_weak_point_link_rendered(self):
        exercise = self._exercise(self.kp)
        Submission.objects.create(exercise=exercise, student=self.student,
                                  code='x', status='failed')
        response = self.client.get(reverse('training:my-progress'))
        self.assertContains(response, '去练习')
        self.assertContains(response, 'knowledge_point=')


class WeakPointPracticeTests(MasterySetup):
    def test_exercise_list_filters_by_kp(self):
        bound = self._exercise(self.kp, slug='bound')
        unbound = Exercise.objects.create(
            title='unbound', slug='unbound', description='x',
            difficulty='beginner', solution_code='def f():\n    return 1',
            test_cases=[{'input': 'f()', 'expected': 1}])
        response = self.client.get(
            reverse('training:exercise-list'), {'knowledge_point': self.kp.id})
        exercises = list(response.context['exercises'])
        self.assertIn(bound, exercises)
        self.assertNotIn(unbound, exercises)
        self.assertContains(response, '正在练习知识点')
        self.assertContains(response, '列表')

    def test_empty_kp_filter_shows_feedback_hint(self):
        response = self.client.get(
            reverse('training:exercise-list'), {'knowledge_point': self.kp.id})
        self.assertContains(response, '请向教师反馈')

    def test_create_form_preselects_kp(self):
        self.client.force_login(self.instructor)
        response = self.client.get(
            reverse('training:exercise-create'), {'kp': self.kp.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_kp_ids'], [self.kp.id])
        self.assertContains(response, 'selected')

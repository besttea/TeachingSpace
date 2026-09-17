"""Unit tests for question_ai helpers: dict conversion, apply, clone,
recompute and sandbox validation (OPTIMIZATION_PLAN 6.5 coverage gate)."""

from django.test import TestCase

from apps.accounts.models import User
from .models import (
    CodeQuestion, EssayQuestion, Exam, MultipleChoiceQuestion, Question,
    StudentExam, TrueFalseQuestion,
)
from .question_ai import (
    apply_question, clone_question, question_to_dict,
    recompute_exam_scores, validate_code_question,
)


def _make_exam(instructor, **kwargs):
    defaults = dict(title='辅助测试考试', description='x', duration_minutes=30,
                    passing_score=60, max_attempts=3, created_by=instructor)
    defaults.update(kwargs)
    return Exam.objects.create(**defaults)


def _add(exam, q_type, order=0, points=5, **specific_kwargs):
    question = Question.objects.create(
        exam=exam, question_type=q_type, question_text=f'{q_type}?',
        points=points, order=order)
    if q_type == 'multiple_choice':
        defaults = dict(options={'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd'},
                        correct_answer='A')
    elif q_type == 'true_false':
        defaults = dict(correct_answer=True)
    elif q_type == 'code':
        defaults = dict(starter_code='', solution_code='',
                        test_cases=[{'input': 'f()', 'expected': 1}])
    else:
        defaults = dict(word_limit=50, rubric='r', sample_answer='s')
    defaults.update(specific_kwargs)
    model = {'multiple_choice': MultipleChoiceQuestion,
             'true_false': TrueFalseQuestion,
             'code': CodeQuestion,
             'essay': EssayQuestion}[q_type]
    model.objects.create(question=question, **defaults)
    return question


class QuestionDictRoundTripTests(TestCase):
    def setUp(self):
        instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.exam = _make_exam(instructor)

    def test_to_dict_all_four_types(self):
        for q_type in ('multiple_choice', 'true_false', 'code', 'essay'):
            question = _add(self.exam, q_type)
            data = question_to_dict(question)
            self.assertEqual(data['type'], q_type)
            self.assertEqual(data['text'], f'{q_type}?')
            self.assertEqual(data['points'], 5)

    def test_apply_all_four_types(self):
        mc = _add(self.exam, 'multiple_choice')
        apply_question(mc, {'text': '新题干', 'points': 8,
                            'options': {'A': 'x', 'B': 'y', 'C': 'z', 'D': 'w'},
                            'correct_answer': 'B', 'explanation': '因为'})
        mc.refresh_from_db()
        self.assertEqual(mc.question_text, '新题干')
        self.assertEqual(mc.points, 8)
        mc_specific = mc.get_specific_question()
        self.assertEqual(mc_specific.correct_answer, 'B')

        tf = _add(self.exam, 'true_false', order=1)
        apply_question(tf, {'text': 'TF改', 'correct_answer': False,
                            'explanation': '错'})
        tf_specific = tf.get_specific_question()
        self.assertFalse(tf_specific.correct_answer)

        code = _add(self.exam, 'code', order=2)
        apply_question(code, {'starter_code': 'def f():\n    ...',
                              'solution_code': 'def f():\n    return 1',
                              'test_cases': [{'input': 'f()', 'expected': 1}],
                              'explanation': 'e'})
        code_specific = code.get_specific_question()
        self.assertEqual(code_specific.solution_code, 'def f():\n    return 1')

        essay = _add(self.exam, 'essay', order=3)
        apply_question(essay, {'word_limit': 120, 'rubric': '新标准',
                               'sample_answer': '新参考'})
        essay_specific = essay.get_specific_question()
        self.assertEqual(essay_specific.word_limit, 120)
        self.assertEqual(essay_specific.rubric, '新标准')

    def test_clone_all_four_types(self):
        source_exam = _make_exam(self.exam.created_by, title='源考试')
        for q_type in ('multiple_choice', 'true_false', 'code', 'essay'):
            source = _add(source_exam, q_type)
            clone = clone_question(source, self.exam, order=0)
            self.assertEqual(clone.question_text, source.question_text)
            self.assertIsNotNone(clone.get_specific_question())
            self.assertEqual(clone.exam, self.exam)
        self.assertEqual(self.exam.questions.count(), 4)


class RecomputeScoresTests(TestCase):
    def setUp(self):
        instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        self.exam = _make_exam(instructor)
        self.question = _add(self.exam, 'multiple_choice', points=10)
        self.attempt = StudentExam.objects.create(
            student=self.student, exam=self.exam, attempt_number=1,
            time_remaining_seconds=1800, score=100, is_submitted=True)

    def test_recompute_only_updates_changed_scores(self):
        from .models import ExamAnswer
        ExamAnswer.objects.create(
            student_exam=self.attempt, question=self.question,
            is_correct=False, points_awarded=0, status='graded',
            answer_data={'selected': 'B'})
        updated = recompute_exam_scores(self.exam)
        self.assertEqual(updated, 1)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, 0)

    def test_recompute_skips_matching_scores_and_unsubmitted(self):
        from .models import ExamAnswer
        ExamAnswer.objects.create(
            student_exam=self.attempt, question=self.question,
            is_correct=True, points_awarded=10, status='graded',
            answer_data={'selected': 'A'})
        # unsubmitted attempt is ignored entirely
        StudentExam.objects.create(
            student=self.student, exam=self.exam, attempt_number=2,
            time_remaining_seconds=1800, score=50)
        updated = recompute_exam_scores(self.exam)
        self.assertEqual(updated, 0)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, 100)


class ValidateCodeQuestionTests(TestCase):
    def setUp(self):
        instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.exam = _make_exam(instructor)

    def test_non_code_questions_always_ok(self):
        question = _add(self.exam, 'essay')
        ok, message = validate_code_question(question_to_dict(question))
        self.assertTrue(ok)
        self.assertEqual(message, '')

    def test_code_question_passes_with_valid_solution(self):
        question = _add(self.exam, 'code',
                        solution_code='def f():\n    return 1',
                        test_cases=[{'input': 'f()', 'expected': 1}])
        ok, message = validate_code_question(question_to_dict(question))
        self.assertTrue(ok, message)

    def test_code_question_fails_with_broken_solution(self):
        question = _add(self.exam, 'code',
                        solution_code='def f():\n    return 2',
                        test_cases=[{'input': 'f()', 'expected': 1}])
        ok, message = validate_code_question(question_to_dict(question))
        self.assertFalse(ok)
        self.assertTrue(message)

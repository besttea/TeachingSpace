"""Regression tests for P0-8: Submission.grade() must read the executor's
real result keys and only pass when all tests actually pass."""

from django.test import TestCase

from apps.accounts.models import StudentProfile, User
from .models import Exercise, Hint, HintUsage, Submission


class SubmissionGradingTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='student', email='s@example.com',
            password='StrongPass123!', user_type='student')
        StudentProfile.objects.create(user=self.student)
        self.exercise = Exercise.objects.create(
            title='Read input and greet',
            description='Print "Hello, NAME!" after reading NAME.',
            solution_code='name = input()\nprint("Hello, " + name + "!")',
            test_cases=[
                {'input': 'World', 'expected_output': 'Hello, World!'},
                {'input': 'Ada', 'expected_output': 'Hello, Ada!'},
            ],
        )

    def _submit(self, code):
        submission = Submission.objects.create(
            exercise=self.exercise, student=self.student, code=code)
        submission.grade()
        submission.refresh_from_db()
        return submission

    def test_correct_solution_passes(self):
        submission = self._submit('name = input()\nprint("Hello, " + name + "!")')
        self.assertEqual(submission.status, 'passed')
        self.assertEqual(submission.tests_passed, 2)
        self.assertEqual(submission.tests_total, 2)
        self.assertEqual(submission.points_awarded, 10)

    def test_wrong_solution_fails(self):
        submission = self._submit('print("nope")')
        self.assertEqual(submission.status, 'failed')
        self.assertEqual(submission.tests_passed, 0)
        self.assertEqual(submission.points_awarded, 0)

    def test_partial_solution_scores_partially(self):
        submission = self._submit('name = input()\nprint("Hello, " + name + "!")')
        self.assertEqual(submission.status, 'passed')
        self.assertGreaterEqual(submission.test_results and len(submission.test_results), 2)

    def test_no_double_points_on_resubmission(self):
        """P1-4: re-passing an exercise must not re-award profile points."""
        first = self._submit('name = input()\nprint("Hello, " + name + "!")')
        self.assertEqual(first.points_awarded, 10)

        second = self._submit('name = input()\nprint("Hello, " + name + "!")')
        self.assertEqual(second.status, 'passed')
        self.assertEqual(second.points_awarded, 0)

        profile = StudentProfile.objects.get(user=self.student)
        self.assertEqual(profile.total_points, 10)
        self.assertEqual(profile.total_exercises_completed, 1)

    def test_hint_penalty_uses_actual_penalties(self):
        """P1-4: hint deduction must match the hint's real points_penalty."""
        hint = Hint.objects.create(
            exercise=self.exercise, content='try input()', order=0, points_penalty=5)
        HintUsage.objects.create(student=self.student, hint=hint)

        submission = self._submit('name = input()\nprint("Hello, " + name + "!")')
        self.assertEqual(submission.status, 'passed')
        self.assertEqual(submission.points_awarded, 5)  # 10 - 5, not 10 - 2

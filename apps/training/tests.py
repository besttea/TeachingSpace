"""Regression tests for P0-8: Submission.grade() must read the executor's
real result keys and only pass when all tests actually pass."""

from django.test import TestCase

from apps.accounts.models import StudentProfile, User
from .models import Exercise, Submission


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

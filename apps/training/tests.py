"""Regression tests for P0-8: Submission.grade() must read the executor's
real result keys and only pass when all tests actually pass."""

import json

from django.test import TestCase
from django.urls import reverse

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


class ExerciseAIModifyTests(TestCase):
    """AI exercise modification endpoint: preview / apply / permissions."""

    def setUp(self):
        from unittest import mock as _mock
        self.instructor = User.objects.create_user(
            username='mod_teacher', email='mt@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='mod_student', email='ms@example.com',
            password='StrongPass123!', user_type='student')
        self.exercise = Exercise.objects.create(
            title='原始题', description='d', solution_code='def f():\n    return 1',
            test_cases=[{'input': 'f()', 'expected': 1}])

        patcher = _mock.patch('apps.ai_agents.training_agent.TrainingAgent.modify_exercise')
        self.mock_modify = patcher.start()
        self.addCleanup(patcher.stop)
        patcher2 = _mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
        patcher2.start()
        self.addCleanup(patcher2.stop)

    def _modify(self, apply):
        return self.client.post(
            reverse('training:exercise-ai-modify', args=[self.exercise.id]),
            data=json.dumps({'instruction': '加边界用例', 'apply': apply}),
            content_type='application/json')

    def test_preview_only_by_default(self):
        self.mock_modify.return_value = {
            'title': '原始题', 'description': 'd',
            'solution_code': 'def f():\n    return 1',
            'test_cases': [{'input': 'f()', 'expected': 1}],
            'hints': [],
        }
        self.client.force_login(self.instructor)
        response = self._modify(apply=False)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(data['applied'])
        self.assertIn('preview', data)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.test_cases, [{'input': 'f()', 'expected': 1}])

    def test_apply_validates_and_saves(self):
        self.mock_modify.return_value = {
            'title': '原始题改', 'description': 'd2',
            'solution_code': 'def f():\n    return 1',
            'test_cases': [{'input': 'f()', 'expected': 1},
                           {'input': 'f()', 'expected': 1}],
            'hints': [{'order': 1, 'content': 'h', 'points_penalty': 2}],
        }
        self.client.force_login(self.instructor)
        response = self._modify(apply=True)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['applied'])
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.title, '原始题改')
        self.assertEqual(len(self.exercise.test_cases), 2)
        self.assertEqual(self.exercise.hints.count(), 1)

    def test_apply_rejected_when_solution_fails_tests(self):
        self.mock_modify.return_value = {
            'title': 'T', 'description': 'd',
            'solution_code': 'def f():\n    return 999',
            'test_cases': [{'input': 'f()', 'expected': 1}],
            'hints': [],
        }
        self.client.force_login(self.instructor)
        response = self._modify(apply=True)
        self.assertEqual(response.status_code, 400)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.test_cases, [{'input': 'f()', 'expected': 1}])

    def test_student_forbidden(self):
        self.client.force_login(self.student)
        response = self._modify(apply=False)
        self.assertEqual(response.status_code, 403)


class ExerciseEditDeleteTests(TestCase):
    """T14: exercise edit form and delete with submission protection."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            username='edit_teacher', email='et@example.com',
            password='StrongPass123!', user_type='instructor')
        self.student = User.objects.create_user(
            username='edit_student', email='es@example.com',
            password='StrongPass123!', user_type='student')
        self.exercise = Exercise.objects.create(
            title='原题', description='d',
            solution_code='def f():\n    return 1',
            test_cases=[{'input': 'f()', 'expected': 1}],
            created_by=self.instructor)
        Hint.objects.create(exercise=self.exercise, content='h1', order=1,
                            points_penalty=2)

    def test_edit_updates_fields(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('training:exercise-edit', args=[self.exercise.id]),
            {'title': '改后题', 'description': 'd2', 'difficulty': 'intermediate',
             'points': '15', 'starter_code': '', 'solution_code': 'def f():\n    return 2',
             'test_cases': '[{"input": "f()", "expected": 2}]',
             'hint_1': '新提示', 'hint_penalty_1': '3'})
        self.assertEqual(response.status_code, 302)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.title, '改后题')
        self.assertEqual(self.exercise.points, 15)
        self.assertEqual(self.exercise.test_cases, [{'input': 'f()', 'expected': 2}])
        self.assertEqual(self.exercise.hints.first().content, '新提示')
        self.assertEqual(self.exercise.hints.count(), 1)

    def test_edit_page_prefills(self):
        self.client.force_login(self.instructor)
        response = self.client.get(
            reverse('training:exercise-edit', args=[self.exercise.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '原题')
        self.assertContains(response, 'h1')

    def test_delete_with_submissions_refused(self):
        StudentProfile.objects.create(user=self.student)
        Submission.objects.create(
            exercise=self.exercise, student=self.student, code='x')
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('training:exercise-delete', args=[self.exercise.id]),
            data=json.dumps({'force': '0'}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Exercise.objects.filter(pk=self.exercise.id).exists())

    def test_delete_force_works(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('training:exercise-delete', args=[self.exercise.id]),
            data=json.dumps({'force': '1'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Exercise.objects.filter(pk=self.exercise.id).exists())

    def test_student_forbidden(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse('training:exercise-edit', args=[self.exercise.id]))
        self.assertEqual(response.status_code, 403)

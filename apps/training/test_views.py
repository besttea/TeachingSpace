"""View coverage for the training app: exercise browsing, submission endpoint,
hints, creation, history and progress (OPTIMIZATION_PLAN 6.5 coverage gate)."""

import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StudentProfile, User
from .models import Exercise, Hint, Submission


def _make_user(username, user_type='student'):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com',
        password='StrongPass123!', user_type=user_type)


def _make_exercise(**kwargs):
    defaults = dict(
        title='两数求和', slug='add-two', description='写一个函数',
        difficulty='beginner', points=10,
        solution_code='def add(a, b):\n    return a + b',
        test_cases=[{'input': 'add(1, 2)', 'expected': 3}],
    )
    defaults.update(kwargs)
    return Exercise.objects.create(**defaults)


class ExerciseBrowseTests(TestCase):
    def setUp(self):
        self.student = _make_user('student')
        self.client.force_login(self.student)

    def test_list_filters_by_difficulty_course_search(self):
        _make_exercise(title='循环练习', difficulty='advanced')
        _make_exercise(title='列表练习', slug='lists', difficulty='intermediate')
        url = reverse('training:exercise-list')
        response = self.client.get(url, {'difficulty': 'advanced'})
        self.assertContains(response, '循环练习')
        self.assertNotContains(response, '列表练习')

        response = self.client.get(url, {'search': '列表'})
        self.assertContains(response, '列表练习')
        self.assertNotContains(response, '循环练习')

    def test_list_marks_completed_exercises(self):
        exercise = _make_exercise()
        Submission.objects.create(exercise=exercise, student=self.student,
                                  code='x', status='passed', tests_passed=1,
                                  tests_total=1)
        response = self.client.get(reverse('training:exercise-list'))
        self.assertIn(exercise.id, response.context['completed_exercises'])
        self.assertFalse(response.context['can_create'])

    def test_list_allows_instructor_create(self):
        instructor = _make_user('teacher', 'instructor')
        self.client.force_login(instructor)
        response = self.client.get(reverse('training:exercise-list'))
        self.assertTrue(response.context['can_create'])

    def test_detail_context_has_hints_and_submissions(self):
        exercise = _make_exercise()
        Hint.objects.create(exercise=exercise, content='提示一', order=1,
                            points_penalty=1)
        Submission.objects.create(exercise=exercise, student=self.student,
                                  code='x', status='failed')
        Submission.objects.create(exercise=exercise, student=self.student,
                                  code='y', status='passed', tests_passed=1,
                                  tests_total=1)
        response = self.client.get(reverse(
            'training:exercise-detail', args=[exercise.slug]))
        context = response.context
        self.assertEqual(context['hints_count'], 1)
        self.assertEqual(len(context['submissions']), 2)
        self.assertEqual(context['best_submission'].status, 'passed')
        self.assertFalse(context['can_modify'])

    def test_detail_404_for_unknown_slug(self):
        response = self.client.get(reverse(
            'training:exercise-detail', args=['nope']))
        self.assertEqual(response.status_code, 404)


class SubmitSolutionViewTests(TestCase):
    def setUp(self):
        self.student = _make_user('student')
        self.client.force_login(self.student)
        self.exercise = _make_exercise()

    def _post(self, code):
        return self.client.post(
            reverse('training:submit-solution', args=[self.exercise.slug]),
            data=json.dumps({'code': code}), content_type='application/json')

    def test_empty_code_rejected(self):
        response = self._post('')
        self.assertEqual(response.status_code, 400)

    def test_oversized_code_rejected(self):
        response = self._post('x = ' + '1' * 100_050)
        self.assertEqual(response.status_code, 400)
        self.assertIn('代码过长', response.json()['error'])

    def test_correct_solution_grades_inline(self):
        response = self._post('def add(a, b):\n    return a + b')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['status'], 'passed')
        self.assertEqual(body['tests_passed'], 1)
        submission = Submission.objects.get(pk=body['submission_id'])
        self.assertTrue(submission.points_awarded > 0)

    def test_unknown_exercise_404(self):
        response = self.client.post(
            reverse('training:submit-solution', args=['missing']),
            data=json.dumps({'code': 'x'}), content_type='application/json')
        self.assertEqual(response.status_code, 404)


class HintViewTests(TestCase):
    def setUp(self):
        self.student = _make_user('student')
        StudentProfile.objects.create(user=self.student, total_points=50)
        self.client.force_login(self.student)
        self.exercise = _make_exercise()
        self.hint = Hint.objects.create(exercise=self.exercise,
                                        content='答案是列表推导',
                                        points_penalty=3)

    def _view(self):
        return self.client.post(reverse('training:view-hint',
                                        args=[self.hint.id]))

    def test_first_view_deducts_points(self):
        response = self._view()
        body = response.json()
        self.assertTrue(body['first_view'])
        self.assertEqual(body['content'], '答案是列表推导')
        self.assertEqual(body['points_penalty'], 3)
        profile = self.student.student_profile
        profile.refresh_from_db()
        self.assertEqual(profile.total_points, 47)

    def test_second_view_no_penalty(self):
        self._view()
        response = self._view()
        body = response.json()
        self.assertFalse(body['first_view'])
        self.assertEqual(body['points_penalty'], 0)
        self.student.student_profile.refresh_from_db()
        self.assertEqual(self.student.student_profile.total_points, 47)

    def test_penalty_floors_at_zero(self):
        profile = self.student.student_profile
        profile.total_points = 1
        profile.save()
        self._view()
        profile.refresh_from_db()
        self.assertEqual(profile.total_points, 0)

    def test_unknown_hint_404(self):
        response = self.client.post(reverse('training:view-hint',
                                            args=[9999]))
        self.assertEqual(response.status_code, 404)


class ExerciseCreateViewTests(TestCase):
    def setUp(self):
        self.instructor = _make_user('teacher', 'instructor')
        self.client.force_login(self.instructor)

    def _post(self, **overrides):
        data = dict(
            title='新练习', description='描述', difficulty='beginner',
            points=10, starter_code='', solution_code='def f():\n    return 1',
            test_cases=json.dumps([{'input': 'f()', 'expected': 1}]),
            hint_1='先想想输入', hint_penalty_1='2',
        )
        data.update(overrides)
        return self.client.post(reverse('training:exercise-create'), data)

    def test_create_with_hints(self):
        response = self._post()
        exercise = Exercise.objects.get(title='新练习')
        self.assertRedirects(response, reverse(
            'training:exercise-detail', args=[exercise.slug]))
        hint = Hint.objects.get(exercise=exercise)
        self.assertEqual(hint.content, '先想想输入')
        self.assertEqual(hint.order, 1)

    def test_missing_title_rejected(self):
        response = self._post(title='')
        self.assertRedirects(response, reverse('training:exercise-create'))
        self.assertFalse(Exercise.objects.filter(title='新练习').exists())

    def test_bad_test_cases_rejected(self):
        response = self._post(test_cases='not json')
        self.assertRedirects(response, reverse('training:exercise-create'))
        self.assertEqual(Exercise.objects.count(), 0)

    def test_student_forbidden(self):
        student = _make_user('student2')
        self.client.force_login(student)
        response = self.client.get(reverse('training:exercise-create'))
        self.assertEqual(response.status_code, 403)

    def test_get_form_lists_published_courses(self):
        from apps.learning.models import Course
        Course.objects.create(title='已发布课程', is_published=True,
                              instructor=self.instructor)
        Course.objects.create(title='草稿课程', is_published=False,
                              instructor=self.instructor)
        response = self.client.get(reverse('training:exercise-create'))
        self.assertContains(response, '已发布课程')
        self.assertNotContains(response, '草稿课程')


class SubmissionHistoryTests(TestCase):
    def setUp(self):
        self.student = _make_user('student')
        self.client.force_login(self.student)
        self.exercise = _make_exercise()

    def test_history_lists_own_submissions(self):
        Submission.objects.create(exercise=self.exercise,
                                  student=self.student, code='x',
                                  status='failed')
        response = self.client.get(reverse(
            'training:submission-history', args=[self.exercise.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['submissions']), 1)

    def test_detail_blocks_other_students(self):
        other = _make_user('other')
        submission = Submission.objects.create(
            exercise=self.exercise, student=other, code='x', status='failed')
        response = self.client.get(reverse(
            'training:submission-detail', args=[submission.id]))
        self.assertEqual(response.status_code, 404)

    def test_detail_shows_plagiarism_hint_for_instructor(self):
        instructor = _make_user('teacher2', 'instructor')
        same_code = 'def add(a, b):\n    return a + b'
        s1 = Submission.objects.create(exercise=self.exercise,
                                       student=self.student, code=same_code,
                                       status='passed', tests_passed=1,
                                       tests_total=1)
        # an identical copy by another student — the instructor sees a 100% badge
        Submission.objects.create(exercise=self.exercise,
                                  student=instructor, code=same_code,
                                  status='passed', tests_passed=1,
                                  tests_total=1)
        self.client.force_login(instructor)
        response = self.client.get(reverse(
            'training:submission-detail', args=[s1.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['similarity'], 100)

    def test_detail_no_similarity_badge_below_threshold(self):
        instructor = _make_user('teacher3', 'instructor')
        Submission.objects.create(exercise=self.exercise,
                                  student=self.student, code='a = 1\nprint(a)',
                                  status='passed', tests_passed=1,
                                  tests_total=1)
        Submission.objects.create(exercise=self.exercise,
                                  student=instructor,
                                  code='import collections\nx = sorted([3, 1, 2])\nprint(x)',
                                  status='passed', tests_passed=1,
                                  tests_total=1)
        target = Submission.objects.get(student=self.student)
        self.client.force_login(instructor)
        response = self.client.get(reverse(
            'training:submission-detail', args=[target.id]))
        self.assertIsNone(response.context['similarity'])


class MyProgressTests(TestCase):
    def setUp(self):
        self.student = _make_user('student')
        StudentProfile.objects.create(user=self.student, total_points=30)
        self.client.force_login(self.student)
        self.exercise = _make_exercise()

    def test_progress_stats(self):
        Submission.objects.create(exercise=self.exercise,
                                  student=self.student, code='x',
                                  status='passed', tests_passed=1,
                                  tests_total=1)
        Submission.objects.create(exercise=self.exercise,
                                  student=self.student, code='y',
                                  status='failed')
        response = self.client.get(reverse('training:my-progress'))
        context = response.context
        self.assertEqual(context['total_submissions'], 2)
        self.assertEqual(context['passed_submissions'], 1)
        self.assertEqual(context['total_points'], 30)
        self.assertEqual(context['exercises_attempted'], 1)

"""Regression tests for P0-4 (registration privilege escalation) and
P0-5 (login open redirect)."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import User, StudentProfile


class RegistrationSecurityTests(TestCase):
    def test_user_type_cannot_be_self_assigned(self):
        """POSTing user_type=admin/instructor must still create a student."""
        for spoofed in ('admin', 'instructor', 'superuser'):
            response = self.client.post(reverse('accounts:register'), {
                'username': f'user_{spoofed}',
                'email': f'{spoofed}@example.com',
                'password': 'StrongPass123!',
                'password_confirm': 'StrongPass123!',
                'user_type': spoofed,
            })
            self.assertEqual(response.status_code, 302)  # success → redirect
            user = User.objects.get(username=f'user_{spoofed}')
            self.assertEqual(user.user_type, 'student')
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
            self.assertTrue(StudentProfile.objects.filter(user=user).exists())
            # registration logs the user in — log out before the next case
            self.client.logout()

    def test_weak_password_rejected(self):
        response = self.client.post(reverse('accounts:register'), {
            'username': 'weakuser',
            'email': 'weak@example.com',
            'password': '123',
            'password_confirm': '123',
        })
        self.assertEqual(response.status_code, 200)  # re-renders form
        self.assertFalse(User.objects.filter(username='weakuser').exists())


class LoginOpenRedirectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='victim', email='v@example.com', password='StrongPass123!')

    def test_external_next_is_ignored(self):
        response = self.client.post(
            reverse('accounts:login') + '?next=https://evil.example.com/phish',
            {'username': 'victim', 'password': 'StrongPass123!'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('evil.example.com', response['Location'])

    def test_relative_next_is_honored(self):
        response = self.client.post(
            reverse('accounts:login') + '?next=/learning/courses/',
            {'username': 'victim', 'password': 'StrongPass123!'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/learning/courses/')


class LoginRateLimitTests(TestCase):
    """T4: brute-force protection — lock after LOGIN_MAX_ATTEMPTS failures."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='ratelimited', email='rl@example.com',
            password='StrongPass123!')

    def _post_login(self, password):
        return self.client.post(reverse('accounts:login'),
                                {'username': 'ratelimited', 'password': password})

    def test_locked_after_repeated_failures(self):
        from django.core.cache import cache
        cache.clear()
        for _ in range(5):
            response = self._post_login('wrong-password')
            self.assertEqual(response.status_code, 200)
        # 6th attempt is blocked even with the CORRECT password
        response = self._post_login('StrongPass123!')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '尝试次数过多')

    def test_success_resets_counter(self):
        from django.core.cache import cache
        cache.clear()
        for _ in range(4):
            self._post_login('wrong-password')
        # correct password succeeds and resets the failure window
        response = self._post_login('StrongPass123!')
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        for _ in range(5):
            response = self._post_login('wrong-password')
        # still 4 more failures before lockout (counter was reset)
        self.assertNotContains(response, '尝试次数过多')


class RateLimitDecoratorTests(SimpleTestCase):
    """T5: per-user rate limiting (cache-backed window)."""

    def test_blocks_after_limit(self):
        from django.core.cache import cache
        from django.test import RequestFactory
        from django.http import JsonResponse
        from apps.core.rate_limit import rate_limit

        cache.clear()

        @rate_limit('test_limit', limit=3, window_seconds=60)
        def view(request):
            return JsonResponse({'ok': True})

        factory = RequestFactory()
        request = factory.post('/x')
        request.user = type('U', (), {'id': 99, 'is_authenticated': True})()

        for _ in range(3):
            self.assertEqual(view(request).status_code, 200)
        self.assertEqual(view(request).status_code, 429)

    def test_counts_per_user(self):
        from django.core.cache import cache
        from django.test import RequestFactory
        from django.http import JsonResponse
        from apps.core.rate_limit import rate_limit

        cache.clear()

        @rate_limit('test_limit2', limit=1, window_seconds=60)
        def view(request):
            return JsonResponse({'ok': True})

        factory = RequestFactory()
        r1 = factory.post('/x')
        r1.user = type('U', (), {'id': 1, 'is_authenticated': True})()
        r2 = factory.post('/x')
        r2.user = type('U', (), {'id': 2, 'is_authenticated': True})()
        self.assertEqual(view(r1).status_code, 200)
        self.assertEqual(view(r2).status_code, 200)  # different user, unaffected


class DashboardActivityTests(TestCase):
    """C: 90-day learning calendar data on the student dashboard."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='cal_student', email='cls@example.com',
            password='StrongPass123!', user_type='student')
        StudentProfile.objects.create(user=self.student)

    def test_activity_includes_actions(self):
        from apps.learning.models import Course, Enrollment
        from apps.training.models import Exercise, Submission
        from apps.examination.models import Exam, StudentExam
        from django.utils import timezone

        instructor = User.objects.create_user(
            username='cal_teacher', email='clt@example.com',
            password='StrongPass123!', user_type='instructor')
        course = Course.objects.create(
            title='CAL', description='x', instructor=instructor, is_published=True)
        Enrollment.objects.create(student=self.student, course=course)
        exercise = Exercise.objects.create(
            title='E', description='d', solution_code='x',
            test_cases=[{'input': 'f()', 'expected': 1}])
        Submission.objects.create(exercise=exercise, student=self.student, code='x')
        exam = Exam.objects.create(
            title='X', description='x', duration_minutes=10,
            passing_score=60, max_attempts=1, is_published=True,
            created_by=instructor)
        StudentExam.objects.create(
            student=self.student, exam=exam, attempt_number=1,
            time_remaining_seconds=600, score=100, is_submitted=True)

        self.client.force_login(self.student)
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 200)
        # today's square carries a title with the count (at least 2 actions)
        self.assertContains(response, '学习日历')
        content = response.content.decode()
        self.assertIn('次活动', content)

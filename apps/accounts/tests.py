"""Regression tests for P0-4 (registration privilege escalation) and
P0-5 (login open redirect)."""

from django.test import TestCase
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

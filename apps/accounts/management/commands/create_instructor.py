"""
Create an instructor account (the ONLY supported provisioning path —
self-registration is student-only by design).

Usage:
    python manage.py create_instructor --username teacher1 [--password xxx] [--email t@school.edu]
    python manage.py create_instructor --username teacher1 --make-superuser

Without --password a random one is generated and printed once.
"""

import secrets

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = 'Create an instructor account'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, required=True)
        parser.add_argument('--password', type=str, default='',
                            help='Password (default: random, printed once)')
        parser.add_argument('--email', type=str, default='')
        parser.add_argument('--make-superuser', action='store_true',
                            help='Also grant Django admin access')

    def handle(self, *args, **options):
        username = options['username']
        if User.objects.filter(username=username).exists():
            raise CommandError(f'User "{username}" already exists')

        password = options['password'] or secrets.token_urlsafe(12)
        user = User.objects.create_user(
            username=username,
            email=options['email'] or f'{username}@example.com',
            password=password,
            user_type='instructor',
        )
        if options['make_superuser']:
            user.is_staff = True
            user.is_superuser = True
            user.save()

        self.stdout.write(self.style.SUCCESS(f'Created instructor: {username}'))
        self.stdout.write(f'  Login: 平台登录页输入 {username} 与以下密码')
        self.stdout.write(self.style.WARNING(f'  Password: {password}（请立即登录并妥善保存）'))

from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.db import IntegrityError
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from datetime import timedelta

from .models import User, StudentProfile
from apps.learning.models import Enrollment, LessonProgress
from apps.training.models import Submission
from apps.examination.models import StudentExam

#: Max profile picture size (5 MB)
MAX_PROFILE_PICTURE_SIZE = 5 * 1024 * 1024

#: Login brute-force protection (per username+IP, cache-backed)
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60


def _login_failure_key(request, username):
    return f'login_fail:{request.META.get("REMOTE_ADDR", "unknown")}:{username}'


def _login_limited(request, username):
    from django.core.cache import cache
    return (cache.get(_login_failure_key(request, username), 0)
            >= LOGIN_MAX_ATTEMPTS)


def _login_failure(request, username):
    from django.core.cache import cache
    key = _login_failure_key(request, username)
    cache.add(key, 0, LOGIN_LOCKOUT_SECONDS)  # ensures the TTL window exists
    cache.incr(key)


def _login_success(request, username):
    from django.core.cache import cache
    cache.delete(_login_failure_key(request, username))


def register_view(request):
    """User registration view (self-registration is student-only)"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        # Get form data. user_type is fixed to 'student' — instructor/admin
        # accounts must be created by an administrator, never self-assigned.
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')

        # Validation
        if not all([username, email, password, password_confirm]):
            messages.error(request, 'All fields are required.')
            return render(request, 'accounts/register.html')

        if password != password_confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'accounts/register.html')

        # Enforce Django's configured password validators
        try:
            validate_password(password, user=User(username=username, email=email))
        except ValidationError as e:
            for message_text in e.messages:
                messages.error(request, message_text)
            return render(request, 'accounts/register.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'accounts/register.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists.')
            return render(request, 'accounts/register.html')

        # Create user
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                user_type='student'
            )

            python_experience = request.POST.get('python_experience', 'beginner')
            StudentProfile.objects.create(
                user=user,
                python_experience=python_experience
            )

            # Log the user in
            login(request, user)
            messages.success(request, f'Welcome {username}! Your account has been created.')
            return redirect('accounts:dashboard')

        except IntegrityError:
            # Race on username/email uniqueness
            messages.error(request, 'Username or email already exists.')
            return render(request, 'accounts/register.html')
        except Exception as e:
            messages.error(request, f'Error creating account: {str(e)}')
            return render(request, 'accounts/register.html')

    return render(request, 'accounts/register.html')


def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not all([username, password]):
            messages.error(request, 'Both username and password are required.')
            return render(request, 'accounts/login.html')

        # Brute-force protection: lock after repeated failures
        if _login_limited(request, username):
            messages.error(
                request,
                f'尝试次数过多，请 {LOGIN_LOCKOUT_SECONDS // 60} 分钟后再试。')
            return render(request, 'accounts/login.html')

        # Authenticate user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            _login_success(request, username)
            messages.success(request, f'Welcome back, {user.username}!')

            # Redirect to next parameter (same-host / relative URLs only)
            # or the dashboard. Never trust an arbitrary external URL.
            next_url = request.GET.get('next', '')
            if not url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                next_url = ''
            if not next_url:
                next_url = 'accounts:dashboard'
            return redirect(next_url)
        else:
            _login_failure(request, username)
            messages.error(request, 'Invalid username or password.')
            return render(request, 'accounts/login.html')

    return render(request, 'accounts/login.html')


@require_http_methods(["POST"])
def logout_view(request):
    """User logout view (POST-only: logout is a state change)"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')


@login_required
def dashboard_view(request):
    """User dashboard view"""
    context = {
        'user': request.user
    }

    # Student-specific data
    if request.user.user_type == 'student':
        # Get student profile
        try:
            profile = StudentProfile.objects.get(user=request.user)
            context['profile'] = profile
        except StudentProfile.DoesNotExist:
            # Create profile if it doesn't exist
            profile = StudentProfile.objects.create(user=request.user)
            context['profile'] = profile

        # Get enrollments
        enrollments = Enrollment.objects.filter(
            student=request.user,
            is_active=True
        ).select_related('course')
        context['enrollments'] = enrollments
        context['total_courses'] = enrollments.count()

        # Get recent lesson progress
        recent_lessons = LessonProgress.objects.filter(
            enrollment__student=request.user
        ).select_related(
            'lesson',
            'lesson__chapter',
            'lesson__chapter__course'
        ).order_by('-last_accessed')[:5]
        context['recent_lessons'] = recent_lessons

        # Get submission statistics
        total_submissions = Submission.objects.filter(student=request.user).count()
        passed_submissions = Submission.objects.filter(
            student=request.user,
            status='passed'
        ).count()
        context['total_submissions'] = total_submissions
        context['passed_submissions'] = passed_submissions

        # Get exam statistics
        exam_attempts = StudentExam.objects.filter(student=request.user, is_submitted=True)
        context['exams_taken'] = exam_attempts.count()
        context['exams_passed'] = sum(1 for attempt in exam_attempts if attempt.is_passing())

        # Calculate completion stats
        completed_lessons = LessonProgress.objects.filter(
            enrollment__student=request.user,
            is_completed=True
        ).count()
        context['completed_lessons'] = completed_lessons

        # Recent activity (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_activity = LessonProgress.objects.filter(
            enrollment__student=request.user,
            last_accessed__gte=week_ago
        ).count()
        context['recent_activity'] = recent_activity

        # Learning calendar: activity counts per day over the last 90 days
        from collections import Counter
        ninety_days_ago = timezone.now().date() - timedelta(days=89)
        activity_counts = Counter()
        for day in LessonProgress.objects.filter(
            enrollment__student=request.user,
            last_accessed__date__gte=ninety_days_ago
        ).values_list('last_accessed__date', flat=True):
            activity_counts[day] += 1
        for day in Submission.objects.filter(
            student=request.user,
            submitted_at__date__gte=ninety_days_ago
        ).values_list('submitted_at__date', flat=True):
            activity_counts[day] += 1
        for day in StudentExam.objects.filter(
            student=request.user, is_submitted=True,
            start_time__date__gte=ninety_days_ago
        ).values_list('start_time__date', flat=True):
            activity_counts[day] += 1
        activity = []
        for offset in range(90):
            day = ninety_days_ago + timedelta(days=offset)
            activity.append({'date': day, 'count': activity_counts.get(day, 0)})
        context['activity'] = activity

    # Instructor-specific data
    elif request.user.user_type == 'instructor':
        from apps.learning.models import Course

        # Get courses taught
        courses_taught = Course.objects.filter(instructor=request.user)
        context['courses_taught'] = courses_taught
        context['total_courses_taught'] = courses_taught.count()

        # Get total enrollments across all courses
        total_students = Enrollment.objects.filter(
            course__instructor=request.user,
            is_active=True
        ).values('student').distinct().count()
        context['total_students'] = total_students

    return render(request, 'accounts/dashboard.html', context)


@login_required
def profile_view(request):
    """User profile view and edit"""
    if request.method == 'POST':
        # Update basic info
        user = request.user
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        new_email = request.POST.get('email', user.email).strip()
        user.bio = request.POST.get('bio', '')

        # Email must stay unique (and not be silently reset by a blank field)
        if new_email and new_email != user.email and User.objects.filter(email=new_email).exists():
            messages.error(request, 'Email already exists.')
            return redirect('accounts:profile')
        user.email = new_email

        # Handle profile picture upload (size + type checked)
        if 'profile_picture' in request.FILES:
            upload = request.FILES['profile_picture']
            if upload.size > MAX_PROFILE_PICTURE_SIZE:
                messages.error(request, 'Profile picture must be smaller than 5 MB.')
                return redirect('accounts:profile')
            if not (upload.content_type or '').startswith('image/'):
                messages.error(request, 'Profile picture must be an image file.')
                return redirect('accounts:profile')
            user.profile_picture = upload

        user.save()

        # Update student profile if exists
        if hasattr(user, 'student_profile'):
            profile = user.student_profile
            profile.python_experience = request.POST.get('python_experience', profile.python_experience)
            profile.save()

        messages.success(request, 'Profile updated successfully!')
        return redirect('accounts:profile')

    context = {
        'user': request.user
    }

    # Get student profile if exists
    if hasattr(request.user, 'student_profile'):
        context['profile'] = request.user.student_profile

    return render(request, 'accounts/profile.html', context)


# ---------------------------------------------------------------------------
# 网页参数设置（分角色：学生个人偏好 / 教师生成默认值 + AI 旋钮 / 管理员全局）
# ---------------------------------------------------------------------------

_PERSONAL_PREF_KEYS = (
    'default_difficulty',        # instructor: beginner/intermediate/advanced
    'default_chapter_count',     # instructor: 1-10
    'default_exam_question_count',  # instructor: 1-30
    'heartbeat_enabled',         # student: bool (学习时长心跳)
)

# 管理员可编辑的全局限流条目（key → (label, 代码默认值)）
_GLOBAL_RATE_DEFAULTS = {
    'exercise_submit': (10, 60),
    'kernel_execute': (60, 300),
    'exercise_ai_draft': (20, 3600),
    'exercise_ai_modify': (20, 3600),
    'question_ai_modify': (20, 3600),
    'lesson_ai_generate': (20, 3600),
    'chapter_ai_plan': (20, 3600),
    'exam_ai_generate': (20, 3600),
    'kp_extract': (20, 3600),
}

_SKILL_NAMES = ('exam_generation', 'exercise_generation',
                'course_design', 'knowledge_extraction',
                'text_generation', 'code_generation',
                'image_generation', 'video_generation')


@login_required
def settings_view(request):
    """Role-gated web settings page.

    - 学生: personal preferences only (heartbeat toggle)
    - 教师: personal defaults + AI skill parameter JSONs (content tuning)
    - 管理员: additionally global rate limits + AI daily cost limit
    """
    from apps.ai_agents.skill_config import DEFAULTS as SKILL_DEFAULTS
    from apps.core.settings_db import (
        get_platform_setting, set_platform_setting)

    is_admin = request.user.is_staff
    is_instructor = is_admin or request.user.user_type == 'instructor'
    saved_message = None

    if request.method == 'POST':
        # ---- personal preferences (all roles) ----
        prefs = dict(request.user.preferences or {})
        if is_instructor:
            difficulty = request.POST.get('default_difficulty')
            if difficulty in ('beginner', 'intermediate', 'advanced'):
                prefs['default_difficulty'] = difficulty
            try:
                prefs['default_chapter_count'] = max(
                    1, min(int(request.POST.get('default_chapter_count', 3)), 10))
            except (TypeError, ValueError):
                prefs['default_chapter_count'] = 3
            try:
                prefs['default_exam_question_count'] = max(
                    1, min(int(request.POST.get('default_exam_question_count', 10)), 30))
            except (TypeError, ValueError):
                prefs['default_exam_question_count'] = 10
        else:
            prefs['heartbeat_enabled'] = (
                request.POST.get('heartbeat_enabled') == 'on')
        request.user.preferences = prefs
        request.user.save()

        # ---- AI skill parameters (instructor + admin) ----
        if is_instructor:
            import json as _json
            for name in _SKILL_NAMES:
                raw = (request.POST.get(f'skill_{name}') or '').strip()
                if not raw:
                    set_platform_setting(f'ai_skill_params:{name}', {},
                                         category='ai', description=f'{name} 参数')
                    continue
                try:
                    parsed = _json.loads(raw)
                    if not isinstance(parsed, dict):
                        raise ValueError('必须是 JSON 对象')
                except (ValueError, _json.JSONDecodeError) as e:
                    messages.error(request, f'{name} 参数 JSON 格式错误：{e}')
                    return redirect('accounts:settings')
                set_platform_setting(f'ai_skill_params:{name}', parsed,
                                     category='ai', description=f'{name} 参数')

        # ---- global knobs (admin only) ----
        if is_admin:
            for key in _GLOBAL_RATE_DEFAULTS:
                limit_raw = request.POST.get(f'rate_limit_{key}')
                window_raw = request.POST.get(f'rate_window_{key}')
                try:
                    limit = max(1, int(limit_raw or 0))
                    window = max(30, int(window_raw or 0))
                except (TypeError, ValueError):
                    continue
                set_platform_setting(
                    f'rate:{key}', {'limit': limit, 'window_seconds': window},
                    category='rate', description='请求限流')
            try:
                cost = float(request.POST.get('ai_cost_limit_daily') or -1)
                if cost >= 0:
                    set_platform_setting('ai_cost_limit_daily', cost,
                                         category='ai', description='AI 每日成本上限（USD）')
            except (TypeError, ValueError):
                pass

        messages.success(request, '设置已保存')
        return redirect('accounts:settings')

    context = {
        'is_admin': is_admin,
        'is_instructor': is_instructor,
        'prefs': dict(request.user.preferences or {}),
        'saved_message': saved_message,
    }

    if is_instructor:
        import json as _json
        context['skill_rows'] = [
            {
                'name': name,
                'current_json': _json.dumps(current, ensure_ascii=False)
                if current else '',
                'defaults': list(SKILL_DEFAULTS.get(name, {}).items()),
            }
            for name in _SKILL_NAMES
            for current in [get_platform_setting(f'ai_skill_params:{name}', {})]
        ]
    if is_admin:
        context['rate_rows'] = [
            {
                'key': key,
                'default_limit': defaults[0],
                'default_window': defaults[1],
                'current_limit': current.get('limit', defaults[0]),
                'current_window': current.get('window_seconds', defaults[1]),
            }
            for key, defaults in _GLOBAL_RATE_DEFAULTS.items()
            for current in [get_platform_setting(f'rate:{key}', {})]
        ]
        context['ai_cost_current'] = get_platform_setting(
            'ai_cost_limit_daily',
            getattr(settings, 'AI_COST_LIMIT_DAILY', 50.0))

    return render(request, 'accounts/settings.html', context)

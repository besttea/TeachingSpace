from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum
from django.utils import timezone
from datetime import timedelta

from .models import User, StudentProfile
from apps.learning.models import Enrollment, LessonProgress
from apps.training.models import Submission
from apps.examination.models import ExamAttempt


def register_view(request):
    """User registration view"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        # Get form data
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        user_type = request.POST.get('user_type', 'student')

        # Validation
        if not all([username, email, password, password_confirm]):
            messages.error(request, 'All fields are required.')
            return render(request, 'accounts/register.html')

        if password != password_confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'accounts/register.html')

        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
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
                user_type=user_type
            )

            # Create student profile if user type is student
            if user_type == 'student':
                python_experience = request.POST.get('python_experience', 'beginner')
                StudentProfile.objects.create(
                    user=user,
                    python_experience=python_experience
                )

            # Log the user in
            login(request, user)
            messages.success(request, f'Welcome {username}! Your account has been created.')
            return redirect('accounts:dashboard')

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

        # Authenticate user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')

            # Redirect to next parameter or dashboard
            next_url = request.GET.get('next', 'accounts:dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
            return render(request, 'accounts/login.html')

    return render(request, 'accounts/login.html')


def logout_view(request):
    """User logout view"""
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
        user.email = request.POST.get('email', user.email)
        user.bio = request.POST.get('bio', '')

        # Handle profile picture upload
        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']

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

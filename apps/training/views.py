from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.contrib import messages
import json

from .models import Exercise, Hint, Submission, HintUsage
from apps.accounts.models import StudentProfile
from apps.learning.models import Course


class ExerciseListView(LoginRequiredMixin, ListView):
    """Display all exercises with filtering"""
    model = Exercise
    template_name = 'training/exercise_list.html'
    context_object_name = 'exercises'
    paginate_by = 12

    def get_queryset(self):
        queryset = Exercise.objects.all()

        # Filter by difficulty
        difficulty = self.request.GET.get('difficulty')
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        # Filter by course
        course_id = self.request.GET.get('course')
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        # Search by title
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(title__icontains=search)

        # Meaningful progression: beginner → intermediate → advanced
        # (plain order_by('difficulty') would sort alphabetically)
        from django.db.models import Case, IntegerField, Value, When
        difficulty_rank = Case(
            When(difficulty='beginner', then=Value(0)),
            When(difficulty='intermediate', then=Value(1)),
            When(difficulty='advanced', then=Value(2)),
            default=Value(9),
            output_field=IntegerField(),
        )
        return queryset.annotate(difficulty_rank=difficulty_rank).order_by(
            'difficulty_rank', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_create'] = (
            self.request.user.is_staff or self.request.user.user_type == 'instructor'
        )

        # Add user's completion status if authenticated
        if self.request.user.is_authenticated:
            completed_exercises = Submission.objects.filter(
                student=self.request.user,
                status='passed'
            ).values_list('exercise_id', flat=True)
            context['completed_exercises'] = list(completed_exercises)

        return context


class ExerciseDetailView(LoginRequiredMixin, DetailView):
    """Display exercise details with code editor"""
    model = Exercise
    template_name = 'training/exercise_detail.html'
    context_object_name = 'exercise'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get student's previous submissions
        all_submissions = Submission.objects.filter(
            exercise=self.object,
            student=self.request.user
        ).order_by('-submitted_at')
        
        context['submissions'] = all_submissions[:5]

        # Get best submission (most recent passed)
        best_submission = all_submissions.filter(status='passed').first()
        context['best_submission'] = best_submission

        # Get hints (don't reveal content yet)
        hints = self.object.hints.all().order_by('order')
        context['hints'] = hints

        # Get hints already viewed by user
        viewed_hints = HintUsage.objects.filter(
            student=self.request.user,
            hint__exercise=self.object
        ).values_list('hint_id', flat=True)
        context['viewed_hints'] = list(viewed_hints)

        # Calculate hints used count for this exercise
        context['hints_used_count'] = len(viewed_hints)

        return context


@login_required
@require_http_methods(["POST"])
def submit_solution(request, slug):
    """Submit code solution for grading"""
    exercise = get_object_or_404(Exercise, slug=slug)

    try:
        data = json.loads(request.body)
        code = data.get('code', '')

        if not code:
            return JsonResponse({'error': 'No code provided'}, status=400)

        # Reject oversized submissions early (the sandbox has the same cap)
        from apps.code_runner.executor import MAX_CODE_LENGTH
        if len(code) > MAX_CODE_LENGTH:
            return JsonResponse({
                'error': f'代码过长（最多 {MAX_CODE_LENGTH} 字符）'
            }, status=400)

        # Count hints used for this exercise
        hints_used = HintUsage.objects.filter(
            student=request.user,
            hint__exercise=exercise
        ).count()

        # Create submission
        submission = Submission.objects.create(
            exercise=exercise,
            student=request.user,
            code=code,
            hints_used=hints_used
        )

        # Grade the submission — via Celery when a broker is configured,
        # inline otherwise (dev default). Refresh if it graded inline.
        from .tasks import grade_submission_async
        graded_inline = grade_submission_async(submission.id)
        if graded_inline:
            submission.refresh_from_db()

        return JsonResponse({
            'success': True,
            'submission_id': submission.id,
            'status': submission.status,
            'tests_passed': submission.tests_passed,
            'tests_total': submission.tests_total,
            'points_awarded': submission.points_awarded,
            'execution_time_ms': submission.execution_time_ms,
            'output': submission.output,
            'error_message': submission.error_message
        })

    except Exception as e:
        # Don't leak internal details to students (except in DEBUG)
        import logging
        logger = logging.getLogger(__name__)
        logger.exception('submit_solution failed')
        from django.conf import settings
        if getattr(settings, 'DEBUG', False):
            return JsonResponse({'error': str(e)}, status=500)
        return JsonResponse({'error': '提交失败，请重试'}, status=500)


@login_required
@require_http_methods(["POST"])
def view_hint(request, hint_id):
    """View a hint (with point penalty)"""
    hint = get_object_or_404(Hint, pk=hint_id)

    # Check if already viewed
    hint_usage, created = HintUsage.objects.get_or_create(
        student=request.user,
        hint=hint
    )

    if created:
        # Deduct points from student profile (atomic F() update, floored at 0)
        if hasattr(request.user, 'student_profile'):
            from django.db.models import F
            from django.db.models.functions import Greatest
            StudentProfile.objects.filter(pk=request.user.student_profile.pk).update(
                total_points=Greatest(F('total_points') - hint.points_penalty, 0)
            )

        return JsonResponse({
            'success': True,
            'first_view': True,
            'content': hint.content,
            'points_penalty': hint.points_penalty
        })
    else:
        # Already viewed, no penalty
        return JsonResponse({
            'success': True,
            'first_view': False,
            'content': hint.content,
            'points_penalty': 0
        })


@login_required
def exercise_create(request):
    """Create an exercise (instructor/staff) — title, code, test cases, hints."""
    if not (request.user.is_staff or request.user.user_type == 'instructor'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Only instructors can create exercises')

    if request.method == 'POST':
        try:
            import json as _json

            title = (request.POST.get('title') or '').strip()
            description = (request.POST.get('description') or '').strip()
            difficulty = request.POST.get('difficulty', 'beginner')
            points = int(request.POST.get('points', 10))
            starter_code = request.POST.get('starter_code', '')
            solution_code = request.POST.get('solution_code', '')
            course_id = request.POST.get('course_id') or None

            if not title or not description:
                messages.error(request, '标题与题目描述不能为空')
                return redirect('training:exercise-create')

            # Test cases: function-mode JSON array or stdin/stdout pairs
            try:
                test_cases = _json.loads(request.POST.get('test_cases', '[]'))
                if not isinstance(test_cases, list) or not test_cases:
                    raise ValueError('test_cases 必须是非空 JSON 数组')
            except (ValueError, _json.JSONDecodeError) as e:
                messages.error(request, f'测试用例格式错误: {e}')
                return redirect('training:exercise-create')

            course = Course.objects.filter(pk=course_id).first() if course_id else None

            exercise = Exercise.objects.create(
                title=title, description=description, difficulty=difficulty,
                points=points, starter_code=starter_code,
                solution_code=solution_code, test_cases=test_cases,
                course=course, created_by=request.user,
            )

            # Hints (up to 3, in order)
            for i in range(1, 4):
                hint_text = (request.POST.get(f'hint_{i}') or '').strip()
                penalty = int(request.POST.get(f'hint_penalty_{i}', 2))
                if hint_text:
                    Hint.objects.create(
                        exercise=exercise, content=hint_text, order=i,
                        points_penalty=penalty)

            messages.success(request, f'练习《{exercise.title}》已创建（立即对学生可见）')
            return redirect('training:exercise-detail', slug=exercise.slug)
        except Exception as e:
            messages.error(request, f'创建失败: {e}')
            return redirect('training:exercise-create')

    context = {'courses': Course.objects.filter(is_published=True)}
    return render(request, 'training/exercise_form.html', context)


@login_required
def submission_history(request, slug):
    """View all submissions for an exercise"""
    exercise = get_object_or_404(Exercise, slug=slug)

    submissions = Submission.objects.filter(
        exercise=exercise,
        student=request.user
    ).select_related('exercise').order_by('-submitted_at')

    context = {
        'exercise': exercise,
        'submissions': submissions
    }

    return render(request, 'training/submission_history.html', context)


@login_required
def submission_detail(request, pk):
    """View details of a specific submission"""
    submission = get_object_or_404(Submission, pk=pk, student=request.user)

    context = {
        'submission': submission
    }

    return render(request, 'training/submission_detail.html', context)


@login_required
def my_progress(request):
    """Student progress dashboard for exercises"""
    # Get all submissions
    submissions = Submission.objects.filter(student=request.user)

    # Statistics
    total_submissions = submissions.count()
    passed_submissions = submissions.filter(status='passed').count()
    total_points = request.user.student_profile.total_points if hasattr(request.user, 'student_profile') else 0

    # Get unique exercises attempted
    exercises_attempted = submissions.values('exercise').distinct().count()

    # Get recent submissions
    recent_submissions = submissions.select_related('exercise').order_by('-submitted_at')[:10]

    context = {
        'total_submissions': total_submissions,
        'passed_submissions': passed_submissions,
        'total_points': total_points,
        'exercises_attempted': exercises_attempted,
        'recent_submissions': recent_submissions
    }

    return render(request, 'training/progress.html', context)

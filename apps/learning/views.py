from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.db.models import F
from django.utils import timezone
import json

from .models import Course, Chapter, Lesson, Cell, CellVersion, Enrollment, LessonProgress


class CourseListView(ListView):
    """Display all published courses"""
    model = Course
    template_name = 'learning/course_list.html'
    context_object_name = 'courses'
    paginate_by = 12

    def get_queryset(self):
        queryset = Course.objects.filter(is_published=True)

        # Filter by difficulty if provided
        difficulty = self.request.GET.get('difficulty')
        if difficulty:
            queryset = queryset.filter(difficulty_level=difficulty)

        # Search by title
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(title__icontains=search)

        return queryset.order_by('-created_at')


class CourseDetailView(DetailView):
    """Display course details with chapters and lessons"""
    model = Course
    template_name = 'learning/course_detail.html'
    context_object_name = 'course'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if user is enrolled
        if self.request.user.is_authenticated:
            context['is_enrolled'] = Enrollment.objects.filter(
                student=self.request.user,
                course=self.object,
                is_active=True
            ).exists()

            # Get user's enrollment if exists
            try:
                enrollment = Enrollment.objects.get(
                    student=self.request.user,
                    course=self.object
                )
                context['enrollment'] = enrollment
                context['progress_percentage'] = enrollment.progress_percentage
            except Enrollment.DoesNotExist:
                pass

        return context


@login_required
@require_http_methods(["POST"])
def enroll_course(request, slug):
    """Enroll user in a course"""
    course = get_object_or_404(Course, slug=slug, is_published=True)

    enrollment, created = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
        defaults={'is_active': True}
    )

    if not created:
        enrollment.is_active = True
        enrollment.save()

    return redirect('learning:course-detail', slug=course.slug)


class LessonDetailView(LoginRequiredMixin, DetailView):
    """Display lesson in notebook interface (read-only for students)"""
    model = Lesson
    template_name = 'learning/lesson_detail.html'
    context_object_name = 'lesson'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all cells for this lesson
        context['cells'] = self.object.cells.all().order_by('order')

        # Check if user is enrolled
        enrollment = Enrollment.objects.filter(
            student=self.request.user,
            course=self.object.chapter.course,
            is_active=True
        ).first()

        if enrollment:
            context['enrollment'] = enrollment

            # Get or create lesson progress
            progress, created = LessonProgress.objects.get_or_create(
                enrollment=enrollment,
                lesson=self.object
            )
            context['progress'] = progress

        # Check if user can edit (instructor or admin)
        context['can_edit'] = (
            self.request.user == self.object.chapter.course.instructor or
            self.request.user.is_staff
        )

        return context


class LessonEditView(LoginRequiredMixin, DetailView):
    """Editable notebook interface for instructors"""
    model = Lesson
    template_name = 'learning/lesson_edit.html'
    context_object_name = 'lesson'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cells'] = self.object.cells.all().order_by('order')
        context['is_editing'] = True
        return context


@login_required
@require_http_methods(["POST"])
def create_cell(request):
    """Create a new cell in a lesson"""
    try:
        data = json.loads(request.body)
        lesson_id = data.get('lesson_id')
        cell_type = data.get('cell_type')
        order = data.get('order', 0)

        lesson = get_object_or_404(Lesson, pk=lesson_id)

        # Check permission (instructor or admin)
        if request.user != lesson.chapter.course.instructor and not request.user.is_staff:
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Shift existing cells down if inserting in the middle
        if order is not None:
            Cell.objects.filter(lesson=lesson, order__gte=order).update(order=F('order') + 1)

        # Create default cell data based on type
        default_data = {
            'text': {'markdown': '# New Text Cell\n\nEdit this cell...', 'rendered_html': ''},
            'code': {'source': '# Write your Python code here\n', 'output': '', 'execution_count': 0},
            'image': {'url': '', 'caption': '', 'alt_text': ''},
            'video': {'url': '', 'source_type': 'youtube', 'caption': ''},
        }

        cell = Cell.objects.create(
            lesson=lesson,
            cell_type=cell_type,
            order=order,
            data=default_data.get(cell_type, {}),
            created_by=request.user
        )

        return JsonResponse({
            'success': True,
            'cell': {
                'id': cell.id,
                'type': cell.cell_type,
                'order': cell.order,
                'data': cell.data
            }
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def update_cell(request, pk):
    """Update cell content"""
    try:
        cell = get_object_or_404(Cell, pk=pk)

        # Check permission
        if request.user != cell.lesson.chapter.course.instructor and not request.user.is_staff:
            return JsonResponse({'error': 'Permission denied'}, status=403)

        data = json.loads(request.body)
        new_data = data.get('data', {})

        # Save version before updating
        CellVersion.objects.create(
            cell=cell,
            snapshot={
                'cell_type': cell.cell_type,
                'data': cell.data,
                'order': cell.order
            },
            editor=request.user,
            change_description=data.get('change_description', 'Cell updated')
        )

        # Update cell
        cell.data = new_data
        cell.last_edited_by = request.user
        cell.save()

        return JsonResponse({
            'success': True,
            'cell': {
                'id': cell.id,
                'data': cell.data,
                'updated_at': cell.updated_at.isoformat()
            }
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def delete_cell(request, pk):
    """Delete a cell"""
    try:
        cell = get_object_or_404(Cell, pk=pk)

        # Check permission
        if request.user != cell.lesson.chapter.course.instructor and not request.user.is_staff:
            return JsonResponse({'error': 'Permission denied'}, status=403)

        lesson = cell.lesson
        order = cell.order

        # Delete the cell
        cell.delete()

        # Reorder remaining cells
        Cell.objects.filter(lesson=lesson, order__gt=order).update(order=F('order') - 1)

        return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def execute_cell(request, pk):
    """Execute a code cell"""
    try:
        cell = get_object_or_404(Cell, pk=pk)

        if cell.cell_type != 'code':
            return JsonResponse({'error': 'Only code cells can be executed'}, status=400)

        # Execute the cell
        result = cell.execute()

        # Track execution in progress
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=cell.lesson.chapter.course,
            is_active=True
        ).first()

        if enrollment:
            progress, _ = LessonProgress.objects.get_or_create(
                enrollment=enrollment,
                lesson=cell.lesson
            )
            progress.track_cell_execution(cell.id)

        return JsonResponse({
            'success': True,
            'output': cell.data.get('output', ''),
            'status': cell.data.get('status', 'error'),
            'execution_time_ms': cell.data.get('execution_time_ms', 0),
            'execution_count': cell.data.get('execution_count', 0)
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def reorder_cells(request):
    """Reorder cells in a lesson"""
    try:
        data = json.loads(request.body)
        lesson_id = data.get('lesson_id')
        cell_orders = data.get('cell_orders', [])  # List of {id: cell_id, order: new_order}

        lesson = get_object_or_404(Lesson, pk=lesson_id)

        # Check permission
        if request.user != lesson.chapter.course.instructor and not request.user.is_staff:
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Update cell orders
        with transaction.atomic():
            for item in cell_orders:
                Cell.objects.filter(id=item['id'], lesson=lesson).update(order=item['order'])

        return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def mark_lesson_complete(request, pk):
    """Mark a lesson as completed"""
    try:
        lesson = get_object_or_404(Lesson, pk=pk)

        enrollment = get_object_or_404(
            Enrollment,
            student=request.user,
            course=lesson.chapter.course,
            is_active=True
        )

        progress, _ = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson
        )

        progress.mark_complete()

        return JsonResponse({
            'success': True,
            'course_progress': enrollment.progress_percentage
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

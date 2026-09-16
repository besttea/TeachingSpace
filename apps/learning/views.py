from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, UpdateView
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.conf import settings
import json
import logging
from django.core.serializers.json import DjangoJSONEncoder

from .models import Course, Chapter, Lesson, Cell, CellVersion, Enrollment, LessonProgress
from .cell_handlers import get_handler

logger = logging.getLogger(__name__)


def _can_edit_lesson(user, lesson):
    """Instructor of the owning course, or staff."""
    return user == lesson.chapter.course.instructor or user.is_staff


def _error_response(e):
    """Uniform API error handling: no internal details to clients (except DEBUG)."""
    logger.exception('Learning API error')
    if getattr(settings, 'DEBUG', False):
        return _error_response(e)
    return JsonResponse({'error': '操作失败，请重试'}, status=400)


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

    def get_queryset(self):
        """Unpublished courses are only visible to their instructor/staff."""
        qs = Course.objects.all()
        user = self.request.user
        if not (user.is_authenticated and user.is_staff):
            qs = qs.filter(is_published=True)
            if user.is_authenticated:
                qs = qs | Course.objects.filter(instructor=user)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if user.is_authenticated:
            context['can_edit'] = (user == self.object.instructor or user.is_staff)
            context['is_enrolled'] = Enrollment.objects.filter(
                student=user,
                course=self.object,
                is_active=True
            ).exists()

            enrollment = None
            try:
                enrollment = Enrollment.objects.get(
                    student=user,
                    course=self.object
                )
                context['enrollment'] = enrollment
                context['progress_percentage'] = enrollment.progress_percentage
                context['completed_lessons_count'] = enrollment.lesson_progress.filter(is_completed=True).count()
            except Enrollment.DoesNotExist:
                pass

            # Precomputed chapter → lesson structure with per-lesson progress,
            # so the template runs in O(chapters + lessons) queries instead of
            # re-loading all progress rows for every lesson (O(L²)).
            progress_map = {}
            if enrollment:
                progress_map = {
                    lp.lesson_id: lp for lp in enrollment.lesson_progress.all()
                }
            chapters_data = []
            for chapter in self.object.chapters.all().prefetch_related('lessons'):
                lessons_data = []
                for lesson in chapter.lessons.all():
                    lp = progress_map.get(lesson.id)
                    lessons_data.append({
                        'lesson': lesson,
                        'progress': lp,
                        'is_completed': lp.is_completed if lp else False,
                    })
                chapters_data.append({'chapter': chapter, 'lessons': lessons_data})
            context['chapters_data'] = chapters_data

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

    def get_queryset(self):
        """Draft/archived lessons are only visible to the instructor/staff."""
        qs = Lesson.objects.all()
        user = self.request.user
        if not user.is_staff:
            qs = qs.filter(
                Q(status='published') | Q(chapter__course__instructor=user)
            )
        return qs

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


class LessonEditView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Editable notebook interface for instructors"""
    model = Lesson
    template_name = 'learning/lesson_edit.html'
    context_object_name = 'lesson'

    def test_func(self):
        lesson = self.get_object()
        return _can_edit_lesson(self.request.user, lesson)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cells = self.object.cells.all().order_by('order')
        context['cells'] = cells
        context['is_editing'] = True
        
        # Serialize cells for JS
        cells_data = []
        for cell in cells:
            cells_data.append({
                'id': cell.id,
                'cell_type': cell.cell_type,
                'order': cell.order,
                'data': cell.data
            })
        context['cells_json'] = json.dumps(cells_data, cls=DjangoJSONEncoder)
        
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
        if not _can_edit_lesson(request.user, lesson):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Validate cell type against the model's choices
        if cell_type not in dict(Cell.CELL_TYPES):
            return JsonResponse({'error': f'Invalid cell type: {cell_type}'}, status=400)

        # Shift existing cells down if inserting in the middle. Update rows
        # one by one, highest first, so the (lesson, order) unique constraint
        # never collides mid-operation.
        with transaction.atomic():
            for cell_id in Cell.objects.filter(
                lesson=lesson, order__gte=order
            ).order_by('-order').values_list('id', flat=True):
                Cell.objects.filter(id=cell_id).update(order=F('order') + 1)

        # Create default cell data based on type
        default_data = {
            'text': {'markdown': '# New Text Cell\n\nEdit this cell...', 'rendered_html': ''},
            'code': {'source': '# Write your Python code here\n', 'output': '', 'execution_count': 0},
            'image': {'url': '', 'caption': '', 'alt_text': ''},
            'video': {'url': '', 'source_type': 'youtube', 'caption': ''},
        }
        
        cell_data = default_data.get(cell_type, {})
        
        # Validate and process using handler
        handler = get_handler(cell_type)
        if handler:
            handler.validate(cell_data)
            cell_data = handler.process(cell_data)

        cell = Cell.objects.create(
            lesson=lesson,
            cell_type=cell_type,
            order=order,
            data=cell_data,
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
        return _error_response(e)


@login_required
@require_http_methods(["POST"])
def update_cell(request, pk):
    """Update cell content"""
    try:
        cell = get_object_or_404(Cell, pk=pk)

        # Check permission
        if not _can_edit_lesson(request.user, cell.lesson):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        data = json.loads(request.body)
        new_data = data.get('data', {})

        # Validate and process using handler
        handler = get_handler(cell.cell_type)
        if handler:
            # Merge with existing data to ensure required fields exist if partial update
            # But here we expect full data replacement usually
            handler.validate(new_data)
            new_data = handler.process(new_data)

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
        return _error_response(e)


@login_required
@require_http_methods(["POST"])
def delete_cell(request, pk):
    """Delete a cell"""
    try:
        cell = get_object_or_404(Cell, pk=pk)

        # Check permission
        if not _can_edit_lesson(request.user, cell.lesson):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        lesson = cell.lesson
        order = cell.order

        # Delete the cell, then renumber the rest one by one (lowest first)
        # so the (lesson, order) unique constraint never collides.
        with transaction.atomic():
            cell.delete()
            for cell_id in Cell.objects.filter(
                lesson=lesson, order__gt=order
            ).order_by('order').values_list('id', flat=True):
                Cell.objects.filter(id=cell_id).update(order=F('order') - 1)

        return JsonResponse({'success': True})

    except Exception as e:
        return _error_response(e)


@login_required
@require_http_methods(["POST"])
def execute_cell(request, pk):
    """Execute a code cell (students must be enrolled in the course)"""
    try:
        cell = get_object_or_404(Cell, pk=pk)

        if cell.cell_type != 'code':
            return JsonResponse({'error': 'Only code cells can be executed'}, status=400)

        lesson = cell.lesson

        # Only the course instructor/staff or enrolled students may run code
        is_instructor = _can_edit_lesson(request.user, lesson)
        enrolled = Enrollment.objects.filter(
            student=request.user,
            course=lesson.chapter.course,
            is_active=True
        ).exists()
        if not (is_instructor or enrolled):
            return JsonResponse({
                'error': 'You must be enrolled in this course to execute code cells'
            }, status=403)

        # Execute WITHOUT persisting the student's output into the shared
        # lesson cell (students must not overwrite each other's results).
        from apps.code_runner.executor import CodeExecutor
        code = cell.data.get('source', '')
        result = CodeExecutor().execute_code(code)

        # Track execution in progress
        if enrolled:
            enrollment = Enrollment.objects.get(
                student=request.user,
                course=lesson.chapter.course,
                is_active=True
            )
            progress, _ = LessonProgress.objects.get_or_create(
                enrollment=enrollment,
                lesson=lesson
            )
            progress.track_cell_execution(cell.id)

        return JsonResponse({
            'success': True,
            'output': result.get('output', ''),
            'status': result.get('status', 'error'),
            'execution_time_ms': result.get('execution_time', 0),
            'execution_count': cell.data.get('execution_count', 0)
        })

    except Exception as e:
        return _error_response(e)


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
        if not _can_edit_lesson(request.user, lesson):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Update cell orders (two-phase: jump to a safe range first so
        # swaps like A:0→1, B:1→0 never collide on the unique constraint)
        with transaction.atomic():
            existing_ids = set(
                lesson.cells.values_list('id', flat=True)
            )
            submitted = {int(item.get('id')) for item in cell_orders}
            submitted_orders = [int(item.get('order')) for item in cell_orders]

            if submitted != existing_ids:
                raise ValueError('提交的顺序列表与本课程单元的单元格不一致')
            if sorted(submitted_orders) != list(range(len(cell_orders))):
                raise ValueError('顺序必须是 0..n-1 的完整排列')

            Cell.objects.filter(lesson=lesson, id__in=submitted).update(
                order=F('order') + 1_000_000
            )
            for item in cell_orders:
                Cell.objects.filter(
                    id=int(item['id']), lesson=lesson
                ).update(order=int(item['order']))

        return JsonResponse({'success': True})

    except Exception as e:
        return _error_response(e)


@login_required
@require_http_methods(["POST"])
def restore_cell_version(request, pk, version_id):
    """Restore a cell to a previous CellVersion snapshot (undo).

    Restores cell_type + data; the cell keeps its current order (restoring
    an old order could collide with the unique constraint). The current
    state is snapshotted first, so the restore itself is undoable.
    """
    try:
        cell = get_object_or_404(Cell, pk=pk)

        if not _can_edit_lesson(request.user, cell.lesson):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        version = get_object_or_404(CellVersion, pk=version_id, cell=cell)
        snapshot = version.snapshot or {}

        with transaction.atomic():
            # Snapshot the current state so the restore can be reverted
            CellVersion.objects.create(
                cell=cell,
                snapshot={
                    'cell_type': cell.cell_type,
                    'data': cell.data,
                    'order': cell.order,
                },
                editor=request.user,
                change_description=f'Restore of version #{version.id}'
            )

            cell.cell_type = snapshot.get('cell_type', cell.cell_type)
            cell.data = snapshot.get('data', cell.data)
            cell.last_edited_by = request.user
            cell.save()

        return JsonResponse({
            'success': True,
            'cell': {'id': cell.id, 'cell_type': cell.cell_type, 'data': cell.data}
        })

    except Exception as e:
        return _error_response(e)


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
        return _error_response(e)

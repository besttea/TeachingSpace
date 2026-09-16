from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.views.generic import ListView, DetailView, UpdateView
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.db.models import F, Q, Count, Prefetch
from django.utils import timezone
from django.conf import settings
import json
import logging
from django.core.serializers.json import DjangoJSONEncoder

from .models import Course, Chapter, Lesson, Cell, CellVersion, Enrollment, LessonProgress
from .cell_handlers import get_handler
from apps.core.rate_limit import rate_limit

logger = logging.getLogger(__name__)


def _can_edit_lesson(user, lesson):
    """Instructor of the owning course, or staff."""
    return user == lesson.chapter.course.instructor or user.is_staff


def _error_response(e):
    """Uniform API error handling: no internal details to clients (except DEBUG)."""
    logger.exception('Learning API error')
    if getattr(settings, 'DEBUG', False):
        return JsonResponse({'error': str(e)}, status=400)
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
            chapters_qs = self.object.chapters.all().prefetch_related(
                Prefetch(
                    'lessons',
                    queryset=Lesson.objects.annotate(cell_count=Count('cells')),
                )
            )
            for chapter in chapters_qs:
                lessons_data = []
                for lesson in chapter.lessons.all():
                    lp = progress_map.get(lesson.id)
                    lessons_data.append({
                        'lesson': lesson,
                        'progress': lp,
                        'is_completed': lp.is_completed if lp else False,
                        'cell_count': getattr(lesson, 'cell_count', 0),
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


# ---------------------------------------------------------------------------
# Instructor console (course / chapter / lesson management + student roster)
# ---------------------------------------------------------------------------


class InstructorDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Instructor console: own courses + create form."""
    model = Course
    template_name = 'learning/instructor/dashboard.html'
    context_object_name = 'courses'
    paginate_by = 20

    def test_func(self):
        return self.request.user.is_staff or self.request.user.user_type == 'instructor'

    def get_queryset(self):
        qs = Course.objects.filter(instructor=self.request.user)
        return qs.prefetch_related('chapters__lessons').order_by('-created_at')


@login_required
@require_http_methods(["POST"])
def instructor_course_create(request):
    """Create a course (instructor; starts unpublished).

    Two flows:
    1. Manual: title/description only → empty draft course.
    2. AI-assisted: ``ai_design=on`` + topic → the CourseDesignAgent generates
       chapters + lesson outline (optionally grounded in ClassLib material);
       the instructor then generates cell content per lesson on the outline page.
    """
    if not (request.user.is_staff or request.user.user_type == 'instructor'):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    try:
        title = (request.POST.get('title') or '').strip()
        description = (request.POST.get('description') or '').strip()
        difficulty = request.POST.get('difficulty', 'beginner')
        if not title:
            messages.error(request, '课程标题不能为空')
            return redirect('learning:instructor-dashboard')
        if difficulty not in dict(Course.DIFFICULTY_CHOICES):
            difficulty = 'beginner'

        course = Course.objects.create(
            title=title,
            description=description or '（暂无描述）',
            difficulty_level=difficulty,
            instructor=request.user,
            is_published=False,  # publish explicitly when ready
        )

        # ---- AI-assisted design flow ----
        if request.POST.get('ai_design') == 'on':
            from apps.ai_agents.ai_config import is_configured
            if not is_configured():
                messages.warning(
                    request, 'AI 服务未配置（缺少 API 密钥），已按手动流程创建空课程；'
                             '配置后可在课程详情页添加章节/课程单元')
                return redirect('learning:instructor-course-manage', slug=course.slug)

            try:
                from apps.ai_agents.skills import CourseSkill
                from apps.chat.notebook_tools import find_related_sections

                chapter_count = int(request.POST.get('chapter_count', 3) or 3)
                use_material = request.POST.get('use_classlib') == 'on'

                source_material = ''
                if use_material:
                    source_material = find_related_sections(title)
                    if source_material:
                        messages.success(
                            request, f'已在 ClassLib 中找到与《{title}》相关的教学素材，'
                                     f'大纲与内容将基于素材生成')

                # Harness CourseSkill: planner-role outline (content off — the
                # instructor fills it per chapter on the course page)
                outline = CourseSkill().run(
                    topic=title,
                    difficulty=difficulty,
                    chapter_count=chapter_count,
                    source_material=source_material,
                    with_content=False,
                )

                created = 0
                for chapter_index, chapter_data in enumerate(outline.get('chapters', [])):
                    chapter = Chapter.objects.create(
                        course=course,
                        title=chapter_data.get('title') or f'第{chapter_index + 1}章',
                        description=chapter_data.get('description', ''),
                        order=chapter_index,
                    )
                    for lesson_index, lesson_data in enumerate(
                            chapter_data.get('lessons', [])):
                        Lesson.objects.create(
                            chapter=chapter,
                            title=lesson_data.get('title') or f'课程单元 {lesson_index + 1}',
                            description=lesson_data.get('description', ''),
                            status='draft',
                            order=lesson_index,
                            created_by=request.user,
                        )
                        created += 1

                messages.success(
                    request, f'AI 已生成课程大纲：{len(outline.get("chapters", []))} 章 '
                             f'{created} 个课程单元。请在下方为每个单元生成内容。')
                return redirect('learning:instructor-course-outline', slug=course.slug)

            except Exception as e:
                logger.exception('AI course design failed')
                messages.warning(
                    request, f'AI 大纲生成失败（{e if settings.DEBUG else "请重试"}），'
                             f'已创建空课程，可手动添加章节')
                return redirect('learning:instructor-course-manage', slug=course.slug)

        messages.success(request, f'课程《{course.title}》已创建（草稿状态，学生不可见）')
        return redirect('learning:instructor-course-manage', slug=course.slug)
    except Exception as e:
        return _error_response(e)


class CourseOutlineView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """AI-assisted course outline review: generate content per lesson."""
    model = Course
    template_name = 'learning/instructor/outline.html'
    context_object_name = 'course'
    slug_url_kwarg = 'slug'

    def test_func(self):
        course = self.get_object()
        return self.request.user == course.instructor or self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        chapters = []
        for chapter in self.object.chapters.all().prefetch_related('lessons'):
            lessons = []
            for lesson in chapter.lessons.all():
                lessons.append({
                    'lesson': lesson,
                    'cell_count': lesson.cells.count(),
                })
            chapters.append({'chapter': chapter, 'lessons': lessons})
        context['chapters'] = chapters
        context['total_empty'] = sum(
            1 for c in chapters for l in c['lessons'] if l['cell_count'] == 0)
        return context


@login_required
@require_http_methods(["POST"])
@rate_limit('lesson_ai_generate', limit=30, window_seconds=3600)
def instructor_lesson_generate(request, pk):
    """AI-generate the cell content of one lesson, grounded in ClassLib
    material when a match exists. Instructor-only."""
    try:
        lesson = get_object_or_404(Lesson, pk=pk)
        if not _can_edit_lesson(request.user, lesson):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        from apps.ai_agents.ai_config import is_configured
        if not is_configured():
            return JsonResponse({'error': 'AI 服务未配置（缺少 API 密钥）'}, status=400)

        from apps.ai_agents.learning_agent import LearningAgent
        from apps.chat.notebook_tools import find_related_sections

        # Auto-ground in ClassLib material matching the course + lesson topic
        query = f'{lesson.chapter.course.title} {lesson.title}'
        source_material = find_related_sections(query)

        generated = LearningAgent().generate_lesson_content(
            topic=lesson.title,
            difficulty=lesson.chapter.course.difficulty_level,
            include_code=True,
            source_material=source_material,
        )
        cells = generated.get('cells', [])
        if not cells:
            return JsonResponse({'error': 'AI 未返回课程单元内容'}, status=400)

        # Replace existing cells (re-generation is idempotent)
        with transaction.atomic():
            lesson.cells.all().delete()
            for order, cell in enumerate(cells):
                cell_type = cell.get('type')
                content = cell.get('content', '')
                if cell_type == 'code':
                    Cell.objects.create(
                        lesson=lesson, cell_type='code', order=order,
                        data={'source': content, 'output': '',
                              'execution_count': 0},
                        created_by=request.user)
                else:
                    Cell.objects.create(
                        lesson=lesson, cell_type='text', order=order,
                        data={'markdown': content},
                        created_by=request.user)

        return JsonResponse({
            'success': True,
            'cell_count': len(cells),
            'grounded': bool(source_material),
            'message': f'已生成 {len(cells)} 个单元格'
                       + ('（已用 ClassLib 素材接地）' if source_material else ''),
        })

    except Exception as e:
        return _error_response(e)


@login_required
@require_http_methods(["POST"])
@rate_limit('chapter_ai_plan', limit=30, window_seconds=3600)
def instructor_chapter_ai_plan(request, pk):
    """AI plans the lessons of one chapter (titles + descriptions), grounded
    in ClassLib material when available. Creates empty draft lessons."""
    try:
        chapter = get_object_or_404(Chapter, pk=pk)
        if not (request.user == chapter.course.instructor or request.user.is_staff):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        from apps.ai_agents.ai_config import is_configured
        if not is_configured():
            return JsonResponse({'error': 'AI 服务未配置（缺少 API 密钥）'}, status=400)

        from apps.ai_agents.course_design_agent import CourseDesignAgent
        from apps.chat.notebook_tools import find_related_sections

        course = chapter.course
        source_material = find_related_sections(f'{course.title} {chapter.title}')
        planned = CourseDesignAgent().design_chapter_lessons(
            chapter_title=chapter.title,
            course_topic=course.title,
            difficulty=course.difficulty_level,
            source_material=source_material,
        )

        lessons = planned.get('lessons', [])
        if not lessons:
            return JsonResponse({'error': 'AI 未返回课程单元规划'}, status=400)

        created = []
        base_order = Lesson.objects.filter(chapter=chapter).count()
        for index, lesson_data in enumerate(lessons):
            lesson = Lesson.objects.create(
                chapter=chapter,
                title=lesson_data.get('title') or f'课程单元 {index + 1}',
                description=lesson_data.get('description', ''),
                status='draft',
                order=base_order + index,
                created_by=request.user,
            )
            created.append({'id': lesson.id, 'title': lesson.title})

        return JsonResponse({
            'success': True,
            'lessons': created,
            'grounded': bool(source_material),
            'message': f'AI 已为本章规划 {len(created)} 个课程单元'
                       + ('（素材接地）' if source_material else ''),
        })

    except Exception as e:
        return _error_response(e)


@login_required
@require_http_methods(["POST"])
def instructor_chapter_create(request, slug):
    """Add a chapter to one of the instructor's courses."""
    course = get_object_or_404(Course, slug=slug)
    if not (request.user == course.instructor or request.user.is_staff):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    try:
        title = (request.POST.get('title') or '').strip()
        if not title:
            messages.error(request, '章节标题不能为空')
            return redirect('learning:instructor-course-manage', slug=slug)
        order = Chapter.objects.filter(course=course).count()
        Chapter.objects.create(
            course=course, title=title,
            description=(request.POST.get('description') or '').strip(),
            order=order)
        messages.success(request, f'章节《{title}》已添加')
    except Exception as e:
        return _error_response(e)
    return redirect('learning:instructor-course-manage', slug=slug)


@login_required
@require_http_methods(["POST"])
def instructor_lesson_create(request, slug):
    """Create a lesson (draft) in a chapter; then open the notebook editor."""
    course = get_object_or_404(Course, slug=slug)
    if not (request.user == course.instructor or request.user.is_staff):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    try:
        title = (request.POST.get('title') or '').strip()
        chapter_id = request.POST.get('chapter_id')
        chapter = get_object_or_404(Chapter, pk=chapter_id, course=course)
        if not title:
            messages.error(request, '课程单元标题不能为空')
            return redirect('learning:instructor-course-manage', slug=slug)

        order = Lesson.objects.filter(chapter=chapter).count()
        lesson = Lesson.objects.create(
            chapter=chapter, title=title,
            description=(request.POST.get('description') or '').strip(),
            status='draft', order=order, created_by=request.user)
        messages.success(request, f'课程单元《{title}》已创建（草稿），开始编辑内容')
        return redirect('learning:lesson-edit', pk=lesson.pk)
    except Exception as e:
        return _error_response(e)


@login_required
@require_http_methods(["POST"])
def instructor_lesson_publish(request, pk):
    """Publish/unpublish a lesson of the instructor's course."""
    lesson = get_object_or_404(Lesson, pk=pk)
    if not _can_edit_lesson(request.user, lesson):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    try:
        action = (request.POST.get('action') or 'publish').strip()
        lesson.status = 'published' if action == 'publish' else 'draft'
        lesson.save()
        return JsonResponse({
            'success': True,
            'status': lesson.status,
            'message': '已发布' if lesson.status == 'published' else '已转为草稿',
        })
    except Exception as e:
        return _error_response(e)


@login_required
@require_http_methods(["POST"])
def instructor_course_publish(request, slug):
    """Publish/unpublish an instructor's course."""
    course = get_object_or_404(Course, slug=slug)
    if not (request.user == course.instructor or request.user.is_staff):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    try:
        action = (request.POST.get('action') or 'publish').strip()
        course.is_published = (action == 'publish')
        course.save()
        return JsonResponse({
            'success': True,
            'is_published': course.is_published,
            'message': '课程已发布' if course.is_published else '课程已下线为草稿',
        })
    except Exception as e:
        return _error_response(e)


class StudentRosterView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Students enrolled in one of the instructor's courses, with progress."""
    model = Course
    template_name = 'learning/instructor/student_roster.html'
    context_object_name = 'course'
    slug_url_kwarg = 'slug'

    def test_func(self):
        course = self.get_object()
        return self.request.user == course.instructor or self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.object
        enrollments = Enrollment.objects.filter(
            course=course
        ).select_related('student').prefetch_related('lesson_progress__lesson')

        roster = []
        for enrollment in enrollments:
            progress_rows = {lp.lesson_id: lp for lp in enrollment.lesson_progress.all()}
            total_published = course.chapters.filter(
                lessons__status='published').count()
            completed = sum(1 for lp in progress_rows.values() if lp.is_completed)
            roster.append({
                'student': enrollment.student,
                'enrolled_at': enrollment.enrolled_at,
                'progress_percentage': enrollment.progress_percentage,
                'completed_lessons': completed,
                'total_lessons': total_published,
            })
        context['roster'] = roster
        return context


# ---------------------------------------------------------------------------
# Cell CRUD API
# ---------------------------------------------------------------------------


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
@rate_limit('kernel_execute', limit=60, window_seconds=300)
def kernel_execute(request, pk):
    """Execute code in the lesson's real Jupyter kernel (persistent state,
    rich outputs). Students must be enrolled; instructors/staff always may."""
    try:
        lesson = get_object_or_404(Lesson, pk=pk)

        is_instructor = _can_edit_lesson(request.user, lesson)
        enrolled = Enrollment.objects.filter(
            student=request.user,
            course=lesson.chapter.course,
            is_active=True
        ).exists()
        if not (is_instructor or enrolled):
            return JsonResponse({
                'error': 'You must be enrolled in this course to execute code'
            }, status=403)

        data = json.loads(request.body)
        code = data.get('code', '')
        if not code.strip():
            return JsonResponse({'error': 'No code provided'}, status=400)

        from .jupyter_kernel import manager as kernel_manager
        result = kernel_manager.execute(request.user.id, lesson.id, code)

        return JsonResponse({
            'success': True,
            'outputs': result['outputs'],
            'execution_count': result['execution_count'],
        })

    except Exception as e:
        return _error_response(e)


@login_required
@require_http_methods(["POST"])
def kernel_restart(request, pk):
    """Restart the lesson's Jupyter kernel (clears all variables)."""
    try:
        lesson = get_object_or_404(Lesson, pk=pk)

        if not (_can_edit_lesson(request.user, lesson) or Enrollment.objects.filter(
                student=request.user, course=lesson.chapter.course,
                is_active=True).exists()):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        from .jupyter_kernel import manager as kernel_manager
        kernel_manager.restart(request.user.id, lesson.id)

        return JsonResponse({
            'success': True,
            'message': '内核已重启，所有变量已清空'
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

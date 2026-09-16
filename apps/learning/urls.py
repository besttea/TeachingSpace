from django.urls import path
from . import views

app_name = 'learning'

urlpatterns = [
    # Course URLs
    path('courses/', views.CourseListView.as_view(), name='course-list'),
    path('courses/<slug:slug>/', views.CourseDetailView.as_view(), name='course-detail'),
    path('courses/<slug:slug>/enroll/', views.enroll_course, name='course-enroll'),

    # Lesson URLs (notebook interface)
    path('lessons/<int:pk>/', views.LessonDetailView.as_view(), name='lesson-detail'),
    path('lessons/<int:pk>/edit/', views.LessonEditView.as_view(), name='lesson-edit'),

    # Instructor console
    path('instructor/', views.InstructorDashboardView.as_view(), name='instructor-dashboard'),
    path('instructor/course/create/', views.instructor_course_create, name='instructor-course-create'),
    path('instructor/course/<slug:slug>/', views.CourseDetailView.as_view(), name='instructor-course-manage'),
    path('instructor/course/<slug:slug>/chapter/create/', views.instructor_chapter_create, name='instructor-chapter-create'),
    path('instructor/course/<slug:slug>/lesson/create/', views.instructor_lesson_create, name='instructor-lesson-create'),
    path('instructor/course/<slug:slug>/students/', views.StudentRosterView.as_view(), name='instructor-student-roster'),
    path('instructor/course/<slug:slug>/publish/', views.instructor_course_publish, name='instructor-course-publish'),
    path('instructor/course/<slug:slug>/outline/', views.CourseOutlineView.as_view(), name='instructor-course-outline'),
    path('api/lessons/<int:pk>/ai-generate/', views.instructor_lesson_generate, name='lesson-ai-generate'),
    path('api/chapters/<int:pk>/ai-plan/', views.instructor_chapter_ai_plan, name='chapter-ai-plan'),
    path('api/lessons/<int:pk>/publish/', views.instructor_lesson_publish, name='lesson-publish'),

    # Cell CRUD API
    path('api/cells/create/', views.create_cell, name='cell-create'),
    path('api/cells/<int:pk>/update/', views.update_cell, name='cell-update'),
    path('api/cells/<int:pk>/delete/', views.delete_cell, name='cell-delete'),
    path('api/cells/<int:pk>/execute/', views.execute_cell, name='cell-execute'),
    path('api/cells/<int:pk>/versions/<int:version_id>/restore/', views.restore_cell_version, name='cell-restore-version'),
    path('api/cells/reorder/', views.reorder_cells, name='cells-reorder'),

    # Progress tracking
    path('api/lessons/<int:pk>/mark-complete/', views.mark_lesson_complete, name='lesson-complete'),

    # Jupyter kernel sessions (real notebook execution)
    path('api/lessons/<int:pk>/kernel/execute/', views.kernel_execute, name='kernel-execute'),
    path('api/lessons/<int:pk>/kernel/restart/', views.kernel_restart, name='kernel-restart'),
]

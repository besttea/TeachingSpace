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
    path('instructor/course/<slug:slug>/publish-all/', views.instructor_course_publish_all, name='instructor-course-publish-all'),
    path('instructor/course/<slug:slug>/outline/', views.CourseOutlineView.as_view(), name='instructor-course-outline'),
    path('api/courses/<int:pk>/design-status/', views.course_design_status_view, name='course-design-status'),
    path('api/lessons/<int:pk>/ai-generate/', views.instructor_lesson_generate, name='lesson-ai-generate'),
    path('api/lessons/<int:pk>/generate-status/', views.lesson_generate_status, name='lesson-generate-status'),
    path('api/chapters/<int:pk>/ai-plan/', views.instructor_chapter_ai_plan, name='chapter-ai-plan'),
    path('api/lessons/<int:pk>/publish/', views.instructor_lesson_publish, name='lesson-publish'),

    # Cell CRUD API
    path('api/cells/create/', views.create_cell, name='cell-create'),
    path('api/cells/<int:pk>/update/', views.update_cell, name='cell-update'),
    path('api/cells/<int:pk>/delete/', views.delete_cell, name='cell-delete'),
    path('api/cells/<int:pk>/execute/', views.execute_cell, name='cell-execute'),
    path('api/cells/<int:pk>/versions/', views.cell_versions, name='cell-versions'),
    path('api/cells/<int:pk>/versions/<int:version_id>/restore/', views.restore_cell_version, name='cell-restore-version'),
    path('api/cells/reorder/', views.reorder_cells, name='cells-reorder'),

    # Progress tracking
    path('api/lessons/<int:pk>/mark-complete/', views.mark_lesson_complete, name='lesson-complete'),
    path('api/lessons/<int:pk>/heartbeat/', views.lesson_heartbeat, name='lesson-heartbeat'),

    # Knowledge points (course-scoped; instructor AI extraction + CRUD)
    path('api/courses/<int:pk>/kp-extract/', views.course_kp_extract, name='course-kp-extract'),
    path('api/courses/<int:pk>/kp-status/', views.course_kp_status, name='course-kp-status'),
    path('api/courses/<int:pk>/kp-add/', views.course_kp_add, name='course-kp-add'),
    path('api/knowledge-points/<int:pk>/update/', views.kp_update, name='kp-update'),
    path('api/knowledge-points/<int:pk>/delete/', views.kp_delete, name='kp-delete'),

    # Cell-level AI generation (lesson editor toolbar — four skills)
    path('api/cells/<int:pk>/ai-text/', views.cell_ai_text, name='cell-ai-text'),
    path('api/cells/<int:pk>/ai-code/', views.cell_ai_code, name='cell-ai-code'),
    path('api/cells/<int:pk>/ai-image/', views.cell_ai_image, name='cell-ai-image'),
    path('api/cells/<int:pk>/ai-video/', views.cell_ai_video, name='cell-ai-video'),
    path('api/cells/<int:pk>/video-status/', views.cell_video_status_view,
         name='cell-video-status'),

    # Jupyter kernel sessions (real notebook execution)
    path('api/lessons/<int:pk>/kernel/execute/', views.kernel_execute, name='kernel-execute'),
    path('api/lessons/<int:pk>/kernel/restart/', views.kernel_restart, name='kernel-restart'),
]

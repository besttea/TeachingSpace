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

    # Cell CRUD API
    path('api/cells/create/', views.create_cell, name='cell-create'),
    path('api/cells/<int:pk>/update/', views.update_cell, name='cell-update'),
    path('api/cells/<int:pk>/delete/', views.delete_cell, name='cell-delete'),
    path('api/cells/<int:pk>/execute/', views.execute_cell, name='cell-execute'),
    path('api/cells/<int:pk>/versions/<int:version_id>/restore/', views.restore_cell_version, name='cell-restore-version'),
    path('api/cells/reorder/', views.reorder_cells, name='cells-reorder'),

    # Progress tracking
    path('api/lessons/<int:pk>/mark-complete/', views.mark_lesson_complete, name='lesson-complete'),
]

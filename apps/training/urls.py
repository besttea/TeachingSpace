from django.urls import path
from . import views

app_name = 'training'

urlpatterns = [
    # Exercise browsing
    path('exercises/', views.ExerciseListView.as_view(), name='exercise-list'),
    path('exercises/create/', views.exercise_create, name='exercise-create'),
    path('exercises/<int:pk>/edit/', views.exercise_edit, name='exercise-edit'),
    path('exercises/<int:pk>/delete/', views.exercise_delete, name='exercise-delete'),
    path('exercises/<slug:slug>/', views.ExerciseDetailView.as_view(), name='exercise-detail'),

    # Submission
    path('exercises/<slug:slug>/submit/', views.submit_solution, name='submit-solution'),
    path('exercises/<slug:slug>/history/', views.submission_history, name='submission-history'),
    path('submissions/<int:pk>/', views.submission_detail, name='submission-detail'),
    path('api/exercises/<int:pk>/ai-modify/', views.exercise_ai_modify, name='exercise-ai-modify'),
    path('api/exercises/ai-draft/', views.exercise_ai_draft, name='exercise-ai-draft'),

    # Hints
    path('api/hints/<int:hint_id>/view/', views.view_hint, name='view-hint'),

    # Progress
    path('my-progress/', views.my_progress, name='my-progress'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
]

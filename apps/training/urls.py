from django.urls import path
from . import views

app_name = 'training'

urlpatterns = [
    # Exercise browsing
    path('exercises/', views.ExerciseListView.as_view(), name='exercise-list'),
    path('exercises/create/', views.exercise_create, name='exercise-create'),
    path('exercises/<slug:slug>/', views.ExerciseDetailView.as_view(), name='exercise-detail'),

    # Submission
    path('exercises/<slug:slug>/submit/', views.submit_solution, name='submit-solution'),
    path('exercises/<slug:slug>/history/', views.submission_history, name='submission-history'),
    path('submissions/<int:pk>/', views.submission_detail, name='submission-detail'),

    # Hints
    path('api/hints/<int:hint_id>/view/', views.view_hint, name='view-hint'),

    # Progress
    path('my-progress/', views.my_progress, name='my-progress'),
]

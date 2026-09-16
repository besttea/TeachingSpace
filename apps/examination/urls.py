from django.urls import path
from . import views

app_name = 'examination'

urlpatterns = [
    # Exam list and detail
    path('', views.ExamListView.as_view(), name='exam-list'),
    path('manage/', views.InstructorExamListView.as_view(), name='exam-manage'),
    path('manage/<int:pk>/review/', views.ExamReviewView.as_view(), name='exam-review'),
    path('api/answers/<int:pk>/grade/', views.exam_review_grade, name='answer-grade'),
    path('api/<int:pk>/publish/', views.exam_publish, name='exam-publish'),
    path('api/questions/<int:pk>/ai-modify/', views.question_ai_modify, name='question-ai-modify'),
    path('manage/questions/<int:pk>/edit/', views.question_edit, name='question-edit'),
    path('<int:pk>/', views.ExamDetailView.as_view(), name='exam-detail'),

    # Exam taking flow
    path('<int:pk>/start/', views.start_exam, name='exam-start'),
    path('<int:exam_id>/take/<int:attempt_id>/', views.TakeExamView.as_view(), name='exam-take'),

    # AJAX endpoints
    path('api/save-answer/', views.save_answer, name='save-answer'),
    path('api/submit/', views.submit_exam, name='submit-exam'),

    # Results
    path('results/<int:attempt_id>/', views.ExamResultsView.as_view(), name='exam-results'),
    path('results/<int:attempt_id>/certificate/', views.certificate_download, name='exam-certificate'),

    # Public certificate verification
    path('certificates/<str:code>/', views.certificate_verify, name='certificate-verify'),
]

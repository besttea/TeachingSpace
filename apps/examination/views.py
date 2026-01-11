from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Q, Count
import json
import random

from .models import (
    Exam, Question, StudentExam, ExamAnswer,
    MultipleChoiceQuestion, CodeQuestion, EssayQuestion, TrueFalseQuestion
)
from apps.code_runner.executor import CodeExecutor


class ExamListView(LoginRequiredMixin, ListView):
    """Display list of available exams"""
    model = Exam
    template_name = 'examination/exam_list.html'
    context_object_name = 'exams'
    paginate_by = 10

    def get_queryset(self):
        """Only show published exams"""
        return Exam.objects.filter(is_published=True).annotate(
            question_count=Count('questions')
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add attempt counts for each exam
        if self.request.user.is_authenticated:
            for exam in context['exams']:
                exam.user_attempts = StudentExam.objects.filter(
                    exam=exam,
                    student=self.request.user
                ).count()
                exam.can_attempt = exam.user_attempts < exam.max_attempts
        return context


class ExamDetailView(LoginRequiredMixin, DetailView):
    """Display exam details before starting"""
    model = Exam
    template_name = 'examination/exam_detail.html'
    context_object_name = 'exam'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        exam = self.object

        # Get user's previous attempts
        attempts = StudentExam.objects.filter(
            exam=exam,
            student=self.request.user,
            is_submitted=True
        ).order_by('-attempt_number')

        context['attempts'] = attempts
        context['attempt_count'] = attempts.count()
        context['can_attempt'] = context['attempt_count'] < exam.max_attempts
        context['total_points'] = exam.get_total_points()

        # Check if there's an ongoing attempt
        ongoing = StudentExam.objects.filter(
            exam=exam,
            student=self.request.user,
            is_submitted=False
        ).first()
        context['ongoing_attempt'] = ongoing

        return context


@login_required
def start_exam(request, pk):
    """Start a new exam attempt"""
    exam = get_object_or_404(Exam, pk=pk, is_published=True)

    # Check if user has attempts remaining
    attempt_count = StudentExam.objects.filter(
        exam=exam,
        student=request.user
    ).count()

    if attempt_count >= exam.max_attempts:
        return JsonResponse({
            'success': False,
            'error': f'您已达到最大尝试次数 ({exam.max_attempts})'
        }, status=400)

    # Check if there's an ongoing attempt
    ongoing = StudentExam.objects.filter(
        exam=exam,
        student=request.user,
        is_submitted=False
    ).first()

    if ongoing:
        # Continue existing attempt
        return redirect('examination:exam-take', exam_id=exam.id, attempt_id=ongoing.id)

    # Create new attempt
    student_exam = StudentExam.objects.create(
        student=request.user,
        exam=exam,
        attempt_number=attempt_count + 1,
        time_remaining_seconds=exam.duration_minutes * 60
    )

    return redirect('examination:exam-take', exam_id=exam.id, attempt_id=student_exam.id)


class TakeExamView(LoginRequiredMixin, TemplateView):
    """Display exam interface with timer"""
    template_name = 'examination/exam_interface.html'

    def get(self, request, exam_id, attempt_id):
        student_exam = get_object_or_404(
            StudentExam,
            id=attempt_id,
            student=request.user,
            exam_id=exam_id
        )

        # Check if already submitted
        if student_exam.is_submitted:
            return redirect('examination:exam-results', attempt_id=student_exam.id)

        # Get questions (randomized if needed)
        questions = list(student_exam.exam.questions.all())

        if student_exam.exam.randomize_questions:
            # Use seed for consistent ordering
            random.seed(student_exam.randomization_seed)
            random.shuffle(questions)

        # Get existing answers
        existing_answers = {
            answer.question_id: answer
            for answer in ExamAnswer.objects.filter(student_exam=student_exam)
        }

        # Prepare questions with their specific details
        questions_data = []
        for question in questions:
            q_data = {
                'question': question,
                'existing_answer': existing_answers.get(question.id),
            }

            # Get specific question details
            specific = question.get_specific_question()
            if isinstance(specific, MultipleChoiceQuestion):
                q_data['mc_question'] = specific
            elif isinstance(specific, CodeQuestion):
                q_data['code_question'] = specific
            elif isinstance(specific, EssayQuestion):
                q_data['essay_question'] = specific
            elif isinstance(specific, TrueFalseQuestion):
                q_data['tf_question'] = specific

            questions_data.append(q_data)

        context = {
            'student_exam': student_exam,
            'exam': student_exam.exam,
            'questions': questions_data,
            'time_remaining': student_exam.time_remaining_seconds,
        }

        return render(request, self.template_name, context)


@login_required
@require_http_methods(["POST"])
def save_answer(request):
    """AJAX endpoint for auto-saving answers"""
    try:
        data = json.loads(request.body)
        student_exam_id = data.get('student_exam_id')
        question_id = data.get('question_id')
        answer_data = data.get('answer_data')

        student_exam = get_object_or_404(
            StudentExam,
            id=student_exam_id,
            student=request.user,
            is_submitted=False
        )

        question = get_object_or_404(Question, id=question_id, exam=student_exam.exam)

        # Create or update answer
        answer, created = ExamAnswer.objects.update_or_create(
            student_exam=student_exam,
            question=question,
            defaults={'answer_data': answer_data}
        )

        return JsonResponse({
            'success': True,
            'message': '答案已保存'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def submit_exam(request):
    """Finalize exam and calculate score"""
    try:
        data = json.loads(request.body)
        student_exam_id = data.get('student_exam_id')

        student_exam = get_object_or_404(
            StudentExam,
            id=student_exam_id,
            student=request.user,
            is_submitted=False
        )

        # Mark as submitted
        student_exam.is_submitted = True
        student_exam.end_time = timezone.now()
        student_exam.save()

        # Auto-grade all answers
        answers = ExamAnswer.objects.filter(student_exam=student_exam)
        for answer in answers:
            if answer.question.question_type in ['multiple_choice', 'true_false']:
                answer.auto_grade()

            # Grade code questions
            elif answer.question.question_type == 'code':
                code_question = answer.question.get_specific_question()
                if code_question:
                    executor = CodeExecutor()
                    code = answer.answer_data.get('code', '')

                    try:
                        result = executor.execute_with_tests(
                            code,
                            code_question.test_cases
                        )

                        # Calculate points based on passed tests
                        total_tests = len(code_question.test_cases)
                        passed_tests = result.get('passed', 0)

                        if total_tests > 0:
                            answer.points_awarded = int(
                                (passed_tests / total_tests) * answer.question.points
                            )
                            answer.is_correct = (passed_tests == total_tests)
                        else:
                            answer.points_awarded = 0
                            answer.is_correct = False

                        answer.feedback = result.get('message', '')
                        answer.status = 'graded'
                        answer.save()

                    except Exception as e:
                        answer.points_awarded = 0
                        answer.is_correct = False
                        answer.feedback = f'代码执行错误: {str(e)}'
                        answer.status = 'graded'
                        answer.save()

        # Calculate total score
        student_exam.score = student_exam.calculate_score()
        student_exam.save()

        # Update student profile
        if student_exam.is_passing():
            profile = request.user.student_profile
            profile.total_exams_passed += 1
            profile.save()

        return JsonResponse({
            'success': True,
            'score': student_exam.score,
            'is_passing': student_exam.is_passing(),
            'redirect_url': f'/examination/results/{student_exam.id}/'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


class ExamResultsView(LoginRequiredMixin, DetailView):
    """Display exam results and score breakdown"""
    model = StudentExam
    template_name = 'examination/exam_results.html'
    context_object_name = 'student_exam'
    pk_url_kwarg = 'attempt_id'

    def get_queryset(self):
        """Only allow users to view their own results"""
        return StudentExam.objects.filter(student=self.request.user, is_submitted=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student_exam = self.object

        # Get all answers with question details
        answers = ExamAnswer.objects.filter(
            student_exam=student_exam
        ).select_related('question').order_by('question__order')

        answers_data = []
        for answer in answers:
            a_data = {
                'answer': answer,
                'question': answer.question,
                'specific': answer.question.get_specific_question()
            }
            answers_data.append(a_data)

        context['answers'] = answers_data
        context['total_points'] = student_exam.exam.get_total_points()
        context['earned_points'] = sum(
            a.points_awarded for a in answers if a.points_awarded is not None
        )
        context['is_passing'] = student_exam.is_passing()

        return context

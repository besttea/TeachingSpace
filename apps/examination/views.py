from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, TemplateView
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count
from django.conf import settings
import json
import logging
import random

logger = logging.getLogger(__name__)

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
        # One grouped query for attempt counts instead of one per exam
        if self.request.user.is_authenticated:
            exams = context['exams']
            attempt_counts = {
                row['exam_id']: row['total']
                for row in StudentExam.objects.filter(
                    exam__in=exams, student=self.request.user
                ).values('exam_id').annotate(total=Count('id'))
            }
            for exam in exams:
                exam.user_attempts = attempt_counts.get(exam.id, 0)
                exam.can_attempt = exam.user_attempts < exam.max_attempts
        return context


class ExamDetailView(LoginRequiredMixin, DetailView):
    """Display exam details before starting"""
    model = Exam
    template_name = 'examination/exam_detail.html'
    context_object_name = 'exam'

    def get_queryset(self):
        """Draft exams are only visible to staff."""
        qs = Exam.objects.all()
        if not self.request.user.is_staff:
            qs = qs.filter(is_published=True)
        return qs

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
    # Lock the exam row so concurrent clicks can't create duplicate
    # attempt_numbers (unique_together would otherwise raise IntegrityError).
    with transaction.atomic():
        exam = Exam.objects.select_for_update().get(pk=pk, is_published=True)

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

        # Draft exams cannot be taken (unless staff)
        if not (student_exam.exam.is_published or request.user.is_staff):
            raise Http404

        # Check if already submitted
        if student_exam.is_submitted:
            return redirect('examination:exam-results', attempt_id=student_exam.id)

        # Get questions (randomized if needed). Prefetch the four specific
        # OneToOne question types so get_specific_question() is free.
        questions = list(
            student_exam.exam.questions.all().prefetch_related(
                'multiplechoicequestion', 'codequestion',
                'essayquestion', 'truefalsequestion'
            )
        )

        if student_exam.exam.randomize_questions:
            # Use a per-attempt RNG instance — never seed the process-global
            # random module (that would perturb concurrent requests).
            rng = random.Random(student_exam.randomization_seed)
            rng.shuffle(questions)

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
            'time_remaining': student_exam.remaining_seconds(),
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

        # Server-side time limit: no saving answers after time is up
        if student_exam.is_timed_out():
            return JsonResponse({
                'success': False,
                'error': '考试时间已结束，无法继续保存答案，请提交试卷'
            }, status=400)

        question = get_object_or_404(Question, id=question_id, exam=student_exam.exam)

        # Validate the answer payload's shape and size before storing
        if not isinstance(answer_data, dict):
            return JsonResponse({
                'success': False,
                'error': '答案格式无效'
            }, status=400)
        if len(json.dumps(answer_data, ensure_ascii=False)) > 100_000:
            return JsonResponse({
                'success': False,
                'error': '答案内容过长'
            }, status=400)

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
    """Finalize exam and calculate score.

    The whole flow runs inside a transaction with a row lock: concurrent
    double-clicks can't double-grade, and a grading crash rolls the
    'submitted' flag back so the student is never locked out.
    """
    try:
        data = json.loads(request.body)
        student_exam_id = data.get('student_exam_id')

        with transaction.atomic():
            student_exam = StudentExam.objects.select_for_update().get(
                id=student_exam_id,
                student=request.user
            )

            if student_exam.is_submitted:
                return JsonResponse({
                    'success': False,
                    'error': '该试卷已提交'
                }, status=400)

            # Mark as submitted
            student_exam.is_submitted = True
            student_exam.end_time = timezone.now()
            student_exam.save()

            # Auto-grade all answers
            answers = ExamAnswer.objects.filter(
                student_exam=student_exam
            ).select_related('question')
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
                            passed_tests = result.get('passed_tests', 0)

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

                        except TimeoutError:
                            answer.points_awarded = 0
                            answer.is_correct = False
                            answer.feedback = '代码执行超时'
                            answer.status = 'graded'
                            answer.save()
                        except Exception as e:
                            answer.points_awarded = 0
                            answer.is_correct = False
                            answer.feedback = f'代码执行错误: {str(e)}'
                            answer.status = 'graded'
                            answer.save()

                # Grade essay questions with the AI (falls back to manual
                # review 'needs_review' when no API key is configured)
                elif answer.question.question_type == 'essay':
                    essay_question = answer.question.get_specific_question()
                    if essay_question and getattr(settings, 'ANTHROPIC_API_KEY', ''):
                        try:
                            from apps.ai_agents.examination_agent import ExaminationAgent
                            evaluation = ExaminationAgent().evaluate_essay_answer(
                                answer.question.question_text,
                                answer.answer_data.get('text', ''),
                                essay_question.rubric,
                                essay_question.sample_answer,
                            )
                            score_pct = evaluation.get('score_percentage', 0)
                            answer.points_awarded = int(
                                (score_pct / 100) * answer.question.points
                            )
                            answer.is_correct = score_pct >= 60
                            answer.feedback = evaluation.get('feedback', '')
                            answer.status = 'graded'
                            answer.save()
                        except Exception as e:
                            logger.warning('AI essay grading failed, keeping needs_review: %s', e)

            # Calculate total score
            student_exam.score = student_exam.calculate_score()
            student_exam.save()

            # Update student profile (guarded: instructors lack a student profile)
            if student_exam.is_passing():
                profile = getattr(request.user, 'student_profile', None)
                if profile is not None:
                    profile.total_exams_passed += 1
                    profile.save()

        return JsonResponse({
            'success': True,
            'score': student_exam.score,
            'is_passing': student_exam.is_passing(),
            'redirect_url': f'/examination/results/{student_exam.id}/'
        })

    except StudentExam.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '未找到可提交的考试记录'
        }, status=400)
    except Exception as e:
        logger.exception('submit_exam failed')
        if getattr(settings, 'DEBUG', False):
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
        return JsonResponse({
            'success': False,
            'error': '交卷失败，请重试'
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
        ).select_related('question').prefetch_related(
            'question__multiplechoicequestion', 'question__codequestion',
            'question__essayquestion', 'question__truefalsequestion'
        ).order_by('question__order')

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

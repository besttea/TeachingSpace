from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, TemplateView
from django.http import JsonResponse, Http404, FileResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, Prefetch
from django.conf import settings
from django.core.files.base import ContentFile
import json
import logging
import random

logger = logging.getLogger(__name__)

from .models import (
    Exam, Question, StudentExam, ExamAnswer, Certificate,
    MultipleChoiceQuestion, CodeQuestion, EssayQuestion, TrueFalseQuestion
)
from apps.code_runner.executor import CodeExecutor
from apps.core.rate_limit import rate_limit


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
        context['question_count'] = exam.questions.count()

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
            'total_points': student_exam.exam.get_total_points(),
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
                # review 'needs_review' when no AI key is configured)
                elif answer.question.question_type == 'essay':
                    from apps.ai_agents.ai_config import is_configured
                    essay_question = answer.question.get_specific_question()
                    if essay_question and is_configured():
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


class InstructorExamListView(LoginRequiredMixin, TemplateView):
    """Instructor console: own exams (incl. drafts) with publish controls."""

    template_name = 'examination/instructor_exams.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if not (user.is_staff or user.user_type == 'instructor'):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

        exams = Exam.objects.filter(created_by=user).annotate(
            question_count=Count('questions'),
            attempt_count=Count('student_attempts'),
        ).prefetch_related(
            Prefetch('questions', queryset=Question.objects.order_by('order').prefetch_related(
                'multiplechoicequestion', 'codequestion',
                'essayquestion', 'truefalsequestion'))
        ).order_by('-created_at')
        context['exams'] = exams
        return context


@login_required
@require_http_methods(["POST"])
def exam_publish(request, pk):
    """Publish/unpublish an exam (creator or staff)."""
    exam = get_object_or_404(Exam, pk=pk)
    if not (request.user == exam.created_by or request.user.is_staff):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    action = (request.POST.get('action') or 'publish').strip()
    exam.is_published = (action == 'publish')
    exam.save()
    return JsonResponse({
        'success': True,
        'is_published': exam.is_published,
        'message': '考试已发布' if exam.is_published else '考试已下线为草稿',
    })


@login_required
@require_http_methods(["POST"])
@rate_limit('question_ai_modify', limit=30, window_seconds=3600)
def question_ai_modify(request, pk):
    """AI-assisted exam question modification (skill mode).

    Body: {instruction, apply}. Preview by default; apply validates code
    questions (solution vs test cases in the sandbox) before saving.
    """
    question = get_object_or_404(Question, pk=pk)
    if not (request.user == question.exam.created_by or request.user.is_staff):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        instruction = (data.get('instruction') or '').strip()
        apply_changes = bool(data.get('apply'))

        if not instruction:
            return JsonResponse({'success': False, 'error': '修改指令不能为空'}, status=400)

        from apps.ai_agents.ai_config import is_configured
        if not is_configured():
            return JsonResponse({'success': False, 'error': 'AI 服务未配置（缺少 API 密钥）'}, status=400)

        from apps.ai_agents.examination_agent import ExaminationAgent
        from apps.examination.question_ai import (
            apply_question, question_to_dict, validate_code_question)

        updated = ExaminationAgent().modify_question(
            question_to_dict(question), instruction)
        if not isinstance(updated, dict) or not updated.get('text'):
            return JsonResponse({'success': False, 'error': 'AI 返回的修改结果无效，请重试'}, status=400)

        preview = {
            'text': updated.get('text', '')[:300],
            'options': updated.get('options'),
            'correct_answer': updated.get('correct_answer'),
            'test_cases_count': len(updated.get('test_cases') or []),
        }

        if not apply_changes:
            return JsonResponse({'success': True, 'applied': False, 'preview': preview})

        ok, message = validate_code_question(updated)
        if not ok:
            return JsonResponse({
                'success': False,
                'error': f'修改后参考答案未通过测试用例（{message}）——未保存，请调整指令重试'
            }, status=400)

        points_changed = updated.get('points') is not None and \
            int(updated.get('points')) != question.points
        apply_question(question, updated)
        # Point changes affect already-submitted attempts — recompute them
        if points_changed:
            from apps.examination.question_ai import recompute_exam_scores
            recompute_exam_scores(question.exam)
        return JsonResponse({
            'success': True, 'applied': True,
            'message': f'已保存修改：题目 #{question.id}'
                        + ('（已重算相关成绩）' if points_changed else ''),
        })

    except Exception as e:
        logger.exception('question_ai_modify failed')
        if getattr(settings, 'DEBUG', False):
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        return JsonResponse({'success': False, 'error': '修改失败，请重试'}, status=500)


class ExamReviewView(LoginRequiredMixin, TemplateView):
    """Instructor essay grading console: needs_review answers per attempt."""

    template_name = 'examination/exam_review.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        exam = get_object_or_404(Exam, pk=self.kwargs['pk'])
        user = self.request.user
        if not (user == exam.created_by or user.is_staff):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

        attempts = exam.student_attempts.filter(is_submitted=True).select_related('student')
        review_items = []
        for attempt in attempts:
            essay_answers = ExamAnswer.objects.filter(
                student_exam=attempt, question__question_type='essay'
            ).select_related('question').order_by('question__order')
            if essay_answers:
                review_items.append({
                    'attempt': attempt,
                    'student': attempt.student,
                    'answers': essay_answers,
                })
        context['exam'] = exam
        context['review_items'] = review_items
        return context


@login_required
@require_http_methods(["POST"])
def exam_review_grade(request, pk):
    """Grade one essay answer (instructor) and recompute the attempt score."""
    answer = get_object_or_404(ExamAnswer, pk=pk)
    if not (request.user == answer.student_exam.exam.created_by
            or request.user.is_staff):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    data = json.loads(request.body)
    try:
        points = int(data.get('points', 0))
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': '分值无效'}, status=400)

    max_points = answer.question.points
    if points < 0 or points > max_points:
        return JsonResponse({'success': False, 'error': f'分值需在 0-{max_points} 之间'}, status=400)

    answer.points_awarded = points
    answer.is_correct = points >= max_points * 0.6
    answer.feedback = (data.get('feedback') or '').strip()
    answer.status = 'graded'
    answer.graded_by = request.user
    answer.save()

    from apps.examination.question_ai import recompute_exam_scores
    recompute_exam_scores(answer.student_exam.exam)

    return JsonResponse({
        'success': True,
        'message': f'已评分 {points}/{max_points} 分，尝试总分已重算',
    })


class ExamResultsView(LoginRequiredMixin, DetailView):
    """Display exam results and score breakdown"""
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
        # T7: answer keys/explanations are only shown when the exam allows
        # immediate results (show_results_immediately)
        context['show_details'] = student_exam.exam.show_results_immediately

        # Certificate (if one was generated before)
        try:
            context['certificate'] = student_exam.certificate
        except Certificate.DoesNotExist:
            context['certificate'] = None

        return context


@login_required
def certificate_download(request, attempt_id):
    """Download (or lazily generate) the certificate PDF for a passed attempt."""
    student_exam = get_object_or_404(
        StudentExam,
        id=attempt_id,
        student=request.user,
        is_submitted=True
    )

    if not student_exam.is_passing():
        return render(request, 'examination/certificate_unavailable.html', {
            'student_exam': student_exam,
        }, status=403)

    certificate = Certificate.objects.filter(student_exam=student_exam).first()
    if certificate is None:
        from .certificates import generate_certificate_pdf

        certificate = Certificate(student_exam=student_exam)
        certificate.save()  # assigns verification_code first (PDF embeds it)
        pdf_bytes = generate_certificate_pdf(
            student_exam, verification_code=certificate.verification_code)
        certificate.certificate_pdf.save(
            f'certificate_{student_exam.id}.pdf',
            ContentFile(pdf_bytes),
        )
        certificate.save()

    response = FileResponse(certificate.certificate_pdf.open('rb'),
                            content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="certificate-{certificate.verification_code[:8]}.pdf"'
    )
    return response


def certificate_verify(request, code):
    """Public certificate verification page (code lookup)."""
    certificate = Certificate.objects.filter(
        verification_code=code
    ).select_related('student_exam__student', 'student_exam__exam').first()

    return render(request, 'examination/certificate_verify.html', {
        'certificate': certificate,
        'valid': certificate is not None,
    })

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Exam, Question, MultipleChoiceQuestion, CodeQuestion,
    EssayQuestion, TrueFalseQuestion, StudentExam, ExamAnswer, Certificate
)


class QuestionInline(admin.TabularInline):
    """Inline for questions in exam admin"""
    model = Question
    extra = 0
    fields = ['order', 'question_type', 'question_text', 'points']
    readonly_fields = []


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    """Admin interface for Exam model"""
    list_display = [
        'title', 'duration_minutes', 'passing_score', 'max_attempts',
        'is_published', 'question_count', 'total_points', 'created_by', 'created_at'
    ]
    list_filter = ['is_published', 'created_at', 'randomize_questions']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'updated_at', 'total_points_display']
    fieldsets = (
        ('基本信息', {
            'fields': ('title', 'description', 'created_by')
        }),
        ('考试设置', {
            'fields': (
                'duration_minutes', 'passing_score', 'max_attempts',
                'is_published', 'randomize_questions', 'show_results_immediately'
            )
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    inlines = [QuestionInline]

    def save_model(self, request, obj, form, change):
        """Set created_by to current user if creating new exam"""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def question_count(self, obj):
        """Display question count"""
        return obj.questions.count()
    question_count.short_description = '题目数'

    def total_points(self, obj):
        """Display total points"""
        return obj.get_total_points()
    total_points.short_description = '总分'

    def total_points_display(self, obj):
        """Display total points in detail view"""
        return obj.get_total_points()
    total_points_display.short_description = '考试总分'


class MultipleChoiceInline(admin.StackedInline):
    """Inline for MC question details"""
    model = MultipleChoiceQuestion
    can_delete = False
    fields = ['options', 'correct_answer', 'explanation']


class CodeQuestionInline(admin.StackedInline):
    """Inline for Code question details"""
    model = CodeQuestion
    can_delete = False
    fields = ['starter_code', 'test_cases', 'solution_code', 'explanation']


class EssayQuestionInline(admin.StackedInline):
    """Inline for Essay question details"""
    model = EssayQuestion
    can_delete = False
    fields = ['word_limit', 'rubric', 'sample_answer']


class TrueFalseQuestionInline(admin.StackedInline):
    """Inline for T/F question details"""
    model = TrueFalseQuestion
    can_delete = False
    fields = ['correct_answer', 'explanation']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """Admin interface for Question model"""
    list_display = [
        'question_text_short', 'exam', 'question_type', 'points', 'order', 'created_at'
    ]
    list_filter = ['question_type', 'exam', 'created_at']
    search_fields = ['question_text', 'exam__title']
    readonly_fields = ['created_at']
    fieldsets = (
        ('基本信息', {
            'fields': ('exam', 'question_type', 'question_text', 'points', 'order')
        }),
        ('时间信息', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def question_text_short(self, obj):
        """Display shortened question text"""
        return obj.question_text[:60] + '...' if len(obj.question_text) > 60 else obj.question_text
    question_text_short.short_description = '题目内容'

    def get_inlines(self, request, obj):
        """Dynamic inlines based on question type"""
        if obj is None:
            return []

        if obj.question_type == 'multiple_choice':
            return [MultipleChoiceInline]
        elif obj.question_type == 'code':
            return [CodeQuestionInline]
        elif obj.question_type == 'essay':
            return [EssayQuestionInline]
        elif obj.question_type == 'true_false':
            return [TrueFalseQuestionInline]

        return []


class ExamAnswerInline(admin.TabularInline):
    """Inline for answers in StudentExam admin"""
    model = ExamAnswer
    extra = 0
    fields = ['question', 'is_correct', 'points_awarded', 'graded_by']
    readonly_fields = ['question', 'is_correct', 'points_awarded']


@admin.register(StudentExam)
class StudentExamAdmin(admin.ModelAdmin):
    """Admin interface for StudentExam model"""
    list_display = [
        'student', 'exam', 'attempt_number', 'score_display',
        'is_submitted', 'status', 'start_time'
    ]
    list_filter = ['is_submitted', 'exam', 'start_time']
    search_fields = ['student__username', 'student__email', 'exam__title']
    readonly_fields = [
        'student', 'exam', 'attempt_number', 'start_time',
        'randomization_seed', 'calculated_score'
    ]
    fieldsets = (
        ('考试信息', {
            'fields': ('student', 'exam', 'attempt_number')
        }),
        ('时间信息', {
            'fields': ('start_time', 'end_time', 'time_remaining_seconds')
        }),
        ('成绩信息', {
            'fields': ('is_submitted', 'score', 'calculated_score')
        }),
        ('其他信息', {
            'fields': ('randomization_seed',),
            'classes': ('collapse',)
        }),
    )
    inlines = [ExamAnswerInline]

    def score_display(self, obj):
        """Display score with color coding"""
        if obj.score is None:
            return '-'

        if obj.is_passing():
            color = 'green'
        else:
            color = 'red'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, f'{obj.score}%'
        )
    score_display.short_description = '得分'

    def status(self, obj):
        """Display exam status"""
        if not obj.is_submitted:
            return format_html('<span style="color: orange;">进行中</span>')
        elif obj.is_passing():
            return format_html('<span style="color: green;">通过</span>')
        else:
            return format_html('<span style="color: red;">未通过</span>')
    status.short_description = '状态'

    def calculated_score(self, obj):
        """Display calculated score"""
        return f'{obj.calculate_score()}%'
    calculated_score.short_description = '计算得分'


@admin.register(ExamAnswer)
class ExamAnswerAdmin(admin.ModelAdmin):
    """Admin interface for ExamAnswer model"""
    list_display = [
        'student_exam', 'question_short', 'is_correct',
        'points_awarded', 'graded_by', 'updated_at'
    ]
    list_filter = ['is_correct', 'created_at', 'updated_at']
    search_fields = [
        'student_exam__student__username',
        'question__question_text',
        'student_exam__exam__title'
    ]
    readonly_fields = ['student_exam', 'question', 'created_at', 'updated_at']
    fieldsets = (
        ('答案信息', {
            'fields': ('student_exam', 'question', 'answer_data')
        }),
        ('评分信息', {
            'fields': ('is_correct', 'points_awarded', 'graded_by', 'feedback')
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def question_short(self, obj):
        """Display shortened question text"""
        text = obj.question.question_text
        return text[:50] + '...' if len(text) > 50 else text
    question_short.short_description = '题目'

    def has_add_permission(self, request):
        """Prevent manual addition of answers"""
        return False


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    """Admin interface for Certificate model"""
    list_display = [
        'student_name', 'exam_title', 'score_display',
        'verification_code', 'issued_at'
    ]
    list_filter = ['issued_at']
    search_fields = [
        'student_exam__student__username',
        'student_exam__exam__title',
        'verification_code'
    ]
    readonly_fields = [
        'student_exam', 'verification_code', 'issued_at',
        'certificate_link'
    ]
    fieldsets = (
        ('证书信息', {
            'fields': ('student_exam', 'certificate_pdf', 'certificate_link')
        }),
        ('验证信息', {
            'fields': ('verification_code', 'issued_at')
        }),
    )

    def student_name(self, obj):
        """Display student name"""
        return obj.student_exam.student.get_full_name() or obj.student_exam.student.username
    student_name.short_description = '学生'

    def exam_title(self, obj):
        """Display exam title"""
        return obj.student_exam.exam.title
    exam_title.short_description = '考试'

    def score_display(self, obj):
        """Display score"""
        score = obj.student_exam.score
        return format_html(
            '<span style="color: green; font-weight: bold;">{}</span>',
            f'{score}%' if score is not None else '-'
        )
    score_display.short_description = '成绩'

    def certificate_link(self, obj):
        """Display certificate download link"""
        if obj.certificate_pdf:
            return format_html(
                '<a href="{}" target="_blank">下载证书</a>',
                obj.certificate_pdf.url
            )
        return '-'
    certificate_link.short_description = '证书文件'

    def has_add_permission(self, request):
        """Prevent manual addition of certificates"""
        return False


# Register remaining models without custom admin (if needed)
admin.site.register(MultipleChoiceQuestion)
admin.site.register(CodeQuestion)
admin.site.register(EssayQuestion)
admin.site.register(TrueFalseQuestion)

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import random
import uuid


class Exam(models.Model):
    """Timed assessment with multiple questions"""
    title = models.CharField(max_length=255, verbose_name="考试标题")
    description = models.TextField(verbose_name="考试描述")
    duration_minutes = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="考试时长(分钟)"
    )
    passing_score = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="及格分数(%)",
        help_text="百分比形式, 例如: 60 表示60%"
    )
    max_attempts = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1)],
        verbose_name="最大尝试次数"
    )
    is_published = models.BooleanField(default=False, verbose_name="已发布")
    randomize_questions = models.BooleanField(
        default=True,
        verbose_name="随机打乱题目顺序"
    )
    show_results_immediately = models.BooleanField(
        default=True,
        verbose_name="立即显示结果"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_exams',
        verbose_name="创建者"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = 'exams'
        ordering = ['-created_at']
        verbose_name = "考试"
        verbose_name_plural = "考试"

    def __str__(self):
        return self.title

    def get_total_points(self):
        """Calculate total possible points for this exam"""
        return self.questions.aggregate(
            total=models.Sum('points')
        )['total'] or 0


class Question(models.Model):
    """Base polymorphic question model"""
    QUESTION_TYPES = (
        ('multiple_choice', '选择题'),
        ('code', '编程题'),
        ('essay', '简答题'),
        ('true_false', '判断题'),
    )

    QUESTION_DIFFICULTY = (
        ('easy', '简单'),
        ('medium', '中等'),
        ('hard', '困难'),
    )

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name="所属考试"
    )
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPES,
        verbose_name="题目类型"
    )
    difficulty = models.CharField(
        max_length=10,
        choices=QUESTION_DIFFICULTY,
        default='medium',
        verbose_name="难度"
    )
    question_text = models.TextField(verbose_name="题目内容")
    points = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        verbose_name="分值"
    )
    order = models.IntegerField(default=0, verbose_name="题目顺序")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        db_table = 'exam_questions'
        ordering = ['order', 'id']
        verbose_name = "考试题目"
        verbose_name_plural = "考试题目"

    def __str__(self):
        return f"{self.get_question_type_display()} - {self.question_text[:50]}"

    def get_specific_question(self):
        """Get the specific question instance (MC, Code, Essay, or T/F)"""
        accessors = {
            'multiple_choice': 'multiplechoicequestion',
            'code': 'codequestion',
            'essay': 'essayquestion',
            'true_false': 'truefalsequestion',
        }
        accessor = accessors.get(self.question_type)
        if accessor:
            return getattr(self, accessor, None)
        return None


class MultipleChoiceQuestion(models.Model):
    """Multiple choice questions with 4 options"""
    question = models.OneToOneField(
        Question,
        on_delete=models.CASCADE,
        primary_key=True,
        verbose_name="题目"
    )
    options = models.JSONField(
        verbose_name="选项",
        help_text="格式: {'A': '选项A内容', 'B': '选项B内容', 'C': '选项C内容', 'D': '选项D内容'}"
    )
    correct_answer = models.CharField(
        max_length=1,
        choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')],
        verbose_name="正确答案"
    )
    explanation = models.TextField(blank=True, verbose_name="答案解析")

    class Meta:
        db_table = 'exam_mc_questions'
        verbose_name = "选择题"
        verbose_name_plural = "选择题"

    def __str__(self):
        return f"选择题: {self.question.question_text[:50]}"


class CodeQuestion(models.Model):
    """Coding questions with test cases"""
    question = models.OneToOneField(
        Question,
        on_delete=models.CASCADE,
        primary_key=True,
        verbose_name="题目"
    )
    starter_code = models.TextField(
        blank=True,
        verbose_name="起始代码",
        help_text="提供给学生的初始代码模板"
    )
    test_cases = models.JSONField(
        verbose_name="测试用例",
        help_text="格式: [{'input': '...', 'expected_output': '...', 'is_hidden': false}, ...]"
    )
    solution_code = models.TextField(verbose_name="参考答案")
    explanation = models.TextField(blank=True, verbose_name="解题思路")

    class Meta:
        db_table = 'exam_code_questions'
        verbose_name = "编程题"
        verbose_name_plural = "编程题"

    def __str__(self):
        return f"编程题: {self.question.question_text[:50]}"


class EssayQuestion(models.Model):
    """Short answer/essay questions (manual grading)"""
    question = models.OneToOneField(
        Question,
        on_delete=models.CASCADE,
        primary_key=True,
        verbose_name="题目"
    )
    word_limit = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="字数限制"
    )
    rubric = models.TextField(
        blank=True,
        verbose_name="评分标准",
        help_text="评分时的参考标准"
    )
    sample_answer = models.TextField(
        blank=True,
        verbose_name="参考答案"
    )

    class Meta:
        db_table = 'exam_essay_questions'
        verbose_name = "简答题"
        verbose_name_plural = "简答题"

    def __str__(self):
        return f"简答题: {self.question.question_text[:50]}"


class TrueFalseQuestion(models.Model):
    """Simple True/False questions"""
    question = models.OneToOneField(
        Question,
        on_delete=models.CASCADE,
        primary_key=True,
        verbose_name="题目"
    )
    correct_answer = models.BooleanField(verbose_name="正确答案 (True=正确, False=错误)")
    explanation = models.TextField(blank=True, verbose_name="答案解析")

    class Meta:
        db_table = 'exam_tf_questions'
        verbose_name = "判断题"
        verbose_name_plural = "判断题"

    def __str__(self):
        return f"判断题: {self.question.question_text[:50]}"


class StudentExam(models.Model):
    """Tracks individual student exam attempts"""
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exam_attempts',
        verbose_name="学生"
    )
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name='student_attempts',
        verbose_name="考试"
    )
    attempt_number = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="尝试次数"
    )
    start_time = models.DateTimeField(auto_now_add=True, verbose_name="开始时间")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    time_remaining_seconds = models.IntegerField(
        verbose_name="剩余时间(秒)",
        help_text="后端验证用，防止客户端作弊"
    )
    score = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="得分(%)"
    )
    is_submitted = models.BooleanField(default=False, verbose_name="已提交")
    randomization_seed = models.IntegerField(
        verbose_name="随机种子",
        help_text="确保每次尝试题目顺序一致"
    )

    class Meta:
        db_table = 'student_exams'
        unique_together = ['student', 'exam', 'attempt_number']
        ordering = ['-start_time']
        verbose_name = "学生考试"
        verbose_name_plural = "学生考试"

    def __str__(self):
        return f"{self.student.username} - {self.exam.title} (尝试 {self.attempt_number})"

    def save(self, *args, **kwargs):
        """Set randomization seed if not already set"""
        if not self.randomization_seed:
            self.randomization_seed = random.randint(1000, 9999)
        super().save(*args, **kwargs)

    def calculate_score(self):
        """Calculate percentage score based on points awarded"""
        total_points = self.exam.get_total_points()
        if total_points == 0:
            return 0

        awarded_points = self.answers.aggregate(
            total=models.Sum('points_awarded')
        )['total'] or 0

        return int((awarded_points / total_points) * 100)

    def remaining_seconds(self):
        """Server-side timer: seconds left, derived from start_time.

        Client-side countdowns are cosmetic; this is the value save/submit
        endpoints enforce (see views).
        """
        if self.end_time:
            return 0
        elapsed = (timezone.now() - self.start_time).total_seconds()
        return max(0, int(self.time_remaining_seconds - elapsed))

    def is_timed_out(self):
        """Whether the exam duration has elapsed (server-side check)."""
        return self.remaining_seconds() <= 0

    def is_passing(self):
        """Check if the exam attempt passed"""
        if self.score is None:
            return False
        return self.score >= self.exam.passing_score


class ExamAnswer(models.Model):
    """Student answers to exam questions"""
    GRADING_STATUS = (
        ('pending', '待评分'),
        ('graded', '已评分'),
        ('needs_review', '需人工复核'),
    )

    student_exam = models.ForeignKey(
        StudentExam,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name="学生考试"
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        verbose_name="题目"
    )
    answer_data = models.JSONField(
        verbose_name="答案数据",
        help_text="格式根据题型: {'selected': 'A'} 或 {'code': '...', 'output': '...'} 或 {'text': '...'}"
    )
    points_awarded = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="获得分数"
    )
    is_correct = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="是否正确"
    )
    status = models.CharField(
        max_length=20,
        choices=GRADING_STATUS,
        default='pending',
        verbose_name="评分状态"
    )
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='graded_answers',
        verbose_name="评分者"
    )
    feedback = models.TextField(blank=True, verbose_name="评分反馈")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="答题时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = 'exam_answers'
        unique_together = ['student_exam', 'question']
        verbose_name = "考试答案"
        verbose_name_plural = "考试答案"

    def __str__(self):
        return f"{self.student_exam.student.username} - {self.question}"

    def auto_grade(self):
        """Auto-grade the answer based on question type"""
        specific_question = self.question.get_specific_question()

        if not specific_question:
            return

        # Multiple Choice grading
        if isinstance(specific_question, MultipleChoiceQuestion):
            selected = self.answer_data.get('selected', '')
            if selected == specific_question.correct_answer:
                self.is_correct = True
                self.points_awarded = self.question.points
            else:
                self.is_correct = False
                self.points_awarded = 0
            self.status = 'graded'

        # True/False grading
        elif isinstance(specific_question, TrueFalseQuestion):
            selected = self.answer_data.get('selected')
            if selected is not None:
                # Convert string to boolean if needed
                if isinstance(selected, str):
                    selected = selected.lower() == 'true'

                if selected == specific_question.correct_answer:
                    self.is_correct = True
                    self.points_awarded = self.question.points
                else:
                    self.is_correct = False
                    self.points_awarded = 0
                self.status = 'graded'

        # Essay questions require manual grading
        elif isinstance(specific_question, EssayQuestion):
            self.status = 'needs_review'

        # Code questions will be graded by code executor (handled in views)

        self.save()


class Certificate(models.Model):
    """Generated certificates for passed exams"""
    student_exam = models.OneToOneField(
        StudentExam,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='certificate',
        verbose_name="学生考试"
    )
    certificate_pdf = models.FileField(
        upload_to='certificates/%Y/%m/',
        verbose_name="证书PDF"
    )
    verification_code = models.CharField(
        max_length=32,
        unique=True,
        verbose_name="验证码"
    )
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name="颁发时间")

    class Meta:
        db_table = 'certificates'
        verbose_name = "证书"
        verbose_name_plural = "证书"

    def __str__(self):
        return f"证书 - {self.student_exam.student.username} - {self.student_exam.exam.title}"

    def save(self, *args, **kwargs):
        """Generate verification code if not set"""
        if not self.verification_code:
            self.verification_code = uuid.uuid4().hex
        super().save(*args, **kwargs)

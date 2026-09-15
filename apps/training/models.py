from django.db import models
from django.conf import settings
from django.utils.text import slugify
from apps.learning.models import Course


class Exercise(models.Model):
    """Coding exercise/challenge"""
    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='beginner')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name='exercises')
    points = models.IntegerField(default=10)
    time_limit_seconds = models.IntegerField(null=True, blank=True)

    # Code execution requirements
    starter_code = models.TextField(blank=True, help_text="Initial code template for students")
    solution_code = models.TextField(help_text="Reference solution")
    test_cases = models.JSONField(default=list, help_text="Test cases in JSON format")

    # Metadata
    total_submissions = models.IntegerField(default=0)
    successful_submissions = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='exercises_created')

    class Meta:
        db_table = 'exercises'
        ordering = ['difficulty', '-created_at']
        indexes = [
            models.Index(fields=['difficulty', '-created_at']),
            models.Index(fields=['course']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or 'untitled'
            self.slug = base
            # Disambiguate duplicate slugs (Chinese titles slugify to "").
            counter = 2
            while type(self).objects.filter(slug=self.slug).exists():
                self.slug = f'{base}-{counter}'
                counter += 1
        super().save(*args, **kwargs)

    @property
    def success_rate(self):
        """Calculate success rate percentage"""
        if self.total_submissions == 0:
            return 0
        return round((self.successful_submissions / self.total_submissions) * 100, 2)


class Hint(models.Model):
    """Progressive hints for exercises"""
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='hints')
    content = models.TextField()
    order = models.PositiveIntegerField(default=0)
    points_penalty = models.IntegerField(default=2, help_text="Points deducted for viewing this hint")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hints'
        ordering = ['order']
        unique_together = ['exercise', 'order']

    def __str__(self):
        return f"Hint #{self.order} for {self.exercise.title}"


class Submission(models.Model):
    """Student code submission"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('error', 'Error'),
        ('timeout', 'Timeout'),
    ]

    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='submissions')
    code = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Execution results
    test_results = models.JSONField(null=True, blank=True, help_text="Detailed test case results")
    output = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)

    # Scoring
    tests_passed = models.IntegerField(default=0)
    tests_total = models.IntegerField(default=0)
    points_awarded = models.IntegerField(default=0)
    hints_used = models.IntegerField(default=0)

    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'submissions'
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['student', 'exercise']),
            models.Index(fields=['status']),
            models.Index(fields=['-submitted_at']),
        ]

    def __str__(self):
        return f"{self.student.username} - {self.exercise.title} ({self.status})"

    def grade(self):
        """Execute and grade the submission.

        Points are awarded only once per (student, exercise): after a first
        passing submission, later ones update their own record but never
        re-credit the profile or exercise stats (no points farming).
        Hint penalties come from the actual viewed hints (consistent with
        ``view_hint``), not a hardcoded per-hint value.
        """
        from django.db import transaction
        from django.db.models import F, Sum

        from apps.accounts.models import StudentProfile
        from apps.code_runner.executor import CodeExecutor

        self.status = 'running'
        self.save()

        try:
            with transaction.atomic():
                # Lock the exercise row so concurrent submissions can't
                # double-increment the counters.
                exercise = Exercise.objects.select_for_update().get(pk=self.exercise_id)
                profile = StudentProfile.objects.select_for_update().filter(
                    user=self.student).first()

                executor = CodeExecutor()
                result = executor.execute_with_tests(
                    code=self.code,
                    test_cases=exercise.test_cases,
                    timeout=exercise.time_limit_seconds or 10
                )

                # Update submission with results
                self.test_results = result.get('test_results', [])
                self.output = result.get('output', '')
                self.tests_passed = result.get('passed_tests', 0)
                self.tests_total = result.get('total_tests', 0)
                self.execution_time_ms = result.get('execution_time', 0)

                # Determine status (guard against empty test suites: 0/0 is not a pass)
                if self.tests_total > 0 and self.tests_passed == self.tests_total:
                    self.status = 'passed'

                    # Sum the actual penalties of hints already viewed for
                    # this exercise (matches view_hint's deduction logic).
                    hint_penalty = HintUsage.objects.filter(
                        student=self.student, hint__exercise=exercise
                    ).aggregate(total=Sum('hint__points_penalty'))['total'] or 0
                    self.points_awarded = max(0, exercise.points - hint_penalty)

                    # Award points/stats only on the FIRST passing submission.
                    already_passed = Submission.objects.filter(
                        student=self.student, exercise=exercise, status='passed'
                    ).exclude(pk=self.pk).exists()
                    if already_passed:
                        self.points_awarded = 0
                    else:
                        exercise.successful_submissions = F('successful_submissions') + 1
                        if profile is not None:
                            profile.total_points = F('total_points') + self.points_awarded
                            profile.total_exercises_completed = F('total_exercises_completed') + 1
                            profile.save()
                else:
                    self.status = 'failed'
                    self.points_awarded = 0

                exercise.total_submissions = F('total_submissions') + 1
                exercise.save()

        except TimeoutError:
            self.status = 'timeout'
            self.error_message = "Code execution exceeded time limit"
        except Exception as e:
            self.status = 'error'
            self.error_message = str(e)

        self.save()
        return self.status


class HintUsage(models.Model):
    """Track which hints a student has viewed"""
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hint_usage')
    hint = models.ForeignKey(Hint, on_delete=models.CASCADE, related_name='usage')
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hint_usage'
        unique_together = ['student', 'hint']
        ordering = ['-viewed_at']

    def __str__(self):
        return f"{self.student.username} viewed hint for {self.hint.exercise.title}"

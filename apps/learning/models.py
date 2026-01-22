from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone


class Course(models.Model):
    """Main course container"""
    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    difficulty_level = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='beginner')
    instructor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='courses_taught')
    thumbnail = models.ImageField(upload_to='course_thumbnails/', blank=True, null=True)
    is_published = models.BooleanField(default=False)
    estimated_duration_hours = models.IntegerField(default=10, help_text="Estimated hours to complete")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'courses'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class Chapter(models.Model):
    """Chapter within a course"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='chapters')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chapters'
        ordering = ['order']
        unique_together = ['course', 'order']

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Lesson(models.Model):
    """Notebook-style lesson container"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=200)
    slug = models.SlugField(blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    order = models.PositiveIntegerField(default=0)
    duration_minutes = models.IntegerField(default=15)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='lessons_created')

    class Meta:
        db_table = 'lessons'
        ordering = ['order']
        unique_together = ['chapter', 'order']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class Cell(models.Model):
    """Individual content cell within a lesson (Jupyter-style)"""
    CELL_TYPES = [
        ('text', 'Text/Markdown'),
        ('code', 'Code'),
        ('image', 'Image'),
        ('video', 'Video'),
    ]

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='cells')
    cell_type = models.CharField(max_length=20, choices=CELL_TYPES)
    order = models.PositiveIntegerField()
    data = models.JSONField(default=dict, help_text="Cell-specific data (markdown, code, image url, etc.)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='cells_created')
    last_edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='cells_edited')

    class Meta:
        db_table = 'cells'
        ordering = ['order']
        unique_together = ['lesson', 'order']
        indexes = [
            models.Index(fields=['lesson', 'order']),
            models.Index(fields=['cell_type']),
        ]

    def __str__(self):
        return f"{self.lesson.title} - {self.cell_type} cell #{self.order}"

    def execute(self):
        """Execute code cell"""
        if self.cell_type != 'code':
            raise ValueError("Only code cells can be executed")

        from apps.code_runner.executor import CodeExecutor
        executor = CodeExecutor()

        code = self.data.get('source', '')
        result = executor.execute_code(code)

        # Update cell data with execution results
        self.data['output'] = result.get('output', '')
        self.data['status'] = result.get('status', 'error')
        self.data['execution_time_ms'] = result.get('execution_time', 0)
        self.data['execution_count'] = self.data.get('execution_count', 0) + 1
        self.save()

        return result


class CellVersion(models.Model):
    """Track cell edit history for undo/redo"""
    cell = models.ForeignKey(Cell, on_delete=models.CASCADE, related_name='versions')
    snapshot = models.JSONField(help_text="Complete cell state at this version")
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    change_description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cell_versions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['cell', '-created_at']),
        ]

    def __str__(self):
        return f"Version of {self.cell} at {self.created_at}"


class Video(models.Model):
    """Video tutorials and Manim animations"""
    SOURCE_TYPES = [
        ('manim_generated', 'Manim Generated'),
        ('uploaded', 'Uploaded'),
        ('youtube', 'YouTube'),
        ('vimeo', 'Vimeo'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('rendering', 'Rendering'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    lesson = models.ForeignKey(Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name='videos')
    cell = models.ForeignKey(Cell, on_delete=models.SET_NULL, null=True, blank=True, related_name='video_content')

    title = models.CharField(max_length=200)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES, default='uploaded')

    # For uploaded/generated videos
    video_file = models.FileField(upload_to='videos/%Y/%m/%d/', blank=True, null=True)

    # For external videos
    external_url = models.URLField(blank=True, null=True)

    # Manim-specific
    manim_script = models.TextField(blank=True, help_text="Python code for Manim animation")

    # Metadata
    thumbnail = models.ImageField(upload_to='video_thumbnails/', blank=True, null=True)
    duration_seconds = models.IntegerField(default=0)
    resolution_width = models.IntegerField(default=1920)
    resolution_height = models.IntegerField(default=1080)
    file_size_bytes = models.BigIntegerField(default=0)

    # Status
    generation_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'videos'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    """Student enrollment in a course"""
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    class Meta:
        db_table = 'enrollments'
        unique_together = ['student', 'course']
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.student.username} enrolled in {self.course.title}"

    @property
    def completed_lessons_count(self):
        """Return number of completed lessons"""
        return self.lesson_progress.filter(is_completed=True).count()

    def calculate_progress(self):
        """Calculate course completion percentage"""
        total_lessons = Lesson.objects.filter(
            chapter__course=self.course,
            status='published'
        ).count()

        if total_lessons == 0:
            return 0.00

        completed_lessons = self.lesson_progress.filter(
            is_completed=True
        ).count()

        self.progress_percentage = (completed_lessons / total_lessons) * 100
        self.save()

        return self.progress_percentage


class LessonProgress(models.Model):
    """Track student progress through lessons and cells"""
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)

    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.IntegerField(default=0)
    last_accessed = models.DateTimeField(auto_now=True)

    # Cell-level tracking
    cells_executed = models.IntegerField(default=0)
    code_cells_run = models.JSONField(default=list, help_text="List of code cell IDs that were executed")

    class Meta:
        db_table = 'lesson_progress'
        unique_together = ['enrollment', 'lesson']
        ordering = ['-last_accessed']

    def __str__(self):
        return f"{self.enrollment.student.username} - {self.lesson.title}"

    def mark_complete(self):
        """Mark lesson as completed"""
        if not self.is_completed:
            self.is_completed = True
            self.completed_at = timezone.now()
            self.save()

            # Update enrollment progress
            self.enrollment.calculate_progress()

    def track_cell_execution(self, cell_id):
        """Track that a code cell was executed"""
        if cell_id not in self.code_cells_run:
            self.code_cells_run.append(cell_id)
            self.cells_executed += 1
            self.save()

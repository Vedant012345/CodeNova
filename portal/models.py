"""
CodeNova Portal Models — v8
Changes from v7:
  - CustomUser: registration_course FK (course selected at registration time)
  - Note: uploaded_by FK, course FK already existed
  - Quiz: time_limit_minutes renamed/added alongside duration, explanation on Question
  - Assignment: attachment field alias (was 'file'), due_date nullable
  - Topic: course FK, video_url, order fields added
  - All new fields nullable/have defaults for backward compat
"""
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


# ─── Custom User ─────────────────────────────────────────────────────────────

class CustomUserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_approved", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", "student")
        return self.create_user(username, email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    ROLE_STUDENT  = "student"
    ROLE_CLIENT   = "client"
    ROLE_INQUIRY  = "inquiry"
    ROLE_CHOICES  = [
        (ROLE_STUDENT, "Student"),
        (ROLE_CLIENT,  "Client"),
        (ROLE_INQUIRY, "Inquiry / Demo"),
    ]

    username    = models.CharField(max_length=150, unique=True)
    email       = models.EmailField(unique=True)
    first_name  = models.CharField(max_length=100, blank=True)
    last_name   = models.CharField(max_length=100, blank=True)
    role        = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_STUDENT)
    is_approved = models.BooleanField(default=False)
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    avatar      = models.ImageField(upload_to="avatars/", null=True, blank=True)
    bio         = models.TextField(blank=True)
    failed_login_count = models.PositiveSmallIntegerField(default=0)

    # ── Course Access Control (v6) ────────────────────────────────────────
    course_selection_done = models.BooleanField(
        default=False,
        help_text="True once the student has completed the course-selection step"
    )
    enrolled_courses = models.ManyToManyField(
        "Course", blank=True,
        related_name="enrolled_students",
        help_text="Courses the student has selected/enrolled in"
    )

    # ── v8: Course chosen at registration time ────────────────────────────
    # When a student picks a course during registration, it's stored here.
    # On approval, enrolled_courses is automatically set from this field.
    # course_selection_done is set True so no extra selection page is shown.
    # WARNING: This field is nullable — existing students have NULL here.
    #   They will go through the old course_select flow as before.
    registration_course = models.ForeignKey(
        "Course",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="registered_students",
        help_text="Course selected during registration. Auto-enrolled on admin approval."
    )

    objects = CustomUserManager()

    USERNAME_FIELD  = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = "User"
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    def get_full_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username

    def is_student(self):
        return self.role == self.ROLE_STUDENT

    def needs_course_selection(self):
        """
        Returns True if the student must visit the course-selection page.
        Students who selected a course at registration have course_selection_done=True
        (set automatically when admin approves), so they skip this page.
        """
        if self.is_superuser or self.role != self.ROLE_STUDENT:
            return False
        return not self.course_selection_done

    def has_courses_assigned(self):
        return self.enrolled_courses.exists()

    def auto_enroll_from_registration(self):
        """
        Called by host_user_action on approval.
        If student selected a course at registration, enroll them now and
        mark course_selection_done=True so they go straight to dashboard.
        """
        if self.registration_course and self.registration_course.is_active:
            self.enrolled_courses.add(self.registration_course)
            if not self.course_selection_done:
                self.course_selection_done = True
                self.save(update_fields=["course_selection_done"])


# ─── Course ──────────────────────────────────────────────────────────────────

class Course(models.Model):
    LEVEL_CHOICES = [
        ("beginner",     "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced",     "Advanced"),
    ]
    title        = models.CharField(max_length=255)
    description  = models.TextField(blank=True)
    subject      = models.CharField(max_length=100, blank=True)
    level        = models.CharField(max_length=20, choices=LEVEL_CHOICES, default="beginner")
    duration     = models.CharField(max_length=60, blank=True)
    icon         = models.CharField(max_length=60, blank=True, default="school")
    is_active    = models.BooleanField(default=True)
    order        = models.PositiveIntegerField(default=0)
    created_at   = models.DateTimeField(auto_now_add=True)
    # v9: Banner image for course landing/selection display
    banner_image = models.ImageField(
        upload_to="course_banners/",
        null=True, blank=True,
        help_text="Banner image displayed on the course card and course detail section."
    )

    class Meta:
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title


# ─── Notes ───────────────────────────────────────────────────────────────────

class Note(models.Model):
    title       = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file        = models.FileField(upload_to="notes/", null=True, blank=True)
    subject     = models.CharField(max_length=100, blank=True)
    course      = models.ForeignKey(
        Course, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="notes"
    )
    # v8: track who uploaded — used by host_views
    uploaded_by = models.ForeignKey(
        "CustomUser", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="uploaded_notes"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


# ─── Quiz ────────────────────────────────────────────────────────────────────

class Quiz(models.Model):
    title       = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    subject     = models.CharField(max_length=100, blank=True)
    # 'duration' kept for backward compat with student views
    duration    = models.PositiveIntegerField(default=30, help_text="Duration in minutes")
    # 'time_limit_minutes' alias used by host_views — synced with duration
    # WARNING: Both fields store the same value. duration is the canonical field.
    # host_views writes to time_limit_minutes; a property keeps them in sync.
    time_limit_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Alias of duration — used by host dashboard forms"
    )
    is_active        = models.BooleanField(default=True)
    is_ai_generated  = models.BooleanField(default=False)
    course           = models.ForeignKey(
        Course, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="quizzes"
    )
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Quizzes"
        ordering = ["-created_at"]

    def __str__(self):
        tag = " [AI]" if self.is_ai_generated else ""
        return f"{self.title}{tag}"

    def total_marks(self):
        return self.questions.aggregate(total=models.Sum("marks"))["total"] or 0

    def save(self, *args, **kwargs):
        # Keep duration and time_limit_minutes in sync
        if self.time_limit_minutes and self.time_limit_minutes != self.duration:
            self.duration = self.time_limit_minutes
        elif self.duration and self.duration != self.time_limit_minutes:
            self.time_limit_minutes = self.duration
        super().save(*args, **kwargs)


class Question(models.Model):
    quiz        = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text        = models.TextField()
    option_a    = models.CharField(max_length=300)
    option_b    = models.CharField(max_length=300)
    option_c    = models.CharField(max_length=300)
    option_d    = models.CharField(max_length=300)
    correct     = models.CharField(max_length=1, choices=[("A","A"),("B","B"),("C","C"),("D","D")])
    marks       = models.PositiveIntegerField(default=1)
    order       = models.PositiveIntegerField(default=0)
    # v8: explanation field for AI-generated questions
    explanation = models.TextField(blank=True, help_text="Why this answer is correct")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"Q{self.order}: {self.text[:60]}"


# ─── Assignment ───────────────────────────────────────────────────────────────

class Assignment(models.Model):
    title       = models.CharField(max_length=255)
    description = models.TextField()
    subject     = models.CharField(max_length=100, blank=True)
    due_date    = models.DateTimeField(null=True, blank=True)  # v8: nullable
    # 'file' is the canonical field; 'attachment' is an alias used by host_views
    file        = models.FileField(upload_to="assignments/files/", null=True, blank=True)
    max_marks   = models.PositiveIntegerField(default=100)
    is_active   = models.BooleanField(default=True)
    course      = models.ForeignKey(
        Course, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="assignments"
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def is_past_due(self):
        if not self.due_date:
            return False
        return timezone.now() > self.due_date

    # v8: 'attachment' property so host_views can write assignment.attachment = file
    @property
    def attachment(self):
        return self.file

    @attachment.setter
    def attachment(self, value):
        self.file = value


class Submission(models.Model):
    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("graded",    "Graded"),
        ("returned",  "Returned"),
    ]
    student      = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="submissions")
    assignment   = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    file         = models.FileField(upload_to="assignments/submissions/", null=True, blank=True)
    text         = models.TextField(blank=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="submitted")
    marks        = models.PositiveIntegerField(null=True, blank=True)
    feedback     = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["student", "assignment"]
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.student.username} -> {self.assignment.title}"


# ─── Quiz Result ──────────────────────────────────────────────────────────────

class QuizResult(models.Model):
    student    = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="quiz_results")
    quiz       = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="results")
    score      = models.PositiveIntegerField(default=0)
    total      = models.PositiveIntegerField(default=0)
    percentage = models.FloatField(default=0.0)
    taken_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["student", "quiz"]
        ordering = ["-taken_at"]

    def __str__(self):
        return f"{self.student.username} - {self.quiz.title} ({self.percentage:.0f}%)"


# ─── Quiz Student Answer (v10) ───────────────────────────────────────────────
# Stores per-question student responses for detailed result display and host analytics.
# Related to QuizResult via (student, quiz) — always created together with QuizResult.

class QuizStudentAnswer(models.Model):
    """
    Stores the student's answer for each question in a quiz attempt.
    Created alongside QuizResult on submission. Immutable after creation.
    """
    student          = models.ForeignKey(CustomUser, on_delete=models.CASCADE,
                                         related_name="quiz_answers")
    quiz             = models.ForeignKey(Quiz, on_delete=models.CASCADE,
                                         related_name="student_answers")
    question         = models.ForeignKey(Question, on_delete=models.CASCADE,
                                         related_name="student_answers")
    selected_answer  = models.CharField(max_length=1, blank=True,
                                        help_text="Student's selected option: A/B/C/D or blank if skipped")
    correct_answer   = models.CharField(max_length=1,
                                        help_text="Correct option at time of submission")
    is_correct       = models.BooleanField(default=False)
    submitted_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        # One answer per student per question per quiz
        unique_together = ["student", "quiz", "question"]
        ordering = ["question__order", "question__id"]

    def __str__(self):
        status = "✓" if self.is_correct else "✗"
        return (f"{self.student.username} | {self.quiz.title} | "
                f"Q{self.question.order}: {self.selected_answer} vs {self.correct_answer} {status}")


# ─── Notification ─────────────────────────────────────────────────────────────

class Notification(models.Model):
    PRIORITY_CHOICES = [
        ("info",    "Info"),
        ("warning", "Warning"),
        ("success", "Success"),
        ("error",   "Error"),
    ]
    target_role = models.CharField(max_length=20, blank=True, default="")
    title      = models.CharField(max_length=255)
    body       = models.TextField()
    priority   = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="info")
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


# ─── Topic ───────────────────────────────────────────────────────────────────

class Topic(models.Model):
    title      = models.CharField(max_length=255)
    content    = models.TextField(blank=True)
    subject    = models.CharField(max_length=100, blank=True)
    resources  = models.TextField(blank=True)
    date       = models.DateField(default=timezone.now)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # v8: course FK (host_views creates topics linked to courses)
    course     = models.ForeignKey(
        Course, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="topics"
    )
    # v8: video URL and ordering for course topics
    video_url  = models.URLField(blank=True)
    order      = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "-date", "-created_at"]

    def __str__(self):
        return f"{self.date}: {self.title}"


class TopicCompletion(models.Model):
    student      = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="completed_topics")
    topic        = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="completions")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["student", "topic"]


# ─── Performance ─────────────────────────────────────────────────────────────

class Performance(models.Model):
    student        = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="performance")
    quiz_avg       = models.FloatField(default=0.0)
    assignment_avg = models.FloatField(default=0.0)
    topics_done    = models.PositiveIntegerField(default=0)
    overall        = models.FloatField(default=0.0)
    updated_at     = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student.username} - {self.overall:.1f}%"


# ─── AI Chat ──────────────────────────────────────────────────────────────────

class ChatMessage(models.Model):
    ROLE_CHOICES = [("user", "User"), ("assistant", "Assistant")]
    student   = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="chat_messages")
    role      = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content   = models.TextField()
    topic     = models.CharField(max_length=200, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.student.username} [{self.role}]: {self.content[:60]}"


# ─── Client Project ───────────────────────────────────────────────────────────

class ClientProject(models.Model):
    STATUS_CHOICES = [
        ("pending",     "Pending"),
        ("in_progress", "In Progress"),
        ("review",      "Under Review"),
        ("completed",   "Completed"),
        ("on_hold",     "On Hold"),
    ]
    client      = models.ForeignKey(CustomUser, on_delete=models.CASCADE,
                                    related_name="projects", limit_choices_to={"role": "client"})
    title       = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    progress    = models.PositiveIntegerField(default=0)
    team_size   = models.PositiveIntegerField(default=1)
    start_date  = models.DateField(null=True, blank=True)
    deadline    = models.DateField(null=True, blank=True)
    tech_stack  = models.CharField(max_length=300, blank=True)
    budget      = models.CharField(max_length=100, blank=True)
    notes       = models.TextField(blank=True)
    live_url    = models.URLField(blank=True)
    demo_video_url = models.URLField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.client.username})"

    def is_overdue(self):
        if self.deadline and self.status not in ("completed",):
            return timezone.now().date() > self.deadline
        return False


# ─── Demo / Inquiry Schedule ──────────────────────────────────────────────────

class DemoSchedule(models.Model):
    STATUS_CHOICES = [
        ("scheduled",   "Scheduled"),
        ("completed",   "Completed"),
        ("cancelled",   "Cancelled"),
        ("rescheduled", "Rescheduled"),
    ]
    PLATFORM_CHOICES = [
        ("zoom",  "Zoom"),
        ("meet",  "Google Meet"),
        ("teams", "MS Teams"),
        ("other", "Other"),
    ]
    inquiry_user = models.ForeignKey(CustomUser, on_delete=models.CASCADE,
                                     related_name="demos", limit_choices_to={"role": "inquiry"})
    title        = models.CharField(max_length=255, default="Demo Session")
    description  = models.TextField(blank=True)
    scheduled_at = models.DateTimeField()
    platform     = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default="zoom")
    meeting_link = models.URLField(blank=True)
    meeting_id   = models.CharField(max_length=100, blank=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    notes        = models.TextField(blank=True)
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email= models.EmailField(blank=True)
    contact_phone= models.CharField(max_length=30, blank=True)
    video_url    = models.URLField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.title} – {self.inquiry_user.username} @ {self.scheduled_at:%Y-%m-%d %H:%M}"


# ─── Contact Message ──────────────────────────────────────────────────────────

class ContactMessage(models.Model):
    SUBJECT_CHOICES = [
        ("enrollment", "Student Enrollment"),
        ("project",    "Project Inquiry"),
        ("demo",       "Book a Demo"),
        ("general",    "General Message"),
    ]
    STATUS_CHOICES = [
        ("new",     "New"),
        ("read",    "Read"),
        ("replied", "Replied"),
    ]
    name       = models.CharField(max_length=150)
    email      = models.EmailField()
    subject    = models.CharField(max_length=30, choices=SUBJECT_CHOICES, default="general")
    message    = models.TextField()
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default="new")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.subject}) — {self.created_at:%Y-%m-%d}"

    @property
    def is_read(self):
        return self.status != "new"

    @is_read.setter
    def is_read(self, value):
        self.status = "read" if value else "new"


# ─── Activity Log ─────────────────────────────────────────────────────────────

class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ("login",          "User Login"),
        ("logout",         "User Logout"),
        ("quiz_attempt",   "Quiz Attempted"),
        ("assignment_sub", "Assignment Submitted"),
        ("topic_done",     "Topic Completed"),
        ("contact_msg",    "Contact Message Sent"),
        ("ai_quiz_gen",    "AI Quiz Generated"),
        ("chat_message",   "Chatbot Message"),
        ("course_select",  "Course Selected"),
        ("user_approved",  "User Approved"),
    ]
    user       = models.ForeignKey(
        "CustomUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activity_logs"
    )
    action     = models.CharField(max_length=30, choices=ACTION_CHOICES)
    detail     = models.CharField(max_length=300, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        uname = self.user.username if self.user else "anonymous"
        return f"{uname} — {self.action} @ {self.timestamp:%Y-%m-%d %H:%M}"


# ─── User Query ───────────────────────────────────────────────────────────────

class UserQuery(models.Model):
    STATUS_CHOICES = [
        ("open",     "Open"),
        ("answered", "Answered"),
        ("closed",   "Closed"),
    ]
    user        = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="queries")
    subject     = models.CharField(max_length=255)
    question    = models.TextField()
    answer      = models.TextField(blank=True)
    answered_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="answered_queries"
    )
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "User Query"
        verbose_name_plural = "User Queries"

    def __str__(self):
        return f"[{self.status.upper()}] {self.user.username}: {self.subject[:60]}"

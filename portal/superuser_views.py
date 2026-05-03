"""
CodeNova Superuser UI Panel — /superuser/
A custom Django-template-based admin UI (separate from /admin/).
"""
import logging
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.db.models import Count, Avg, Q
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.core.paginator import Paginator
from datetime import timedelta

from .models import (
    CustomUser, Note, Quiz, Question, Assignment, Submission,
    QuizResult, Notification, Topic, ClientProject, DemoSchedule,
    ContactMessage, ActivityLog, Performance, Course
)
from .quiz_parser import parse_quiz_text, validate_and_preview, QuizParseError

logger = logging.getLogger(__name__)


# ─── Decorator ───────────────────────────────────────────────────────────────

def superuser_required(view_fn):
    """Only allow authenticated superusers."""
    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return redirect("portal:su_login")
        return view_fn(request, *args, **kwargs)
    return wrapper


def _log(request, action, detail=""):
    """Helper to record an ActivityLog entry."""
    ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", ""))
    ActivityLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action, detail=detail[:300], ip_address=ip or None
    )


# ─── Auth ─────────────────────────────────────────────────────────────────────

def su_login(request):
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("portal:su_dashboard")
    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user and user.is_superuser:
            auth_login(request, user)
            _log(request, "login", f"Superuser login: {user.username}")
            return redirect("portal:su_dashboard")
        else:
            error = "Invalid credentials or insufficient permissions."
    return render(request, "portal/superuser/login.html", {"error": error})


def su_logout(request):
    auth_logout(request)
    return redirect("portal:su_login")


# ─── Dashboard / Analytics ────────────────────────────────────────────────────

@superuser_required
def su_dashboard(request):
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    # User stats
    total_users     = CustomUser.objects.filter(is_superuser=False).count()
    approved_users  = CustomUser.objects.filter(is_superuser=False, is_approved=True).count()
    pending_users   = CustomUser.objects.filter(is_superuser=False, is_approved=False).count()
    by_role = CustomUser.objects.filter(is_superuser=False).values("role").annotate(n=Count("id"))
    role_counts = {r["role"]: r["n"] for r in by_role}

    # Content stats
    total_quizzes      = Quiz.objects.count()
    ai_quizzes         = Quiz.objects.filter(is_ai_generated=True).count()
    total_assignments  = Assignment.objects.count()
    total_notes        = Note.objects.count()
    total_topics       = Topic.objects.count()
    quiz_attempts      = QuizResult.objects.count()
    avg_quiz_score     = QuizResult.objects.aggregate(a=Avg("percentage"))["a"] or 0
    submissions_count  = Submission.objects.count()
    contact_messages   = ContactMessage.objects.filter(status="new").count()
    active_projects    = ClientProject.objects.filter(status="in_progress").count()
    upcoming_demos     = DemoSchedule.objects.filter(status="scheduled", scheduled_at__gte=now).count()

    # Recent activity — v9: select_related to avoid N+1 on user FK
    recent_logs  = ActivityLog.objects.select_related("user").order_by("-timestamp")[:15]
    recent_users = CustomUser.objects.filter(is_superuser=False).only(
        "username", "email", "role", "date_joined", "is_approved"
    ).order_by("-date_joined")[:5]
    pending_list = CustomUser.objects.filter(is_superuser=False, is_approved=False).only(
        "username", "email", "role", "date_joined"
    ).order_by("-date_joined")[:8]
    new_messages = ContactMessage.objects.filter(status="new").order_by("-created_at")[:5]

    ctx = {
        "total_users": total_users, "approved_users": approved_users,
        "pending_users": pending_users, "role_counts": role_counts,
        "total_quizzes": total_quizzes, "ai_quizzes": ai_quizzes,
        "total_assignments": total_assignments, "total_notes": total_notes,
        "total_topics": total_topics, "quiz_attempts": quiz_attempts,
        "avg_quiz_score": round(avg_quiz_score, 1),
        "submissions_count": submissions_count,
        "contact_messages": contact_messages,
        "active_projects": active_projects, "upcoming_demos": upcoming_demos,
        "recent_logs": recent_logs, "recent_users": recent_users,
        "pending_list": pending_list, "new_messages": new_messages,
    }
    return render(request, "portal/superuser/dashboard.html", ctx)


# ─── Users ────────────────────────────────────────────────────────────────────

@superuser_required
def su_users(request):
    qs = CustomUser.objects.filter(is_superuser=False).order_by("-date_joined")
    # Filters
    role   = request.GET.get("role", "")
    status = request.GET.get("status", "")
    q      = request.GET.get("q", "")
    if role:
        qs = qs.filter(role=role)
    if status == "approved":
        qs = qs.filter(is_approved=True)
    elif status == "pending":
        qs = qs.filter(is_approved=False)
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) |
                       Q(first_name__icontains=q) | Q(last_name__icontains=q))
    paginator = Paginator(qs, 20)
    page      = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/superuser/users.html", {
        "page": page, "role": role, "status": status, "q": q,
    })


@superuser_required
@require_POST
def su_user_action(request, pk):
    user = get_object_or_404(CustomUser, pk=pk, is_superuser=False)
    action = request.POST.get("action")
    if action == "approve":
        user.is_approved = True
        user.failed_login_count = 0
        user.save(update_fields=["is_approved", "failed_login_count"])
        messages.success(request, f"User '{user.username}' approved.")
        _log(request, "login", f"Approved user: {user.username}")
    elif action == "reject":
        user.is_approved = False
        user.save(update_fields=["is_approved"])
        messages.warning(request, f"User '{user.username}' approval revoked.")
    elif action == "delete":
        uname = user.username
        user.delete()
        messages.error(request, f"User '{uname}' deleted.")
    return redirect(request.POST.get("next", "portal:su_users"))


@superuser_required
@require_POST
def su_bulk_approve(request):
    """Approve all pending users."""
    count = CustomUser.objects.filter(is_superuser=False, is_approved=False).update(is_approved=True)
    messages.success(request, f"{count} pending user(s) approved.")
    return redirect("portal:su_users")


# ─── Notes ────────────────────────────────────────────────────────────────────

@superuser_required
def su_notes(request):
    notes   = Note.objects.select_related("course").order_by("-created_at")
    courses = Course.objects.filter(is_active=True).order_by("order", "title")
    if request.method == "POST":
        title     = request.POST.get("title", "").strip()
        subject   = request.POST.get("subject", "").strip()
        desc      = request.POST.get("description", "").strip()
        file      = request.FILES.get("file")
        course_id = request.POST.get("course_id", "").strip()
        if title:
            course = None
            if course_id:
                try:
                    course = Course.objects.get(pk=course_id, is_active=True)
                except Course.DoesNotExist:
                    # WARNING: Invalid course_id submitted. Proceeding without course assignment.
                    pass
            note = Note.objects.create(
                title=title, subject=subject, description=desc,
                file=file if file else None, is_active=True,
                course=course,
            )
            messages.success(request, f"Note '{note.title}' added (course: {course or 'All'}).")
            return redirect("portal:su_notes")
        else:
            messages.error(request, "Title is required.")
    return render(request, "portal/superuser/notes.html", {"notes": notes, "courses": courses})


@superuser_required
@require_POST
def su_note_delete(request, pk):
    note = get_object_or_404(Note, pk=pk)
    note.delete()
    messages.success(request, "Note deleted.")
    return redirect("portal:su_notes")


@superuser_required
@require_POST
def su_note_toggle(request, pk):
    note = get_object_or_404(Note, pk=pk)
    note.is_active = not note.is_active
    note.save(update_fields=["is_active"])
    return redirect("portal:su_notes")


# ─── Quizzes ─────────────────────────────────────────────────────────────────

@superuser_required
def su_quizzes(request):
    quizzes = Quiz.objects.select_related("course").prefetch_related("questions", "results").order_by("-created_at")
    return render(request, "portal/superuser/quizzes.html", {"quizzes": quizzes})


@superuser_required
def su_quiz_create(request):
    """Create quiz via plain-text parser or manual form. Now includes course assignment."""
    parse_error    = None
    parse_preview  = None
    parse_raw      = ""
    courses        = Course.objects.filter(is_active=True).order_by("order", "title")

    if request.method == "POST":
        mode = request.POST.get("mode", "text")
        course_id = request.POST.get("course_id", "").strip()
        course = None
        if course_id:
            try:
                course = Course.objects.get(pk=course_id, is_active=True)
            except Course.DoesNotExist:
                # WARNING: Invalid course_id. Quiz will be unlinked (visible to all students).
                pass

        if mode == "text":
            raw_text = request.POST.get("quiz_text", "")
            parse_raw = raw_text
            title    = request.POST.get("title", "").strip()
            subject  = request.POST.get("subject", "").strip()
            duration = int(request.POST.get("duration", 20))

            if request.POST.get("preview"):
                result = validate_and_preview(raw_text)
                if result["success"]:
                    parse_preview = result["questions"]
                else:
                    parse_error = result["error"]
            elif request.POST.get("save"):
                try:
                    questions = parse_quiz_text(raw_text)
                    if not title:
                        parse_error = "Quiz title is required."
                    else:
                        quiz = Quiz.objects.create(
                            title=title, subject=subject,
                            duration=duration, is_active=True, course=course,
                            description=f"Created via text parser — {len(questions)} questions."
                        )
                        for q_data in questions:
                            Question.objects.create(
                                quiz=quiz, text=q_data["text"],
                                option_a=q_data["option_a"], option_b=q_data["option_b"],
                                option_c=q_data["option_c"], option_d=q_data["option_d"],
                                correct=q_data["correct"], marks=1, order=q_data["order"],
                            )
                        messages.success(request, f"Quiz '{quiz.title}' created with {len(questions)} questions (course: {course or 'All'}).")
                        return redirect("portal:su_quizzes")
                except QuizParseError as e:
                    parse_error = str(e)

        elif mode == "manual":
            title    = request.POST.get("title", "").strip()
            subject  = request.POST.get("subject", "").strip()
            duration = int(request.POST.get("duration", 20))
            desc     = request.POST.get("description", "").strip()
            if title:
                quiz = Quiz.objects.create(
                    title=title, subject=subject,
                    duration=duration, description=desc, is_active=True, course=course,
                )
                messages.success(request, f"Quiz '{quiz.title}' created (course: {course or 'All'}). Add questions below.")
                return redirect("portal:su_quiz_questions", pk=quiz.pk)
            else:
                messages.error(request, "Title is required.")

    return render(request, "portal/superuser/quiz_create.html", {
        "parse_error": parse_error,
        "parse_preview": parse_preview,
        "parse_raw": parse_raw,
        "courses": courses,
    })


@superuser_required
def su_quiz_questions(request, pk):
    quiz      = get_object_or_404(Quiz, pk=pk)
    questions = quiz.questions.all()

    if request.method == "POST":
        text     = request.POST.get("text", "").strip()
        option_a = request.POST.get("option_a", "").strip()
        option_b = request.POST.get("option_b", "").strip()
        option_c = request.POST.get("option_c", "").strip()
        option_d = request.POST.get("option_d", "").strip()
        correct  = request.POST.get("correct", "A").upper()
        order    = questions.count() + 1
        if text and all([option_a, option_b, option_c, option_d]):
            Question.objects.create(
                quiz=quiz, text=text,
                option_a=option_a, option_b=option_b,
                option_c=option_c, option_d=option_d,
                correct=correct, marks=1, order=order
            )
            messages.success(request, "Question added.")
            return redirect("portal:su_quiz_questions", pk=pk)
        else:
            messages.error(request, "All fields are required.")

    return render(request, "portal/superuser/quiz_questions.html", {
        "quiz": quiz, "questions": questions,
    })


@superuser_required
@require_POST
def su_question_delete(request, pk):
    q = get_object_or_404(Question, pk=pk)
    quiz_pk = q.quiz_id
    q.delete()
    messages.success(request, "Question deleted.")
    return redirect("portal:su_quiz_questions", pk=quiz_pk)


@superuser_required
@require_POST
def su_quiz_delete(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    title = quiz.title
    quiz.delete()
    messages.success(request, f"Quiz '{title}' deleted.")
    return redirect("portal:su_quizzes")


@superuser_required
@require_POST
def su_quiz_toggle(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    quiz.is_active = not quiz.is_active
    quiz.save(update_fields=["is_active"])
    return redirect("portal:su_quizzes")


# ─── Assignments ─────────────────────────────────────────────────────────────

@superuser_required
def su_assignments(request):
    assignments = Assignment.objects.select_related("course").prefetch_related("submissions").order_by("-created_at")
    courses     = Course.objects.filter(is_active=True).order_by("order", "title")
    if request.method == "POST":
        from django.utils.dateparse import parse_datetime
        title     = request.POST.get("title", "").strip()
        subject   = request.POST.get("subject", "").strip()
        desc      = request.POST.get("description", "").strip()
        due_date  = request.POST.get("due_date", "")
        max_marks = int(request.POST.get("max_marks", 100))
        file      = request.FILES.get("file")
        course_id = request.POST.get("course_id", "").strip()
        if title and due_date:
            parsed_due = parse_datetime(due_date)
            if parsed_due:
                course = None
                if course_id:
                    try:
                        course = Course.objects.get(pk=course_id, is_active=True)
                    except Course.DoesNotExist:
                        # WARNING: Invalid course_id. Assignment will be unlinked (visible to all).
                        pass
                a = Assignment.objects.create(
                    title=title, subject=subject, description=desc,
                    due_date=parsed_due, max_marks=max_marks,
                    file=file if file else None, is_active=True,
                    course=course,
                )
                messages.success(request, f"Assignment '{a.title}' created (course: {course or 'All'}).")
                return redirect("portal:su_assignments")
            else:
                messages.error(request, "Invalid date/time format.")
        else:
            messages.error(request, "Title and due date are required.")
    return render(request, "portal/superuser/assignments.html", {
        "assignments": assignments, "courses": courses,
    })


@superuser_required
@require_POST
def su_assignment_delete(request, pk):
    a = get_object_or_404(Assignment, pk=pk)
    a.delete()
    messages.success(request, "Assignment deleted.")
    return redirect("portal:su_assignments")


@superuser_required
@require_POST
def su_grade_submission(request, pk):
    sub = get_object_or_404(Submission, pk=pk)
    marks    = request.POST.get("marks", "")
    feedback = request.POST.get("feedback", "").strip()
    if marks.isdigit():
        sub.marks    = int(marks)
        sub.feedback = feedback
        sub.status   = "graded"
        sub.save(update_fields=["marks", "feedback", "status"])
        messages.success(request, f"Submission graded: {marks} marks.")
    else:
        messages.error(request, "Invalid marks value.")
    return redirect("portal:su_assignments")


# ─── Client Projects ─────────────────────────────────────────────────────────

@superuser_required
def su_projects(request):
    projects = ClientProject.objects.select_related("client").order_by("-created_at")
    clients  = CustomUser.objects.filter(role="client", is_approved=True)

    if request.method == "POST":
        from django.utils.dateparse import parse_date
        client_id = request.POST.get("client_id")
        title     = request.POST.get("title", "").strip()
        desc      = request.POST.get("description", "").strip()
        status    = request.POST.get("status", "pending")
        progress  = int(request.POST.get("progress", 0))
        team_size = int(request.POST.get("team_size", 1))
        deadline  = parse_date(request.POST.get("deadline", "") or "")
        tech      = request.POST.get("tech_stack", "").strip()
        budget    = request.POST.get("budget", "").strip()
        if client_id and title:
            client = get_object_or_404(CustomUser, pk=client_id, role="client")
            ClientProject.objects.create(
                client=client, title=title, description=desc,
                status=status, progress=progress, team_size=team_size,
                deadline=deadline, tech_stack=tech, budget=budget
            )
            messages.success(request, f"Project '{title}' created.")
            return redirect("portal:su_projects")
        else:
            messages.error(request, "Client and title are required.")

    return render(request, "portal/superuser/projects.html", {
        "projects": projects, "clients": clients,
        "status_choices": ClientProject.STATUS_CHOICES,
    })


@superuser_required
@require_POST
def su_project_update(request, pk):
    project = get_object_or_404(ClientProject, pk=pk)
    project.status         = request.POST.get("status", project.status)
    project.progress       = int(request.POST.get("progress", project.progress))
    project.notes          = request.POST.get("notes", project.notes)
    project.live_url       = request.POST.get("live_url", project.live_url)
    project.demo_video_url = request.POST.get("demo_video_url", project.demo_video_url)
    project.save(update_fields=["status", "progress", "notes", "live_url", "demo_video_url"])
    messages.success(request, "Project updated.")
    return redirect("portal:su_projects")


@superuser_required
@require_POST
def su_project_delete(request, pk):
    p = get_object_or_404(ClientProject, pk=pk)
    p.delete()
    messages.success(request, "Project deleted.")
    return redirect("portal:su_projects")


# ─── Demo Schedules ───────────────────────────────────────────────────────────

@superuser_required
def su_demos(request):
    demos    = DemoSchedule.objects.select_related("inquiry_user").order_by("scheduled_at")
    inquirers = CustomUser.objects.filter(role="inquiry", is_approved=True)

    if request.method == "POST":
        from django.utils.dateparse import parse_datetime
        user_id    = request.POST.get("user_id")
        title      = request.POST.get("title", "Demo Session").strip()
        sched_str  = request.POST.get("scheduled_at", "")
        platform   = request.POST.get("platform", "zoom")
        link       = request.POST.get("meeting_link", "").strip()
        meeting_id = request.POST.get("meeting_id", "").strip()
        desc       = request.POST.get("description", "").strip()
        if user_id and sched_str:
            sched = parse_datetime(sched_str)
            if sched:
                user = get_object_or_404(CustomUser, pk=user_id, role="inquiry")
                DemoSchedule.objects.create(
                    inquiry_user=user, title=title, scheduled_at=sched,
                    platform=platform, meeting_link=link,
                    meeting_id=meeting_id, description=desc, status="scheduled"
                )
                messages.success(request, f"Demo session '{title}' scheduled.")
                return redirect("portal:su_demos")
            else:
                messages.error(request, "Invalid date/time format.")
        else:
            messages.error(request, "User and scheduled time are required.")

    return render(request, "portal/superuser/demos.html", {
        "demos": demos, "inquirers": inquirers,
        "platform_choices": DemoSchedule.PLATFORM_CHOICES,
        "status_choices":   DemoSchedule.STATUS_CHOICES,
    })


@superuser_required
@require_POST
def su_demo_update_status(request, pk):
    demo = get_object_or_404(DemoSchedule, pk=pk)
    demo.status    = request.POST.get("status", demo.status)
    demo.video_url = request.POST.get("video_url", demo.video_url)
    demo.save(update_fields=["status", "video_url"])
    messages.success(request, "Demo session updated.")
    return redirect("portal:su_demos")


@superuser_required
@require_POST
def su_demo_delete(request, pk):
    d = get_object_or_404(DemoSchedule, pk=pk)
    d.delete()
    messages.success(request, "Demo session deleted.")
    return redirect("portal:su_demos")


# ─── Notifications ────────────────────────────────────────────────────────────

@superuser_required
def su_notifications(request):
    notifs = Notification.objects.all().order_by("-created_at")
    if request.method == "POST":
        title       = request.POST.get("title", "").strip()
        body        = request.POST.get("body", "").strip()
        priority    = request.POST.get("priority", "info")
        target_role = request.POST.get("target_role", "")
        if title and body:
            Notification.objects.create(
                title=title, body=body, priority=priority,
                target_role=target_role, is_active=True
            )
            messages.success(request, f"Notification '{title}' posted.")
            return redirect("portal:su_notifications")
        else:
            messages.error(request, "Title and body are required.")
    return render(request, "portal/superuser/notifications.html", {
        "notifs": notifs,
        "priority_choices": Notification.PRIORITY_CHOICES,
        "role_choices": [("", "All Roles")] + list(CustomUser.ROLE_CHOICES),
    })


@superuser_required
@require_POST
def su_notification_delete(request, pk):
    n = get_object_or_404(Notification, pk=pk)
    n.delete()
    messages.success(request, "Notification deleted.")
    return redirect("portal:su_notifications")


@superuser_required
@require_POST
def su_notification_toggle(request, pk):
    n = get_object_or_404(Notification, pk=pk)
    n.is_active = not n.is_active
    n.save(update_fields=["is_active"])
    return redirect("portal:su_notifications")


# ─── Contact Messages ─────────────────────────────────────────────────────────

@superuser_required
def su_messages(request):
    msgs = ContactMessage.objects.all().order_by("-created_at")
    return render(request, "portal/superuser/messages.html", {"msgs": msgs})


@superuser_required
@require_POST
def su_message_mark_read(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    msg.status = "read"
    msg.save(update_fields=["status"])
    return redirect("portal:su_messages")


@superuser_required
@require_POST
def su_message_delete(request, pk):
    m = get_object_or_404(ContactMessage, pk=pk)
    m.delete()
    messages.success(request, "Message deleted.")
    return redirect("portal:su_messages")


# ─── Activity Log ─────────────────────────────────────────────────────────────

@superuser_required
def su_activity(request):
    logs = ActivityLog.objects.select_related("user").order_by("-timestamp")
    paginator = Paginator(logs, 50)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/superuser/activity.html", {"page": page})


# ═══════════════════════════════════════════════════════════════════════════════
# COURSE-BASED ACCESS CONTROL — ADMIN VIEWS
# Added in v4 upgrade. These views manage:
#   1. Course CRUD (su_courses, su_course_delete, su_course_toggle)
#   2. Student ↔ Course assignment (su_user_courses)
#   3. Course field on Notes/Quizzes/Assignments is handled in their
#      respective su_notes / su_quizzes / su_assignments views below
#      (the add-form now includes a course dropdown).
# ═══════════════════════════════════════════════════════════════════════════════

from .models import Course  # noqa — already imported at top in original, but safe here


@superuser_required
def su_courses(request):
    """
    List and create courses.
    Courses are the core entities for access control.
    WARNING: Deleting a course sets course=NULL on all linked Notes/Quizzes/Assignments
    (SET_NULL). Content becomes visible to all students again. Communicate this to admins.
    """
    courses = Course.objects.annotate(
        student_count=Count("enrolled_students"),
        notes_count=Count("notes"),
        quiz_count=Count("quizzes"),
        assignment_count=Count("assignments"),
    ).order_by("order", "title")

    if request.method == "POST":
        title    = request.POST.get("title", "").strip()
        subject  = request.POST.get("subject", "").strip()
        desc     = request.POST.get("description", "").strip()
        level    = request.POST.get("level", "beginner")
        duration = request.POST.get("duration", "").strip()
        icon     = request.POST.get("icon", "school").strip()
        order    = int(request.POST.get("order", 0) or 0)

        if title:
            course = Course.objects.create(
                title=title, subject=subject, description=desc,
                level=level, duration=duration, icon=icon or "school",
                order=order, is_active=True,
            )
            messages.success(request, f"Course '{course.title}' created successfully.")
            _log(request, "login", f"Created course: {course.title}")
            return redirect("portal:su_courses")
        else:
            messages.error(request, "Course title is required.")

    return render(request, "portal/superuser/courses.html", {
        "courses": courses,
        "level_choices": Course.LEVEL_CHOICES,
    })


@superuser_required
@require_POST
def su_course_delete(request, pk):
    """
    Delete a course.
    WARNING: This sets course=NULL on all linked Notes, Quizzes, Assignments (SET_NULL).
    Students enrolled in only this course will see all unlinked content.
    The student's enrolled_courses M2M entry is automatically removed by Django.
    """
    course = get_object_or_404(Course, pk=pk)
    title  = course.title
    # Warn if students are enrolled
    enrolled_count = course.enrolled_students.count()
    course.delete()
    if enrolled_count:
        messages.warning(
            request,
            f"Course '{title}' deleted. {enrolled_count} student(s) had this course — "
            "they now have no course assignment and will see only unlinked content."
        )
    else:
        messages.success(request, f"Course '{title}' deleted.")
    return redirect("portal:su_courses")


@superuser_required
@require_POST
def su_course_toggle(request, pk):
    """Toggle course active status. Inactive courses are hidden from students."""
    course = get_object_or_404(Course, pk=pk)
    course.is_active = not course.is_active
    course.save(update_fields=["is_active"])
    status = "activated" if course.is_active else "deactivated"
    messages.success(request, f"Course '{course.title}' {status}.")
    return redirect("portal:su_courses")


@superuser_required
def su_user_courses(request, pk):
    """
    View/modify a specific student's enrolled courses.
    Admin can:
      - See what the student selected
      - Add or remove courses
      - Reset their selection (forces them back to course_select page)

    This is the primary tool for admin course verification/modification
    after a student submits their initial selection.

    WARNING: If you clear all courses and also set course_selection_done=False,
    the student will be redirected to the course selection page on next login.
    If you only clear courses but leave course_selection_done=True,
    the student will see the dashboard but with no course content.
    """
    student = get_object_or_404(CustomUser, pk=pk, role="student", is_superuser=False)
    all_courses     = Course.objects.filter(is_active=True).order_by("order", "title")
    current_courses = student.enrolled_courses.all()

    if request.method == "POST":
        action = request.POST.get("action", "update")

        if action == "reset":
            # Force student back to course selection page
            student.enrolled_courses.clear()
            student.course_selection_done = False
            student.save(update_fields=["course_selection_done"])
            messages.warning(
                request,
                f"Student '{student.username}' course selection reset. "
                "They will be prompted to re-select on next login."
            )
            return redirect("portal:su_users")

        elif action == "update":
            selected_ids = request.POST.getlist("course_ids")
            if selected_ids:
                selected_courses = Course.objects.filter(pk__in=selected_ids, is_active=True)
                student.enrolled_courses.set(selected_courses)
                # Mark selection as done (admin assigned)
                student.course_selection_done = True
                student.save(update_fields=["course_selection_done"])
                course_names = ", ".join(c.title for c in selected_courses)
                messages.success(
                    request,
                    f"Enrolled '{student.username}' in: {course_names}"
                )
            else:
                # WARNING: Admin cleared all courses. Student will see only unlinked content.
                student.enrolled_courses.clear()
                messages.warning(
                    request,
                    f"All courses cleared for '{student.username}'. "
                    "They will only see unlinked legacy content."
                )
            return redirect("portal:su_user_courses", pk=pk)

    return render(request, "portal/superuser/user_courses.html", {
        "student": student,
        "all_courses": all_courses,
        "current_courses": current_courses,
        "selection_done": student.course_selection_done,
    })

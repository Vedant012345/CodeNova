"""
CodeNova Host / Teacher Dashboard — /host/
A full UI-based admin panel for superusers (teachers/hosts).

This is separate from both /admin/ (Django admin) and /superuser/ (original su panel).
URL prefix: /host/
Access: Superuser login only. No public registration.

SECURITY:
  API key is always loaded from the .env file.
  Access enforced by @host_required decorator on every view.
"""
import logging
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.db.models import Count, Avg, Q
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from datetime import timedelta

from .models import (
    CustomUser, Note, Quiz, Question, Assignment, Submission,
    QuizResult, QuizStudentAnswer, Notification, Topic, TopicCompletion, Performance,
    ChatMessage, ClientProject, DemoSchedule, ContactMessage,
    ActivityLog, Course, UserQuery,
)
from .ai_service import generate_quiz_questions, chat_with_student

logger = logging.getLogger(__name__)


# ─── Auth Decorator ──────────────────────────────────────────────────────────

def host_required(view_fn):
    """Block non-superusers. Redirect to /host/login/."""
    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return redirect("portal:host_login")
        return view_fn(request, *args, **kwargs)
    return wrapper


def _log(request, action, detail=""):
    ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", ""))
    ActivityLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action, detail=detail[:300], ip_address=ip or None
    )


# ─── Auth Views ───────────────────────────────────────────────────────────────

def host_login(request):
    """
    Login page for the Host Dashboard.
    Only superusers may proceed.
    """
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("portal:host_index")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user and user.is_superuser:
            auth_login(request, user)
            _log(request, "login", f"Host login: {username}")
            return redirect("portal:host_index")
        elif user:
            error = "This account does not have host access."
        else:
            error = "Invalid username or password."

    return render(request, "portal/host/login.html", {"error": error})


def host_logout(request):
    auth_logout(request)
    return redirect("portal:host_login")


# ─── Dashboard Home ───────────────────────────────────────────────────────────

@host_required
def host_index(request):
    """Main host dashboard — summary KPIs + quick links to all sections."""
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    stats = {
        "total_users":    CustomUser.objects.filter(is_superuser=False).count(),
        "pending_users":  CustomUser.objects.filter(is_approved=False, is_superuser=False).count(),
        "total_notes":    Note.objects.count(),
        "total_quizzes":  Quiz.objects.count(),
        "ai_quizzes":     Quiz.objects.filter(is_ai_generated=True).count(),
        "open_queries":   UserQuery.objects.filter(status="open").count(),
        "chat_messages":  ChatMessage.objects.count(),
        "upcoming_demos": DemoSchedule.objects.filter(
            scheduled_at__gte=now, status="scheduled"
        ).count(),
        "active_projects": ClientProject.objects.filter(
            status__in=["in_progress", "review"]
        ).count(),
        "new_messages":   ContactMessage.objects.filter(status="new").count(),
        "recent_signups": CustomUser.objects.filter(
            date_joined__gte=week_ago, is_superuser=False
        ).count(),
        "quiz_attempts":  QuizResult.objects.count(),
    }

    # Recent activity — v9: use select_related to avoid N+1 on user FK
    recent_logs    = ActivityLog.objects.select_related("user").order_by("-timestamp")[:8]
    pending_users  = CustomUser.objects.filter(
        is_approved=False, is_superuser=False
    ).order_by("-date_joined").select_related("registration_course")[:5]
    open_queries   = UserQuery.objects.filter(
        status="open"
    ).select_related("user").order_by("-created_at")[:5]
    recent_chat    = ChatMessage.objects.select_related("student").order_by("-timestamp")[:5]

    return render(request, "portal/host/index.html", {
        "stats": stats,
        "recent_logs": recent_logs,
        "pending_users": pending_users,
        "open_queries": open_queries,
        "recent_chat": recent_chat,
        # v9: recent unread contact messages for dashboard preview
        "new_contact_msgs": ContactMessage.objects.filter(status="new").select_related().order_by("-created_at")[:4],
    })


# ─── User Management ─────────────────────────────────────────────────────────

@host_required
def host_users(request):
    """List and filter all non-superuser accounts."""
    role   = request.GET.get("role", "")
    status = request.GET.get("status", "")
    q      = request.GET.get("q", "").strip()

    qs = CustomUser.objects.filter(is_superuser=False).order_by("-date_joined").prefetch_related("enrolled_courses")
    if role:
        qs = qs.filter(role=role)
    if status == "pending":
        qs = qs.filter(is_approved=False)
    elif status == "approved":
        qs = qs.filter(is_approved=True)
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q))

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "portal/host/users.html", {
        "page": page,
        "role_choices": CustomUser.ROLE_CHOICES,
        "current_role": role,
        "current_status": status,
        "q": q,
    })


@host_required
@require_POST
def host_user_action(request, pk):
    """
    Approve, reject, or toggle active state of a user.
    v8: On approval, automatically enroll student in their registration_course
        (the course they selected during registration). This means approved
        students go straight to the dashboard — no course selection page needed.
    """
    user   = get_object_or_404(CustomUser, pk=pk, is_superuser=False)
    action = request.POST.get("action")
    if action == "approve":
        user.is_approved = True
        user.save(update_fields=["is_approved"])
        # v8: Auto-enroll from registration course
        # WARNING: auto_enroll_from_registration() only acts if registration_course is set.
        # Students without a registration_course still go through the course_select page.
        user.auto_enroll_from_registration()
        messages.success(request, f"{user.username} approved.")
        if user.registration_course:
            messages.info(request, f"Auto-enrolled in: {user.registration_course.title}")
        _log(request, "user_approved", f"Approved {user.username}")
    elif action == "reject":
        user.is_approved = False
        user.save(update_fields=["is_approved"])
        messages.success(request, f"{user.username} rejected.")
    elif action == "toggle_active":
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        messages.success(request, f"{user.username} {'activated' if user.is_active else 'deactivated'}.")
    elif action == "delete":
        uname = user.username
        user.delete()
        messages.success(request, f"User '{uname}' deleted.")
    return redirect(request.POST.get("next", "portal:host_users"))


@host_required
@require_POST
def host_bulk_approve(request):
    """Approve all pending users at once."""
    n = CustomUser.objects.filter(is_approved=False, is_superuser=False).update(is_approved=True)
    messages.success(request, f"Approved {n} user(s).")
    _log(request, "user_approved", f"Bulk approved {n} users")
    return redirect("portal:host_users")


# ─── Notes Management ─────────────────────────────────────────────────────────

@host_required
def host_notes(request):
    notes = Note.objects.select_related("uploaded_by").order_by("-created_at")
    q = request.GET.get("q", "").strip()
    if q:
        notes = notes.filter(Q(title__icontains=q) | Q(subject__icontains=q))

    # Create new note
    if request.method == "POST":
        title   = request.POST.get("title", "").strip()
        subject = request.POST.get("subject", "").strip()
        desc    = request.POST.get("description", "").strip()
        file    = request.FILES.get("file")
        if title and file:
            Note.objects.create(
                title=title, subject=subject, description=desc,
                file=file, uploaded_by=request.user, is_active=True
            )
            messages.success(request, f"Note '{title}' uploaded.")
            return redirect("portal:host_notes")
        else:
            messages.error(request, "Title and file are required.")

    paginator = Paginator(notes, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/host/notes.html", {"page": page, "q": q})


@host_required
@require_POST
def host_note_delete(request, pk):
    n = get_object_or_404(Note, pk=pk)
    n.delete()
    messages.success(request, "Note deleted.")
    return redirect("portal:host_notes")


@host_required
@require_POST
def host_note_toggle(request, pk):
    n = get_object_or_404(Note, pk=pk)
    n.is_active = not n.is_active
    n.save(update_fields=["is_active"])
    return redirect("portal:host_notes")


# ─── Quiz Management ──────────────────────────────────────────────────────────

@host_required
def host_quizzes(request):
    quizzes = Quiz.objects.annotate(q_count=Count("questions")).order_by("-created_at")
    if request.method == "POST":
        title   = request.POST.get("title", "").strip()
        subject = request.POST.get("subject", "").strip()
        desc    = request.POST.get("description", "").strip()
        mins    = request.POST.get("time_limit_minutes", 0)
        if title:
            Quiz.objects.create(
                title=title, subject=subject, description=desc,
                time_limit_minutes=int(mins or 0),
                is_active=True, is_ai_generated=False
            )
            messages.success(request, f"Quiz '{title}' created.")
            return redirect("portal:host_quizzes")
        messages.error(request, "Title is required.")

    paginator = Paginator(quizzes, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/host/quizzes.html", {"page": page})


@host_required
def host_quiz_questions(request, pk):
    """Manage questions for a specific quiz."""
    quiz = get_object_or_404(Quiz, pk=pk)
    questions = quiz.questions.order_by("order")

    if request.method == "POST":
        action = request.POST.get("action", "add")
        if action == "add":
            text    = request.POST.get("text", "").strip()
            opt_a   = request.POST.get("option_a", "").strip()
            opt_b   = request.POST.get("option_b", "").strip()
            opt_c   = request.POST.get("option_c", "").strip()
            opt_d   = request.POST.get("option_d", "").strip()
            correct = request.POST.get("correct", "A").upper()
            expl    = request.POST.get("explanation", "").strip()
            if text and opt_a and opt_b:
                Question.objects.create(
                    quiz=quiz, text=text,
                    option_a=opt_a, option_b=opt_b,
                    option_c=opt_c, option_d=opt_d,
                    correct=correct, explanation=expl,
                    order=questions.count() + 1
                )
                messages.success(request, "Question added.")
                return redirect("portal:host_quiz_questions", pk=pk)
            messages.error(request, "Question text and at least 2 options are required.")

    return render(request, "portal/host/quiz_questions.html", {
        "quiz": quiz, "questions": questions
    })


@host_required
@require_POST
def host_question_delete(request, pk):
    q = get_object_or_404(Question, pk=pk)
    quiz_pk = q.quiz_id
    q.delete()
    messages.success(request, "Question deleted.")
    return redirect("portal:host_quiz_questions", pk=quiz_pk)


@host_required
@require_POST
def host_quiz_delete(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    quiz.delete()
    messages.success(request, "Quiz deleted.")
    return redirect("portal:host_quizzes")


@host_required
@require_POST
def host_quiz_toggle(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    quiz.is_active = not quiz.is_active
    quiz.save(update_fields=["is_active"])
    return redirect("portal:host_quizzes")


# ─── Quiz Analytics (v10) ────────────────────────────────────────────────────

@host_required
def host_quiz_analytics(request, pk=None):
    """
    v10: Host dashboard quiz analytics.
    Shows per-student score and full answer breakdown for every quiz attempt.
    Optional: filter by quiz (pk).
    """
    quizzes = Quiz.objects.filter(is_active=True).order_by("-created_at")
    selected_quiz = None

    if pk:
        selected_quiz = get_object_or_404(Quiz, pk=pk)
        results = (
            QuizResult.objects
            .filter(quiz=selected_quiz)
            .select_related("student")
            .order_by("-taken_at")
        )
    else:
        results = (
            QuizResult.objects
            .select_related("student", "quiz")
            .order_by("-taken_at")
        )

    # Build enriched data: for each result pull per-question answers
    analytics = []
    for result in results:
        answers = (
            QuizStudentAnswer.objects
            .filter(student=result.student, quiz=result.quiz)
            .select_related("question")
            .order_by("question__order", "question__id")
        )
        answer_detail = []
        for ans in answers:
            q = ans.question
            option_map = {"A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d}
            answer_detail.append({
                "question_text":  q.text,
                "selected":       ans.selected_answer,
                "selected_text":  option_map.get(ans.selected_answer, "— Not answered —"),
                "correct":        ans.correct_answer,
                "correct_text":   option_map.get(ans.correct_answer, ""),
                "is_correct":     ans.is_correct,
                "marks":          q.marks,
                "order":          q.order,
            })
        analytics.append({
            "result":        result,
            "student":       result.student,
            "quiz":          result.quiz,
            "answer_detail": answer_detail,
            "correct_count": sum(1 for a in answer_detail if a["is_correct"]),
            "wrong_count":   sum(1 for a in answer_detail if not a["is_correct"]),
        })

    return render(request, "portal/host/quiz_analytics.html", {
        "analytics":     analytics,
        "quizzes":       quizzes,
        "selected_quiz": selected_quiz,
    })


# ─── AI Quiz Generator ────────────────────────────────────────────────────────

@host_required
def host_ai_quiz(request):
    """
    AI Quiz Generator — v8 upgrade.
    Supports 5 to 50 questions (validated server-side).
    Uses Groq with multi-model fallback (llama3 → mixtral → gemma → llama3-70b).

    GROQ_API_KEY is loaded from the .env file — never hardcoded.
    See ai_service.py for full implementation.
    """
    result = None
    if request.method == "POST":
        topic   = request.POST.get("topic", "").strip()
        subject = request.POST.get("subject", "").strip()
        course_id = request.POST.get("course_id", "").strip()

        # v8: Validate n is between 5 and 50
        try:
            n = int(request.POST.get("n", 10))
            if not (5 <= n <= 50):
                messages.error(request, "Number of questions must be between 5 and 50.")
                n = 10  # reset to safe default
        except (ValueError, TypeError):
            n = 10

        if not topic:
            messages.error(request, "Please enter a topic.")
        else:
            # Determine course assignment
            course = None
            if course_id:
                from .models import Course as CourseModel
                try:
                    course = CourseModel.objects.get(pk=course_id, is_active=True)
                except CourseModel.DoesNotExist:
                    pass  # WARNING: Invalid course_id — quiz will be unlinked

            # Call Groq AI with multi-model fallback
            ai_result = generate_quiz_questions(topic=topic, subject=subject, n=n)

            if ai_result["success"]:
                quiz = Quiz.objects.create(
                    title=f"AI Quiz: {topic[:80]}",
                    subject=subject or topic,
                    description=f"AI-generated ({n} questions) on: {topic}",
                    is_active=True,
                    is_ai_generated=True,
                    course=course,
                )
                for i, q in enumerate(ai_result["questions"]):
                    Question.objects.create(
                        quiz=quiz,
                        text=q["text"],
                        option_a=q["option_a"],
                        option_b=q["option_b"],
                        option_c=q["option_c"],
                        option_d=q["option_d"],
                        correct=q["correct"],
                        explanation=q.get("explanation", ""),
                        order=i + 1,
                    )
                _log(request, "ai_quiz_gen", f"Generated quiz: {topic} ({n} Qs via {ai_result.get('model_used','?')})")
                messages.success(
                    request,
                    f"✅ Quiz '{quiz.title}' created with {len(ai_result['questions'])} questions! "
                    f"(Model: {ai_result.get('model_used', 'AI')})"
                )
                result = {"quiz": quiz, "questions": ai_result["questions"]}
            else:
                messages.error(request, f"AI error: {ai_result['error']}")

    courses = Course.objects.filter(is_active=True).order_by("order", "title")
    recent_ai_quizzes = Quiz.objects.filter(is_ai_generated=True).select_related("course").order_by("-created_at")[:10]
    return render(request, "portal/host/ai_quiz.html", {
        "result": result,
        "recent_ai_quizzes": recent_ai_quizzes,
        "courses": courses,
        "question_range": list(range(5, 51, 5)),  # [5, 10, 15, ..., 50]
    })


# ─── AI Chatbot Monitor ───────────────────────────────────────────────────────

@host_required
def host_ai_chat(request):
    """
    Host-side AI chatbot + chat log viewer.
    Host can also test the chatbot directly.
    Multi-model fallback handled in ai_service.py.
    """
    ai_reply = None
    if request.method == "POST" and request.POST.get("host_question"):
        question = request.POST.get("host_question", "").strip()
        if question:
            result = chat_with_student(question, history=[], topic="general")
            ai_reply = result.get("reply") if result["success"] else f"Error: {result['error']}"

    chat_logs = ChatMessage.objects.select_related("student").order_by("-timestamp")
    paginator = Paginator(chat_logs, 30)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "portal/host/ai_chat.html", {
        "page": page,
        "ai_reply": ai_reply,
        "total_chats": chat_logs.count(),
        "models": ["llama3-8b-8192", "mixtral-8x7b-32768", "gemma-7b-it", "llama3-70b-8192"],
    })


# ─── Assignments ──────────────────────────────────────────────────────────────

@host_required
def host_assignments(request):
    assignments = Assignment.objects.annotate(
        sub_count=Count("submissions")
    ).order_by("-created_at")

    if request.method == "POST":
        title    = request.POST.get("title", "").strip()
        desc     = request.POST.get("description", "").strip()
        subject  = request.POST.get("subject", "").strip()
        due      = request.POST.get("due_date", "")
        max_m    = int(request.POST.get("max_marks", 100))
        file     = request.FILES.get("attachment")
        if title:
            from django.utils.dateparse import parse_datetime
            Assignment.objects.create(
                title=title, description=desc, subject=subject,
                due_date=parse_datetime(due) if due else None,
                max_marks=max_m, attachment=file
            )
            messages.success(request, f"Assignment '{title}' created.")
            return redirect("portal:host_assignments")
        messages.error(request, "Title is required.")

    paginator = Paginator(assignments, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/host/assignments.html", {"page": page})


@host_required
def host_submissions(request, pk):
    """View all submissions for an assignment and grade them."""
    assignment  = get_object_or_404(Assignment, pk=pk)
    submissions = Submission.objects.filter(assignment=assignment).select_related("student")

    if request.method == "POST":
        sub_pk = request.POST.get("submission_id")
        marks  = request.POST.get("marks", "")
        feedback = request.POST.get("feedback", "").strip()
        sub  = get_object_or_404(Submission, pk=sub_pk, assignment=assignment)
        try:
            sub.marks    = int(marks)
            sub.feedback = feedback
            sub.status   = "graded"
            sub.save(update_fields=["marks", "feedback", "status"])
            messages.success(request, f"Graded {sub.student.username}.")
        except (ValueError, TypeError):
            messages.error(request, "Invalid marks value.")
        return redirect("portal:host_submissions", pk=pk)

    return render(request, "portal/host/submissions.html", {
        "assignment": assignment, "submissions": submissions
    })


@host_required
@require_POST
def host_assignment_delete(request, pk):
    a = get_object_or_404(Assignment, pk=pk)
    a.delete()
    messages.success(request, "Assignment deleted.")
    return redirect("portal:host_assignments")


# ─── Client Projects ──────────────────────────────────────────────────────────

@host_required
def host_projects(request):
    projects = ClientProject.objects.select_related("client").order_by("-created_at")
    clients  = CustomUser.objects.filter(role="client", is_approved=True)

    if request.method == "POST":
        from django.utils.dateparse import parse_date
        client_id  = request.POST.get("client_id")
        title      = request.POST.get("title", "").strip()
        desc       = request.POST.get("description", "").strip()
        status     = request.POST.get("status", "pending")
        progress   = int(request.POST.get("progress", 0))
        tech       = request.POST.get("tech_stack", "").strip()
        live_url   = request.POST.get("live_url", "").strip()
        demo_url   = request.POST.get("demo_video_url", "").strip()
        deadline   = parse_date(request.POST.get("deadline", "") or "")
        if client_id and title:
            client = get_object_or_404(CustomUser, pk=client_id, role="client")
            ClientProject.objects.create(
                client=client, title=title, description=desc,
                status=status, progress=progress, tech_stack=tech,
                live_url=live_url, demo_video_url=demo_url, deadline=deadline
            )
            messages.success(request, f"Project '{title}' created.")
            return redirect("portal:host_projects")
        messages.error(request, "Client and title are required.")

    paginator = Paginator(projects, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/host/projects.html", {
        "page": page, "clients": clients,
        "status_choices": ClientProject.STATUS_CHOICES,
    })


@host_required
@require_POST
def host_project_update(request, pk):
    project = get_object_or_404(ClientProject, pk=pk)
    project.status         = request.POST.get("status", project.status)
    project.progress       = int(request.POST.get("progress", project.progress))
    project.notes          = request.POST.get("notes", project.notes)
    project.live_url       = request.POST.get("live_url", project.live_url)
    project.demo_video_url = request.POST.get("demo_video_url", project.demo_video_url)
    project.save(update_fields=["status", "progress", "notes", "live_url", "demo_video_url"])
    messages.success(request, "Project updated.")
    return redirect("portal:host_projects")


@host_required
@require_POST
def host_project_delete(request, pk):
    p = get_object_or_404(ClientProject, pk=pk)
    p.delete()
    messages.success(request, "Project deleted.")
    return redirect("portal:host_projects")


# ─── Demo Sessions ────────────────────────────────────────────────────────────

@host_required
def host_demos(request):
    demos      = DemoSchedule.objects.select_related("inquiry_user").order_by("scheduled_at")
    inquirers  = CustomUser.objects.filter(role="inquiry", is_approved=True)

    if request.method == "POST":
        from django.utils.dateparse import parse_datetime
        user_id    = request.POST.get("user_id")
        title      = request.POST.get("title", "Demo Session").strip()
        sched_str  = request.POST.get("scheduled_at", "")
        platform   = request.POST.get("platform", "zoom")
        link       = request.POST.get("meeting_link", "").strip()
        meeting_id = request.POST.get("meeting_id", "").strip()
        video_url  = request.POST.get("video_url", "").strip()
        desc       = request.POST.get("description", "").strip()

        if user_id and sched_str:
            sched = parse_datetime(sched_str)
            if sched:
                user = get_object_or_404(CustomUser, pk=user_id, role="inquiry")
                DemoSchedule.objects.create(
                    inquiry_user=user, title=title, scheduled_at=sched,
                    platform=platform, meeting_link=link, meeting_id=meeting_id,
                    video_url=video_url, description=desc, status="scheduled"
                )
                messages.success(request, f"Demo '{title}' scheduled.")
                return redirect("portal:host_demos")
            messages.error(request, "Invalid date/time format.")
        else:
            messages.error(request, "User and scheduled time are required.")

    return render(request, "portal/host/demos.html", {
        "demos": demos, "inquirers": inquirers,
        "platform_choices": DemoSchedule.PLATFORM_CHOICES,
        "status_choices":   DemoSchedule.STATUS_CHOICES,
    })


@host_required
@require_POST
def host_demo_update(request, pk):
    demo           = get_object_or_404(DemoSchedule, pk=pk)
    demo.status    = request.POST.get("status", demo.status)
    demo.video_url = request.POST.get("video_url", demo.video_url)
    demo.meeting_link = request.POST.get("meeting_link", demo.meeting_link)
    demo.save(update_fields=["status", "video_url", "meeting_link"])
    messages.success(request, "Demo updated.")
    return redirect("portal:host_demos")


@host_required
@require_POST
def host_demo_delete(request, pk):
    d = get_object_or_404(DemoSchedule, pk=pk)
    d.delete()
    messages.success(request, "Demo deleted.")
    return redirect("portal:host_demos")


# ─── User Queries (Ask Question) ─────────────────────────────────────────────

@host_required
def host_queries(request):
    """
    Inbox for student/client questions.
    Host can read, reply, and close queries here.
    """
    status_filter = request.GET.get("status", "open")
    q             = request.GET.get("q", "").strip()

    queries = UserQuery.objects.select_related(
        "user", "answered_by"
    ).order_by("-created_at")

    if status_filter and status_filter != "all":
        queries = queries.filter(status=status_filter)
    if q:
        queries = queries.filter(
            Q(subject__icontains=q) | Q(question__icontains=q) | Q(user__username__icontains=q)
        )

    paginator = Paginator(queries, 20)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "portal/host/queries.html", {
        "page": page,
        "status_filter": status_filter,
        "q": q,
        "open_count":     UserQuery.objects.filter(status="open").count(),
        "answered_count": UserQuery.objects.filter(status="answered").count(),
        "closed_count":   UserQuery.objects.filter(status="closed").count(),
    })


@host_required
@require_POST
def host_query_reply(request, pk):
    """Post a reply to a user query."""
    query   = get_object_or_404(UserQuery, pk=pk)
    answer  = request.POST.get("answer", "").strip()
    new_status = request.POST.get("status", "answered")
    if answer:
        query.answer      = answer
        query.answered_by = request.user
        query.status      = new_status
        query.save()
        messages.success(request, f"Reply sent to {query.user.username}.")
    else:
        messages.error(request, "Reply cannot be empty.")
    return redirect("portal:host_queries")


@host_required
@require_POST
def host_query_status(request, pk):
    """Change query status (open/answered/closed)."""
    query = get_object_or_404(UserQuery, pk=pk)
    query.status = request.POST.get("status", query.status)
    query.save(update_fields=["status"])
    return redirect("portal:host_queries")


# ─── Courses & Topics ────────────────────────────────────────────────────────

@host_required
def host_courses(request):
    # MERGE_NOTE: Updated for V6 — annotate with enrolled student count from
    # the new enrolled_students M2M relationship added in migration 0006.
    # v9: Use prefetch_related for topics to avoid N+1
    courses = Course.objects.annotate(
        topic_count=Count("topics"),
        enrolled_count=Count("enrolled_students"),
    ).prefetch_related("topics").order_by("order", "-created_at")

    if request.method == "POST":
        action = request.POST.get("action", "add_course")
        if action == "add_course":
            title   = request.POST.get("title", "").strip()
            subject = request.POST.get("subject", "").strip()
            desc    = request.POST.get("description", "").strip()
            level   = request.POST.get("level", "beginner")
            icon    = request.POST.get("icon", "school")
            banner  = request.FILES.get("banner_image")
            if title:
                course = Course.objects.create(
                    title=title, subject=subject, description=desc,
                    level=level, icon=icon, is_active=True
                )
                if banner:
                    course.banner_image = banner
                    course.save(update_fields=["banner_image"])
                messages.success(request, f"Course '{title}' created.")
                return redirect("portal:host_courses")
            messages.error(request, "Title is required.")
        elif action == "add_topic":
            course_id = request.POST.get("course_id")
            title     = request.POST.get("topic_title", "").strip()
            order     = int(request.POST.get("topic_order", 1))
            video_url = request.POST.get("video_url", "").strip()
            content   = request.POST.get("content", "").strip()
            if course_id and title:
                course = get_object_or_404(Course, pk=course_id)
                Topic.objects.create(
                    course=course, title=title, order=order,
                    video_url=video_url, content=content
                )
                messages.success(request, f"Topic '{title}' added to {course.title}.")
                return redirect("portal:host_courses")
            messages.error(request, "Course and topic title are required.")

    return render(request, "portal/host/courses.html", {
        "courses": courses,
        "level_choices": Course.LEVEL_CHOICES,
    })


@host_required
@require_POST
def host_course_delete(request, pk):
    c = get_object_or_404(Course, pk=pk)
    c.delete()
    messages.success(request, "Course deleted.")
    return redirect("portal:host_courses")


@host_required
@require_POST
def host_topic_delete(request, pk):
    t = get_object_or_404(Topic, pk=pk)
    t.delete()
    messages.success(request, "Topic deleted.")
    return redirect("portal:host_courses")


# ─── Notifications ────────────────────────────────────────────────────────────

@host_required
def host_notifications(request):
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
            messages.success(request, f"Notification '{title}' published.")
            return redirect("portal:host_notifications")
        messages.error(request, "Title and body are required.")

    paginator = Paginator(notifs, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/host/notifications.html", {
        "page": page,
        "priority_choices": Notification.PRIORITY_CHOICES,
        "role_choices": [("", "All Roles")] + list(CustomUser.ROLE_CHOICES),
    })


@host_required
@require_POST
def host_notification_delete(request, pk):
    n = get_object_or_404(Notification, pk=pk)
    n.delete()
    messages.success(request, "Notification deleted.")
    return redirect("portal:host_notifications")


@host_required
@require_POST
def host_notification_toggle(request, pk):
    n = get_object_or_404(Notification, pk=pk)
    n.is_active = not n.is_active
    n.save(update_fields=["is_active"])
    return redirect("portal:host_notifications")


# ─── Contact Messages ─────────────────────────────────────────────────────────

@host_required
def host_contact_messages(request):
    """
    v9: View and manage messages from the homepage 'Get in Touch' form.
    Separate from the Ask Question / UserQuery system.
    """
    filter_status = request.GET.get("status", "")
    qs = ContactMessage.objects.all()
    if filter_status in ("new", "read", "replied"):
        qs = qs.filter(status=filter_status)

    paginator = Paginator(qs.order_by("-created_at"), 20)
    page = paginator.get_page(request.GET.get("page"))

    unread_count = ContactMessage.objects.filter(status="new").count()

    return render(request, "portal/host/contact_messages.html", {
        "page": page,
        "filter_status": filter_status,
        "unread_count": unread_count,
        "status_choices": ContactMessage.STATUS_CHOICES,
        "subject_choices": ContactMessage.SUBJECT_CHOICES,
    })


@host_required
@require_POST
def host_contact_mark_read(request, pk):
    """Toggle read/unread status on a contact message."""
    msg = get_object_or_404(ContactMessage, pk=pk)
    new_status = request.POST.get("status", "read")
    if new_status in ("new", "read", "replied"):
        msg.status = new_status
        msg.save(update_fields=["status"])
        messages.success(request, f"Message marked as '{msg.get_status_display()}'.")
    return redirect(request.META.get("HTTP_REFERER", "portal:host_contact_messages"))


@host_required
@require_POST
def host_contact_delete(request, pk):
    """Delete a contact message."""
    msg = get_object_or_404(ContactMessage, pk=pk)
    msg.delete()
    messages.success(request, "Message deleted.")
    return redirect("portal:host_contact_messages")


# ─── Course Banner Upload (v9) ────────────────────────────────────────────────

@host_required
@require_POST
def host_course_banner(request, pk):
    """Upload or remove banner image for a course."""
    course = get_object_or_404(Course, pk=pk)
    action = request.POST.get("banner_action", "upload")
    if action == "remove":
        if course.banner_image:
            course.banner_image.delete(save=False)
        course.banner_image = None
        course.save(update_fields=["banner_image"])
        messages.success(request, f"Banner removed from '{course.title}'.")
    elif "banner_image" in request.FILES:
        course.banner_image = request.FILES["banner_image"]
        course.save(update_fields=["banner_image"])
        messages.success(request, f"Banner updated for '{course.title}'.")
    else:
        messages.error(request, "No image file provided.")
    return redirect("portal:host_courses")

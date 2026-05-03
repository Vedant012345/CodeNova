"""
CodeNova Portal Views — v4
Course-based access control: student course selection, content filtering,
admin course assignment. All existing functionality preserved.
"""
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.db.models import Avg, Sum, Prefetch, Count, Q
from django.utils import timezone
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_POST
import os

from .models import (
    CustomUser, Note, Quiz, Question, Assignment, Submission,
    QuizResult, QuizStudentAnswer, Notification, Topic, TopicCompletion, Performance,
    ChatMessage, ClientProject, DemoSchedule, ContactMessage, ActivityLog,
    Course, UserQuery,
)
from .forms import (
    RegistrationForm, LoginForm, ProfileForm,
    SubmissionForm, AIQuizGenerateForm, CourseSelectionForm
)
from . import ai_service

logger = logging.getLogger(__name__)

SUPPORT_EMAIL = "support@scholarflow.com"
SUPPORT_PHONE = "+1 (555) 123-4567"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


def _log(request, action, detail=""):
    ActivityLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action, detail=detail[:300],
        ip_address=_get_client_ip(request) or None
    )


def _approved_required(view_fn):
    """Requires authentication + admin approval."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.urls import reverse
            return redirect(f"{reverse('portal:login')}?next={request.path}")
        if not request.user.is_approved:
            return redirect("portal:pending")
        return view_fn(request, *args, **kwargs)
    wrapper.__name__ = view_fn.__name__
    return wrapper


def _role_required(*roles):
    def decorator(view_fn):
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.urls import reverse
                return redirect(f"{reverse('portal:login')}?next={request.path}")
            if not request.user.is_approved:
                return redirect("portal:pending")
            if request.user.role not in roles:
                messages.error(request, "You don't have permission to view that page.")
                return redirect("portal:dashboard")
            return view_fn(request, *args, **kwargs)
        wrapper.__name__ = view_fn.__name__
        return wrapper
    return decorator


def _student_course_required(view_fn):
    """
    Decorator for student-only views that require course selection to be done.
    If student hasn't selected courses yet → redirect to course selection.
    If admin hasn't assigned/confirmed courses → redirect to pending-course page.

    WARNING: This checks course_selection_done, not enrolled_courses.exists().
    A student CAN have course_selection_done=True but enrolled_courses empty if
    the admin removed all their courses. The dashboard handles this gracefully.
    Superusers always bypass this check.
    """
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.urls import reverse
            return redirect(f"{reverse('portal:login')}?next={request.path}")
        if not request.user.is_approved:
            return redirect("portal:pending")
        if request.user.role != "student" or request.user.is_superuser:
            return view_fn(request, *args, **kwargs)
        # Student-specific course guard
        if not request.user.course_selection_done:
            return redirect("portal:course_select")
        return view_fn(request, *args, **kwargs)
    wrapper.__name__ = view_fn.__name__
    return wrapper


def _get_student_courses(user):
    """
    Returns the queryset of Course objects for a student.
    WARNING: Returns empty queryset if student hasn't enrolled in any courses.
    Call this only for role='student' users.
    """
    return user.enrolled_courses.filter(is_active=True)


def _filter_content_for_student(queryset, user, course_field="course"):
    """
    Filter a Note/Quiz/Assignment queryset for a student:
    - Items assigned to one of the student's courses → SHOWN
    - Items with course=NULL (legacy/unassigned) → SHOWN to all students
      (backward-compatible: existing content without course still visible)
    - Items assigned to a course the student is NOT enrolled in → HIDDEN

    WARNING: If you want STRICT filtering (hide all unassigned content),
    change the Q(course__isnull=True) branch to only show enrolled content.
    Currently we show unassigned content to preserve backward compatibility.
    """
    student_courses = _get_student_courses(user)
    return queryset.filter(
        Q(**{f"{course_field}__in": student_courses}) |
        Q(**{f"{course_field}__isnull": True})
    )


def _recalc_performance(user):
    """Recalculate and cache performance snapshot."""
    quiz_avg = (
        QuizResult.objects.filter(student=user)
        .aggregate(avg=Avg("percentage"))["avg"] or 0.0
    )
    sub_qs = Submission.objects.filter(student=user, marks__isnull=False).select_related("assignment")
    if sub_qs.exists():
        total_pct = sum(
            (s.marks / s.assignment.max_marks * 100)
            for s in sub_qs if s.assignment.max_marks
        )
        assign_avg = total_pct / sub_qs.count()
    else:
        assign_avg = 0.0

    topics_done  = TopicCompletion.objects.filter(student=user).count()
    total_topics = Topic.objects.filter(is_active=True).count() or 1
    topic_pct    = min((topics_done / total_topics) * 100, 100)
    overall      = quiz_avg * 0.5 + assign_avg * 0.4 + topic_pct * 0.1

    perf, _ = Performance.objects.get_or_create(student=user)
    perf.quiz_avg       = round(quiz_avg, 1)
    perf.assignment_avg = round(assign_avg, 1)
    perf.topics_done    = topics_done
    perf.overall        = round(overall, 1)
    perf.save()
    return perf


def _notifications_for(user):
    return Notification.objects.filter(is_active=True).filter(
        Q(target_role="") | Q(target_role=user.role)
    )


# ─── Homepage ─────────────────────────────────────────────────────────────────

def homepage(request):
    if request.user.is_authenticated and request.user.is_approved:
        return redirect("portal:dashboard")
    contact_success = request.GET.get("sent") == "1"
    # v9: only_fields needed + banner for display; no topics needed on homepage
    active_courses  = Course.objects.filter(is_active=True).only(
        "id", "title", "description", "subject", "level", "duration", "icon", "banner_image", "order"
    ).order_by("order", "-created_at")
    active_projects = ClientProject.objects.filter(
        status__in=("in_progress", "review", "completed")
    ).select_related("client").order_by("-updated_at")[:6]
    return render(request, "portal/homepage.html", {
        "contact_success": contact_success,
        "active_courses":  active_courses,
        "active_projects": active_projects,
    })


def contact_submit(request):
    if request.method != "POST":
        return redirect("portal:homepage")
    name    = request.POST.get("name", "").strip()
    email   = request.POST.get("email", "").strip()
    subject = request.POST.get("subject", "general")
    message = request.POST.get("message", "").strip()
    errors = []
    if not name:   errors.append("Name is required.")
    if not email or "@" not in email: errors.append("A valid email is required.")
    if not message: errors.append("Message cannot be empty.")
    if errors:
        return render(request, "portal/homepage.html", {
            "contact_errors": errors, "contact_name": name,
            "contact_email": email, "contact_subject": subject, "contact_message": message,
        })
    ContactMessage.objects.create(
        name=name, email=email, subject=subject, message=message,
        ip_address=_get_client_ip(request) or None
    )
    _log(request, "contact_msg", f"{name} <{email}>: {subject}")
    from django.urls import reverse as _rev
    return redirect(_rev("portal:homepage") + "?sent=1#contact")


# ─── Auth ─────────────────────────────────────────────────────────────────────

def login_choice(request):
    if request.user.is_authenticated and request.user.is_approved:
        return redirect("portal:dashboard")
    return render(request, "portal/login_choice.html")


def register_choice(request):
    if request.user.is_authenticated:
        return redirect("portal:dashboard")
    return render(request, "portal/register_choice.html")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("portal:dashboard")
    prefill_role = request.GET.get("role", "student")
    initial = {"role": prefill_role} if prefill_role in ("student", "client", "inquiry") else {}
    form = RegistrationForm(
        request.POST if request.method == "POST" else None,
        initial=initial
    )
    if request.method == "POST" and form.is_valid():
        user = form.save()
        _log(request, "login", f"Registered: {user.username} as {user.role}")
        # v8: Tell students what happens next based on whether they picked a course
        if user.role == "student" and user.registration_course:
            messages.success(
                request,
                f"Account created! You selected '{user.registration_course.title}'. "
                "Once approved by admin, you'll go straight to your dashboard."
            )
        else:
            messages.success(request, "Account created! Awaiting admin approval.")
        return redirect("portal:login")
    active_courses = Course.objects.filter(is_active=True).order_by("order", "title")
    return render(request, "portal/register.html", {
        "form": form,
        "prefill_role": prefill_role,
        "active_courses": active_courses,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect("portal:dashboard")
    role_hint    = request.GET.get("role", "")
    error        = None
    show_support = False

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        try:
            db_user = CustomUser.objects.get(username=username)
        except CustomUser.DoesNotExist:
            db_user = None

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_approved:
                error = "Your account is awaiting admin approval."
                user.failed_login_count = 0
                user.save(update_fields=["failed_login_count"])
            else:
                user.failed_login_count = 0
                user.save(update_fields=["failed_login_count"])
                login(request, user)
                _log(request, "login", f"Login: {user.username} ({user.role})")
                # Superusers go to host dashboard
                if user.is_superuser:
                    return redirect("portal:host_index")
                # After login: students who haven't selected courses → redirect there
                if (user.role == "student" and not user.is_superuser
                        and not user.course_selection_done):
                    return redirect("portal:course_select")
                return redirect(request.GET.get("next", "portal:dashboard"))
        else:
            if db_user:
                db_user.failed_login_count += 1
                db_user.save(update_fields=["failed_login_count"])
                if db_user.failed_login_count >= 2:
                    show_support = True
                    error = "Login failed multiple times. Please contact support."
                else:
                    error = "Invalid username or password."
            else:
                error = "Invalid username or password."

    return render(request, "portal/login.html", {
        "error": error, "show_support": show_support,
        "support_email": SUPPORT_EMAIL, "support_phone": SUPPORT_PHONE,
        "role_hint": role_hint,
    })


def logout_view(request):
    if request.user.is_authenticated:
        _log(request, "logout", f"Logout: {request.user.username}")
    logout(request)
    return redirect("portal:homepage")


def pending_view(request):
    return render(request, "portal/pending.html", {
        "support_email": SUPPORT_EMAIL,
        "support_phone": SUPPORT_PHONE,
    })


# ─── Course Selection (Student First-Login Flow) ──────────────────────────────

@_approved_required
def course_select_view(request):
    """
    v8: Students who picked a course at registration have course_selection_done=True
    set automatically — they skip this page and go straight to the dashboard.
    This page is only shown to students who registered BEFORE v8 (no registration_course).
    """
    user = request.user

    # Non-students, superusers, or already-done students skip this page
    if user.role != "student" or user.is_superuser or user.course_selection_done:
        return redirect("portal:dashboard")

    available_courses = Course.objects.filter(is_active=True).order_by("order", "title")

    if not available_courses.exists():
        # WARNING: No courses in DB. Show an informational page instead of a broken form.
        return render(request, "portal/course_select.html", {
            "form": None,
            "no_courses": True,
            "support_email": SUPPORT_EMAIL,
        })

    # Use request.POST directly when method is POST — don't use "or None" pattern
    # because an empty POST dict {} is falsy in Python, making the form unbound.
    # WARNING: Using `CourseSelectionForm(request.POST or None)` would treat an
    # empty POST (no checkboxes checked) as an unbound form and skip validation.
    form = CourseSelectionForm(request.POST if request.method == "POST" else None)

    if request.method == "POST" and form.is_valid():
        selected_courses = form.cleaned_data["courses"]
        # Set many-to-many relationship
        user.enrolled_courses.set(selected_courses)
        user.course_selection_done = True
        user.save(update_fields=["course_selection_done"])
        _log(
            request, "course_select",
            f"Selected: {', '.join(c.title for c in selected_courses)}"
        )
        course_names = ", ".join(c.title for c in selected_courses)
        messages.success(
            request,
            f"Course(s) selected: {course_names}. Welcome to your dashboard!"
        )
        return redirect("portal:dashboard")

    return render(request, "portal/course_select.html", {
        "form": form,
        "no_courses": False,
        "available_courses": available_courses,
        "support_email": SUPPORT_EMAIL,
    })


# ─── Dashboard Router ─────────────────────────────────────────────────────────

@_approved_required
def dashboard_view(request):
    user = request.user
    # Students must complete course selection first
    if (user.role == CustomUser.ROLE_STUDENT and not user.is_superuser
            and not user.course_selection_done):
        return redirect("portal:course_select")
    if user.role == CustomUser.ROLE_STUDENT:
        return _student_dashboard(request)
    elif user.role == CustomUser.ROLE_CLIENT:
        return _client_dashboard(request)
    elif user.role == CustomUser.ROLE_INQUIRY:
        return _inquiry_dashboard(request)
    return redirect("portal:login")


def _student_dashboard(request):
    """
    Student dashboard with course-based content filtering.

    Filtering logic:
      - Content with course assigned to student's enrolled courses → SHOWN
      - Content with course=NULL (legacy, unassigned) → SHOWN (backward compat)
      - Content assigned to other courses → HIDDEN

    Edge cases:
      - Student has no enrolled courses (admin removed all) → shows warning banner
      - All content filtered out → shows "No content for your course" message
    """
    user = request.user
    perf = _recalc_performance(user)

    # v9: prefetch enrolled courses once — reused for all filter operations
    student_courses = _get_student_courses(user)
    has_courses = student_courses.exists()

    course_filter = Q(course__in=student_courses) | Q(course__isnull=True)

    # v9: use values_list with flat=True — single column, no model overhead
    submitted_ids = Submission.objects.filter(student=user).values_list("assignment_id", flat=True)

    total_assignments   = Assignment.objects.filter(is_active=True).filter(course_filter).count()
    pending_assignments = (
        Assignment.objects.filter(is_active=True)
        .filter(course_filter)
        .exclude(id__in=submitted_ids)
        .count()
    )
    total_quizzes     = Quiz.objects.filter(is_active=True).filter(course_filter).count()
    attempted_quizzes = QuizResult.objects.filter(student=user).count()
    # v9: select_related course to avoid extra query when template accesses topic.course
    today_topic   = Topic.objects.filter(is_active=True).select_related("course").first()
    notifications = _notifications_for(user).only("title", "body", "priority")[:5]

    return render(request, "portal/dashboard_student.html", {
        "perf": perf,
        "total_assignments": total_assignments,
        "pending_assignments": pending_assignments,
        "total_quizzes": total_quizzes,
        "attempted_quizzes": attempted_quizzes,
        "today_topic": today_topic,
        "notifications": notifications,
        "student_courses": student_courses,
        "has_courses": has_courses,
    })


def _client_dashboard(request):
    user     = request.user
    projects = ClientProject.objects.filter(client=user).only(
        "title", "status", "progress", "team_size", "deadline", "created_at",
        "description", "tech_stack", "notes", "start_date", "live_url", "demo_video_url",
    )
    total     = projects.count()
    completed = projects.filter(status="completed").count()
    active    = projects.filter(status="in_progress").count()
    notifications = _notifications_for(user).only("title", "body", "priority")[:5]
    return render(request, "portal/dashboard_client.html", {
        "projects": projects, "total_projects": total,
        "completed_projects": completed, "active_projects": active,
        "notifications": notifications,
    })


def _inquiry_dashboard(request):
    user   = request.user
    demos  = DemoSchedule.objects.filter(inquiry_user=user).order_by("scheduled_at")
    upcoming = demos.filter(status="scheduled", scheduled_at__gte=timezone.now()).first()
    video_demos = demos.exclude(video_url="").order_by("-scheduled_at")
    notifications = _notifications_for(user).only("title", "body", "priority")[:5]
    return render(request, "portal/dashboard_inquiry.html", {
        "demos": demos, "upcoming_demo": upcoming,
        "video_demos": video_demos, "notifications": notifications,
        "support_email": SUPPORT_EMAIL, "support_phone": SUPPORT_PHONE,
    })


# ─── Notes ───────────────────────────────────────────────────────────────────

@_student_course_required
def notes_view(request):
    """
    Shows only notes linked to the student's enrolled courses (or unlinked legacy notes).
    WARNING: If student's courses have been deleted, enrolled_courses.filter(is_active=True)
    will return empty, and only unlinked notes will show.
    """
    user    = request.user
    subject = request.GET.get("subject", "")

    # v9: select_related course to avoid N+1 when template accesses note.course
    notes = Note.objects.filter(is_active=True).select_related("course", "uploaded_by")
    notes = _filter_content_for_student(notes, user)

    if subject:
        notes = notes.filter(subject__icontains=subject)

    subjects = Note.objects.filter(is_active=True).values_list("subject", flat=True).distinct()
    student_courses = _get_student_courses(user)
    no_content = not notes.exists()

    return render(request, "portal/notes.html", {
        "notes": notes, "subjects": subjects, "current_subject": subject,
        "student_courses": student_courses, "no_content": no_content,
    })


@_student_course_required
def note_download(request, pk):
    """Download a note file. Validates student has access to this note's course."""
    user = request.user
    student_courses = _get_student_courses(user)
    # Allow download if note belongs to student's course OR has no course (legacy)
    note = get_object_or_404(
        Note,
        pk=pk, is_active=True
    )
    # Access check
    if note.course and note.course not in student_courses:
        # WARNING: This could fail if the student somehow accesses a URL for another course's note.
        # Fix: This check ensures they can't download notes outside their enrolled courses.
        messages.error(request, "You don't have access to this note.")
        return redirect("portal:notes")
    if not note.file:
        raise Http404("No file attached.")
    return FileResponse(note.file.open(), as_attachment=True,
                        filename=os.path.basename(note.file.name))


# ─── Quizzes ─────────────────────────────────────────────────────────────────

@_student_course_required
def quizzes_view(request):
    """Shows only quizzes linked to the student's enrolled courses."""
    user = request.user
    student_courses = _get_student_courses(user)
    course_filter = Q(course__in=student_courses) | Q(course__isnull=True)

    quizzes = Quiz.objects.filter(is_active=True).filter(course_filter).prefetch_related(
        Prefetch("questions", queryset=Question.objects.only("id")),
        Prefetch("results", queryset=QuizResult.objects.filter(student=user)),
    )
    attempted = set(QuizResult.objects.filter(student=user).values_list("quiz_id", flat=True))
    quiz_data = []
    for q in quizzes:
        result = next((r for r in q.results.all()), None)
        quiz_data.append({"quiz": q, "result": result, "attempted": q.id in attempted})

    no_content = not quiz_data

    return render(request, "portal/quizzes.html", {
        "quiz_data": quiz_data,
        "student_courses": student_courses,
        "no_content": no_content,
    })


@_student_course_required
def quiz_attempt(request, pk):
    """Attempt a quiz — validates course access before allowing attempt.
    v10: saves per-question QuizStudentAnswer records, redirects to result page after submission.
    """
    user = request.user
    student_courses = _get_student_courses(user)
    quiz = get_object_or_404(Quiz, pk=pk, is_active=True)

    # Course access check
    if quiz.course and quiz.course not in student_courses:
        messages.error(request, "You don't have access to this quiz.")
        return redirect("portal:quizzes")

    # v10: Lock check — redirect to result if already attempted
    existing_result = QuizResult.objects.filter(student=user, quiz=quiz).first()
    if existing_result:
        return redirect("portal:quiz_result", pk=quiz.pk)

    questions = quiz.questions.all()
    if request.method == "POST":
        score = 0
        total = quiz.total_marks()
        answer_objects = []
        for q in questions:
            selected = request.POST.get(f"q_{q.id}", "").upper().strip()
            correct  = q.correct.upper()
            correct_flag = (selected == correct and selected in ("A", "B", "C", "D"))
            if correct_flag:
                score += q.marks
            answer_objects.append(QuizStudentAnswer(
                student=user,
                quiz=quiz,
                question=q,
                selected_answer=selected,
                correct_answer=correct,
                is_correct=correct_flag,
            ))
        pct = round((score / total * 100), 1) if total else 0
        QuizResult.objects.create(
            student=user, quiz=quiz, score=score, total=total, percentage=pct
        )
        QuizStudentAnswer.objects.bulk_create(answer_objects, ignore_conflicts=True)
        _recalc_performance(user)
        _log(request, "quiz_attempt", f"{quiz.title} — {pct}%")
        messages.success(request, f"Quiz submitted! You scored {score}/{total} ({pct}%).")
        return redirect("portal:quiz_result", pk=quiz.pk)

    return render(request, "portal/quiz_attempt.html", {"quiz": quiz, "questions": questions})


@_student_course_required
def quiz_result(request, pk):
    """v10: Show detailed quiz result after submission."""
    user   = request.user
    quiz   = get_object_or_404(Quiz, pk=pk, is_active=True)
    result = get_object_or_404(QuizResult, student=user, quiz=quiz)
    answers = (
        QuizStudentAnswer.objects
        .filter(student=user, quiz=quiz)
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
            "explanation":    q.explanation,
            "order":          q.order,
        })
    correct_count = sum(1 for a in answer_detail if a["is_correct"])
    wrong_count   = len(answer_detail) - correct_count
    return render(request, "portal/quiz_result.html", {
        "quiz":          quiz,
        "result":        result,
        "answer_detail": answer_detail,
        "correct_count": correct_count,
        "wrong_count":   wrong_count,
    })


# ─── AI Quiz Generator ────────────────────────────────────────────────────────

@_student_course_required
def ai_quiz_generate(request):
    # ── STUDENT GUARD: AI Quiz generation is a HOST-only feature.
    # Students can VIEW and ATTEMPT quizzes via the Quizzes page.
    # The backend logic is preserved; only students are blocked from this endpoint.
    if request.user.role == "student":
        messages.error(request, "AI Quiz generation is only available to hosts.")
        return redirect("portal:quizzes")
    form  = AIQuizGenerateForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        topic    = form.cleaned_data["topic"]
        subject  = form.cleaned_data.get("subject", "")
        n        = int(form.cleaned_data["num_questions"])
        duration = form.cleaned_data["duration"]
        result = ai_service.generate_quiz_questions(topic, subject, n)
        if result["success"] and result["questions"]:
            quiz = Quiz.objects.create(
                title=f"AI Quiz: {topic[:80]}",
                description=f"AI-generated quiz on: {topic}",
                subject=subject or "General",
                duration=duration, is_active=True, is_ai_generated=True,
            )
            for q_data in result["questions"]:
                Question.objects.create(
                    quiz=quiz, text=q_data["text"],
                    option_a=q_data["option_a"], option_b=q_data["option_b"],
                    option_c=q_data["option_c"], option_d=q_data["option_d"],
                    correct=q_data["correct"], marks=1, order=q_data["order"],
                )
            _log(request, "ai_quiz_gen", f"Topic: {topic}, {len(result['questions'])} Qs")
            messages.success(request, f"AI quiz generated with {len(result['questions'])} questions!")
            return redirect("portal:quiz_attempt", pk=quiz.pk)
        else:
            error = result.get("error", "AI generation failed.")
    return render(request, "portal/ai_quiz_generate.html", {"form": form, "error": error})


# ─── AI Chatbot ───────────────────────────────────────────────────────────────

@_approved_required
def chatbot_view(request):
    recent_messages = (
        ChatMessage.objects.filter(student=request.user)
        .only("role", "content", "timestamp", "topic")
        .order_by("-timestamp")[:40]
    )
    recent_messages = list(reversed(recent_messages))
    topics = Topic.objects.filter(is_active=True).values_list("title", flat=True)
    return render(request, "portal/chatbot.html", {
        "messages": recent_messages, "topics": topics,
    })


@require_POST
@_approved_required
def chatbot_send(request):
    try:
        body    = json.loads(request.body)
        message = body.get("message", "").strip()
        topic   = body.get("topic", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid request"}, status=400)
    if not message:
        return JsonResponse({"error": "Empty message"}, status=400)
    ChatMessage.objects.create(student=request.user, role="user", content=message, topic=topic)
    _log(request, "chat_message", f"Topic: {topic or 'general'}")
    history = list(
        ChatMessage.objects.filter(student=request.user)
        .order_by("-timestamp")[:20]
        .values("role", "content")
    )
    history = [{"role": m["role"], "content": m["content"]} for m in reversed(history)]
    result = ai_service.chat_with_student(message, history, topic)
    if result["success"]:
        ChatMessage.objects.create(student=request.user, role="assistant", content=result["reply"], topic=topic)
        return JsonResponse({"reply": result["reply"]})
    return JsonResponse({"reply": result["error"]})


# ─── Assignments ─────────────────────────────────────────────────────────────

@_student_course_required
def assignments_view(request):
    """Shows only assignments linked to the student's enrolled courses."""
    user = request.user
    student_courses = _get_student_courses(user)
    course_filter = Q(course__in=student_courses) | Q(course__isnull=True)

    assignments = (
        Assignment.objects.filter(is_active=True)
        .filter(course_filter)
        # v9: select_related course to avoid N+1 in template
        .select_related("course")
    )
    submission_map = {
        s.assignment_id: s
        for s in Submission.objects.filter(student=user).select_related("assignment")
    }
    data = [
        {"assignment": a, "submission": submission_map.get(a.id), "past_due": a.is_past_due()}
        for a in assignments
    ]
    no_content = not data

    return render(request, "portal/assignments.html", {
        "data": data,
        "student_courses": student_courses,
        "no_content": no_content,
    })


@_student_course_required
def assignment_submit(request, pk):
    """Submit assignment — validates course access."""
    user = request.user
    student_courses = _get_student_courses(user)
    assignment = get_object_or_404(Assignment, pk=pk, is_active=True)

    # Course access check
    if assignment.course and assignment.course not in student_courses:
        # WARNING: Student trying to submit for an assignment outside their courses.
        messages.error(request, "You don't have access to this assignment.")
        return redirect("portal:assignments")

    if Submission.objects.filter(student=user, assignment=assignment).exists():
        messages.info(request, "Already submitted.")
        return redirect("portal:assignments")

    form = SubmissionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        sub = form.save(commit=False)
        sub.student = user
        sub.assignment = assignment
        sub.save()
        _recalc_performance(user)
        _log(request, "assignment_sub", assignment.title)
        messages.success(request, "Assignment submitted!")
        return redirect("portal:assignments")

    return render(request, "portal/assignment_submit.html", {
        "assignment": assignment, "form": form,
    })


# ─── Performance ─────────────────────────────────────────────────────────────

@_student_course_required
def performance_view(request):
    perf = _recalc_performance(request.user)
    quiz_results = (
        QuizResult.objects.filter(student=request.user)
        .select_related("quiz")
        .only("score", "total", "percentage", "taken_at",
              "quiz__title", "quiz__subject", "quiz__is_ai_generated")
    )
    submissions = (
        Submission.objects.filter(student=request.user, marks__isnull=False)
        .select_related("assignment")
        .only("marks", "status", "feedback", "submitted_at",
              "assignment__title", "assignment__subject", "assignment__max_marks")
    )
    completed = (
        TopicCompletion.objects.filter(student=request.user)
        .select_related("topic")
        .only("completed_at", "topic__title", "topic__subject")
    )
    return render(request, "portal/performance.html", {
        "perf": perf, "quiz_results": quiz_results,
        "submissions": submissions, "completed": completed,
    })


# ─── Learning ────────────────────────────────────────────────────────────────

@_student_course_required
def learning_view(request):
    # v9: filter topics to student's enrolled courses + select_related to avoid N+1
    user = request.user
    student_courses = _get_student_courses(user)
    course_filter = Q(course__in=student_courses) | Q(course__isnull=True)
    topics = (
        Topic.objects.filter(is_active=True)
        .filter(course_filter)
        .select_related("course")
    )
    completed_ids = set(
        TopicCompletion.objects.filter(student=user).values_list("topic_id", flat=True)
    )
    data = [{"topic": t, "done": t.id in completed_ids} for t in topics]
    return render(request, "portal/learning.html", {
        "data": data, "today_topic": topics.first(), "completed_ids": completed_ids,
    })


@require_POST
@_student_course_required
def mark_topic_done(request, pk):
    topic = get_object_or_404(Topic, pk=pk, is_active=True)
    _, created = TopicCompletion.objects.get_or_create(student=request.user, topic=topic)
    _recalc_performance(request.user)
    if created:
        _log(request, "topic_done", topic.title)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"status": "ok", "created": created})
    messages.success(request, f'"{topic.title}" marked as completed.')
    return redirect("portal:learning")


# ─── Notifications ───────────────────────────────────────────────────────────

@_approved_required
def notifications_view(request):
    notes = _notifications_for(request.user)
    return render(request, "portal/notifications.html", {"notifications": notes})


# ─── Profile ─────────────────────────────────────────────────────────────────

@_approved_required
def profile_view(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("portal:profile")
    return render(request, "portal/profile.html", {"form": form})


# ─── Client ──────────────────────────────────────────────────────────────────

@_role_required("client")
def client_projects_view(request):
    projects = ClientProject.objects.filter(client=request.user)
    return render(request, "portal/client_projects.html", {"projects": projects})


# ─── Inquiry ─────────────────────────────────────────────────────────────────

@_role_required("inquiry")
def inquiry_demos_view(request):
    demos = DemoSchedule.objects.filter(inquiry_user=request.user)
    return render(request, "portal/inquiry_demos.html", {
        "demos": demos,
        "support_email": SUPPORT_EMAIL, "support_phone": SUPPORT_PHONE,
    })


# ─── Global Ask Question System ───────────────────────────────────────────────

@_approved_required
def ask_question_view(request):
    user = request.user
    queries = UserQuery.objects.filter(user=user).order_by("-created_at")
    if request.method == "POST":
        subject  = request.POST.get("subject", "").strip()
        question = request.POST.get("question", "").strip()
        if not subject or not question:
            messages.error(request, "Both subject and question are required.")
        else:
            UserQuery.objects.create(user=user, subject=subject, question=question)
            messages.success(request, "Your question has been submitted! The host will reply shortly.")
            return redirect("portal:ask_question")
    return render(request, "portal/ask_question.html", {"queries": queries})


# ─── Host Dashboard ───────────────────────────────────────────────────────────

@_approved_required
def host_dashboard_view(request):
    if not request.user.is_superuser:
        messages.error(request, "Access restricted to hosts/teachers.")
        return redirect("portal:dashboard")
    ai_quizzes       = Quiz.objects.filter(is_ai_generated=True).order_by("-created_at")[:10]
    ai_quiz_count    = Quiz.objects.filter(is_ai_generated=True).count()
    chat_logs        = ChatMessage.objects.select_related("student").order_by("-timestamp")[:20]
    chat_count       = ChatMessage.objects.count()
    open_queries     = UserQuery.objects.filter(status="open").select_related("user").order_by("-created_at")
    answered_queries = UserQuery.objects.filter(status="answered").select_related("user", "answered_by").order_by("-updated_at")[:10]
    return render(request, "portal/host_dashboard.html", {
        "ai_quizzes": ai_quizzes, "ai_quiz_count": ai_quiz_count,
        "chat_logs": chat_logs, "chat_count": chat_count,
        "open_queries": open_queries, "answered_queries": answered_queries,
    })


@require_POST
def host_answer_query(request, pk):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return redirect("portal:su_login")
    query  = get_object_or_404(UserQuery, pk=pk)
    answer = request.POST.get("answer", "").strip()
    if answer:
        query.answer      = answer
        query.answered_by = request.user
        query.status      = "answered"
        query.save()
        messages.success(request, f"Reply sent to {query.user.username}.")
    else:
        messages.error(request, "Answer cannot be empty.")
    return redirect("portal:host_dashboard")

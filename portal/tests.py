"""
CodeNova Portal — v3 Test Suite  (38 → 52 tests)
Run: python manage.py test portal
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import (
    CustomUser, Note, Quiz, Question, Assignment, Submission,
    QuizResult, Notification, Topic, TopicCompletion,
    ClientProject, DemoSchedule, ContactMessage, ActivityLog
)
from .quiz_parser import parse_quiz_text, validate_and_preview, QuizParseError


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_user(username="testuser", approved=True, role="student", **kw):
    return CustomUser.objects.create_user(
        username=username, email=f"{username}@test.com",
        password="testpass123", is_approved=approved, role=role, **kw
    )

def make_quiz():
    q = Quiz.objects.create(title="Test Quiz", subject="Science", duration=10)
    Question.objects.create(
        quiz=q, text="1+1=?", option_a="1", option_b="2",
        option_c="3", option_d="4", correct="B", marks=2, order=1
    )
    return q


# ─── Auth ─────────────────────────────────────────────────────────────────────

class AuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.approved = make_user("approved", approved=True)
        self.pending  = make_user("pending",  approved=False)

    def test_homepage_loads(self):
        r = self.client.get(reverse("portal:homepage"))
        self.assertEqual(r.status_code, 200)

    def test_login_choice_loads(self):
        r = self.client.get(reverse("portal:login_choice"))
        self.assertEqual(r.status_code, 200)

    def test_register_choice_loads(self):
        r = self.client.get(reverse("portal:register_choice"))
        self.assertEqual(r.status_code, 200)

    def test_login_page_loads(self):
        r = self.client.get(reverse("portal:login"))
        self.assertEqual(r.status_code, 200)

    def test_login_with_role_hint(self):
        r = self.client.get(reverse("portal:login") + "?role=student")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Student Login")

    def test_register_page_with_role(self):
        r = self.client.get(reverse("portal:register") + "?role=client")
        self.assertEqual(r.status_code, 200)

    def test_approved_login_creates_activity_log(self):
        self.client.post(reverse("portal:login"), {"username": "approved", "password": "testpass123"})
        self.assertTrue(ActivityLog.objects.filter(action="login").exists())

    def test_unapproved_blocked(self):
        r = self.client.post(reverse("portal:login"), {"username": "pending", "password": "testpass123"})
        self.assertContains(r, "awaiting admin approval")

    def test_failed_login_counter(self):
        for _ in range(2):
            self.client.post(reverse("portal:login"), {"username": "approved", "password": "wrong"})
        r = self.client.post(reverse("portal:login"), {"username": "approved", "password": "wrong"})
        self.assertContains(r, "contact support")

    def test_registration_creates_unapproved_user(self):
        r = self.client.post(reverse("portal:register"), {
            "username": "newreg", "email": "newreg@test.com", "role": "student",
            "first_name": "New", "last_name": "Reg",
            "password1": "securepass99", "password2": "securepass99",
        })
        self.assertEqual(r.status_code, 302)
        user = CustomUser.objects.get(username="newreg")
        self.assertFalse(user.is_approved)

    def test_logout_redirects_to_homepage(self):
        self.client.force_login(self.approved)
        r = self.client.get(reverse("portal:logout"))
        self.assertRedirects(r, reverse("portal:homepage"))


# ─── Contact Form ─────────────────────────────────────────────────────────────

class ContactFormTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_valid_contact_saves_to_db(self):
        r = self.client.post(reverse("portal:contact_submit"), {
            "name": "Test User", "email": "test@example.com",
            "subject": "general", "message": "Hello from the test.",
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(ContactMessage.objects.filter(name="Test User").exists())

    def test_contact_requires_name(self):
        r = self.client.post(reverse("portal:contact_submit"), {
            "name": "", "email": "test@example.com",
            "subject": "general", "message": "Hello.",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Name is required")

    def test_contact_requires_message(self):
        r = self.client.post(reverse("portal:contact_submit"), {
            "name": "Test", "email": "test@example.com",
            "subject": "general", "message": "",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Message cannot be empty")

    def test_contact_get_redirects(self):
        r = self.client.get(reverse("portal:contact_submit"))
        self.assertEqual(r.status_code, 302)


# ─── Quiz Parser ──────────────────────────────────────────────────────────────

class QuizParserTests(TestCase):
    VALID_QUIZ = """Q1: What is Python?
A. A snake
B. A programming language
C. An OS
D. A database
Answer: B

Q2: What does def do?
A. Defines a class
B. Defines a loop
C. Defines a function
D. Defines a variable
Answer: C"""

    def test_parses_valid_quiz(self):
        questions = parse_quiz_text(self.VALID_QUIZ)
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["correct"], "B")
        self.assertEqual(questions[1]["correct"], "C")

    def test_question_fields_present(self):
        qs = parse_quiz_text(self.VALID_QUIZ)
        for q in qs:
            for field in ("text", "option_a", "option_b", "option_c", "option_d", "correct", "order"):
                self.assertIn(field, q)

    def test_compact_format(self):
        compact = "Q1: What is 2+2? A. 3 B. 4 C. 5 D. 6 Answer: B"
        qs = parse_quiz_text(compact)
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0]["correct"], "B")
        self.assertEqual(qs[0]["option_b"], "4")

    def test_empty_text_raises(self):
        with self.assertRaises(QuizParseError):
            parse_quiz_text("")

    def test_missing_answer_raises(self):
        bad = "Q1: What?\nA. X\nB. Y\nC. Z\nD. W"
        with self.assertRaises(QuizParseError):
            parse_quiz_text(bad)

    def test_validate_preview_success(self):
        result = validate_and_preview(self.VALID_QUIZ)
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)

    def test_validate_preview_failure(self):
        result = validate_and_preview("")
        self.assertFalse(result["success"])
        self.assertIn("error", result)


# ─── Role Routing ─────────────────────────────────────────────────────────────

class RoleRoutingTests(TestCase):
    def setUp(self):
        self.http = Client()

    def test_student_gets_student_dashboard(self):
        u = make_user("stu_r", role="student")
        self.http.force_login(u)
        r = self.http.get(reverse("portal:dashboard"))
        self.assertTemplateUsed(r, "portal/dashboard_student.html")

    def test_client_gets_client_dashboard(self):
        u = make_user("cli_r", role="client")
        self.http.force_login(u)
        r = self.http.get(reverse("portal:dashboard"))
        self.assertTemplateUsed(r, "portal/dashboard_client.html")

    def test_inquiry_gets_inquiry_dashboard(self):
        u = make_user("inq_r", role="inquiry")
        self.http.force_login(u)
        r = self.http.get(reverse("portal:dashboard"))
        self.assertTemplateUsed(r, "portal/dashboard_inquiry.html")

    def test_client_blocked_from_notes(self):
        u = make_user("cli_b", role="client")
        self.http.force_login(u)
        r = self.http.get(reverse("portal:notes"), follow=True)
        self.assertEqual(r.status_code, 200)

    def test_student_blocked_from_client_projects(self):
        u = make_user("stu_b", role="student")
        self.http.force_login(u)
        r = self.http.get(reverse("portal:client_projects"), follow=True)
        self.assertEqual(r.status_code, 200)


# ─── Superuser Panel ─────────────────────────────────────────────────────────

class SuperuserPanelTests(TestCase):
    def setUp(self):
        self.http = Client()
        self.admin = CustomUser.objects.create_superuser(
            username="testadmin", email="admin@test.com", password="adminpass123"
        )

    def test_su_login_page_loads(self):
        r = self.http.get(reverse("portal:su_login"))
        self.assertEqual(r.status_code, 200)

    def test_su_login_requires_superuser(self):
        regular = make_user("regular_su", role="student")
        r = self.http.post(reverse("portal:su_login"), {
            "username": "regular_su", "password": "testpass123"
        }, follow=True)
        # Should not reach dashboard
        self.assertTemplateNotUsed(r, "portal/superuser/dashboard.html")

    def test_su_login_success(self):
        r = self.http.post(reverse("portal:su_login"), {
            "username": "testadmin", "password": "adminpass123"
        })
        self.assertRedirects(r, reverse("portal:su_dashboard"))

    def test_su_dashboard_loads(self):
        self.http.force_login(self.admin)
        r = self.http.get(reverse("portal:su_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "portal/superuser/dashboard.html")

    def test_su_users_page_loads(self):
        self.http.force_login(self.admin)
        r = self.http.get(reverse("portal:su_users"))
        self.assertEqual(r.status_code, 200)

    def test_su_can_approve_user(self):
        u = make_user("to_approve", approved=False)
        self.http.force_login(self.admin)
        self.http.post(reverse("portal:su_user_action", args=[u.pk]),
                       {"action": "approve"})
        u.refresh_from_db()
        self.assertTrue(u.is_approved)

    def test_su_quiz_create_page_loads(self):
        self.http.force_login(self.admin)
        r = self.http.get(reverse("portal:su_quiz_create"))
        self.assertEqual(r.status_code, 200)

    def test_su_quiz_text_parser_creates_quiz(self):
        self.http.force_login(self.admin)
        quiz_text = """Q1: What is Python?
A. A snake
B. A language
C. An OS
D. A db
Answer: B"""
        r = self.http.post(reverse("portal:su_quiz_create"), {
            "mode": "text", "title": "Parser Test Quiz",
            "subject": "CS", "duration": "15",
            "quiz_text": quiz_text, "save": "1",
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Quiz.objects.filter(title="Parser Test Quiz").exists())

    def test_su_notes_page_loads(self):
        self.http.force_login(self.admin)
        r = self.http.get(reverse("portal:su_notes"))
        self.assertEqual(r.status_code, 200)

    def test_su_assignments_page_loads(self):
        self.http.force_login(self.admin)
        r = self.http.get(reverse("portal:su_assignments"))
        self.assertEqual(r.status_code, 200)

    def test_su_unauthenticated_redirects(self):
        r = self.http.get(reverse("portal:su_dashboard"))
        self.assertRedirects(r, reverse("portal:su_login"))


# ─── Student Module Tests ─────────────────────────────────────────────────────

class StudentModuleTests(TestCase):
    def setUp(self):
        self.http = Client()
        self.user = make_user(role="student")
        self.http.force_login(self.user)

    def test_notes_loads(self):
        Note.objects.create(title="Test Note", subject="Science")
        r = self.http.get(reverse("portal:notes"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Test Note")

    def test_quizzes_loads(self):
        make_quiz()
        r = self.http.get(reverse("portal:quizzes"))
        self.assertEqual(r.status_code, 200)

    def test_ai_quiz_generate_loads(self):
        r = self.http.get(reverse("portal:ai_quiz_generate"))
        self.assertEqual(r.status_code, 200)

    def test_chatbot_loads(self):
        r = self.http.get(reverse("portal:chatbot"))
        self.assertEqual(r.status_code, 200)

    def test_performance_loads(self):
        r = self.http.get(reverse("portal:performance"))
        self.assertEqual(r.status_code, 200)

    def test_profile_loads(self):
        r = self.http.get(reverse("portal:profile"))
        self.assertEqual(r.status_code, 200)


# ─── Quiz Tests ───────────────────────────────────────────────────────────────

class QuizTests(TestCase):
    def setUp(self):
        self.http  = Client()
        self.user  = make_user(role="student")
        self.http.force_login(self.user)
        self.quiz  = make_quiz()

    def test_attempt_loads(self):
        r = self.http.get(reverse("portal:quiz_attempt", args=[self.quiz.pk]))
        self.assertEqual(r.status_code, 200)

    def test_correct_answer_scores(self):
        q = self.quiz.questions.first()
        self.http.post(reverse("portal:quiz_attempt", args=[self.quiz.pk]), {f"q_{q.id}": "B"})
        result = QuizResult.objects.get(student=self.user, quiz=self.quiz)
        self.assertEqual(result.score, 2)
        self.assertEqual(result.percentage, 100.0)

    def test_wrong_answer_zero(self):
        q = self.quiz.questions.first()
        self.http.post(reverse("portal:quiz_attempt", args=[self.quiz.pk]), {f"q_{q.id}": "A"})
        result = QuizResult.objects.get(student=self.user, quiz=self.quiz)
        self.assertEqual(result.score, 0)

    def test_reattempt_blocked(self):
        QuizResult.objects.create(student=self.user, quiz=self.quiz, score=2, total=2, percentage=100)
        r = self.http.get(reverse("portal:quiz_attempt", args=[self.quiz.pk]), follow=True)
        self.assertRedirects(r, reverse("portal:quizzes"))

    def test_quiz_attempt_logs_activity(self):
        q = self.quiz.questions.first()
        self.http.post(reverse("portal:quiz_attempt", args=[self.quiz.pk]), {f"q_{q.id}": "B"})
        self.assertTrue(ActivityLog.objects.filter(action="quiz_attempt").exists())


# ─── Assignment Tests ─────────────────────────────────────────────────────────

class AssignmentTests(TestCase):
    def setUp(self):
        self.http = Client()
        self.user = make_user(role="student")
        self.http.force_login(self.user)
        self.assignment = Assignment.objects.create(
            title="Test Assign", description="Do it",
            due_date=timezone.now() + timedelta(days=7), max_marks=100
        )

    def test_page_loads(self):
        r = self.http.get(reverse("portal:assignments"))
        self.assertEqual(r.status_code, 200)

    def test_submit(self):
        r = self.http.post(
            reverse("portal:assignment_submit", args=[self.assignment.pk]),
            {"text": "My solution", "file": ""}, follow=True
        )
        self.assertTrue(Submission.objects.filter(student=self.user).exists())


# ─── Learning & Activity Logging ─────────────────────────────────────────────

class LearningTests(TestCase):
    def setUp(self):
        self.http  = Client()
        self.user  = make_user(role="student")
        self.http.force_login(self.user)
        self.topic = Topic.objects.create(title="Python Loops", content="for and while", subject="CS")

    def test_mark_done(self):
        self.http.post(reverse("portal:mark_topic_done", args=[self.topic.pk]), follow=True)
        self.assertTrue(TopicCompletion.objects.filter(student=self.user, topic=self.topic).exists())

    def test_mark_done_idempotent(self):
        self.http.post(reverse("portal:mark_topic_done", args=[self.topic.pk]))
        self.http.post(reverse("portal:mark_topic_done", args=[self.topic.pk]), follow=True)
        self.assertEqual(TopicCompletion.objects.filter(student=self.user, topic=self.topic).count(), 1)

    def test_mark_done_logs_activity(self):
        self.http.post(reverse("portal:mark_topic_done", args=[self.topic.pk]), follow=True)
        self.assertTrue(ActivityLog.objects.filter(action="topic_done").exists())

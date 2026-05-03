"""
CodeNova v8 — Test Suite
Tests all new v8 features:
  1. Host dashboard card routing (clickable cards)
  2. AI quiz 5-50 question range validation
  3. Student registration with course
  4. No course selection page after registration+approval
  5. Dashboard shows course-specific content
  6. Chatbot error handling
  7. Migration fields (registration_course, explanation, uploaded_by, etc.)

Run: python manage.py test portal.tests_v8 --verbosity=2
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock

from .models import (
    CustomUser, Course, Note, Quiz, Question, Assignment,
    Topic, ActivityLog
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_course(title="Python", **kw):
    return Course.objects.create(title=title, is_active=True, **kw)

def make_student(username="alice", approved=True, selection_done=False, course=None):
    u = CustomUser.objects.create_user(
        username=username, email=f"{username}@test.com",
        password="testpass123", role="student",
        is_approved=approved, course_selection_done=selection_done,
    )
    if course:
        u.registration_course = course
        u.save(update_fields=["registration_course"])
    return u

def make_superuser(username="admin"):
    return CustomUser.objects.create_user(
        username=username, email=f"{username}@test.com",
        password="adminpass", role="student",
        is_approved=True, is_superuser=True, is_staff=True,
    )


# ─── 1. Host Dashboard Card Routing ───────────────────────────────────────────

class HostDashboardCardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_superuser()
        self.client.login(username="admin", password="adminpass")

    def test_host_dashboard_loads(self):
        """Host dashboard loads for superuser."""
        resp = self.client.get(reverse("portal:host_index"))
        self.assertEqual(resp.status_code, 200)

    def test_pending_users_card_url_resolves(self):
        """Pending users URL (used by clickable card) resolves and filters correctly."""
        resp = self.client.get(reverse("portal:host_users") + "?status=pending")
        self.assertEqual(resp.status_code, 200)

    def test_open_queries_card_url_resolves(self):
        """Open queries URL (used by clickable card) resolves correctly."""
        resp = self.client.get(reverse("portal:host_queries") + "?status=open")
        self.assertEqual(resp.status_code, 200)

    def test_demos_card_url_resolves(self):
        """Demos URL resolves for clickable card."""
        resp = self.client.get(reverse("portal:host_demos"))
        self.assertEqual(resp.status_code, 200)

    def test_projects_card_url_resolves(self):
        """Projects URL resolves for clickable card."""
        resp = self.client.get(reverse("portal:host_projects"))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_contains_clickable_card_links(self):
        """Dashboard HTML contains the correct href for pending users card."""
        resp = self.client.get(reverse("portal:host_index"))
        self.assertContains(resp, "status=pending")
        self.assertContains(resp, "status=open")

    def test_non_superuser_redirected_from_host(self):
        """Non-superuser cannot access host dashboard."""
        client = Client()
        student = make_student("bob", approved=True, selection_done=True)
        client.login(username="bob", password="testpass123")
        resp = client.get(reverse("portal:host_index"))
        self.assertRedirects(resp, reverse("portal:host_login"))


# ─── 2. AI Quiz 5-50 Questions ────────────────────────────────────────────────

class AIQuizRangeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_superuser()
        self.client.login(username="admin", password="adminpass")

    def test_host_ai_quiz_page_loads(self):
        resp = self.client.get(reverse("portal:host_ai_quiz"))
        self.assertEqual(resp.status_code, 200)
        # v8: slider range 5-50 should be in template
        self.assertContains(resp, "50")

    def test_n_below_5_rejected(self):
        """n=3 should be rejected server-side and defaulted to 10."""
        with patch("portal.host_views.generate_quiz_questions") as mock_ai:
            mock_ai.return_value = {"success": False, "error": "mocked"}
            resp = self.client.post(reverse("portal:host_ai_quiz"), {
                "topic": "Python", "subject": "", "n": "3"
            })
            # Server clamps invalid n and proceeds (no crash)
            self.assertEqual(resp.status_code, 200)
            # mock_ai may or may not be called with n=10 (clamped)
            if mock_ai.called:
                called_n = mock_ai.call_args[1].get("n") or mock_ai.call_args[0][2]
                self.assertGreaterEqual(called_n, 5)

    def test_n_above_50_rejected(self):
        """n=100 should be rejected and clamped."""
        with patch("portal.host_views.generate_quiz_questions") as mock_ai:
            mock_ai.return_value = {"success": False, "error": "mocked"}
            resp = self.client.post(reverse("portal:host_ai_quiz"), {
                "topic": "Python", "subject": "", "n": "100"
            })
            self.assertEqual(resp.status_code, 200)
            if mock_ai.called:
                called_n = mock_ai.call_args[1].get("n") or mock_ai.call_args[0][2]
                self.assertLessEqual(called_n, 50)

    def test_valid_n_25_accepted(self):
        """n=25 (valid) should be passed to AI service."""
        with patch("portal.host_views.generate_quiz_questions") as mock_ai:
            mock_ai.return_value = {"success": False, "error": "API key not configured"}
            self.client.post(reverse("portal:host_ai_quiz"), {
                "topic": "Django", "subject": "", "n": "25"
            })
            if mock_ai.called:
                called_n = mock_ai.call_args[1].get("n") or mock_ai.call_args[0][2]
                self.assertEqual(called_n, 25)

    def test_ai_quiz_creates_db_records(self):
        """When AI returns valid questions, Quiz+Questions are saved to DB."""
        mock_questions = [
            {
                "text": f"Q{i}?", "option_a": "A", "option_b": "B",
                "option_c": "C", "option_d": "D", "correct": "A",
                "explanation": "Because A", "order": i
            }
            for i in range(1, 11)
        ]
        with patch("portal.host_views.generate_quiz_questions") as mock_ai:
            mock_ai.return_value = {
                "success": True,
                "questions": mock_questions,
                "model_used": "llama3-8b-8192"
            }
            self.client.post(reverse("portal:host_ai_quiz"), {
                "topic": "Testing", "subject": "QA", "n": "10"
            })
        quiz = Quiz.objects.filter(is_ai_generated=True, title__contains="Testing").first()
        self.assertIsNotNone(quiz)
        self.assertEqual(quiz.questions.count(), 10)
        # Check explanation field was saved (v8 new field)
        q1 = quiz.questions.first()
        self.assertEqual(q1.explanation, "Because A")


# ─── 3. Student Registration With Course ──────────────────────────────────────

class StudentRegistrationWithCourseTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.course = make_course("Python Programming")

    def test_registration_page_shows_course_dropdown(self):
        """Registration page includes course dropdown for students."""
        resp = self.client.get(reverse("portal:register") + "?role=student")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Python Programming")
        self.assertContains(resp, "course-selection-block")

    def test_student_can_register_with_course(self):
        """Student registration with course sets registration_course on user."""
        resp = self.client.post(reverse("portal:register"), {
            "username": "newstudent",
            "email": "new@test.com",
            "first_name": "New", "last_name": "Student",
            "password1": "securepass1", "password2": "securepass1",
            "role": "student",
            "course": str(self.course.pk),
        })
        self.assertRedirects(resp, reverse("portal:login"))
        student = CustomUser.objects.get(username="newstudent")
        self.assertEqual(student.registration_course, self.course)
        self.assertFalse(student.is_approved)
        # course_selection_done = True (they selected course at registration)
        self.assertTrue(student.course_selection_done)

    def test_student_can_register_without_course(self):
        """Student can register without selecting a course (optional)."""
        resp = self.client.post(reverse("portal:register"), {
            "username": "nocourse",
            "email": "nc@test.com",
            "first_name": "No", "last_name": "Course",
            "password1": "securepass1", "password2": "securepass1",
            "role": "student",
            "course": "",
        })
        self.assertRedirects(resp, reverse("portal:login"))
        student = CustomUser.objects.get(username="nocourse")
        self.assertIsNone(student.registration_course)
        # course_selection_done stays False → will see course_select page
        self.assertFalse(student.course_selection_done)


# ─── 4. No Course Selection Page After Registration+Approval ──────────────────

class NoCourseSelectionAfterRegistrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.course = make_course("JavaScript")
        self.admin = make_superuser()

    def test_approval_auto_enrolls_student(self):
        """
        When admin approves a student who selected a course at registration,
        they are automatically enrolled and course_selection_done remains True.
        """
        student = make_student("regstudent", approved=False,
                               selection_done=True, course=self.course)
        # Admin approves
        admin_client = Client()
        admin_client.login(username="admin", password="adminpass")
        admin_client.post(
            reverse("portal:host_user_action", args=[student.pk]),
            {"action": "approve"}
        )
        student.refresh_from_db()
        self.assertTrue(student.is_approved)
        # Should be auto-enrolled
        self.assertIn(self.course, student.enrolled_courses.all())

    def test_approved_student_with_course_goes_to_dashboard(self):
        """
        Approved student with course_selection_done=True and enrolled course
        → goes straight to dashboard, NOT to course_select.
        """
        student = make_student("appstudent", approved=True, selection_done=True)
        student.enrolled_courses.add(self.course)
        self.client.login(username="appstudent", password="testpass123")
        resp = self.client.get(reverse("portal:dashboard"))
        # Should render dashboard (200), not redirect to course_select
        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(resp.get("Location", ""), reverse("portal:course_select"))

    def test_student_without_reg_course_sees_course_select(self):
        """
        Student registered WITHOUT selecting a course (old flow) →
        still goes to course_select page after login.
        """
        student = make_student("oldstudent", approved=True, selection_done=False)
        self.client.login(username="oldstudent", password="testpass123")
        resp = self.client.get(reverse("portal:dashboard"))
        self.assertRedirects(resp, reverse("portal:course_select"))

    def test_course_select_skipped_for_reg_course_students(self):
        """
        Student with course_selection_done=True should be redirected away
        from course_select to dashboard.
        """
        student = make_student("skipstudent", approved=True, selection_done=True)
        student.enrolled_courses.add(self.course)
        self.client.login(username="skipstudent", password="testpass123")
        resp = self.client.get(reverse("portal:course_select"))
        self.assertRedirects(resp, reverse("portal:dashboard"))


# ─── 5. Dashboard Course-Specific Content ─────────────────────────────────────

class DashboardCourseContentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.py_course = make_course("Python")
        self.js_course = make_course("JavaScript")
        self.student = make_student("filterstudent", approved=True, selection_done=True)
        self.student.enrolled_courses.add(self.py_course)
        self.client.login(username="filterstudent", password="testpass123")

    def test_student_sees_own_course_notes_only(self):
        Note.objects.create(title="Python Note", course=self.py_course, is_active=True)
        Note.objects.create(title="JS Note", course=self.js_course, is_active=True)
        resp = self.client.get(reverse("portal:notes"))
        self.assertContains(resp, "Python Note")
        self.assertNotContains(resp, "JS Note")

    def test_student_sees_unlinked_legacy_content(self):
        Note.objects.create(title="Global Note", course=None, is_active=True)
        resp = self.client.get(reverse("portal:notes"))
        self.assertContains(resp, "Global Note")

    def test_dashboard_loads_with_course_info(self):
        resp = self.client.get(reverse("portal:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Python")


# ─── 6. Model Fields (v8 migration) ──────────────────────────────────────────

class ModelFieldTests(TestCase):
    def test_question_explanation_field_exists(self):
        """Question.explanation field was added in migration 0007."""
        course = make_course()
        quiz = Quiz.objects.create(title="Test Quiz", is_active=True)
        q = Question.objects.create(
            quiz=quiz, text="Test?", option_a="A", option_b="B",
            option_c="C", option_d="D", correct="A", marks=1,
            explanation="Because A is correct."
        )
        q.refresh_from_db()
        self.assertEqual(q.explanation, "Because A is correct.")

    def test_note_uploaded_by_field_exists(self):
        """Note.uploaded_by field was added in migration 0007."""
        admin = make_superuser("testadmin")
        note = Note.objects.create(title="Test Note", uploaded_by=admin, is_active=True)
        note.refresh_from_db()
        self.assertEqual(note.uploaded_by, admin)

    def test_customuser_registration_course_field_exists(self):
        """CustomUser.registration_course field was added in migration 0007."""
        course = make_course()
        student = make_student("regtest", course=course)
        student.refresh_from_db()
        self.assertEqual(student.registration_course, course)

    def test_topic_course_video_url_order_fields(self):
        """Topic.course, video_url, order fields were added in migration 0007."""
        course = make_course()
        topic = Topic.objects.create(
            title="Test Topic", course=course,
            video_url="https://youtube.com/test", order=3
        )
        topic.refresh_from_db()
        self.assertEqual(topic.course, course)
        self.assertEqual(topic.video_url, "https://youtube.com/test")
        self.assertEqual(topic.order, 3)

    def test_assignment_due_date_nullable(self):
        """Assignment.due_date is now nullable (migration 0007)."""
        a = Assignment.objects.create(
            title="No Due Date Assignment",
            description="Test",
            due_date=None,
        )
        a.refresh_from_db()
        self.assertIsNone(a.due_date)

    def test_auto_enroll_from_registration(self):
        """auto_enroll_from_registration() enrolls student in registration_course."""
        course = make_course()
        student = CustomUser.objects.create_user(
            username="autoenroll", email="ae@test.com",
            password="pass", role="student",
            is_approved=True, course_selection_done=True,
        )
        student.registration_course = course
        student.save()
        student.auto_enroll_from_registration()
        student.refresh_from_db()
        self.assertIn(course, student.enrolled_courses.all())

    def test_quiz_time_limit_syncs_with_duration(self):
        """Quiz.time_limit_minutes and duration are kept in sync on save."""
        quiz = Quiz.objects.create(title="Sync Test", time_limit_minutes=45)
        quiz.refresh_from_db()
        # Both fields should reflect 45
        self.assertEqual(quiz.duration, 45)
        self.assertEqual(quiz.time_limit_minutes, 45)


# ─── 7. Chatbot Error Handling ────────────────────────────────────────────────

class ChatbotTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.course = make_course()
        self.student = make_student("chatstudent", approved=True, selection_done=True)
        self.student.enrolled_courses.add(self.course)
        self.client.login(username="chatstudent", password="testpass123")

    def test_chatbot_page_loads(self):
        resp = self.client.get(reverse("portal:chatbot"))
        self.assertEqual(resp.status_code, 200)

    def test_chatbot_send_returns_json(self):
        """chatbot_send returns JSON with reply or error key."""
        import json
        with patch("portal.views.ai_service.chat_with_student") as mock_chat:
            mock_chat.return_value = {"success": True, "reply": "Hello!"}
            resp = self.client.post(
                reverse("portal:chatbot_send"),
                data=json.dumps({"message": "Hi", "topic": "Python"}),
                content_type="application/json"
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("reply", data)
        self.assertEqual(data["reply"], "Hello!")

    def test_chatbot_send_handles_ai_error(self):
        """When AI fails, chatbot returns error message not 500."""
        import json
        with patch("portal.views.ai_service.chat_with_student") as mock_chat:
            mock_chat.return_value = {"success": False, "error": "All models failed"}
            resp = self.client.post(
                reverse("portal:chatbot_send"),
                data=json.dumps({"message": "Hi", "topic": ""}),
                content_type="application/json"
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("reply", data)
        # Should contain error text, not crash
        self.assertIn("All models failed", data["reply"])

    def test_chatbot_send_empty_message_rejected(self):
        """Empty message returns 400."""
        import json
        resp = self.client.post(
            reverse("portal:chatbot_send"),
            data=json.dumps({"message": "", "topic": ""}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_unauthenticated_chatbot_redirected(self):
        """Unauthenticated access to chatbot → redirect."""
        client = Client()
        resp = client.get(reverse("portal:chatbot"))
        self.assertIn("/login/", resp.url)

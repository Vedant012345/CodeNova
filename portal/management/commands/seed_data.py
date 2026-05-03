"""
Management command: python manage.py seed_data [--flush]
Seeds the database with multi-role demo users and rich sample content.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, date


class Command(BaseCommand):
    help = "Seed the database with v2 demo users and sample content"

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Clear existing content first')

    def handle(self, *args, **options):
        from portal.models import (
            CustomUser, Note, Quiz, Question, Assignment,
            Notification, Topic, ClientProject, DemoSchedule
        )

        if options['flush']:
            self.stdout.write("Flushing content...")
            CustomUser.objects.exclude(is_superuser=True).delete()
            for M in [Note, Quiz, Assignment, Notification, Topic, ClientProject, DemoSchedule]:
                M.objects.all().delete()

        # ── Admin ────────────────────────────────────────────────────────────
        if not CustomUser.objects.filter(username='admin').exists():
            CustomUser.objects.create_superuser(
                username='admin', email='admin@scholarflow.com',
                password='admin123', first_name='Admin', last_name='User'
            )
            self.stdout.write(self.style.SUCCESS("  ✓ Admin (admin / admin123)"))
        else:
            self.stdout.write("  – Admin already exists")

        # ── Users ────────────────────────────────────────────────────────────
        users_spec = [
            ('student',   'student@example.com',   'student123',   'Alex',  'Johnson', 'student',  True),
            ('client1',   'client1@example.com',   'client123',    'Sarah', 'Chen',    'client',   True),
            ('demo1',     'demo1@example.com',      'demo1234',     'Marco', 'Silva',   'inquiry',  True),
            ('pending_s', 'pending_s@example.com',  'pending123',   'Jamie', 'Smith',   'student',  False),
        ]
        created_users = {}
        for uname, email, pw, fn, ln, role, approved in users_spec:
            if not CustomUser.objects.filter(username=uname).exists():
                u = CustomUser.objects.create_user(
                    username=uname, email=email, password=pw,
                    first_name=fn, last_name=ln, role=role, is_approved=approved
                )
                created_users[uname] = u
                st = "approved" if approved else "pending"
                self.stdout.write(self.style.SUCCESS(f"  ✓ {role.capitalize()} '{uname}' ({st})"))
            else:
                created_users[uname] = CustomUser.objects.get(username=uname)

        # ── Notes ────────────────────────────────────────────────────────────
        notes_data = [
            ("Introduction to Python",          "Core concepts: variables, data types, loops, functions, and OOP.", "Computer Science"),
            ("Algebra Fundamentals",            "Linear equations, quadratic formulas, polynomials, graphing.",      "Mathematics"),
            ("World History: Industrial Revolution", "Key events, inventors, and social transformations 1760–1840.",  "History"),
            ("Organic Chemistry: Functional Groups", "Aldehydes, ketones, carboxylic acids, reaction mechanisms.",   "Chemistry"),
        ]
        for title, desc, subj in notes_data:
            Note.objects.get_or_create(title=title, defaults={"description": desc, "subject": subj})
        self.stdout.write(self.style.SUCCESS(f"  ✓ {len(notes_data)} Notes"))

        # ── Quizzes ──────────────────────────────────────────────────────────
        if not Quiz.objects.filter(title="Python Basics Quiz").exists():
            q1 = Quiz.objects.create(title="Python Basics Quiz", description="Test Python fundamentals.", subject="Computer Science", duration=20)
            Question.objects.bulk_create([
                Question(quiz=q1, text="What keyword defines a function in Python?",    option_a="func",  option_b="def",        option_c="define", option_d="function",     correct="B", marks=2, order=1),
                Question(quiz=q1, text="Which data type is immutable?",                 option_a="list",  option_b="dict",       option_c="tuple",  option_d="set",          correct="C", marks=2, order=2),
                Question(quiz=q1, text="What does len() return?",                       option_a="Last element", option_b="Sum", option_c="Type",   option_d="Count",        correct="D", marks=1, order=3),
                Question(quiz=q1, text="Which symbol denotes comments in Python?",      option_a="//",    option_b="/*",         option_c="#",      option_d="--",           correct="C", marks=1, order=4),
                Question(quiz=q1, text="What does 'import' do?",                        option_a="Creates file", option_b="Loads module", option_c="Declares var", option_d="Starts loop", correct="B", marks=2, order=5),
            ])
            self.stdout.write(self.style.SUCCESS("  ✓ Quiz: Python Basics (5 Qs)"))

        if not Quiz.objects.filter(title="Algebra Quiz").exists():
            q2 = Quiz.objects.create(title="Algebra Quiz", description="Linear & quadratic equations.", subject="Mathematics", duration=25)
            Question.objects.bulk_create([
                Question(quiz=q2, text="Slope-intercept form?",         option_a="ax+by=c", option_b="y=mx+b",   option_c="x=my+b",  option_d="y=ax²+bx+c", correct="B", marks=2, order=1),
                Question(quiz=q2, text="Max solutions of a quadratic?", option_a="1",       option_b="3",        option_c="2",       option_d="4",           correct="C", marks=1, order=2),
                Question(quiz=q2, text="What is the quadratic formula?",option_a="x=−b±√(b²−4ac)/2a", option_b="x=b±√(b²+4ac)/2a", option_c="x=−b/2a", option_d="x=√(b²−4ac)", correct="A", marks=3, order=3),
            ])
            self.stdout.write(self.style.SUCCESS("  ✓ Quiz: Algebra (3 Qs)"))

        # ── Assignments ──────────────────────────────────────────────────────
        assignments = [
            ("Python Mini Project",   "Build a calculator app with addition, subtraction, multiplication, division and error handling.", "Computer Science", 7,  100),
            ("Algebra Problem Set",   "Solve 20 problems from Chapter 4 covering linear and quadratic functions. Show all steps.",         "Mathematics",       3,  50),
            ("History Essay",         "Write a 1000-word essay on social impacts of the Industrial Revolution: labour and urbanisation.",  "History",          14, 100),
        ]
        for title, desc, subj, days, marks in assignments:
            Assignment.objects.get_or_create(title=title, defaults={
                "description": desc, "subject": subj,
                "due_date": timezone.now() + timedelta(days=days),
                "max_marks": marks
            })
        self.stdout.write(self.style.SUCCESS(f"  ✓ {len(assignments)} Assignments"))

        # ── Notifications ────────────────────────────────────────────────────
        notifs = [
            ("Welcome to CodeNova v2!", "The upgraded portal is live with AI quizzes, chatbot tutor, and multi-role dashboards.", "success", ""),
            ("AI Quiz Generator Active",   "Generate custom quizzes instantly from any topic using Groq LLaMA 3.",                   "info",    "student"),
            ("Assignment Reminder",        "The Algebra Problem Set is due in 3 days. Submit before the deadline.",                   "warning", "student"),
            ("Client Portal Updated",      "Your project dashboard now shows real-time progress and team updates.",                   "info",    "client"),
        ]
        for title, body, priority, target in notifs:
            Notification.objects.get_or_create(title=title, defaults={"body": body, "priority": priority, "target_role": target})
        self.stdout.write(self.style.SUCCESS(f"  ✓ {len(notifs)} Notifications"))

        # ── Topics ───────────────────────────────────────────────────────────
        topics_data = [
            ("Python Functions & Scope",   "Functions are reusable code blocks defined with `def`. Understanding local vs global scope is critical for writing clean code.", "Computer Science", date.today(),              "https://docs.python.org/3/tutorial/"),
            ("Linear Equations",           "A linear equation: ax + b = c. Solved by isolating the variable through inverse operations.", "Mathematics", date.today() - timedelta(1), ""),
            ("The Steam Engine",           "Watt's 1769 steam engine improvements catalysed the Industrial Revolution, reshaping economics and society.", "History", date.today() - timedelta(2), ""),
            ("Lists & Dictionaries",       "Lists are ordered mutable sequences. Dictionaries are key-value stores. Choosing between them is a foundational Python skill.", "Computer Science", date.today() - timedelta(3), ""),
        ]
        for title, content, subj, dt, res in topics_data:
            Topic.objects.get_or_create(title=title, defaults={"content": content, "subject": subj, "date": dt, "resources": res})
        self.stdout.write(self.style.SUCCESS(f"  ✓ {len(topics_data)} Topics"))

        # ── Client Projects ──────────────────────────────────────────────────
        client = created_users.get('client1')
        if client and not ClientProject.objects.filter(client=client).exists():
            ClientProject.objects.create(
                client=client, title="E-Commerce Platform",
                description="Full-stack Django/React e-commerce site with Stripe payments, inventory management, and analytics dashboard.",
                status="in_progress", progress=65, team_size=3,
                start_date=date.today() - timedelta(30),
                deadline=date.today() + timedelta(45),
                tech_stack="Django, React, PostgreSQL, Stripe, AWS",
                budget="$8,000",
            )
            ClientProject.objects.create(
                client=client, title="Mobile App UI Design",
                description="Figma prototype and React Native implementation of a fitness tracking application.",
                status="review", progress=90, team_size=2,
                start_date=date.today() - timedelta(60),
                deadline=date.today() + timedelta(7),
                tech_stack="React Native, Figma, Firebase",
                budget="$4,500",
            )
            ClientProject.objects.create(
                client=client, title="API Integration Service",
                description="Python microservice for integrating with third-party CRM and marketing automation APIs.",
                status="completed", progress=100, team_size=1,
                start_date=date.today() - timedelta(90),
                deadline=date.today() - timedelta(10),
                tech_stack="Python, FastAPI, Redis",
                budget="$2,000",
            )
            self.stdout.write(self.style.SUCCESS("  ✓ 3 Client Projects"))

        # ── Demo Schedules ───────────────────────────────────────────────────
        inquiry = created_users.get('demo1')
        if inquiry and not DemoSchedule.objects.filter(inquiry_user=inquiry).exists():
            DemoSchedule.objects.create(
                inquiry_user=inquiry,
                title="CodeNova Platform Demo",
                description="Live walkthrough of the student portal, AI quiz generator, chatbot tutor, and admin panel.",
                scheduled_at=timezone.now() + timedelta(days=2, hours=10),
                platform="zoom",
                meeting_link="https://zoom.us/j/1234567890",
                meeting_id="123 456 7890",
                status="scheduled",
                contact_name="Marco Silva",
                contact_email="demo1@example.com",
                contact_phone="+1 555 999 8888",
            )
            DemoSchedule.objects.create(
                inquiry_user=inquiry,
                title="Initial Discovery Call",
                description="Brief intro call to understand requirements.",
                scheduled_at=timezone.now() - timedelta(days=5),
                platform="meet",
                meeting_link="https://meet.google.com/abc-defg-hij",
                status="completed",
            )
            self.stdout.write(self.style.SUCCESS("  ✓ 2 Demo Sessions"))

        self.stdout.write(self.style.SUCCESS("\n✅ v2 seed complete!"))
        self.stdout.write("   Admin       →  admin / admin123")
        self.stdout.write("   Student     →  student / student123")
        self.stdout.write("   Client      →  client1 / client123")
        self.stdout.write("   Inquiry     →  demo1 / demo1234")
        self.stdout.write("   Visit       →  http://127.0.0.1:8000/")

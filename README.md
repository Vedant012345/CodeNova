# ScholarFlow v2 — Multi-Role Education Platform

A production-ready Django education platform with admin-controlled user approval,
multi-role dashboards, AI-powered quiz generation, AI chatbot, client project
tracking, and inquiry/demo scheduling.

---

## Quick Start

```bash
# 1. Create & activate virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your Groq API key (free at console.groq.com)
export GROQ_API_KEY=your_key_here      # Linux/Mac
set GROQ_API_KEY=your_key_here         # Windows

# 4. Run migrations
python manage.py migrate

# 5. Load demo data (users + content)
python manage.py seed_data

# 6. Start the server
python manage.py runserver
```

Open http://127.0.0.1:8000/

---

## Demo Credentials

| Role         | Username  | Password     | Notes            |
|--------------|-----------|--------------|------------------|
| Admin        | admin     | admin123     | Full admin panel |
| Student      | student   | student123   | AI quiz + chat   |
| Client       | client1   | client123    | Project tracking |
| Inquiry/Demo | demo1     | demo1234     | Demo sessions    |
| Pending      | pending_s | pending123   | Awaiting approval|

---

## User Approval Flow

1. User registers → selects **role** (Student / Client / Inquiry)  
2. Account created with `is_approved = False`  
3. Admin logs into `/admin/` → Users → select → **"Approve selected users"**  
4. User can now sign in and access their role-specific dashboard  
5. Login blocked with message until approved  
6. After **2 failed login attempts** → support contact details shown  

---

## Feature Matrix

| Feature                     | Student | Client | Inquiry |
|-----------------------------|:-------:|:------:|:-------:|
| Notes (download)            | ✅      | ❌     | ❌      |
| Quizzes (manual)            | ✅      | ❌     | ❌      |
| **AI Quiz Generator**       | ✅      | ❌     | ❌      |
| **AI Chatbot (ScholarBot)** | ✅      | ❌     | ❌      |
| Assignments                 | ✅      | ❌     | ❌      |
| Performance tracking        | ✅      | ❌     | ❌      |
| Learning center             | ✅      | ❌     | ❌      |
| **Client project tracking** | ❌      | ✅     | ❌      |
| **Demo session management** | ❌      | ❌     | ✅      |
| Notifications               | ✅      | ✅     | ✅      |
| Profile                     | ✅      | ✅     | ✅      |

---

## AI Features Setup

Get a **free** Groq API key at https://console.groq.com — no credit card required.

```bash
export GROQ_API_KEY=gsk_your_key_here
```

The app works fully without a key (AI features will show a friendly error).
All other features (quizzes, assignments, notes, etc.) work without Groq.

---

## Project Structure

```
scholarflow/
├── manage.py
├── requirements.txt
├── README.md
├── db.sqlite3                      ← Pre-seeded demo database
├── scholarflow/
│   ├── settings.py
│   ├── settings_production.py
│   └── urls.py
└── portal/
    ├── models.py                   ← 12 models incl. ChatMessage, ClientProject, DemoSchedule
    ├── views.py                    ← Role-based routing, AI quiz, chatbot AJAX
    ├── urls.py                     ← 24 URL patterns
    ├── forms.py                    ← Registration with role selector
    ├── admin.py                    ← Full admin with badges, bulk approve
    ├── ai_service.py               ← Groq integration (quiz gen + chatbot)
    ├── templatetags/
    │   └── portal_tags.py          ← options filter for quiz rendering
    ├── management/commands/
    │   └── seed_data.py            ← Full demo data for all 3 roles
    ├── migrations/
    └── templates/portal/
        ├── homepage.html           ← Dark Obsidian Flux design, public landing page
        ├── base.html               ← Dark sidebar, role-aware nav
        ├── login.html              ← Support details on repeated failures
        ├── register.html           ← Role-selector card UI
        ├── pending.html
        ├── dashboard_student.html
        ├── dashboard_client.html
        ├── dashboard_inquiry.html
        ├── ai_quiz_generate.html   ← AI quiz generation UI
        ├── chatbot.html            ← Live AJAX chat with typing indicator
        ├── notes.html
        ├── quizzes.html
        ├── quiz_attempt.html
        ├── assignments.html
        ├── assignment_submit.html
        ├── performance.html
        ├── learning.html
        ├── notifications.html
        ├── profile.html
        ├── client_projects.html
        └── inquiry_demos.html
```

---

## Run Tests

```bash
python manage.py test portal        # 38 tests
```

---

## Production Notes

- Set `GROQ_API_KEY` environment variable  
- Change `SECRET_KEY` in `settings.py`  
- Set `DEBUG = False` and configure `ALLOWED_HOSTS`  
- Use PostgreSQL: set `DATABASE_URL` env var (see `settings_production.py`)  
- Serve static/media via nginx or AWS S3  
- Use gunicorn as WSGI server  
# CodeNova
# CodeNova

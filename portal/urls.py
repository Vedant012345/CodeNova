"""
CodeNova Portal URLs — v7 (Merged)
======================================
MERGE_NOTE: Unified from V5 (host_views, /host/ dashboard, UserQuery system)
            and V6 (course access control, course_select, su_courses, su_user_courses).

Single, clean URL configuration. No duplicates. No conflicts.
"""
from django.urls import path
from . import views
from . import superuser_views as sv
from . import host_views as hv

app_name = "portal"

urlpatterns = [
    # ══ Public ════════════════════════════════════════════════════════════════
    path("",               views.homepage,       name="homepage"),
    path("contact/send/",  views.contact_submit, name="contact_submit"),

    # ══ Auth ══════════════════════════════════════════════════════════════════
    path("login/",           views.login_view,      name="login"),
    path("login/choice/",    views.login_choice,    name="login_choice"),
    path("register/",        views.register_view,   name="register"),
    path("register/choice/", views.register_choice, name="register_choice"),
    path("logout/",          views.logout_view,     name="logout"),
    path("pending/",         views.pending_view,    name="pending"),

    # ══ Course Selection (V6) ════════════════════════════════════════════════
    path("course/select/", views.course_select_view, name="course_select"),

    # ══ Dashboard ════════════════════════════════════════════════════════════
    path("dashboard/", views.dashboard_view, name="dashboard"),

    # ══ Notes ════════════════════════════════════════════════════════════════
    path("notes/",                   views.notes_view,    name="notes"),
    path("notes/<int:pk>/download/", views.note_download, name="note_download"),

    # ══ Quizzes ══════════════════════════════════════════════════════════════
    path("quizzes/",                  views.quizzes_view,     name="quizzes"),
    path("quizzes/<int:pk>/attempt/", views.quiz_attempt,     name="quiz_attempt"),
    path("quizzes/<int:pk>/result/",  views.quiz_result,      name="quiz_result"),   # v10
    path("quizzes/ai-generate/",      views.ai_quiz_generate, name="ai_quiz_generate"),

    # ══ AI Chatbot ═══════════════════════════════════════════════════════════
    path("chatbot/",      views.chatbot_view, name="chatbot"),
    path("chatbot/send/", views.chatbot_send, name="chatbot_send"),

    # ══ Assignments ══════════════════════════════════════════════════════════
    path("assignments/",                 views.assignments_view,  name="assignments"),
    path("assignments/<int:pk>/submit/", views.assignment_submit, name="assignment_submit"),

    # ══ Performance & Learning ═══════════════════════════════════════════════
    path("performance/",            views.performance_view, name="performance"),
    path("learning/",               views.learning_view,    name="learning"),
    path("learning/<int:pk>/done/", views.mark_topic_done,  name="mark_topic_done"),

    # ══ All Roles ════════════════════════════════════════════════════════════
    path("notifications/", views.notifications_view, name="notifications"),
    path("profile/",       views.profile_view,       name="profile"),
    path("ask/",           views.ask_question_view,  name="ask_question"),

    # ══ Client ═══════════════════════════════════════════════════════════════
    path("client/projects/", views.client_projects_view, name="client_projects"),

    # ══ Inquiry ══════════════════════════════════════════════════════════════
    path("inquiry/demos/", views.inquiry_demos_view, name="inquiry_demos"),

    # ══ Host dashboard views (student-facing reply widgets) ═══════════════════
    path("host/dashboard/",              views.host_dashboard_view, name="host_dashboard"),
    path("host/query/<int:pk>/answer/",  views.host_answer_query,   name="host_answer_query"),

    # ══ HOST / TEACHER DASHBOARD (/host/) — full UI admin panel ══════════════
    path("host/login/",  hv.host_login,  name="host_login"),
    path("host/logout/", hv.host_logout, name="host_logout"),
    path("host/",        hv.host_index,  name="host_index"),
    path("host/users/",                       hv.host_users,        name="host_users"),
    path("host/users/<int:pk>/action/",       hv.host_user_action,  name="host_user_action"),
    path("host/users/bulk-approve/",          hv.host_bulk_approve, name="host_bulk_approve"),
    path("host/notes/",                       hv.host_notes,        name="host_notes"),
    path("host/notes/<int:pk>/delete/",       hv.host_note_delete,  name="host_note_delete"),
    path("host/notes/<int:pk>/toggle/",       hv.host_note_toggle,  name="host_note_toggle"),
    path("host/quizzes/",                     hv.host_quizzes,           name="host_quizzes"),
    path("host/quizzes/<int:pk>/questions/",  hv.host_quiz_questions,    name="host_quiz_questions"),
    path("host/quizzes/<int:pk>/delete/",     hv.host_quiz_delete,       name="host_quiz_delete"),
    path("host/quizzes/<int:pk>/toggle/",     hv.host_quiz_toggle,       name="host_quiz_toggle"),
    path("host/quizzes/analytics/",           hv.host_quiz_analytics,    name="host_quiz_analytics"),  # v10
    path("host/quizzes/<int:pk>/analytics/",  hv.host_quiz_analytics,    name="host_quiz_analytics_quiz"),  # v10
    path("host/questions/<int:pk>/delete/",   hv.host_question_delete,   name="host_question_delete"),
    path("host/ai/quiz/",  hv.host_ai_quiz, name="host_ai_quiz"),
    path("host/ai/chat/",  hv.host_ai_chat, name="host_ai_chat"),
    path("host/assignments/",                      hv.host_assignments,       name="host_assignments"),
    path("host/assignments/<int:pk>/delete/",      hv.host_assignment_delete, name="host_assignment_delete"),
    path("host/assignments/<int:pk>/submissions/", hv.host_submissions,       name="host_submissions"),
    path("host/projects/",                   hv.host_projects,       name="host_projects"),
    path("host/projects/<int:pk>/update/",   hv.host_project_update, name="host_project_update"),
    path("host/projects/<int:pk>/delete/",   hv.host_project_delete, name="host_project_delete"),
    path("host/demos/",                  hv.host_demos,       name="host_demos"),
    path("host/demos/<int:pk>/update/",  hv.host_demo_update, name="host_demo_update"),
    path("host/demos/<int:pk>/delete/",  hv.host_demo_delete, name="host_demo_delete"),
    path("host/queries/",                    hv.host_queries,      name="host_queries"),
    path("host/queries/<int:pk>/reply/",     hv.host_query_reply,  name="host_query_reply"),
    path("host/queries/<int:pk>/status/",    hv.host_query_status, name="host_query_status"),
    path("host/courses/",                    hv.host_courses,       name="host_courses"),
    path("host/courses/<int:pk>/delete/",    hv.host_course_delete, name="host_course_delete"),
    path("host/topics/<int:pk>/delete/",     hv.host_topic_delete,  name="host_topic_delete"),
    path("host/notifications/",                      hv.host_notifications,       name="host_notifications"),
    path("host/notifications/<int:pk>/delete/",      hv.host_notification_delete, name="host_notification_delete"),
    path("host/notifications/<int:pk>/toggle/",      hv.host_notification_toggle, name="host_notification_toggle"),

    # ── v9: Contact Messages (separate from Ask Question system) ──────────────
    path("host/contact-messages/",                       hv.host_contact_messages,   name="host_contact_messages"),
    path("host/contact-messages/<int:pk>/mark-read/",    hv.host_contact_mark_read,  name="host_contact_mark_read"),
    path("host/contact-messages/<int:pk>/delete/",       hv.host_contact_delete,     name="host_contact_delete"),

    # ── v9: Course Banner Upload ──────────────────────────────────────────────
    path("host/courses/<int:pk>/banner/",  hv.host_course_banner, name="host_course_banner"),

    # ══ SUPERUSER UI PANEL (/superuser/) ════════════════════════════════════
    path("superuser/login/",  sv.su_login,     name="su_login"),
    path("superuser/logout/", sv.su_logout,    name="su_logout"),
    path("superuser/",        sv.su_dashboard, name="su_dashboard"),
    path("superuser/users/",                      sv.su_users,        name="su_users"),
    path("superuser/users/<int:pk>/action/",      sv.su_user_action,  name="su_user_action"),
    path("superuser/users/bulk-approve/",         sv.su_bulk_approve, name="su_bulk_approve"),
    path("superuser/users/<int:pk>/courses/",     sv.su_user_courses, name="su_user_courses"),
    path("superuser/notes/",                      sv.su_notes,       name="su_notes"),
    path("superuser/notes/<int:pk>/delete/",      sv.su_note_delete, name="su_note_delete"),
    path("superuser/notes/<int:pk>/toggle/",      sv.su_note_toggle, name="su_note_toggle"),
    path("superuser/quizzes/",                        sv.su_quizzes,         name="su_quizzes"),
    path("superuser/quizzes/create/",                 sv.su_quiz_create,     name="su_quiz_create"),
    path("superuser/quizzes/<int:pk>/questions/",     sv.su_quiz_questions,  name="su_quiz_questions"),
    path("superuser/quizzes/<int:pk>/delete/",        sv.su_quiz_delete,     name="su_quiz_delete"),
    path("superuser/quizzes/<int:pk>/toggle/",        sv.su_quiz_toggle,     name="su_quiz_toggle"),
    path("superuser/questions/<int:pk>/delete/",      sv.su_question_delete, name="su_question_delete"),
    path("superuser/assignments/",                    sv.su_assignments,       name="su_assignments"),
    path("superuser/assignments/<int:pk>/delete/",    sv.su_assignment_delete, name="su_assignment_delete"),
    path("superuser/submissions/<int:pk>/grade/",     sv.su_grade_submission,  name="su_grade_submission"),
    path("superuser/projects/",                   sv.su_projects,       name="su_projects"),
    path("superuser/projects/<int:pk>/update/",   sv.su_project_update, name="su_project_update"),
    path("superuser/projects/<int:pk>/delete/",   sv.su_project_delete, name="su_project_delete"),
    path("superuser/demos/",                      sv.su_demos,              name="su_demos"),
    path("superuser/demos/<int:pk>/status/",      sv.su_demo_update_status, name="su_demo_update_status"),
    path("superuser/demos/<int:pk>/delete/",      sv.su_demo_delete,        name="su_demo_delete"),
    path("superuser/notifications/",                  sv.su_notifications,       name="su_notifications"),
    path("superuser/notifications/<int:pk>/delete/",  sv.su_notification_delete, name="su_notification_delete"),
    path("superuser/notifications/<int:pk>/toggle/",  sv.su_notification_toggle, name="su_notification_toggle"),
    path("superuser/messages/",                   sv.su_messages,          name="su_messages"),
    path("superuser/messages/<int:pk>/read/",     sv.su_message_mark_read, name="su_message_mark_read"),
    path("superuser/messages/<int:pk>/delete/",   sv.su_message_delete,    name="su_message_delete"),
    path("superuser/activity/", sv.su_activity, name="su_activity"),
    path("superuser/courses/",                    sv.su_courses,       name="su_courses"),
    path("superuser/courses/<int:pk>/delete/",    sv.su_course_delete, name="su_course_delete"),
    path("superuser/courses/<int:pk>/toggle/",    sv.su_course_toggle, name="su_course_toggle"),
]

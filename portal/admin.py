"""
CodeNova Admin — v2
Full admin panel with role-aware management, project tracking, demo scheduling.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import (
    CustomUser, Note, Quiz, Question, Assignment, Submission,
    QuizResult, Notification, Topic, TopicCompletion, Performance,
    ChatMessage, ClientProject, DemoSchedule, Course, UserQuery
)


# ─── Custom User Admin ────────────────────────────────────────────────────────

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display  = ("username", "email", "get_full_name", "role_badge", "is_approved", "is_active", "date_joined")
    list_filter   = ("role", "is_approved", "is_active", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering      = ("-date_joined",)
    actions       = ["approve_users", "revoke_users"]

    fieldsets = (
        (None,           {"fields": ("username", "password")}),
        ("Personal",     {"fields": ("first_name", "last_name", "email", "avatar", "bio")}),
        ("Role & Access",{"fields": ("role", "is_approved", "is_active", "is_staff", "is_superuser",
                                     "groups", "user_permissions")}),
        ("Security",     {"fields": ("failed_login_count",)}),
        ("Dates",        {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields":  ("username", "email", "password1", "password2",
                        "first_name", "last_name", "role", "is_approved"),
        }),
    )

    def role_badge(self, obj):
        colors = {"student": "#3525cd", "client": "#006c49", "inquiry": "#571ac0"}
        color = colors.get(obj.role, "#666")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600;">{}</span>',
            color, obj.get_role_display()
        )
    role_badge.short_description = "Role"

    @admin.action(description="✅ Approve selected users")
    def approve_users(self, request, queryset):
        updated = queryset.update(is_approved=True, failed_login_count=0)
        self.message_user(request, f"{updated} user(s) approved.")

    @admin.action(description="❌ Revoke approval")
    def revoke_users(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f"{updated} user(s) revoked.")


# ─── Note Admin ───────────────────────────────────────────────────────────────

@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display  = ("title", "subject", "is_active", "created_at")
    list_filter   = ("subject", "is_active")
    search_fields = ("title", "description")
    list_editable = ("is_active",)


# ─── Quiz Admin ───────────────────────────────────────────────────────────────

class QuestionInline(admin.TabularInline):
    model  = Question
    extra  = 3
    fields = ("order", "text", "option_a", "option_b", "option_c", "option_d", "correct", "marks")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display  = ("title", "subject", "duration", "question_count", "is_ai_generated", "is_active", "created_at")
    list_filter   = ("subject", "is_active", "is_ai_generated")
    search_fields = ("title",)
    inlines       = [QuestionInline]
    list_editable = ("is_active",)

    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = "Questions"


# ─── Assignment Admin ─────────────────────────────────────────────────────────

class SubmissionInline(admin.TabularInline):
    model       = Submission
    extra       = 0
    fields      = ("student", "status", "marks", "feedback", "submitted_at")
    readonly_fields = ("student", "submitted_at")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display  = ("title", "subject", "due_date", "max_marks", "is_active", "submission_count")
    list_filter   = ("subject", "is_active")
    search_fields = ("title",)
    inlines       = [SubmissionInline]

    def submission_count(self, obj):
        return obj.submissions.count()
    submission_count.short_description = "Submissions"


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display  = ("student", "assignment", "status", "marks", "submitted_at")
    list_filter   = ("status",)
    search_fields = ("student__username", "assignment__title")
    list_editable = ("status", "marks")


@admin.register(QuizResult)
class QuizResultAdmin(admin.ModelAdmin):
    list_display  = ("student", "quiz", "score", "total", "percentage_display", "taken_at")
    list_filter   = ("quiz",)
    search_fields = ("student__username",)
    readonly_fields = ("taken_at",)

    def percentage_display(self, obj):
        color = "#006c49" if obj.percentage >= 50 else "#ba1a1a"
        return format_html('<span style="color:{}; font-weight:600;">{:.1f}%</span>', color, obj.percentage)
    percentage_display.short_description = "Score %"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ("title", "priority", "target_role", "is_active", "created_at")
    list_filter   = ("priority", "is_active", "target_role")
    list_editable = ("is_active",)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display  = ("title", "subject", "date", "is_active")
    list_filter   = ("subject", "is_active")
    search_fields = ("title", "content")
    list_editable = ("is_active",)


@admin.register(Performance)
class PerformanceAdmin(admin.ModelAdmin):
    list_display    = ("student", "quiz_avg", "assignment_avg", "topics_done", "overall", "updated_at")
    readonly_fields = ("updated_at",)


# ─── Chat Message Admin ───────────────────────────────────────────────────────

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display  = ("student", "role", "topic", "short_content", "timestamp")
    list_filter   = ("role",)
    search_fields = ("student__username", "content")
    readonly_fields = ("timestamp",)

    def short_content(self, obj):
        return obj.content[:80]
    short_content.short_description = "Content"


# ─── Client Project Admin ─────────────────────────────────────────────────────

@admin.register(ClientProject)
class ClientProjectAdmin(admin.ModelAdmin):
    list_display  = ("title", "client", "status_badge", "progress_bar", "team_size", "deadline", "is_overdue_flag")
    list_filter   = ("status",)
    search_fields = ("title", "client__username")
    list_editable = ("team_size",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Project Info",   {"fields": ("client", "title", "description", "tech_stack", "budget")}),
        ("Status",         {"fields": ("status", "progress")}),
        ("Team & Timeline",{"fields": ("team_size", "start_date", "deadline")}),
        ("Preview Links",  {"fields": ("live_url", "demo_video_url"),
                            "description": "Add a live URL and/or demo video URL for the client-facing preview."}),
        ("Notes",          {"fields": ("notes",)}),
        ("Timestamps",     {"fields": ("created_at", "updated_at")}),
    )

    def status_badge(self, obj):
        colors = {
            "pending":"#777","in_progress":"#3525cd",
            "review":"#571ac0","completed":"#006c49","on_hold":"#ba1a1a"
        }
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:12px; font-size:11px;">{}</span>',
            colors.get(obj.status,"#666"), obj.get_status_display()
        )
    status_badge.short_description = "Status"

    def progress_bar(self, obj):
        color = "#006c49" if obj.progress >= 75 else "#3525cd" if obj.progress >= 40 else "#ba1a1a"
        return format_html(
            '<div style="width:100px;background:#eee;border-radius:4px;overflow:hidden;">'
            '<div style="width:{}%;background:{};height:8px;"></div></div> {}%',
            obj.progress, color, obj.progress
        )
    progress_bar.short_description = "Progress"

    def is_overdue_flag(self, obj):
        if obj.is_overdue():
            return format_html('<span style="color:#ba1a1a; font-weight:600;">⚠ Overdue</span>')
        return "—"
    is_overdue_flag.short_description = "Overdue?"


# ─── Demo Schedule Admin ──────────────────────────────────────────────────────

@admin.register(DemoSchedule)
class DemoScheduleAdmin(admin.ModelAdmin):
    list_display  = ("title", "inquiry_user", "scheduled_at", "platform", "status_badge", "meeting_link_display")
    list_filter   = ("status", "platform")
    search_fields = ("inquiry_user__username", "title")
    readonly_fields = ("created_at",)

    fieldsets = (
        ("Session Info",   {"fields": ("inquiry_user", "title", "description")}),
        ("Schedule",       {"fields": ("scheduled_at", "status")}),
        ("Meeting Details",{"fields": ("platform", "meeting_link", "meeting_id")}),
        ("Recorded Lecture",{"fields": ("video_url",),
                              "description": "Paste a YouTube or hosted video URL to make this session available as a recorded lecture on the demo dashboard."}),
        ("Contact",        {"fields": ("contact_name", "contact_email", "contact_phone")}),
        ("Notes",          {"fields": ("notes",)}),
        ("Timestamps",     {"fields": ("created_at",)}),
    )

    def status_badge(self, obj):
        colors = {"scheduled":"#3525cd","completed":"#006c49","cancelled":"#ba1a1a","rescheduled":"#571ac0"}
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:12px; font-size:11px;">{}</span>',
            colors.get(obj.status,"#666"), obj.get_status_display()
        )
    status_badge.short_description = "Status"

    def meeting_link_display(self, obj):
        if obj.meeting_link:
            return format_html('<a href="{}" target="_blank">Join →</a>', obj.meeting_link)
        return "—"
    meeting_link_display.short_description = "Meeting Link"


# ─── Course Admin ─────────────────────────────────────────────────────────────

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display  = ("title", "subject", "level_badge", "duration", "is_active", "order", "created_at")
    list_filter   = ("level", "is_active")
    search_fields = ("title", "subject", "description")
    list_editable = ("is_active", "order")
    ordering      = ("order", "-created_at")

    fieldsets = (
        ("Course Info", {"fields": ("title", "description", "subject", "level", "duration", "icon")}),
        ("Visibility",  {"fields": ("is_active", "order")}),
    )

    def level_badge(self, obj):
        colors = {"beginner": "#006c49", "intermediate": "#3525cd", "advanced": "#571ac0"}
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600;">{}</span>',
            colors.get(obj.level, "#666"), obj.get_level_display()
        )
    level_badge.short_description = "Level"


@admin.register(UserQuery)
class UserQueryAdmin(admin.ModelAdmin):
    list_display  = ("subject", "user", "status", "answered_by", "created_at", "updated_at")
    list_filter   = ("status",)
    search_fields = ("subject", "question", "answer", "user__username")
    readonly_fields = ("user", "question", "created_at", "updated_at")
    ordering      = ("-created_at",)
    fieldsets = (
        ("Question", {"fields": ("user", "subject", "question", "created_at")}),
        ("Reply",    {"fields": ("answer", "answered_by", "status", "updated_at")}),
    )

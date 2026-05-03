"""
Migration 0007 — v8 Upgrades
Adds:
  - CustomUser.registration_course FK (course chosen at registration)
  - Note.uploaded_by FK
  - Quiz.time_limit_minutes field
  - Question.explanation field
  - Assignment.due_date -> nullable
  - Topic.course FK, video_url, order fields
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0006_course_access_control'),
    ]

    operations = [
        # ── CustomUser.registration_course ────────────────────────────────
        migrations.AddField(
            model_name='customuser',
            name='registration_course',
            field=models.ForeignKey(
                to='portal.Course',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='registered_students',
                help_text='Course selected at registration time. Auto-enrolled on admin approval.'
            ),
        ),

        # ── Note.uploaded_by ──────────────────────────────────────────────
        migrations.AddField(
            model_name='note',
            name='uploaded_by',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='uploaded_notes',
            ),
        ),

        # ── Quiz.time_limit_minutes ───────────────────────────────────────
        migrations.AddField(
            model_name='quiz',
            name='time_limit_minutes',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Alias of duration — used by host dashboard forms'
            ),
        ),

        # ── Question.explanation ──────────────────────────────────────────
        migrations.AddField(
            model_name='question',
            name='explanation',
            field=models.TextField(
                blank=True,
                help_text='Why this answer is correct'
            ),
        ),

        # ── Assignment.due_date nullable ──────────────────────────────────
        migrations.AlterField(
            model_name='assignment',
            name='due_date',
            field=models.DateTimeField(null=True, blank=True),
        ),

        # ── Topic.course FK ───────────────────────────────────────────────
        migrations.AddField(
            model_name='topic',
            name='course',
            field=models.ForeignKey(
                to='portal.Course',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='topics',
            ),
        ),

        # ── Topic.video_url ───────────────────────────────────────────────
        migrations.AddField(
            model_name='topic',
            name='video_url',
            field=models.URLField(blank=True),
        ),

        # ── Topic.order ───────────────────────────────────────────────────
        migrations.AddField(
            model_name='topic',
            name='order',
            field=models.PositiveIntegerField(default=1),
        ),

        # ── Topic.content optional ────────────────────────────────────────
        migrations.AlterField(
            model_name='topic',
            name='content',
            field=models.TextField(blank=True),
        ),
    ]

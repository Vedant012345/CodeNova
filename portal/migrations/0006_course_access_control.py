"""
Migration 0006 — Course-Based Access Control
Adds:
  - ManyToMany between CustomUser ↔ Course (student course selection)
  - course ForeignKey on Note, Quiz, Assignment (nullable for backward compat)
  - course_selection_done BooleanField on CustomUser

WARNING: All content FK fields (note.course, quiz.course, assignment.course)
are nullable=True to preserve backward compatibility. Existing content will
have course=NULL and will NOT be filtered until the admin assigns courses.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0005_userquery'),
    ]

    operations = [
        # ── 1. course_selection_done flag on CustomUser ────────────────────
        migrations.AddField(
            model_name='customuser',
            name='course_selection_done',
            field=models.BooleanField(
                default=False,
                help_text='True once the student has completed the course-selection step'
            ),
        ),

        # ── 2. Student ↔ Course ManyToMany ────────────────────────────────
        migrations.AddField(
            model_name='customuser',
            name='enrolled_courses',
            field=models.ManyToManyField(
                to='portal.Course',
                blank=True,
                related_name='enrolled_students',
                help_text='Courses the student has selected/enrolled in'
            ),
        ),

        # ── 3. course FK on Note ───────────────────────────────────────────
        migrations.AddField(
            model_name='note',
            name='course',
            field=models.ForeignKey(
                to='portal.Course',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='notes',
                help_text='Leave blank to show to all courses (legacy support)'
            ),
        ),

        # ── 4. course FK on Quiz ───────────────────────────────────────────
        migrations.AddField(
            model_name='quiz',
            name='course',
            field=models.ForeignKey(
                to='portal.Course',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='quizzes',
                help_text='Leave blank to show to all courses (legacy support)'
            ),
        ),

        # ── 5. course FK on Assignment ────────────────────────────────────
        migrations.AddField(
            model_name='assignment',
            name='course',
            field=models.ForeignKey(
                to='portal.Course',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='assignments',
                help_text='Leave blank to show to all courses (legacy support)'
            ),
        ),
    ]

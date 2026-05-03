"""
Migration 0009: v10 Quiz Analytics
- QuizStudentAnswer: stores per-question student responses for result detail and host analytics
"""
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0008_v9_enhancements"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuizStudentAnswer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("selected_answer", models.CharField(
                    max_length=1, blank=True,
                    help_text="Student's selected option: A/B/C/D or blank if skipped"
                )),
                ("correct_answer", models.CharField(
                    max_length=1,
                    help_text="Correct option at time of submission"
                )),
                ("is_correct", models.BooleanField(default=False)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("student", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="quiz_answers",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("quiz", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="student_answers",
                    to="portal.quiz",
                )),
                ("question", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="student_answers",
                    to="portal.question",
                )),
            ],
            options={
                "ordering": ["question__order", "question__id"],
                "unique_together": {("student", "quiz", "question")},
            },
        ),
    ]


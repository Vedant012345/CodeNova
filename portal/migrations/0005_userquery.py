"""
Migration: Add UserQuery model for the Global Ask Question system.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0004_course_demoschedule_video_url_clientproject_live_url'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserQuery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=255)),
                ('question', models.TextField()),
                ('answer', models.TextField(blank=True, help_text='Host/Teacher reply goes here')),
                ('status', models.CharField(
                    choices=[('open', 'Open'), ('answered', 'Answered'), ('closed', 'Closed')],
                    default='open', max_length=10
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='queries',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('answered_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='answered_queries',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'User Query',
                'verbose_name_plural': 'User Queries',
                'ordering': ['-created_at'],
            },
        ),
    ]

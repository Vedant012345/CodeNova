# Generated migration for CodeNova v4 enhancements
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0003_contactmessage_activitylog'),
    ]

    operations = [
        # Add Course model
        migrations.CreateModel(
            name='Course',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('subject', models.CharField(blank=True, max_length=100)),
                ('level', models.CharField(
                    choices=[('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced')],
                    default='beginner', max_length=20
                )),
                ('duration', models.CharField(blank=True, help_text="e.g. '8 weeks'", max_length=60)),
                ('icon', models.CharField(blank=True, default='school', help_text='Material Symbols icon name', max_length=60)),
                ('is_active', models.BooleanField(default=True)),
                ('order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['order', '-created_at'],
            },
        ),
        # Add video_url to DemoSchedule
        migrations.AddField(
            model_name='demoschedule',
            name='video_url',
            field=models.URLField(blank=True, help_text='YouTube or hosted video URL for the demo session'),
        ),
        # Add live_url to ClientProject
        migrations.AddField(
            model_name='clientproject',
            name='live_url',
            field=models.URLField(blank=True, help_text='Live URL of the deployed project/web app'),
        ),
        # Add demo_video_url to ClientProject
        migrations.AddField(
            model_name='clientproject',
            name='demo_video_url',
            field=models.URLField(blank=True, help_text='YouTube or hosted demo video URL'),
        ),
    ]

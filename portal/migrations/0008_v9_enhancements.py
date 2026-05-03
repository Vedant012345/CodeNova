"""
Migration 0008: v9 Enhancements
- Course.banner_image  (ImageField, nullable)
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0007_v8_upgrades"),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="banner_image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="course_banners/",
                help_text="Banner image displayed on the course card and course detail section.",
            ),
        ),
    ]

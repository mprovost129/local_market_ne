from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0029_support_contactmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactmessage",
            name="internal_notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="last_responded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="last_responded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="responded_contact_messages",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="response_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="sla_tag",
            field=models.CharField(
                choices=[("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")],
                default="normal",
                help_text="Internal triage label for response urgency.",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="SupportResponseTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120)),
                ("subject", models.CharField(blank=True, default="", max_length=200)),
                ("body", models.TextField(max_length=6000)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["title"],
            },
        ),
    ]

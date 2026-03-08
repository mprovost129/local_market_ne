from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_support_inbox_hardening"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportOutboundEmailLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("to_email", models.EmailField(max_length=254)),
                ("from_email", models.EmailField(max_length=254)),
                ("subject", models.CharField(blank=True, default="", max_length=200)),
                ("body", models.TextField(max_length=8000)),
                (
                    "status",
                    models.CharField(
                        choices=[("sent", "Sent"), ("failed", "Failed")],
                        default="sent",
                        max_length=20,
                    ),
                ),
                ("error_text", models.TextField(blank=True, default="")),
                ("sent_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "contact_message",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outbound_emails",
                        to="core.contactmessage",
                    ),
                ),
                (
                    "sent_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="support_outbound_emails",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-sent_at"],
            },
        ),
    ]

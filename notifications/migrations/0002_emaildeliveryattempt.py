from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailDeliveryAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("to_email", models.EmailField(db_index=True, max_length=254)),
                ("from_email", models.EmailField(blank=True, default="", max_length=254)),
                ("subject", models.CharField(blank=True, default="", max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[("sent", "Sent"), ("failed", "Failed")],
                        db_index=True,
                        default="sent",
                        max_length=12,
                    ),
                ),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_attempts",
                        to="notifications.notification",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="emaildeliveryattempt",
            index=models.Index(fields=["status", "created_at"], name="notificatio_status__4c4c1a_idx"),
        ),
        migrations.AddIndex(
            model_name="emaildeliveryattempt",
            index=models.Index(fields=["to_email", "created_at"], name="notificatio_to_emai_2b0c0f_idx"),
        ),
        migrations.AddIndex(
            model_name="emaildeliveryattempt",
            index=models.Index(fields=["notification", "created_at"], name="notificatio_notific_4f3c87_idx"),
        ),
    ]

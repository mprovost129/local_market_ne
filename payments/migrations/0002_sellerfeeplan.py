from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SellerFeePlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="If disabled, this fee plan is ignored and default/waiver logic applies.",
                    ),
                ),
                (
                    "starts_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Optional plan start. Leave blank for immediate effect.",
                        null=True,
                    ),
                ),
                (
                    "ends_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Optional plan end. Leave blank for no expiration.",
                        null=True,
                    ),
                ),
                (
                    "custom_sales_percent",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Optional fixed platform fee percent for this seller. Overrides discount when set.",
                        max_digits=6,
                        null=True,
                    ),
                ),
                (
                    "discount_percent",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        help_text="Percent discount off global platform fee (0-100). 100 = fully comped.",
                        max_digits=6,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fee_plan",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["is_active", "starts_at", "ends_at"], name="payments_se_is_acti_3d1adf_idx")],
            },
        ),
    ]

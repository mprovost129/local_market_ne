# core/migrations/0025_waitlistentry.py
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_siteconfig_seller_onboarding_policy"),
    ]

    operations = [
        migrations.CreateModel(
            name="WaitlistEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("source_path", models.CharField(blank=True, default="", max_length=200)),
                ("user_agent", models.CharField(blank=True, default="", max_length=240)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
            ],
        ),
    ]

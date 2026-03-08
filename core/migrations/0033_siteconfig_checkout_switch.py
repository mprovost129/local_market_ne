from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_siteconfig_free_digital_listing_cap"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="checkout_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "If disabled, checkout is blocked sitewide (browsing still works). "
                    "Use for emergency rollback or payment incident response."
                ),
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="checkout_disabled_message",
            field=models.CharField(
                blank=True,
                default="Checkout is temporarily unavailable. Please try again soon.",
                help_text="Message shown when checkout is disabled.",
                max_length=240,
            ),
        ),
    ]

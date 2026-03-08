from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_support_outbound_email_log"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="free_digital_listing_cap",
            field=models.PositiveIntegerField(
                default=5,
                help_text=(
                    "Maximum number of active FREE FILE listings a seller may publish without Stripe onboarding. "
                    "Set to 0 to require Stripe before any FREE FILE listings can be published."
                ),
            ),
        ),
    ]

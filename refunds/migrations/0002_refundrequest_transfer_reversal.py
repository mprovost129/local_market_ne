from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("refunds", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="refundrequest",
            name="transfer_reversal_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="refundrequest",
            name="transfer_reversal_amount_cents",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="refundrequest",
            name="transfer_reversed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

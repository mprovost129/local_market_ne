from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_orderitem_is_tip"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderevent",
            name="meta",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

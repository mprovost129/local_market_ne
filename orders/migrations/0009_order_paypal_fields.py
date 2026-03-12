from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0008_alter_order_platform_fee_cents_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="paypal_capture_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="order",
            name="paypal_order_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
    ]

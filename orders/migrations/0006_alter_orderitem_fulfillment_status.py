from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0005_alter_order_payment_method"),
    ]

    operations = [
        migrations.AlterField(
            model_name="orderitem",
            name="fulfillment_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("ready", "Ready"),
                    ("out_for_delivery", "Out for delivery"),
                    ("picked_up", "Picked up"),
                    ("shipped", "Shipped"),
                    ("delivered", "Delivered"),
                    ("canceled", "Canceled"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
    ]

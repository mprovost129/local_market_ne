from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0004_rename_payments_sel_seller__180d7f_idx_payments_se_seller__605481_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SellerPayPalAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("paypal_merchant_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("paypal_account_email", models.EmailField(blank=True, default="", max_length=254)),
                ("partner_referral_tracking_id", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("payments_receivable", models.BooleanField(default=False)),
                ("primary_email_confirmed", models.BooleanField(default=False)),
                ("onboarding_started_at", models.DateTimeField(blank=True, null=True)),
                ("onboarding_completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="paypal_connect",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="sellerpaypalaccount",
            index=models.Index(fields=["paypal_merchant_id"], name="payments_se_paypal__d6d212_idx"),
        ),
        migrations.AddIndex(
            model_name="sellerpaypalaccount",
            index=models.Index(
                fields=["payments_receivable", "primary_email_confirmed"],
                name="payments_se_payment_0f2626_idx",
            ),
        ),
    ]

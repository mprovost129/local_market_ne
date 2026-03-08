from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_rename_accounts_pro_is_age_1e8d51_idx_accounts_pr_is_age__21ff69_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="seller_prohibited_items_ack",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="profile",
            name="seller_prohibited_items_ack_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_profile_storefront_layout"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="show_business_address_public",
            field=models.BooleanField(
                default=False,
                help_text="If enabled, your business address is shown publicly on your storefront/listings.",
            ),
        ),
    ]

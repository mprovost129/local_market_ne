from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_profile_show_business_address_public"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="private_geo_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="private_latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text="Private seller latitude for internal geo matching. Never shown publicly.",
                max_digits=9,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="private_longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text="Private seller longitude for internal geo matching. Never shown publicly.",
                max_digits=9,
                null=True,
            ),
        ),
    ]

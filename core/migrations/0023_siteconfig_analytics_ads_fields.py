from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_siteconfig_seo_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="ga_measurement_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional GA4 Measurement ID (e.g., G-XXXX). Leave blank to disable.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="adsense_enabled",
            field=models.BooleanField(
                default=False,
                help_text="If enabled, inject Google AdSense script sitewide.",
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="adsense_client_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="AdSense client id (e.g., ca-pub-...). Used only if AdSense is enabled.",
                max_length=64,
            ),
        ),
    ]

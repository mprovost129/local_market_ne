from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_siteconfig_analytics_ads_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="seller_requires_age_18",
            field=models.BooleanField(
                default=True,
                help_text="If enabled, sellers must confirm they are 18+ before starting Stripe onboarding.",
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="seller_prohibited_items_notice",
            field=models.CharField(
                blank=True,
                default="No tobacco, alcohol, or firearms are allowed on Local Market NE.",
                help_text="Shown to sellers during onboarding as a reminder of prohibited items.",
                max_length=240,
            ),
        ),
    ]

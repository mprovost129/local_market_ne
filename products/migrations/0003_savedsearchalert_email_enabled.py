from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0002_savedsearchalert"),
    ]

    operations = [
        migrations.AddField(
            model_name="savedsearchalert",
            name="email_enabled",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]

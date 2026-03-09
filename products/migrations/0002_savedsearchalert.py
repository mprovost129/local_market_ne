from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SavedSearchAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("GOOD", "Products"), ("SERVICE", "Services")], db_index=True, max_length=10)),
                ("query", models.CharField(blank=True, default="", max_length=200)),
                ("category_id_filter", models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ("zip_prefix", models.CharField(blank=True, db_index=True, default="", max_length=5)),
                ("radius_miles", models.PositiveIntegerField(default=0)),
                ("sort", models.CharField(blank=True, default="new", max_length=24)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("last_notified_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="saved_search_alerts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="savedsearchalert",
            index=models.Index(fields=["user", "kind", "is_active", "created_at"], name="products_sa_user_id_7a3dd8_idx"),
        ),
        migrations.AddIndex(
            model_name="savedsearchalert",
            index=models.Index(fields=["kind", "is_active", "last_notified_at"], name="products_sa_kind_9de24b_idx"),
        ),
    ]

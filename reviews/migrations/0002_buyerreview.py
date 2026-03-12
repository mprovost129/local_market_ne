from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0009_order_paypal_fields"),
        ("reviews", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BuyerReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "rating",
                    models.PositiveSmallIntegerField(
                        help_text="1-5 stars",
                        validators=[MinValueValidator(1), MaxValueValidator(5)],
                    ),
                ),
                ("title", models.CharField(blank=True, default="", max_length=120)),
                ("body", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "buyer",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="buyer_reviews_received",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="buyer_reviews",
                        to="orders.order",
                    ),
                ),
                (
                    "seller",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="buyer_reviews_written",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="buyerreview",
            constraint=models.UniqueConstraint(
                fields=("seller", "buyer", "order"),
                name="uniq_buyer_review_per_order",
            ),
        ),
        migrations.AddIndex(
            model_name="buyerreview",
            index=models.Index(fields=["buyer", "created_at"], name="reviews_buy_buyer_i_6f32d4_idx"),
        ),
        migrations.AddIndex(
            model_name="buyerreview",
            index=models.Index(fields=["seller", "created_at"], name="reviews_buy_seller__7dce18_idx"),
        ),
        migrations.AddIndex(
            model_name="buyerreview",
            index=models.Index(fields=["rating"], name="reviews_buy_rating_93c71f_idx"),
        ),
    ]

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Product(models.Model):
    """A seller listing.

    LocalMarketNE v1 supports:
    - GOOD: physical goods (pickup / seller delivery / optional shipping)
    - SERVICE: request-to-book services (appointments), optional Stripe deposit
    """

    if TYPE_CHECKING:
        images: models.Manager["ProductImage"]
        engagement_events: models.Manager["ProductEngagementEvent"]

    class Kind(models.TextChoices):
        GOOD = "GOOD", "Product"
        SERVICE = "SERVICE", "Service"

    id = models.BigAutoField(primary_key=True)

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="products",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.GOOD, db_index=True)

    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, blank=True)
    slug_is_manual = models.BooleanField(
        default=False,
        help_text="If checked, slug will not auto-update when the title changes.",
    )

    short_description = models.CharField(max_length=280, blank=True, default="")
    description = models.TextField(blank=True, default="")

    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        related_name="products",
    )
    subcategory = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        related_name="products_subcategory",
        null=True,
        blank=True,
        help_text="Optional subcategory under the main category.",
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Full price for this product/service.",
    )
    is_free = models.BooleanField(default=False)

    # Draft-first default
    is_active = models.BooleanField(default=False, db_index=True)

    is_featured = models.BooleanField(default=False, db_index=True)
    is_trending = models.BooleanField(default=False, db_index=True)

    # -------------------------
    # Goods (physical)
    # -------------------------
    stock_qty = models.PositiveIntegerField(
        default=0,
        help_text="Available quantity for products. Set 0 to indicate out of stock (unless made-to-order).",
    )
    is_made_to_order = models.BooleanField(
        default=False,
        help_text="If enabled, buyers can purchase even when stock is 0 and seller will fulfill later.",
    )
    lead_time_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Estimated days to fulfill after purchase (for made-to-order items).",
    )

    # Fulfillment options (Goods)
    fulfillment_pickup_enabled = models.BooleanField(
        default=True,
        help_text="If enabled, buyers can choose pickup for this product.",
    )
    fulfillment_delivery_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, seller offers local delivery for this product.",
    )
    fulfillment_shipping_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, seller is willing to ship this product (optional in v1).",
    )
    pickup_instructions = models.TextField(
        blank=True,
        default="",
        help_text="Shown to buyers after purchase when pickup is selected.",
    )
    delivery_radius_miles = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="If delivery is enabled, maximum delivery radius in miles (optional).",
    )
    delivery_fee_cents = models.PositiveIntegerField(
        default=0,
        help_text="If delivery is enabled, optional delivery fee in cents.",
    )
    shipping_fee_cents = models.PositiveIntegerField(
        default=0,
        help_text="If shipping is enabled, optional shipping fee in cents.",
    )

    # -------------------------
    # Services (appointments)
    # -------------------------
    service_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Service duration in minutes (15-minute increments).",
    )
    service_cancellation_policy = models.TextField(
        blank=True,
        default="",
        help_text="Shown to buyers during booking/checkout.",
    )

    service_cancellation_window_hours = models.PositiveIntegerField(
        default=0,
        help_text="If > 0, buyer cannot cancel within this many hours of the appointment start.",
    )
    service_deposit_cents = models.PositiveIntegerField(
        default=0,
        help_text="Optional deposit collected via Stripe at checkout (in cents). 0 disables deposits.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["seller", "slug"], name="uniq_product_slug_per_seller"),
        ]
        indexes = [
            models.Index(fields=["kind", "is_active", "created_at"]),
            models.Index(fields=["slug"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("products:detail", args=[self.pk, self.slug])

    @property
    def primary_image(self):
        img = self.images.filter(is_primary=True).order_by("sort_order", "created_at").first()
        if img:
            return img
        return self.images.order_by("sort_order", "created_at").first()

    def clean(self):
        super().clean()

        if self.is_free:
            self.price = Decimal("0.00")

        # Category/type compatibility (best-effort)
        if self.category_id:
            try:
                cat_type = getattr(self.category, "type", "")
                if self.kind == self.Kind.GOOD and cat_type and cat_type != "GOOD":
                    raise ValidationError({"category": "Category type must be Goods for products."})
                if self.kind == self.Kind.SERVICE and cat_type and cat_type != "SERVICE":
                    raise ValidationError({"category": "Category type must be Services for service listings."})
            except Exception:
                pass

        if self.kind == self.Kind.GOOD:
            if not (
                self.fulfillment_pickup_enabled
                or self.fulfillment_delivery_enabled
                or self.fulfillment_shipping_enabled
            ):
                raise ValidationError("At least one fulfillment method must be enabled for a product.")

            if self.is_made_to_order and not self.lead_time_days:
                raise ValidationError({"lead_time_days": "Lead time is required for made-to-order items."})

        if self.kind == self.Kind.SERVICE:
            if not self.service_duration_minutes:
                raise ValidationError({"service_duration_minutes": "Service duration is required for services."})
            if int(self.service_duration_minutes) % 15 != 0:
                raise ValidationError({"service_duration_minutes": "Service duration must be in 15-minute increments."})

    def save(self, *args, **kwargs):
        if not self.slug_is_manual:
            base = slugify(self.title or "")[:160] or "listing"
            if not self.slug or (self.pk and self.slug and self.slug != base):
                self.slug = base
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Compatibility aliases (older templates/views used these names)
    # ------------------------------------------------------------------

    @property
    def pickup_enabled(self) -> bool:
        return bool(self.fulfillment_pickup_enabled)

    @property
    def delivery_enabled(self) -> bool:
        return bool(self.fulfillment_delivery_enabled)

    @property
    def shipping_enabled(self) -> bool:
        return bool(self.fulfillment_shipping_enabled)


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/images/")
    alt_text = models.CharField(max_length=160, blank=True, default="")
    is_primary = models.BooleanField(
        default=False,
        help_text="Primary image used for cards/OG where applicable.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]
        indexes = [models.Index(fields=["product", "sort_order"])]

    def __str__(self) -> str:
        return f"{self.product_id} image"


class ProductEngagementEvent(models.Model):
    class Kind(models.TextChoices):
        VIEW = "VIEW", "View"
        ADD_TO_CART = "ADD_TO_CART", "Add to cart"
        CLICK = "CLICK", "Click"
        REVIEW = "REVIEW", "Review"
        PURCHASE = "PURCHASE", "Purchase"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="engagement_events")
    kind = models.CharField(max_length=24, choices=Kind.choices, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    session_key = models.CharField(
        max_length=80,
        blank=True,
        default="",
        db_index=True,
        help_text="Anonymous session key (used for throttling/analytics when user is not logged in).",
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["product", "kind", "created_at"]),
            models.Index(fields=["kind", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind} {self.product_id}"


class SavedSearchAlert(models.Model):
    class Kind(models.TextChoices):
        GOOD = "GOOD", "Products"
        SERVICE = "SERVICE", "Services"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_search_alerts",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, db_index=True)
    query = models.CharField(max_length=200, blank=True, default="")
    category_id_filter = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    zip_prefix = models.CharField(max_length=5, blank=True, default="", db_index=True)
    radius_miles = models.PositiveIntegerField(default=0)
    sort = models.CharField(max_length=24, blank=True, default="new")
    email_enabled = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_notified_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "kind", "is_active", "created_at"]),
            models.Index(fields=["kind", "is_active", "last_notified_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"SavedSearchAlert<{self.user_id}:{self.kind}>"

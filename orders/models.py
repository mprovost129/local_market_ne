# orders/models.py
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from notifications.services import notify_email_and_in_app




# --- URL helpers (used by email templates / other apps) ---

def _site_base_url() -> str:
    base = (getattr(settings, "SITE_BASE_URL", "") or "").strip().rstrip("/")
    if base:
        return base
    return "http://localhost:8000"


def _absolute_static_url(path: str) -> str:
    base = _site_base_url().rstrip("/")
    static_url = (getattr(settings, "STATIC_URL", "/static/") or "/static/").strip()
    if not static_url.startswith("/"):
        static_url = f"/{static_url}"
    if not static_url.endswith("/"):
        static_url = f"{static_url}/"
    return f"{base}{static_url}{path.lstrip('/')}"

@dataclass(frozen=True)
class LineItem:
    name: str
    quantity: int
    unit_price_cents: int
    total_cents: int


class Order(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"
        REFUNDED = "refunded", "Refunded"

    class Kind(models.TextChoices):
        DIGITAL = "digital", "Digital only"
        PHYSICAL = "physical", "Physical only"
        MIXED = "mixed", "Mixed (digital + physical)"

    class PaymentMethod(models.TextChoices):
        STRIPE = "stripe", "Stripe"
        VENMO = "venmo", "Venmo"
        PAYPAL = "paypal", "PayPal"
        ZELLE = "zelle", "Zelle"
        CASHAPP = "cashapp", "Cash App"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Buyer identity (registered or guest)
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Registered buyer. Null means guest checkout.",
    )
    guest_email = models.EmailField(blank=True, default="")
    order_token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)

    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT, db_index=True)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.PHYSICAL)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.STRIPE, db_index=True)

    currency = models.CharField(max_length=8, default="usd")

    subtotal_cents = models.PositiveIntegerField(default=0)
    tax_cents = models.PositiveIntegerField(default=0)
    shipping_cents = models.PositiveIntegerField(default=0)
    total_cents = models.PositiveIntegerField(default=0)

    marketplace_sales_percent_snapshot = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Marketplace % cut captured at order creation time.",
    )
    platform_fee_cents_snapshot = models.PositiveIntegerField(
        default=0,
        help_text="Flat marketplace service fee snapshot captured at order creation time.",
    )

    # Stripe
    stripe_session_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    # PayPal (native in-app checkout)
    paypal_order_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    paypal_capture_id = models.CharField(max_length=255, blank=True, default="")

    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Shipping snapshot
    shipping_name = models.CharField(max_length=255, blank=True, default="")
    shipping_phone = models.CharField(max_length=64, blank=True, default="")
    shipping_line1 = models.CharField(max_length=255, blank=True, default="")
    shipping_line2 = models.CharField(max_length=255, blank=True, default="")
    shipping_city = models.CharField(max_length=120, blank=True, default="")
    shipping_state = models.CharField(max_length=120, blank=True, default="")
    shipping_postal_code = models.CharField(max_length=32, blank=True, default="")
    shipping_country = models.CharField(max_length=2, blank=True, default="")

    # Pack Q inventory reservation flags
    inventory_reserved = models.BooleanField(
        default=False,
        help_text="True if stock was reserved/decremented when the order was created (PENDING).",
    )
    inventory_released = models.BooleanField(
        default=False,
        help_text="True if reserved stock was released back (canceled/expired).",
    )

    # Pack P: off-platform checkout note + timestamp
    offplatform_note = models.TextField(blank=True, default="", help_text="Optional buyer note when marking off-platform payment.")
    offplatform_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = (
            ("can_retry_payouts", "Can retry payout transfers"),
        )
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["stripe_session_id"]),
            models.Index(fields=["payment_method"]),
        ]

    def __str__(self) -> str:
        return f"Order {self.pk} ({self.status})"

    @property
    def is_guest(self) -> bool:
        return self.buyer_id is None

    @property
    def buyer_email(self) -> str:
        if self.buyer and getattr(self.buyer, "email", ""):
            return self.buyer.email
        return self.guest_email

    @property
    def requires_shipping(self) -> bool:
        for item in self.items.all():
            if item.is_service or item.is_tip:
                continue
            if item.requires_shipping:
                return True
        return False

    def recompute_totals(self) -> None:
        subtotal = 0
        shipping = 0
        tax = 0
        for item in self.items.all():
            subtotal += int(item.line_total_cents)
            shipping += int(item.shipping_fee_cents_snapshot or 0) + int(item.delivery_fee_cents_snapshot or 0)
            tax += int(item.tax_cents or 0)

        self.subtotal_cents = max(0, subtotal)
        self.shipping_cents = max(0, shipping)
        self.tax_cents = max(0, tax)
        platform_fee = max(0, int(self.platform_fee_cents_snapshot or 0))
        self.total_cents = max(0, self.subtotal_cents + self.shipping_cents + self.tax_cents + platform_fee)

    # ------------------------------------------------------------------
    # Pack AH: invariants + status transition guardrails
    # ------------------------------------------------------------------

    _IMMUTABLE_FINANCIAL_FIELDS = {
        "subtotal_cents",
        "tax_cents",
        "shipping_cents",
        "total_cents",
        "currency",
        "marketplace_sales_percent_snapshot",
        "platform_fee_cents_snapshot",
    }

    _ALLOWED_STATUS_TRANSITIONS = {
        Status.DRAFT: {Status.PENDING, Status.AWAITING_PAYMENT, Status.CANCELED},
        Status.PENDING: {Status.AWAITING_PAYMENT, Status.PAID, Status.CANCELED},
        Status.AWAITING_PAYMENT: {Status.PAID, Status.CANCELED},
        Status.PAID: {Status.REFUNDED},
        Status.CANCELED: set(),
        Status.REFUNDED: set(),
    }

    def _enforce_status_transition(self, old_status: str, new_status: str) -> None:
        if not old_status or not new_status or old_status == new_status:
            return
        allowed = self._ALLOWED_STATUS_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            raise ValueError(f"Invalid order status transition: {old_status} -> {new_status}")

    def _enforce_financial_immutability(self, old: "Order") -> None:
        # Buyers can still adjust fulfillment/tips while order is pre-payment.
        if not old or old.status in {self.Status.DRAFT, self.Status.PENDING, self.Status.AWAITING_PAYMENT}:
            return
        for fname in self._IMMUTABLE_FINANCIAL_FIELDS:
            if getattr(old, fname) != getattr(self, fname):
                raise ValueError(f"Order financial field '{fname}' is immutable after payment/cancel/refund")

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old = (
                    Order.objects.filter(pk=self.pk)
                    .only("status", *self._IMMUTABLE_FINANCIAL_FIELDS)
                    .first()
                )
            except Exception:
                old = None
            if old:
                self._enforce_status_transition(old.status, self.status)
                self._enforce_financial_immutability(old)
        return super().save(*args, **kwargs)

    @transaction.atomic
    def mark_paid(self, *, payment_intent_id: str = "", session_id: str = "", note: str = "") -> None:
        if self.status == self.Status.PAID:
            return

        payment_intent_id = (payment_intent_id or "").strip()
        session_id = (session_id or "").strip()

        # Pack AH: Stripe ID consistency check
        if self.payment_method == self.PaymentMethod.STRIPE:
            if payment_intent_id == "FREE":
                if not self.stripe_session_id:
                    self.stripe_session_id = "FREE"
                if not self.stripe_payment_intent_id:
                    self.stripe_payment_intent_id = "FREE"
            else:
                if session_id and not self.stripe_session_id:
                    self.stripe_session_id = session_id
                if payment_intent_id and not self.stripe_payment_intent_id:
                    self.stripe_payment_intent_id = payment_intent_id
                if not (self.stripe_session_id or "").strip() or not (self.stripe_payment_intent_id or "").strip():
                    raise ValueError("Stripe-paid order missing session/payment_intent IDs")

        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at", "stripe_session_id", "stripe_payment_intent_id", "updated_at"])

        try:
            OrderEvent.objects.create(order=self, type=OrderEvent.Type.PAID, message=(note or ""))
        except Exception:
            pass

        # Keep seller ledger in sync for payouts dashboard and reconciliation.
        try:
            from payments.services import ensure_sale_balance_entries_for_paid_order
            ensure_sale_balance_entries_for_paid_order(order=self)
        except Exception:
            pass

        # Create seller fulfillment tasks for any paid goods items (best-effort; idempotent).
        try:
            from .services import ensure_fulfillment_tasks_for_paid_order
            ensure_fulfillment_tasks_for_paid_order(order=self)
        except Exception:
            pass

        # Notify buyer (best-effort)
        if self.buyer and self.buyer_email:
            notify_email_and_in_app(
                user=self.buyer,
                kind="ORDER",
                email_subject="Order paid",
                email_template_html="emails/order_paid.html",
                context={"order": self, "buyer_email": self.buyer_email},
            )

    @transaction.atomic
    def mark_canceled(self, *, note: str = "") -> None:
        if self.status == self.Status.CANCELED:
            return

        self.status = self.Status.CANCELED
        self.save(update_fields=["status", "updated_at"])

        try:
            OrderEvent.objects.create(order=self, type=OrderEvent.Type.CANCELED, message=(note or ""))
        except Exception:
            pass

        if self.inventory_reserved and not self.inventory_released:
            from products.models import Product

            qty_by_product: dict[int, int] = {}
            for item in self.items.select_related("product").all():
                if item.is_service or item.is_tip:
                    continue
                product = getattr(item, "product", None)
                if not product:
                    continue
                if getattr(product, "kind", "") != Product.Kind.GOOD:
                    continue
                if getattr(product, "is_made_to_order", False):
                    continue
                qty_by_product[int(product.id)] = qty_by_product.get(int(product.id), 0) + int(item.quantity or 0)

            if qty_by_product:
                locked = {
                    int(p.id): p
                    for p in Product.objects.select_for_update().filter(id__in=list(qty_by_product.keys()))
                }
                for pid, qty in qty_by_product.items():
                    prod = locked.get(int(pid))
                    if not prod:
                        continue
                    prod.stock_qty = int(prod.stock_qty or 0) + int(qty or 0)
                    prod.save(update_fields=["stock_qty", "updated_at"] if hasattr(prod, "updated_at") else ["stock_qty"])

            self.inventory_released = True
            self.save(update_fields=["inventory_released", "updated_at"])

    def set_shipping_from_stripe(
        self,
        *,
        name: str = "",
        phone: str = "",
        line1: str = "",
        line2: str = "",
        city: str = "",
        state: str = "",
        postal_code: str = "",
        country: str = "",
    ) -> None:
        self.shipping_name = name or ""
        self.shipping_phone = phone or ""
        self.shipping_line1 = line1 or ""
        self.shipping_line2 = line2 or ""
        self.shipping_city = city or ""
        self.shipping_state = state or ""
        self.shipping_postal_code = postal_code or ""
        self.shipping_country = country or ""
        self.save(
            update_fields=[
                "shipping_name",
                "shipping_phone",
                "shipping_line1",
                "shipping_line2",
                "shipping_city",
                "shipping_state",
                "shipping_postal_code",
                "shipping_country",
                "updated_at",
            ]
        )


class OrderItem(models.Model):
    class FulfillmentMethod(models.TextChoices):
        PICKUP = "pickup", "Pickup"
        DELIVERY = "delivery", "Delivery"
        SHIPPING = "shipping", "Shipping"

    class FulfillmentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        PICKED_UP = "picked_up", "Picked up"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELED = "canceled", "Canceled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="order_items")
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sold_order_items")

    title_snapshot = models.CharField(max_length=255, blank=True, default="")
    sku_snapshot = models.CharField(max_length=80, blank=True, default="")
    unit_price_cents_snapshot = models.PositiveIntegerField(default=0)
    quantity = models.PositiveIntegerField(default=1)
    line_total_cents = models.PositiveIntegerField(default=0)

    # tax/shipping per line (if needed)
    tax_cents = models.PositiveIntegerField(default=0)

    # Snapshotted fee ledger
    marketplace_fee_cents = models.PositiveIntegerField(default=0)
    seller_net_cents = models.PositiveIntegerField(default=0)

    # v1 listing family flags
    is_service = models.BooleanField(default=False)

    # Pack AH: tip line support (tips are stored as separate OrderItem rows)
    is_tip = models.BooleanField(default=False)

    # Fulfillment snapshot fields (Pack P)
    fulfillment_mode_snapshot = models.CharField(max_length=20, default="pickup")
    delivery_fee_cents_snapshot = models.PositiveIntegerField(null=True, blank=True)
    shipping_fee_cents_snapshot = models.PositiveIntegerField(null=True, blank=True)
    pickup_instructions_snapshot = models.TextField(blank=True, default="")

    # Tracking fields (Pack P)
    tracking_carrier = models.CharField(max_length=32, blank=True, default="")
    tracking_number = models.CharField(max_length=64, blank=True, default="", db_index=True)
    tracking_url = models.URLField(blank=True, default="")

    fulfillment_status = models.CharField(max_length=16, choices=FulfillmentStatus.choices, default=FulfillmentStatus.PENDING, db_index=True)

    # Pack Q: lead time snapshot for made-to-order
    lead_time_days_snapshot = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["seller", "created_at"]),
            models.Index(fields=["fulfillment_status"]),
        ]

    def __str__(self) -> str:
        return f"Item {self.pk} ({self.product.pk})"

    # Compatibility helpers (older code paths used different attribute names)
    @property
    def unit_price_cents(self) -> int:
        return int(self.unit_price_cents_snapshot or 0)

    @property
    def fulfillment_method(self) -> str:
        return str(self.fulfillment_mode_snapshot or "pickup")

    @fulfillment_method.setter
    def fulfillment_method(self, value: str) -> None:
        self.fulfillment_mode_snapshot = (value or "").strip().lower() or "pickup"

    @property
    def requires_shipping(self) -> bool:
        return str(self.fulfillment_mode_snapshot or "").strip().lower() == "shipping"


class OrderEvent(models.Model):
    class Type(models.TextChoices):
        ORDER_CREATED = "order_created", "Order created"
        CHECKOUT_STARTED = "checkout_started", "Checkout started"
        STRIPE_SESSION_CREATED = "stripe_session_created", "Stripe_session_created"
        CHECKOUT_COMPLETED = "checkout_completed", "Checkout completed"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"
        REFUND_REQUESTED = "refund_requested", "Refund requested"
        REFUNDED = "refunded", "Refunded"
        TRANSFER_CREATED = "transfer_created", "Transfer created"
        TRANSFER_REVERSED = "transfer_reversed", "Transfer reversed"
        NOTE = "note", "Note"
        WARNING = "warning", "Warning"

    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    type = models.CharField(max_length=32, choices=Type.choices, db_index=True)
    message = models.TextField(blank=True, default="")
    # Optional structured metadata for ops/reconciliation (additive; safe default).
    # Example: {"seller_id": 123, "transfer_id": "tr_...", "amount_cents": 5000}
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["type", "created_at"]),
        ]


class SellerFulfillmentTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="fulfillment_tasks")
    order_item = models.OneToOneField(OrderItem, on_delete=models.CASCADE, related_name="fulfillment_task")

    is_done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["seller", "is_done", "created_at"]),
        ]


class StripeWebhookEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=255, db_index=True)
    livemode = models.BooleanField(default=False)

    raw_json = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, default="received", db_index=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        permissions = (
            ("can_reprocess_webhooks", "Can reprocess Stripe webhooks"),
        )
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]


class StripeWebhookDelivery(models.Model):
    id = models.BigAutoField(primary_key=True)
    webhook_event = models.ForeignKey(StripeWebhookEvent, on_delete=models.CASCADE, related_name="deliveries")

    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, related_name="stripe_webhook_deliveries")
    stripe_session_id = models.CharField(max_length=255, blank=True, default="", db_index=True)

    delivered_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=32, default="ok", db_index=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-delivered_at"]
        indexes = [
            models.Index(fields=["stripe_session_id", "delivered_at"]),
        ]

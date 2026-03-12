# payments/models.py
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.db import models
from django.utils import timezone


def _sync_profile_stripe_fields(*, user, stripe_account_id: str, onboarding_complete: bool) -> None:
    """
    Keep accounts.Profile legacy fields synced with payments.SellerStripeAccount.

    We intentionally avoid importing Profile directly to prevent circular imports.
    """
    try:
        Profile = apps.get_model("accounts", "Profile")
    except Exception:
        return

    if not user:
        return

    # Update only the two legacy fields; do not touch role flags here.
    try:
        Profile.objects.filter(user=user).update(
            stripe_account_id=stripe_account_id or "",
            stripe_onboarding_complete=onboarding_complete,
            updated_at=timezone.now(),
        )
    except Exception:
        # Best-effort; never break payments flow if profile update fails.
        return


class SellerStripeAccount(models.Model):
    """
    Stores Stripe Connect Express account linkage for a seller user.

    SOURCE OF TRUTH:
      - payments.SellerStripeAccount fields are authoritative
      - accounts.Profile.stripe_* fields are legacy mirrors for admin/UI convenience
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stripe_connect",
    )

    stripe_account_id = models.CharField(max_length=255, blank=True, default="", db_index=True)

    details_submitted = models.BooleanField(default=False)
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)

    onboarding_started_at = models.DateTimeField(null=True, blank=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_account_id"]),
            models.Index(fields=["details_submitted", "charges_enabled", "payouts_enabled"]),
        ]

    def __str__(self) -> str:
        return f"SellerStripeAccount<{self.user.id}> {self.stripe_account_id or 'unlinked'}"

    @property
    def is_ready(self) -> bool:
        return bool(self.stripe_account_id) and self.details_submitted and self.charges_enabled and self.payouts_enabled

    def _sync_profile(self) -> None:
        _sync_profile_stripe_fields(
            user=self.user,
            stripe_account_id=self.stripe_account_id or "",
            onboarding_complete=self.is_ready,
        )

    def mark_onboarding_started(self) -> None:
        changed = False
        if not self.onboarding_started_at:
            self.onboarding_started_at = timezone.now()
            changed = True

        if changed:
            self.save(update_fields=["onboarding_started_at", "updated_at"])

        # Always mirror current account id + completion flag to Profile.
        self._sync_profile()

    def mark_onboarding_completed_if_ready(self) -> None:
        changed = False
        if self.is_ready and not self.onboarding_completed_at:
            self.onboarding_completed_at = timezone.now()
            changed = True

        if changed:
            self.save(update_fields=["onboarding_completed_at", "updated_at"])

        # Always mirror current truth to Profile.
        self._sync_profile()


class SellerPayPalAccount(models.Model):
    """
    Stores PayPal partner onboarding linkage for a seller user.

    This is separate from profile.paypal_me_url (which is only an optional
    off-platform handle and not a connected marketplace payout account).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="paypal_connect",
    )

    # Set after PayPal seller onboarding succeeds.
    paypal_merchant_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    paypal_account_email = models.EmailField(blank=True, default="")

    # We store the latest referral tracking id for diagnostics/webhook correlation.
    partner_referral_tracking_id = models.CharField(max_length=64, blank=True, default="", db_index=True)

    # Best-effort capability flags from merchant-integrations API.
    payments_receivable = models.BooleanField(default=False)
    primary_email_confirmed = models.BooleanField(default=False)

    onboarding_started_at = models.DateTimeField(null=True, blank=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["paypal_merchant_id"]),
            models.Index(fields=["payments_receivable", "primary_email_confirmed"]),
        ]

    def __str__(self) -> str:
        mid = self.paypal_merchant_id or "unlinked"
        return f"SellerPayPalAccount<{self.user.id}> {mid}"

    @property
    def is_ready(self) -> bool:
        return bool(self.paypal_merchant_id) and bool(self.payments_receivable)

    def mark_onboarding_started(self, *, tracking_id: str = "") -> None:
        changed = False
        if not self.onboarding_started_at:
            self.onboarding_started_at = timezone.now()
            changed = True
        if tracking_id and self.partner_referral_tracking_id != tracking_id:
            self.partner_referral_tracking_id = tracking_id[:64]
            changed = True
        if changed:
            self.save(update_fields=["onboarding_started_at", "partner_referral_tracking_id", "updated_at"])

    def mark_onboarding_completed_if_ready(self) -> None:
        if self.is_ready and not self.onboarding_completed_at:
            self.onboarding_completed_at = timezone.now()
            self.save(update_fields=["onboarding_completed_at", "updated_at"])


class SellerFeeWaiver(models.Model):
    """
    Per-seller marketplace fee waiver window.
    During the window, marketplace cut is 0% (seller still pays Stripe fees).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fee_waiver",
    )

    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["ends_at"]),
        ]

    def __str__(self) -> str:
        return f"SellerFeeWaiver<{self.user.id}> {self.starts_at.date()} → {self.ends_at.date()}"

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return self.starts_at <= now < self.ends_at

    @classmethod
    def ensure_for_seller(cls, *, user, waiver_days: int) -> "SellerFeeWaiver":
        """
        Create waiver if missing. Never shortens an existing waiver.
        """
        waiver_days = max(0, min(int(waiver_days or 0), 365))
        if (obj := cls.objects.filter(user=user).first()):
            return obj

        starts = timezone.now()
        ends = starts + timedelta(days=waiver_days)
        return cls.objects.create(user=user, starts_at=starts, ends_at=ends)

    def extend_by_days(self, *, days: int) -> None:
        """
        Extend waiver window by N days from current `ends_at`.
        Never shortens the window.
        """
        d = max(0, int(days or 0))
        if d <= 0:
            return
        self.ends_at = self.ends_at + timedelta(days=d)
        self.save(update_fields=["ends_at", "updated_at"])


class SellerFeePlan(models.Model):
    """
    Per-seller marketplace fee customization.

    Precedence in fee calculation:
      1) Active SellerFeePlan (this model)
      2) Active SellerFeeWaiver (0%)
      3) SiteConfig marketplace_sales_percent
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fee_plan",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="If disabled, this fee plan is ignored and default/waiver logic applies.",
    )
    starts_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional plan start. Leave blank for immediate effect.",
    )
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional plan end. Leave blank for no expiration.",
    )

    # If set, this exact percent is used (0 = fully comped, 10 = 10% platform fee)
    custom_sales_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional fixed platform fee percent for this seller. Overrides discount when set.",
    )

    # Applied only when custom_sales_percent is empty.
    discount_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Percent discount off global platform fee (0-100). 100 = fully comped.",
    )

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
        ]

    def __str__(self) -> str:
        return f"SellerFeePlan<{self.user_id}> active={self.is_active}"

    @property
    def is_currently_active(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now >= self.ends_at:
            return False
        return True

    def clean(self) -> None:
        try:
            if self.custom_sales_percent is not None:
                pct = Decimal(self.custom_sales_percent)
                if pct < 0:
                    self.custom_sales_percent = Decimal("0.00")
                elif pct > 100:
                    self.custom_sales_percent = Decimal("100.00")
        except Exception:
            self.custom_sales_percent = Decimal("0.00")

        try:
            d = Decimal(self.discount_percent or Decimal("0.00"))
            if d < 0:
                self.discount_percent = Decimal("0.00")
            elif d > 100:
                self.discount_percent = Decimal("100.00")
        except Exception:
            self.discount_percent = Decimal("0.00")

    def save(self, *args, **kwargs) -> None:
        self.clean()
        super().save(*args, **kwargs)


class SellerBalanceEntry(models.Model):
    """
    Append-only ledger for seller balances.

    amount_cents:
      > 0  => platform owes seller
      < 0  => seller owes platform
    """

    class Reason(models.TextChoices):
        SALE = "sale", "Sale (order paid)"
        PAYOUT = "payout", "Payout"
        REFUND = "refund", "Refund"
        CHARGEBACK = "chargeback", "Chargeback"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="balance_entries",
    )

    amount_cents = models.IntegerField(
        help_text="Signed cents. Positive = owed to seller, negative = seller owes platform."
    )

    reason = models.CharField(max_length=32, choices=Reason.choices)

    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seller_balance_entries",
    )

    order_item = models.ForeignKey(
        "orders.OrderItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seller_balance_entries",
    )

    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["seller", "-created_at"]),
            models.Index(fields=["reason", "-created_at"]),
        ]
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["seller", "order", "reason"],
                name="uniq_seller_order_reason",
            )
        ]

    def __str__(self) -> str:
        return f"{self.seller.id}: {self.amount_cents} ({self.reason})"


class SellerFeeInvoice(models.Model):
    """
    Tracks marketplace fees owed by sellers for off-platform-paid orders.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PAID = "paid", "Paid"
        VOID = "void", "Voided"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fee_invoices",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="seller_fee_invoices",
    )
    amount_cents = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    payment_method_snapshot = models.CharField(max_length=20, blank=True, default="")
    stripe_session_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["seller", "status", "-created_at"]),
            models.Index(fields=["order", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["seller", "order"], name="uniq_seller_fee_invoice_per_order"),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"SellerFeeInvoice<{self.seller_id}:{self.order_id}> ${self.amount_cents/100:.2f} {self.status}"

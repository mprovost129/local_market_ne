from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class AppointmentRequest(models.Model):
    """A buyer-initiated request to book a service listing.

    Lifecycle (v1):
    - REQUESTED: buyer requested a slot
    - DEPOSIT_PENDING: seller accepted; deposit required and created
    - DEPOSIT_PAID: deposit order is paid (Stripe webhook)
    - SCHEDULED: final appointment confirmed/scheduled (defaults to requested slot)
    - COMPLETED: seller marked complete
    - CANCELED: buyer or seller canceled
    - DECLINED: seller declined
    """

    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Requested"
        DEPOSIT_PENDING = "DEPOSIT_PENDING", "Deposit pending"
        DEPOSIT_PAID = "DEPOSIT_PAID", "Deposit paid"
        AWAITING_BUYER_CONFIRMATION = "AWAITING_BUYER_CONFIRMATION", "Awaiting buyer confirmation"
        SCHEDULED = "SCHEDULED", "Scheduled"
        DECLINED = "DECLINED", "Declined"
        CANCELED = "CANCELED", "Canceled"
        COMPLETED = "COMPLETED", "Completed"

    service = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="appointment_requests")
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="appointment_requests")
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="appointment_requests_received"
    )

    requested_start = models.DateTimeField()
    requested_end = models.DateTimeField()

    # Seller-confirmed schedule (defaults to requested_* when scheduled)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    scheduled_notes = models.TextField(blank=True, default="")

    # Buyer confirmation (required after seller reschedule)
    buyer_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Reminder tracking (cron/management command driven)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    message = models.TextField(blank=True, default="")

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.REQUESTED)

    # Snapshot key service terms at request time
    duration_minutes_snapshot = models.PositiveIntegerField(default=0)
    deposit_cents_snapshot = models.PositiveIntegerField(default=0)
    cancellation_policy_snapshot = models.TextField(blank=True, default="")
    cancellation_window_hours_snapshot = models.PositiveIntegerField(default=0)

    # Optional link once a deposit order is created/paid
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments"
    )

    accepted_at = models.DateTimeField(null=True, blank=True)
    deposit_paid_at = models.DateTimeField(null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["seller", "status", "created_at"]),
            models.Index(fields=["buyer", "status", "created_at"]),
            models.Index(fields=["service", "status", "created_at"]),
        ]
        ordering = ["-created_at"]

    @property
    def needs_buyer_confirmation(self) -> bool:
        return self.status == self.Status.AWAITING_BUYER_CONFIRMATION

    @property
    def effective_start(self):
        return self.scheduled_start or self.requested_start

    @property
    def effective_end(self):
        return self.scheduled_end or self.requested_end

    def clean(self):
        super().clean()
        if self.service_id and getattr(self.service, "kind", None) != "SERVICE":
            raise ValidationError("Appointment requests can only be created for service listings.")
        if self.requested_end and self.requested_start and self.requested_end <= self.requested_start:
            raise ValidationError("End time must be after start time.")
        if self.scheduled_start and self.scheduled_end and self.scheduled_end <= self.scheduled_start:
            raise ValidationError("Scheduled end must be after scheduled start.")

    def save(self, *args, **kwargs):
        # Snapshot service fields on create
        if not self.pk and self.service_id:
            dur = int(getattr(self.service, "service_duration_minutes", 0) or 0)
            dep = int(getattr(self.service, "service_deposit_cents", 0) or 0)
            pol = str(getattr(self.service, "service_cancellation_policy", "") or "")
            win = int(getattr(self.service, "service_cancellation_window_hours", 0) or 0)
            self.duration_minutes_snapshot = dur
            self.deposit_cents_snapshot = dep
            self.cancellation_policy_snapshot = pol
            self.cancellation_window_hours_snapshot = win
        return super().save(*args, **kwargs)

    @property
    def requires_deposit(self) -> bool:
        return int(self.deposit_cents_snapshot or 0) > 0

    @property
    def deposit_amount_display(self) -> str:
        cents = int(self.deposit_cents_snapshot or 0)
        return f"${cents/100:.2f}"

    @property
    def is_pending(self) -> bool:
        return self.status in {self.Status.REQUESTED, self.Status.DEPOSIT_PENDING, self.Status.DEPOSIT_PAID}

    @property
    def is_scheduled(self) -> bool:
        return self.status == self.Status.SCHEDULED

    def schedule_default(self, note: str = "") -> None:
        """Idempotently set scheduled_* fields to requested_* and mark as SCHEDULED."""
        if not self.scheduled_start:
            self.scheduled_start = self.requested_start
        if not self.scheduled_end:
            self.scheduled_end = self.requested_end
        if note and not self.scheduled_notes:
            self.scheduled_notes = note
        if not self.scheduled_at:
            self.scheduled_at = timezone.now()
        self.status = self.Status.SCHEDULED


class AvailabilityRule(models.Model):
    """Weekly availability window for a seller."""

    class Weekday(models.IntegerChoices):
        MON = 0, "Mon"
        TUE = 1, "Tue"
        WED = 2, "Wed"
        THU = 3, "Thu"
        FRI = 4, "Fri"
        SAT = 5, "Sat"
        SUN = 6, "Sun"

    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="availability_rules")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices, db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["seller", "is_active", "weekday"]),
        ]
        ordering = ["seller_id", "weekday", "start_time"]

    def clean(self):
        super().clean()
        if self.end_time and self.start_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

    def __str__(self) -> str:
        return f"{self.get_weekday_display()} {self.start_time}-{self.end_time}"


class AvailabilityException(models.Model):
    """One-off overrides for a given date."""

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="availability_exceptions"
    )
    date = models.DateField(db_index=True)
    is_closed = models.BooleanField(default=False)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    note = models.CharField(max_length=160, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["seller", "date"], name="uniq_availability_exception_per_seller_date"),
        ]
        indexes = [
            models.Index(fields=["seller", "date"]),
        ]
        ordering = ["-date"]

    def clean(self):
        super().clean()
        if self.is_closed:
            return
        if (self.start_time and not self.end_time) or (self.end_time and not self.start_time):
            raise ValidationError("Provide both start and end time, or mark as closed.")
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

    def __str__(self) -> str:
        if self.is_closed:
            return f"{self.date} closed"
        if self.start_time and self.end_time:
            return f"{self.date} {self.start_time}-{self.end_time}"
        return f"{self.date} override"

from __future__ import annotations

from datetime import date as date_cls, datetime

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from products.models import Product

from .services import compute_available_slots


class AppointmentRequestForm(forms.Form):
    requested_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Select a date.",
    )
    requested_time = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select an available start time.",
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control", "placeholder": "Optional message for the seller..."}),
    )

    def __init__(self, *args, service: Product, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = service

        # If the user has already picked a date (POST or GET), prefill choices.
        day = None
        raw_date = None
        if self.data:
            raw_date = self.data.get("requested_date")
        if raw_date:
            try:
                day = date_cls.fromisoformat(raw_date)
            except Exception:
                day = None

        if day:
            slots = compute_available_slots(service=service, day=day)
            choices = [(s.start.strftime("%H:%M"), s.start.strftime("%I:%M %p").lstrip("0")) for s in slots]
        else:
            choices = []

        self.fields["requested_time"].choices = choices

    def clean(self):
        cleaned = super().clean()
        if self.service.kind != Product.Kind.SERVICE:
            raise ValidationError("This listing is not a service.")

        day = cleaned.get("requested_date")
        t = cleaned.get("requested_time")
        if not day or not t:
            return cleaned

        try:
            hour, minute = t.split(":")
            dt = datetime.combine(day, datetime.min.time()).replace(hour=int(hour), minute=int(minute))
        except Exception:
            raise ValidationError("Please choose a valid time.")

        tz = timezone.get_current_timezone()
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, tz)

        # Validate dt is in available slots
        slots = compute_available_slots(service=self.service, day=day)
        allowed = {s.start for s in slots}
        if dt not in allowed:
            raise ValidationError("That time is no longer available. Please choose another slot.")

        cleaned["requested_start"] = dt
        return cleaned

class AppointmentRescheduleForm(forms.Form):
    """Seller rescheduling form for an existing AppointmentRequest."""

    scheduled_start = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
        help_text="Choose the new start date/time.",
    )
    scheduled_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control", "placeholder": "Optional note to the buyer..."}),
    )

    def __init__(self, *args, ar, **kwargs):
        super().__init__(*args, **kwargs)
        self.ar = ar

    def clean_scheduled_start(self):
        dt = self.cleaned_data["scheduled_start"]
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        if dt <= timezone.now():
            raise ValidationError("Scheduled start must be in the future.")
        return dt

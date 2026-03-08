from __future__ import annotations

from typing import Mapping

from django.urls import reverse
from django.utils import timezone

from notifications.services import notify_email_and_in_app
from .models import AppointmentRequest


def _status_label(ar: AppointmentRequest) -> str:
    try:
        return ar.get_status_display()
    except Exception:
        return str(ar.status)


def _action_url_for_user(ar: AppointmentRequest, *, for_seller: bool) -> str:
    if for_seller:
        return reverse("appointments:seller_requests")
    return reverse("appointments:buyer_requests")


def notify_appointment_event(
    *,
    ar: AppointmentRequest,
    recipient_user,
    event_key: str,
    actor_label: str,
    extra_context: Mapping[str, object] | None = None,
) -> None:
    """Send email + in-app notification for appointment lifecycle changes.

    event_key is a short machine key like:
      - requested
      - accepted
      - declined
      - deposit_pending
      - deposit_paid
      - scheduled
      - rescheduled
      - canceled
      - completed
    """
    ctx = {
        "ar": ar,
        "event_key": event_key,
        "status_label": _status_label(ar),
        "actor_label": actor_label,
        "now": timezone.now(),
    }
    if extra_context:
        ctx.update(dict(extra_context))

    # Subject
    service_name = getattr(ar.service, "title", None) or getattr(ar.service, "name", None) or "Service"
    subject = f"Appointment update: {service_name} — {ctx['status_label']}"

    # Determine action URL by role
    for_seller = (recipient_user == ar.seller)
    action_url = _action_url_for_user(ar, for_seller=for_seller)

    notify_email_and_in_app(
        user=recipient_user,
        kind="appointment_update",
        email_subject=subject,
        email_template_html="appointments/emails/appointment_update.html",
        email_template_txt="appointments/emails/appointment_update.txt",
        context=ctx,
        title=subject,
        body=f"{service_name}: {ctx['status_label']} (by {actor_label})",
        action_url=action_url,
        payload={
            "appointment_request_id": ar.pk,
            "event_key": event_key,
            "status": ar.status,
        },
    )

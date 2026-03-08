from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core.config import get_site_config
from appointments.models import AppointmentRequest
from appointments.notifications import notify_appointment_event


class Command(BaseCommand):
    help = "Send appointment reminder notifications for upcoming scheduled appointments."

    def handle(self, *args, **options):
        cfg = get_site_config()
        if not cfg.appointment_reminders_enabled:
            self.stdout.write("Appointment reminders disabled (SiteConfig).")
            return

        hours = int(cfg.appointment_reminder_hours_before or 24)
        now = timezone.now()
        window_start = now
        window_end = now + timedelta(hours=hours)

        qs = AppointmentRequest.objects.filter(
            status=AppointmentRequest.Status.SCHEDULED,
            scheduled_start__gte=window_start,
            scheduled_start__lte=window_end,
        ).filter(Q(reminder_sent_at__isnull=True) | Q(reminder_sent_at__lt=now - timedelta(hours=hours)))

        count = 0
        for ar in qs.iterator():
            try:
                notify_appointment_event(
                    ar=ar,
                    recipient_user=ar.buyer,
                    event_key="reminder",
                    actor_label="LocalMarketNE",
                    extra_context={"reminder_hours": hours},
                )
            except Exception:
                pass

            try:
                notify_appointment_event(
                    ar=ar,
                    recipient_user=ar.seller,
                    event_key="reminder",
                    actor_label="LocalMarketNE",
                    extra_context={"reminder_hours": hours},
                )
            except Exception:
                pass

            ar.reminder_sent_at = now
            ar.save(update_fields=["reminder_sent_at", "updated_at"])
            count += 1

        self.stdout.write(f"Sent {count} appointment reminders.")

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls, datetime, time, timedelta
from typing import List, Optional

from django.db.models import Q
from django.utils import timezone

from products.models import Product

from .models import AvailabilityException, AvailabilityRule, AppointmentRequest


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime


def compute_available_slots(
    *,
    service: Product,
    day: date_cls,
    slot_minutes: int = 15,
    horizon_days: int = 60,
) -> List[Slot]:
    """Compute available appointment start slots for a service on a given day.

    - Uses seller weekly rules + one-off date exceptions
    - Excludes already ACCEPTED appointments for the same seller (any service)
    - Returns slots in the current timezone
    """

    if service.kind != Product.Kind.SERVICE:
        return []

    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    if day < today or day > (today + timedelta(days=int(horizon_days or 60))):
        return []

    duration = int(service.service_duration_minutes or 0)
    if duration <= 0:
        return []

    # Exception overrides
    ex = AvailabilityException.objects.filter(seller=service.seller, date=day).first()
    if ex and ex.is_closed:
        return []

    windows: list[tuple[time, time]] = []
    if ex and ex.start_time and ex.end_time:
        windows = [(ex.start_time, ex.end_time)]
    else:
        weekday = int(day.weekday())
        rules = AvailabilityRule.objects.filter(
            seller=service.seller,
            is_active=True,
            weekday=weekday,
        ).order_by("start_time")
        for r in rules:
            windows.append((r.start_time, r.end_time))

    if not windows:
        return []

    # Busy blocks for appointments that already occupy seller time.
    start_of_day = timezone.make_aware(datetime.combine(day, time.min), tz)
    end_of_day = timezone.make_aware(datetime.combine(day, time.max), tz)
    busy_statuses = [
        AppointmentRequest.Status.DEPOSIT_PENDING,
        AppointmentRequest.Status.DEPOSIT_PAID,
        AppointmentRequest.Status.AWAITING_BUYER_CONFIRMATION,
        AppointmentRequest.Status.SCHEDULED,
    ]
    busy = list(
        AppointmentRequest.objects.filter(
            seller=service.seller,
            status__in=busy_statuses,
        )
        .filter(
            Q(requested_start__lte=end_of_day, requested_end__gte=start_of_day)
            | Q(scheduled_start__lte=end_of_day, scheduled_end__gte=start_of_day)
        )
        .values_list("requested_start", "requested_end", "scheduled_start", "scheduled_end")
    )

    def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
        return a_start < b_end and b_start < a_end

    slots: list[Slot] = []
    now = timezone.now()

    for w_start, w_end in windows:
        w_start_dt = timezone.make_aware(datetime.combine(day, w_start), tz)
        w_end_dt = timezone.make_aware(datetime.combine(day, w_end), tz)
        # last possible start
        last_start = w_end_dt - timedelta(minutes=duration)
        cur = w_start_dt
        while cur <= last_start:
            if cur >= now + timedelta(minutes=1):
                cur_end = cur + timedelta(minutes=duration)
                conflict = False
                for req_start, req_end, sched_start, sched_end in busy:
                    b_start = sched_start or req_start
                    b_end = sched_end or req_end
                    if overlaps(cur, cur_end, b_start, b_end):
                        conflict = True
                        break
                if not conflict:
                    slots.append(Slot(start=cur, end=cur_end))
            cur += timedelta(minutes=int(slot_minutes or 15))

    # Deduplicate in case overlapping rules produce same start
    uniq: dict[datetime, Slot] = {s.start: s for s in slots}
    return [uniq[k] for k in sorted(uniq.keys())]

from __future__ import annotations

from datetime import date as date_cls, timedelta, timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from products.models import Product
from payments.utils import seller_is_stripe_ready
from products.permissions import is_owner_user
from .forms import AppointmentRequestForm, AppointmentRescheduleForm
from .models import AppointmentRequest, AvailabilityException, AvailabilityRule
from .notifications import notify_appointment_event
from .services import compute_available_slots
from .services_booking import create_deposit_order_for_appointment


@login_required
def request_appointment(request: HttpRequest, product_id: int) -> HttpResponse:
    service = get_object_or_404(Product, pk=product_id, is_active=True)
    if service.kind != Product.Kind.SERVICE:
        raise Http404()
    if not is_owner_user(request.user) and not seller_is_stripe_ready(service.seller):
        messages.error(request, "This seller is not ready to accept bookings yet.")
        return redirect(service.get_absolute_url())

    if request.method == "POST":
        form = AppointmentRequestForm(request.POST, service=service)
        if form.is_valid():
            start = form.cleaned_data["requested_start"]
            duration = int(service.service_duration_minutes or 0)
            end = start + timedelta(minutes=duration)
            ar = AppointmentRequest.objects.create(
                service=service,
                buyer=request.user,
                seller=service.seller,
                requested_start=start,
                requested_end=end,
                message=form.cleaned_data.get("message", "") or "",
            )
            messages.success(request, "Appointment request sent to the seller.")
            try:
                notify_appointment_event(
                    ar=ar,
                    recipient_user=ar.seller,
                    event_key="requested",
                    actor_label=str(ar.buyer.username),
                )
            except Exception:
                pass
            return redirect("appointments:buyer_requests")
    else:
        form = AppointmentRequestForm(service=service)

    deposit_amount = (int(service.service_deposit_cents or 0) / 100.0)
    return render(
        request,
        "appointments/request_appointment.html",
        {"service": service, "form": form, "deposit_amount": deposit_amount},
    )


@login_required
def buyer_requests(request: HttpRequest) -> HttpResponse:
    qs = AppointmentRequest.objects.filter(buyer=request.user).select_related("service", "seller")
    return render(request, "appointments/buyer_requests.html", {"requests": qs})


@login_required
def seller_requests(request: HttpRequest) -> HttpResponse:
    # seller view: requests for services they own
    qs = AppointmentRequest.objects.filter(seller=request.user).select_related("service", "buyer")
    return render(request, "appointments/seller_requests.html", {"requests": qs})


@login_required
def seller_request_update(request: HttpRequest, req_id: int, action: str) -> HttpResponse:
    ar = get_object_or_404(AppointmentRequest, pk=req_id, seller=request.user)
    if action not in ("accept", "decline"):
        raise Http404()
    if ar.status != AppointmentRequest.Status.REQUESTED:
        messages.info(request, "This request is no longer pending.")
        return redirect("appointments:seller_requests")

    if action == "accept":
        ar.accepted_at = timezone.now()

        # If a deposit is required, create a deposit order now and link it.
        if ar.requires_deposit:
            ar.status = AppointmentRequest.Status.DEPOSIT_PENDING
            ar.save(update_fields=["status", "accepted_at", "updated_at"])
            if not ar.order_id:
                try:
                    order = create_deposit_order_for_appointment(ar)
                    ar.order = order
                    ar.save(update_fields=["order", "updated_at"])
                except Exception:
                    ar.status = AppointmentRequest.Status.REQUESTED
                    ar.accepted_at = None
                    ar.save(update_fields=["status", "accepted_at", "updated_at"])
                    messages.error(request, "Could not create deposit checkout. Please try again.")
                    return redirect("appointments:seller_requests")
            messages.success(request, "Accepted. Waiting for buyer deposit payment.")
            try:
                notify_appointment_event(ar=ar, recipient_user=ar.buyer, event_key="deposit_pending", actor_label=str(ar.seller.username))
            except Exception:
                pass
        else:
            # No deposit required; schedule immediately to the requested slot.
            ar.schedule_default()
            ar.save(update_fields=[
                "status",
                "scheduled_start",
                "scheduled_end",
                "scheduled_notes",
                "scheduled_at",
                "accepted_at",
                "updated_at",
            ])
            messages.success(request, "Accepted and scheduled.")
            try:
                notify_appointment_event(ar=ar, recipient_user=ar.buyer, event_key="scheduled", actor_label=str(ar.seller.username))
            except Exception:
                pass
    else:
        ar.status = AppointmentRequest.Status.DECLINED
        ar.declined_at = timezone.now()
        ar.save(update_fields=["status", "declined_at", "updated_at"])
        messages.success(request, "Appointment request declined.")
        try:
            notify_appointment_event(ar=ar, recipient_user=ar.buyer, event_key="declined", actor_label=str(ar.seller.username))
        except Exception:
            pass

    return redirect("appointments:seller_requests")


@login_required
def seller_reschedule(request: HttpRequest, req_id: int) -> HttpResponse:
    ar = get_object_or_404(AppointmentRequest, pk=req_id, seller=request.user)
    if ar.status not in {
        AppointmentRequest.Status.DEPOSIT_PAID,
        AppointmentRequest.Status.SCHEDULED,
        AppointmentRequest.Status.DEPOSIT_PENDING,
        AppointmentRequest.Status.REQUESTED,
    }:
        messages.info(request, "This appointment cannot be rescheduled.")
        return redirect("appointments:seller_requests")

    if request.method == "POST":
        form = AppointmentRescheduleForm(request.POST, ar=ar)
        if form.is_valid():
            start = form.cleaned_data["scheduled_start"]
            duration = int(ar.duration_minutes_snapshot or 0)
            end = start + timedelta(minutes=duration) if duration else None

            ar.scheduled_start = start
            if end:
                ar.scheduled_end = end
            note = (form.cleaned_data.get("scheduled_notes") or "").strip()
            if note:
                # append notes to preserve history
                if ar.scheduled_notes:
                    ar.scheduled_notes = f"{ar.scheduled_notes}\n\nReschedule note: {note}"
                else:
                    ar.scheduled_notes = f"Reschedule note: {note}"
            if not ar.scheduled_at:
                ar.scheduled_at = timezone.now()
            ar.buyer_confirmed_at = None
            ar.status = AppointmentRequest.Status.AWAITING_BUYER_CONFIRMATION
            ar.save(update_fields=["status", "scheduled_start", "scheduled_end", "scheduled_notes", "scheduled_at", "buyer_confirmed_at", "updated_at"])

            messages.success(request, "Appointment rescheduled.")
            try:
                notify_appointment_event(ar=ar, recipient_user=ar.buyer, event_key="rescheduled", actor_label=str(ar.seller.username))
            except Exception:
                pass
            return redirect("appointments:seller_requests")
    else:
        initial_dt = ar.scheduled_start or ar.requested_start
        form = AppointmentRescheduleForm(ar=ar, initial={"scheduled_start": initial_dt, "scheduled_notes": ""})

    return render(request, "appointments/seller_reschedule.html", {"ar": ar, "form": form})


@login_required
def available_slots_api(request: HttpRequest, product_id: int) -> JsonResponse:
    service = get_object_or_404(Product, pk=product_id, is_active=True)
    if service.kind != Product.Kind.SERVICE:
        raise Http404()

    raw = (request.GET.get("date") or "").strip()
    try:
        day = date_cls.fromisoformat(raw)
    except Exception:
        return JsonResponse({"slots": [], "error": "invalid_date"}, status=400)

    slots = compute_available_slots(service=service, day=day)
    tz = timezone.get_current_timezone()
    return JsonResponse(
        {
            "slots": [
                {
                    "value": s.start.astimezone(tz).strftime("%H:%M"),
                    "label": s.start.astimezone(tz).strftime("%I:%M %p").lstrip("0"),
                }
                for s in slots
            ]
        }
    )


@login_required
def seller_availability(request: HttpRequest) -> HttpResponse:
    """Simple seller availability management (weekly rules + date exceptions)."""
    user = request.user

    if request.method == "POST":
        kind = (request.POST.get("kind") or "").strip()
        if kind == "rule":
            try:
                weekday = int(request.POST.get("weekday") or 0)
                start_time = request.POST.get("start_time")
                end_time = request.POST.get("end_time")
                AvailabilityRule.objects.create(
                    seller=user,
                    weekday=weekday,
                    start_time=start_time,
                    end_time=end_time,
                    is_active=True,
                )
                messages.success(request, "Availability rule added.")
            except Exception:
                messages.error(request, "Could not add rule. Check your inputs.")
        elif kind == "exception":
            try:
                date_raw = request.POST.get("date")
                is_closed = bool(request.POST.get("is_closed"))
                start_time = request.POST.get("start_time") or None
                end_time = request.POST.get("end_time") or None
                note = (request.POST.get("note") or "").strip()
                AvailabilityException.objects.update_or_create(
                    seller=user,
                    date=date_cls.fromisoformat(date_raw),
                    defaults={
                        "is_closed": is_closed,
                        "start_time": start_time,
                        "end_time": end_time,
                        "note": note,
                    },
                )
                messages.success(request, "Date exception saved.")
            except Exception:
                messages.error(request, "Could not save exception. Check your inputs.")

        return redirect("appointments:seller_availability")

    if request.GET.get("delete_rule"):
        AvailabilityRule.objects.filter(id=request.GET.get("delete_rule"), seller=user).delete()
        messages.success(request, "Rule deleted.")
        return redirect("appointments:seller_availability")
    if request.GET.get("delete_exception"):
        AvailabilityException.objects.filter(id=request.GET.get("delete_exception"), seller=user).delete()
        messages.success(request, "Exception deleted.")
        return redirect("appointments:seller_availability")

    rules = AvailabilityRule.objects.filter(seller=user).order_by("weekday", "start_time")
    exceptions = AvailabilityException.objects.filter(seller=user).order_by("-date")

    return render(
        request,
        "appointments/seller_availability.html",
        {
            "rules": rules,
            "exceptions": exceptions,
            "weekday_choices": AvailabilityRule.Weekday.choices,
        },
    )


@login_required
def buyer_cancel_request(request: HttpRequest, req_id: int) -> HttpResponse:
    ar = get_object_or_404(AppointmentRequest, pk=req_id, buyer=request.user)
    if request.method != "POST":
        return redirect("appointments:buyer_requests")

    if ar.status not in {AppointmentRequest.Status.REQUESTED, AppointmentRequest.Status.DEPOSIT_PENDING, AppointmentRequest.Status.DEPOSIT_PAID, AppointmentRequest.Status.SCHEDULED}:
        messages.info(request, "This request can’t be canceled.")
        return redirect("appointments:buyer_requests")

    # Enforce cancellation window (hours before start)
    window_hours = int(getattr(ar, "cancellation_window_hours_snapshot", 0) or 0)
    if ar.status in {AppointmentRequest.Status.DEPOSIT_PAID, AppointmentRequest.Status.SCHEDULED} and window_hours > 0:
        cutoff = ar.requested_start - timedelta(hours=window_hours)
        if timezone.now() >= cutoff:
            messages.error(request, f"Cancellation is not allowed within {window_hours} hours of the appointment start.")
            return redirect("appointments:buyer_requests")

    ar.status = AppointmentRequest.Status.CANCELED
    ar.canceled_at = timezone.now()
    ar.save(update_fields=["status", "canceled_at", "updated_at"])
    messages.success(request, "Appointment request canceled.")
    try:
        notify_appointment_event(ar=ar, recipient_user=ar.seller, event_key="canceled", actor_label=str(ar.buyer.username))
    except Exception:
        pass
    return redirect("appointments:buyer_requests")


@login_required
def seller_mark_completed(request: HttpRequest, req_id: int) -> HttpResponse:
    ar = get_object_or_404(AppointmentRequest, pk=req_id, seller=request.user)
    if request.method != "POST":
        return redirect("appointments:seller_requests")

    if ar.status != AppointmentRequest.Status.SCHEDULED:
        messages.info(request, "Only scheduled appointments can be completed.")
        return redirect("appointments:seller_requests")

    ar.status = AppointmentRequest.Status.COMPLETED
    ar.completed_at = timezone.now()
    ar.save(update_fields=["status", "completed_at", "updated_at"])
    messages.success(request, "Marked completed.")
    try:
        notify_appointment_event(ar=ar, recipient_user=ar.buyer, event_key="completed", actor_label=str(ar.seller.username))
    except Exception:
        pass
    return redirect("appointments:seller_requests")


@login_required
def seller_cancel(request: HttpRequest, req_id: int) -> HttpResponse:
    ar = get_object_or_404(AppointmentRequest, pk=req_id, seller=request.user)
    if request.method != "POST":
        return redirect("appointments:seller_requests")

    if ar.status not in {AppointmentRequest.Status.REQUESTED, AppointmentRequest.Status.DEPOSIT_PENDING, AppointmentRequest.Status.DEPOSIT_PAID, AppointmentRequest.Status.SCHEDULED}:
        messages.info(request, "This request can’t be canceled.")
        return redirect("appointments:seller_requests")

    ar.status = AppointmentRequest.Status.CANCELED
    ar.canceled_at = timezone.now()
    ar.save(update_fields=["status", "canceled_at", "updated_at"])
    messages.success(request, "Appointment canceled.")
    try:
        notify_appointment_event(ar=ar, recipient_user=ar.buyer, event_key="canceled", actor_label=str(ar.seller.username))
    except Exception:
        pass
    return redirect("appointments:seller_requests")


@login_required
def buyer_confirm(request: HttpRequest, req_id: int) -> HttpResponse:
    ar = get_object_or_404(AppointmentRequest, pk=req_id, buyer=request.user)
    if ar.status != AppointmentRequest.Status.AWAITING_BUYER_CONFIRMATION:
        messages.info(request, "This appointment does not need confirmation.")
        return redirect("appointments:buyer_requests")

    if request.method == "POST":
        ar.status = AppointmentRequest.Status.SCHEDULED
        ar.buyer_confirmed_at = timezone.now()
        ar.save(update_fields=["status", "buyer_confirmed_at", "updated_at"])

        messages.success(request, "Appointment confirmed.")
        try:
            notify_appointment_event(
                ar=ar,
                recipient_user=ar.seller,
                event_key="confirmed",
                actor_label=ar.buyer.username,
                extra_context={},
            )
        except Exception:
            pass
        try:
            notify_appointment_event(
                ar=ar,
                recipient_user=ar.buyer,
                event_key="confirmed",
                actor_label=ar.buyer.username,
                extra_context={},
            )
        except Exception:
            pass

        return redirect("appointments:buyer_requests")

    return render(request, "appointments/buyer_confirm.html", {"ar": ar})


@login_required
def appointment_ics(request: HttpRequest, req_id: int) -> HttpResponse:
    # Buyer or seller can download the calendar invite.
    ar = get_object_or_404(AppointmentRequest, pk=req_id)
    if ar.buyer_id != request.user.id and ar.seller_id != request.user.id and not request.user.is_staff:
        raise Http404()

    start = ar.effective_start
    end = ar.effective_end
    if not start or not end:
        raise Http404()

    # iCalendar expects UTC or TZID. We'll emit UTC to avoid TZ complexities.
    start_utc = start.astimezone(dt_timezone.utc)
    end_utc = end.astimezone(dt_timezone.utc)

    def _fmt(dt):
        return dt.strftime("%Y%m%dT%H%M%SZ")

    uid = f"lmne-appt-{ar.pk}@localmarketne"
    summary = f"LocalMarketNE: {ar.service.title}"
    desc_lines = [
        f"Service: {ar.service.title}",
        f"Seller: {ar.seller.username}",
        f"Buyer: {ar.buyer.username}",
    ]
    if ar.scheduled_notes:
        desc_lines.append("")
        desc_lines.append(ar.scheduled_notes)

    description = "\n".join(desc_lines).replace("\r", "")
    location = getattr(ar.service, "service_location_text", "") or ""

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//LocalMarketNE//Appointments//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{_fmt(timezone.now().astimezone(dt_timezone.utc))}\r\n"
        f"DTSTART:{_fmt(start_utc)}\r\n"
        f"DTEND:{_fmt(end_utc)}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{description}\r\n"
        + (f"LOCATION:{location}\r\n" if location else "")
        + "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    resp = HttpResponse(ics, content_type="text/calendar; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="appointment-{ar.pk}.ics"'
    return resp

# orders/webhooks.py
from __future__ import annotations

import json
from typing import Any, Tuple

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from .models import Order, StripeWebhookDelivery, StripeWebhookEvent
from .stripe_service import create_transfers_for_paid_order


def _get_header(request: HttpRequest, name: str) -> str:
    return request.headers.get(name, request.META.get(f"HTTP_{name.upper().replace('-', '_')}", ""))


def _verify_and_parse(request: HttpRequest) -> Any:
    """Verify webhook signature and return the Stripe event as a dict.

    Uses stripe-python's signature verification if available. Falls back to unsigned JSON in dev.
    """
    payload = request.body
    sig_header = _get_header(request, "Stripe-Signature")
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    try:
        import stripe

        stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=secret)
        return event.to_dict_recursive() if hasattr(event, "to_dict_recursive") else dict(event)
    except Exception:
        # Debug-only escape hatch for local testing without webhook signatures.
        if bool(getattr(settings, "DEBUG", False)) and not secret:
            try:
                return json.loads(payload.decode("utf-8"))
            except Exception:
                return None
        return None


@transaction.atomic
def process_stripe_event_dict(
    *,
    event: dict,
    webhook_event: StripeWebhookEvent,
    source: str = "webhook",
) -> Tuple[StripeWebhookEvent, StripeWebhookDelivery]:
    """Process a normalized Stripe event dict against our Order model.

    This is the shared core for:
      - the inbound webhook HTTP view
      - staff ops reprocessing tools

    `source` is stored on the delivery row to aid investigations.
    """
    stripe_event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("type") or "").strip()
    livemode = bool(event.get("livemode", False))

    # keep webhook_event current
    webhook_event.event_type = event_type
    webhook_event.livemode = livemode
    webhook_event.raw_json = event
    webhook_event.save(update_fields=["event_type", "livemode", "raw_json"])

    # Derive order
    data_obj = (event.get("data") or {}).get("object") or {}
    metadata = (data_obj.get("metadata") or {}) if isinstance(data_obj, dict) else {}
    order_id = str(metadata.get("order_id") or "").strip()

    order = None
    if order_id:
        order = Order.objects.select_for_update().filter(pk=order_id).first()

    # Delivery record (every attempt gets one)
    delivery = StripeWebhookDelivery.objects.create(
        webhook_event=webhook_event,
        order=order,
        stripe_session_id=str((data_obj.get("id") or "")) if isinstance(data_obj, dict) else "",
        delivered_at=timezone.now(),
        status=("reprocessed" if source != "webhook" else "received"),
        error_message="",
    )

    try:
        if event_type == "checkout.session.completed":
            if not order:
                raise ValueError("Order not found")

            payment_intent = str((data_obj.get("payment_intent") or "")).strip()
            session_id = str((data_obj.get("id") or "")).strip()

            was_paid = (order.status == Order.Status.PAID)

            # Shipping snapshot (if present)
            shipping = data_obj.get("shipping_details") or {}
            addr = (shipping.get("address") or {}) if isinstance(shipping, dict) else {}
            order.set_shipping_from_stripe(
                name=str(shipping.get("name") or ""),
                phone=str(shipping.get("phone") or ""),
                line1=str(addr.get("line1") or ""),
                line2=str(addr.get("line2") or ""),
                city=str(addr.get("city") or ""),
                state=str(addr.get("state") or ""),
                postal_code=str(addr.get("postal_code") or ""),
                country=str(addr.get("country") or ""),
            )

            order.mark_paid(payment_intent_id=payment_intent, session_id=session_id)
            # Idempotency guard: only trigger seller transfers on the first paid transition.
            if not was_paid:
                create_transfers_for_paid_order(order=order)
            try:
                from appointments.models import AppointmentRequest

                now = timezone.now()
                for ar in AppointmentRequest.objects.select_for_update().filter(
                    order=order,
                    status=AppointmentRequest.Status.DEPOSIT_PENDING,
                ):
                    ar.status = AppointmentRequest.Status.DEPOSIT_PAID
                    ar.deposit_paid_at = now
                    ar.save(update_fields=["status", "deposit_paid_at", "updated_at"])
            except Exception:
                pass

            # Native analytics funnel event (Pack AK): ORDER_PAID
            # Only log on an actual state transition to avoid double-counting on reprocess.
            if not was_paid:
                try:
                    from analytics.models import AnalyticsEvent
                    from analytics.services import log_system_event

                    log_system_event(
                        event_type=AnalyticsEvent.EventType.ORDER_PAID,
                        path="/stripe/webhook/checkout.session.completed",
                        status_code=200,
                        meta={
                            "order_id": str(order.pk),
                            "stripe_event_id": stripe_event_id,
                            "stripe_session_id": session_id,
                            "payment_intent": payment_intent,
                            "total_cents": int(getattr(order, "total_cents", 0) or 0),
                            "source": source,
                        },
                        host="",
                        environment=("production" if livemode else "development"),
                    )
                except Exception:
                    pass

            webhook_event.status = "processed"
            webhook_event.processed_at = timezone.now()
            delivery.status = "ok"

        elif event_type in {"checkout.session.expired", "checkout.session.async_payment_failed"}:
            if order and order.status in {Order.Status.AWAITING_PAYMENT, Order.Status.PENDING}:
                order.mark_canceled(note="Stripe checkout expired")
            webhook_event.status = "processed"
            webhook_event.processed_at = timezone.now()
            delivery.status = "ok"

        else:
            webhook_event.status = "ignored"
            webhook_event.processed_at = timezone.now()
            delivery.status = "ignored"

        webhook_event.error_message = ""
        webhook_event.save(update_fields=["status", "processed_at", "error_message"])
        delivery.error_message = ""
        delivery.save(update_fields=["status", "error_message"])
        return webhook_event, delivery

    except Exception as e:
        webhook_event.status = "error"
        webhook_event.error_message = str(e)
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "error_message", "processed_at"])

        delivery.status = "error"
        delivery.error_message = str(e)
        delivery.save(update_fields=["status", "error_message"])
        raise


@transaction.atomic
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    event = _verify_and_parse(request)
    if not isinstance(event, dict) or not event.get("id"):
        return HttpResponse(status=400)

    stripe_event_id = str(event.get("id"))
    event_type = str(event.get("type") or "")
    livemode = bool(event.get("livemode", False))

    webhook_event, created = StripeWebhookEvent.objects.get_or_create(
        stripe_event_id=stripe_event_id,
        defaults={
            "event_type": event_type,
            "livemode": livemode,
            "raw_json": event,
            "created_at": timezone.now(),
            "status": "received",
        },
    )

    if not created and webhook_event.processed_at:
        return HttpResponse(status=200)

    try:
        process_stripe_event_dict(event=event, webhook_event=webhook_event, source="webhook")
        return HttpResponse(status=200)
    except Exception:
        return HttpResponse(status=200)

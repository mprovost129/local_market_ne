# orders/stripe_service.py
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.urls import reverse

import stripe

from .models import Order, OrderEvent, OrderItem
from .emails import send_payout_email
from products.permissions import is_owner_user

logger = logging.getLogger(__name__)


def _stripe() -> Any:
    stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    return stripe


def _assert_order_sellers_stripe_ready(order: Order) -> None:
    """Block checkout if any seller is inactive or not Stripe-ready (unless owner/admin bypass)."""
    for oi in order.items.select_related("seller").all():
        seller = oi.seller
        if hasattr(seller, "is_active") and not seller.is_active:
            raise ValueError("A seller in this order is currently unavailable.")

        # Owner/admin bypass
        if order.buyer_id and (getattr(order.buyer, "is_staff", False) or is_owner_user(order.buyer)):
            continue

        stripe_account = getattr(seller, "stripe_connect", None)
        if not stripe_account or not getattr(stripe_account, "is_ready", False):
            raise ValueError("A seller in your cart has not completed Stripe onboarding.")


def _build_checkout_urls(*, request: Any, order: Order) -> tuple[str, str]:
    if request is None:
        raise ValueError("request is required when success_url/cancel_url are not provided.")
    success_url = request.build_absolute_uri(reverse("orders:checkout_success")) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = request.build_absolute_uri(reverse("orders:checkout_cancel", kwargs={"order_id": order.pk}))
    if order.is_guest:
        cancel_url = f"{cancel_url}?t={order.order_token}"
    return success_url, cancel_url


def create_checkout_session_for_order(
    *,
    order: Order,
    request: Any | None = None,
    success_url: str = "",
    cancel_url: str = "",
) -> Any:
    """Create a Stripe Checkout Session for a marketplace order."""
    _assert_order_sellers_stripe_ready(order)
    if not success_url or not cancel_url:
        success_url, cancel_url = _build_checkout_urls(request=request, order=order)

    s = _stripe()

    line_items: list[dict[str, Any]] = []
    for item in order.items.all():
        # Tips are allowed and pass through as normal line items.
        unit_amount = int(item.unit_price_cents_snapshot or 0)
        qty = int(item.quantity or 1)

        name = item.title_snapshot or getattr(item.product, "title", "Item")

        line_items.append(
            {
                "price_data": {
                    "currency": order.currency or "usd",
                    "unit_amount": unit_amount,
                    "product_data": {"name": name},
                },
                "quantity": qty,
            }
        )

    if int(order.shipping_cents or 0) > 0:
        line_items.append(
            {
                "price_data": {
                    "currency": order.currency or "usd",
                    "unit_amount": int(order.shipping_cents),
                    "product_data": {"name": "Shipping / Delivery"},
                },
                "quantity": 1,
            }
        )
    if int(order.platform_fee_cents_snapshot or 0) > 0:
        line_items.append(
            {
                "price_data": {
                    "currency": order.currency or "usd",
                    "unit_amount": int(order.platform_fee_cents_snapshot),
                    "product_data": {"name": "Marketplace service fee"},
                },
                "quantity": 1,
            }
        )

    session = s.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "order_id": str(order.pk),
            "payment_method": order.payment_method,
        },
    )

    order.stripe_session_id = session.id
    order.status = Order.Status.AWAITING_PAYMENT
    order.save(update_fields=["stripe_session_id", "status", "updated_at"])

    try:
        OrderEvent.objects.create(order=order, type=OrderEvent.Type.STRIPE_SESSION_CREATED, message=session.id)
    except Exception:
        pass

    return session


def create_transfers_for_paid_order(*, order: Order, payment_intent_id: str = "") -> None:
    """Create Stripe Connect transfers per seller based on OrderItem ledger snapshots."""
    if order.payment_method != Order.PaymentMethod.STRIPE:
        return

    s = _stripe()
    if payment_intent_id and not (order.stripe_payment_intent_id or "").strip():
        order.stripe_payment_intent_id = str(payment_intent_id).strip()
        order.save(update_fields=["stripe_payment_intent_id", "updated_at"])

    source_transaction = ""
    pi_or_charge = (order.stripe_payment_intent_id or "").strip()
    if pi_or_charge.startswith("ch_"):
        source_transaction = pi_or_charge
    elif pi_or_charge.startswith("pi_"):
        payment_intent_api = getattr(s, "PaymentIntent", None)
        if payment_intent_api and hasattr(payment_intent_api, "retrieve"):
            try:
                pi = payment_intent_api.retrieve(pi_or_charge, expand=["latest_charge"])
                latest_charge = ""
                if isinstance(pi, dict):
                    raw = pi.get("latest_charge")
                    if isinstance(raw, dict):
                        latest_charge = str(raw.get("id") or "").strip()
                    else:
                        latest_charge = str(raw or "").strip()
                else:
                    raw = getattr(pi, "latest_charge", "")
                    if isinstance(raw, dict):
                        latest_charge = str(raw.get("id") or "").strip()
                    else:
                        latest_charge = str(getattr(raw, "id", "") or raw or "").strip()
                if latest_charge.startswith("ch_"):
                    source_transaction = latest_charge
            except Exception:
                logger.warning(
                    "Could not resolve charge id from payment_intent for order=%s pi=%s",
                    order.pk,
                    pi_or_charge,
                    exc_info=True,
                )

    # Sum seller nets by seller
    per_seller: dict[int, int] = {}
    for item in order.items.select_related("seller").all():
        if item.is_tip:
            # tips already set seller_net to tip cents
            pass
        seller_id = int(item.seller_id)
        per_seller[seller_id] = per_seller.get(seller_id, 0) + int(item.seller_net_cents or 0)

    for seller_id, payout_cents in per_seller.items():
        if payout_cents <= 0:
            continue

        seller = next((oi.seller for oi in order.items.all() if int(oi.seller_id) == int(seller_id)), None)
        if not seller:
            continue

        stripe_account = getattr(seller, "stripe_connect", None)
        stripe_account_id = str(getattr(stripe_account, "stripe_account_id", "") or "").strip()
        is_ready = bool(getattr(stripe_account, "is_ready", False))
        if not stripe_account_id or not is_ready:
            try:
                OrderEvent.objects.create(
                    order=order,
                    type=OrderEvent.Type.WARNING,
                    message=f"transfer skipped seller={seller_id} (not ready)",
                    meta={"seller_id": int(seller_id)},
                )
            except Exception:
                pass
            continue

        # Idempotency key: order + seller
        idem = f"order_{order.pk}_seller_{seller_id}_transfer"

        transfer_payload = {
            "amount": int(payout_cents),
            "currency": order.currency or "usd",
            "destination": stripe_account_id,
            "metadata": {"order_id": str(order.pk), "seller_id": str(seller_id)},
            "idempotency_key": idem,
        }
        if source_transaction:
            transfer_payload["source_transaction"] = source_transaction

        transfer = s.Transfer.create(**transfer_payload)

        try:
            OrderEvent.objects.create(
                order=order,
                type=OrderEvent.Type.TRANSFER_CREATED,
                message=str(getattr(transfer, "id", "")),
                meta={
                    "seller_id": int(seller_id),
                    "transfer_id": str(getattr(transfer, "id", "")),
                    "amount_cents": int(payout_cents),
                    "stripe_account_id": str(getattr(stripe_account, "stripe_account_id", "")),
                },
            )
        except Exception:
            pass

        # Best-effort payout email
        try:
            send_payout_email(
                order=order,
                seller=seller,
                payout_cents=int(payout_cents),
                balance_before_cents=0,
                transfer_id=str(getattr(transfer, "id", "")),
            )
        except Exception:
            pass

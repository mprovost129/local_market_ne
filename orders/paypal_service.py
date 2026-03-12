from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests
from requests import HTTPError
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

from .models import Order, OrderEvent


def paypal_enabled() -> bool:
    return bool((getattr(settings, "PAYPAL_CLIENT_ID", "") or "").strip() and (getattr(settings, "PAYPAL_CLIENT_SECRET", "") or "").strip())


def _paypal_base_url() -> str:
    env = (getattr(settings, "PAYPAL_ENV", "sandbox") or "sandbox").strip().lower()
    if env in {"live", "production", "prod"}:
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def _money(cents: int) -> str:
    return f"{(Decimal(int(cents or 0)) / Decimal('100')):.2f}"


def _token_cache_key() -> str:
    return f"paypal:oauth:{(getattr(settings, 'PAYPAL_ENV', 'sandbox') or 'sandbox').strip().lower()}"


def _get_access_token() -> str:
    cached = cache.get(_token_cache_key())
    if cached:
        return str(cached)

    client_id = (getattr(settings, "PAYPAL_CLIENT_ID", "") or "").strip()
    client_secret = (getattr(settings, "PAYPAL_CLIENT_SECRET", "") or "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("PayPal credentials are not configured")

    r = requests.post(
        f"{_paypal_base_url()}/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json", "Accept-Language": "en_US"},
        timeout=12,
    )
    r.raise_for_status()
    payload = r.json() or {}
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("PayPal access token missing")
    expires_in = int(payload.get("expires_in") or 300)
    cache.set(_token_cache_key(), token, timeout=max(60, expires_in - 60))
    return token


def _paypal_request(*, method: str, path: str, json_payload: dict | None = None, headers: dict | None = None) -> dict:
    token = _get_access_token()
    hdrs = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if headers:
        hdrs.update(headers)
    r = requests.request(
        method=method.upper(),
        url=f"{_paypal_base_url()}{path}",
        json=json_payload,
        headers=hdrs,
        timeout=16,
    )
    r.raise_for_status()
    return r.json() if r.content else {}


def _extract_capture_id(order_payload: dict) -> str:
    capture_id = ""
    for unit in (order_payload.get("purchase_units") or []):
        payments = (unit.get("payments") or {}) if isinstance(unit, dict) else {}
        captures = (payments.get("captures") or []) if isinstance(payments, dict) else []
        if captures:
            capture_id = str((captures[0] or {}).get("id") or "").strip()
            if capture_id:
                break
    return capture_id


def _get_paypal_order_details(*, paypal_order_id: str) -> dict:
    oid = str(paypal_order_id or "").strip()
    if not oid:
        return {}
    return _paypal_request(method="GET", path=f"/v2/checkout/orders/{oid}")


def _get_seller_paypal_connect(seller) -> Any | None:
    try:
        return getattr(seller, "paypal_connect", None)
    except Exception:
        return None


def get_unready_paypal_sellers(*, order: Order) -> list[str]:
    """Return usernames for sellers in order without a ready PayPal connected account."""
    missing: list[str] = []
    seen: set[int] = set()
    for item in order.items.select_related("seller").all():
        seller = getattr(item, "seller", None)
        if not seller:
            continue
        sid = int(getattr(seller, "id", 0) or 0)
        if sid in seen:
            continue
        seen.add(sid)
        acct = _get_seller_paypal_connect(seller)
        if not acct or not getattr(acct, "is_ready", False):
            missing.append(str(getattr(seller, "username", sid)))
    return missing


def _alloc_flat_platform_fee(*, seller_basis_cents: dict[int, int], total_fee_cents: int) -> dict[int, int]:
    total_fee = max(0, int(total_fee_cents or 0))
    out = {int(sid): 0 for sid in seller_basis_cents.keys()}
    if total_fee <= 0 or not out:
        return out

    total_basis = sum(max(0, int(v or 0)) for v in seller_basis_cents.values())
    sids = sorted(out.keys())
    if total_basis <= 0:
        out[sids[0]] = total_fee
        return out

    used = 0
    for sid in sids[:-1]:
        share = (total_fee * max(0, int(seller_basis_cents.get(sid, 0) or 0))) // total_basis
        out[sid] = int(share)
        used += int(share)
    out[sids[-1]] = max(0, total_fee - used)
    return out


def _build_paypal_purchase_units(*, order: Order) -> list[dict[str, Any]]:
    per_seller: dict[int, dict[str, Any]] = {}
    for item in order.items.select_related("seller").all():
        seller = getattr(item, "seller", None)
        if not seller:
            continue
        sid = int(item.seller_id)
        row = per_seller.setdefault(
            sid,
            {
                "seller": seller,
                "gross_cents": 0,
                "shipping_cents": 0,
                "marketplace_fee_cents": 0,
            },
        )
        row["gross_cents"] += int(item.line_total_cents or 0)
        if not bool(item.is_tip):
            row["shipping_cents"] += int(item.shipping_fee_cents_snapshot or 0) + int(item.delivery_fee_cents_snapshot or 0)
        row["marketplace_fee_cents"] += int(item.marketplace_fee_cents or 0)

    if not per_seller:
        raise RuntimeError("Order has no payable seller lines.")

    flat_alloc = _alloc_flat_platform_fee(
        seller_basis_cents={sid: int(v["gross_cents"]) for sid, v in per_seller.items()},
        total_fee_cents=int(order.platform_fee_cents_snapshot or 0),
    )

    currency = str((order.currency or "usd").upper())
    units: list[dict[str, Any]] = []
    total_units_cents = 0
    for sid in sorted(per_seller.keys()):
        row = per_seller[sid]
        seller = row["seller"]
        acct = _get_seller_paypal_connect(seller)
        merchant_id = str(getattr(acct, "paypal_merchant_id", "") or "").strip()
        if not merchant_id:
            raise RuntimeError(f"Seller '{getattr(seller, 'username', sid)}' is missing a PayPal merchant account.")

        gross_cents = int(row["gross_cents"] or 0)
        shipping_cents = int(row["shipping_cents"] or 0)
        marketplace_fee_cents = int(row["marketplace_fee_cents"] or 0)
        flat_fee_cents = int(flat_alloc.get(sid, 0) or 0)
        unit_total_cents = max(0, gross_cents + shipping_cents + flat_fee_cents)
        platform_fee_total_cents = max(0, marketplace_fee_cents + flat_fee_cents)
        total_units_cents += unit_total_cents

        unit: dict[str, Any] = {
            "reference_id": str(sid),
            "custom_id": f"{order.pk}:{sid}",
            "description": f"Local Market NE order {order.pk} · seller {getattr(seller, 'username', sid)}",
            "payee": {"merchant_id": merchant_id},
            "amount": {
                "currency_code": currency,
                "value": _money(unit_total_cents),
            },
        }
        if platform_fee_total_cents > 0:
            unit["payment_instruction"] = {
                "platform_fees": [
                    {
                        "amount": {
                            "currency_code": currency,
                            "value": _money(platform_fee_total_cents),
                        }
                    }
                ],
                "disbursement_mode": "INSTANT",
            }
        units.append(unit)

    if total_units_cents != int(order.total_cents or 0):
        raise RuntimeError(
            f"PayPal amount mismatch for order {order.pk}: expected {int(order.total_cents or 0)} got {total_units_cents}."
        )
    return units


def create_paypal_order_for_checkout(*, request, order: Order) -> str:
    if not paypal_enabled():
        raise RuntimeError("PayPal is not enabled")
    if int(order.total_cents or 0) <= 0:
        raise RuntimeError("Order total must be positive for PayPal checkout")
    missing = get_unready_paypal_sellers(order=order)
    if missing:
        raise RuntimeError("One or more sellers have not completed PayPal onboarding: " + ", ".join(missing))

    return_url = request.build_absolute_uri(reverse("orders:paypal_return", kwargs={"order_id": order.pk}))
    if order.is_guest:
        return_url = f"{return_url}?t={order.order_token}"
    cancel_url = request.build_absolute_uri(reverse("orders:checkout_cancel", kwargs={"order_id": order.pk}))
    if order.is_guest:
        cancel_url = f"{cancel_url}?t={order.order_token}"

    currency = str((order.currency or "usd").upper())
    payload = {
        "intent": "CAPTURE",
        "purchase_units": _build_paypal_purchase_units(order=order),
        "application_context": {
            "brand_name": "Local Market NE",
            "user_action": "PAY_NOW",
            "return_url": return_url,
            "cancel_url": cancel_url,
            "shipping_preference": "GET_FROM_FILE" if order.requires_shipping else "NO_SHIPPING",
        },
    }
    headers = {"Prefer": "return=representation"}
    attribution_id = (getattr(settings, "PAYPAL_PARTNER_ATTRIBUTION_ID", "") or "").strip()
    if attribution_id:
        headers["PayPal-Partner-Attribution-Id"] = attribution_id

    data = _paypal_request(method="POST", path="/v2/checkout/orders", json_payload=payload, headers=headers)
    paypal_order_id = str(data.get("id") or "").strip()
    if not paypal_order_id:
        raise RuntimeError("PayPal order id missing")

    approve_url = ""
    for link in (data.get("links") or []):
        if str(link.get("rel") or "").lower() == "approve":
            approve_url = str(link.get("href") or "").strip()
            break
    if not approve_url:
        raise RuntimeError("PayPal approve URL missing")

    order.payment_method = Order.PaymentMethod.PAYPAL
    order.paypal_order_id = paypal_order_id
    order.save(update_fields=["payment_method", "paypal_order_id", "updated_at"])
    try:
        OrderEvent.objects.create(order=order, type=OrderEvent.Type.CHECKOUT_STARTED, message=f"PayPal order created: {paypal_order_id}")
    except Exception:
        pass
    return approve_url


def capture_paypal_order(*, order: Order, paypal_order_id: str) -> tuple[bool, str]:
    oid = str(paypal_order_id or "").strip()
    if not oid:
        return False, "Missing PayPal order id."
    if order.status == Order.Status.PAID:
        return True, str(order.paypal_capture_id or oid)
    if str(order.paypal_order_id or "").strip() and str(order.paypal_order_id).strip() != oid:
        return False, "PayPal order id mismatch."

    try:
        data = _paypal_request(method="POST", path=f"/v2/checkout/orders/{oid}/capture", json_payload={})
    except HTTPError:
        # Common race: webhook captured first, then return URL tries to capture again.
        # Confirm status via order lookup and treat as success if already completed.
        data = _get_paypal_order_details(paypal_order_id=oid)

    status = str(data.get("status") or "").upper()
    if status != "COMPLETED":
        return False, f"PayPal capture not completed (status={status or 'unknown'})."

    capture_id = _extract_capture_id(data)

    order.paypal_order_id = oid
    order.paypal_capture_id = capture_id
    order.save(update_fields=["paypal_order_id", "paypal_capture_id", "updated_at"])
    order.mark_paid(payment_intent_id=f"PAYPAL:{capture_id or oid}", note="PayPal payment captured.")
    return True, capture_id or oid


def verify_paypal_webhook(*, headers: dict, body: dict) -> bool:
    webhook_id = (getattr(settings, "PAYPAL_WEBHOOK_ID", "") or "").strip()
    if not webhook_id:
        return False
    payload = {
        "transmission_id": headers.get("paypal-transmission-id", ""),
        "transmission_time": headers.get("paypal-transmission-time", ""),
        "cert_url": headers.get("paypal-cert-url", ""),
        "auth_algo": headers.get("paypal-auth-algo", ""),
        "transmission_sig": headers.get("paypal-transmission-sig", ""),
        "webhook_id": webhook_id,
        "webhook_event": body,
    }
    data = _paypal_request(method="POST", path="/v1/notifications/verify-webhook-signature", json_payload=payload)
    return str(data.get("verification_status") or "").upper() == "SUCCESS"

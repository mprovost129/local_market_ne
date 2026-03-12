from __future__ import annotations

import uuid
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse


def paypal_partner_onboarding_enabled() -> bool:
    return bool(
        (getattr(settings, "PAYPAL_CLIENT_ID", "") or "").strip()
        and (getattr(settings, "PAYPAL_CLIENT_SECRET", "") or "").strip()
        and (getattr(settings, "PAYPAL_PARTNER_MERCHANT_ID", "") or "").strip()
    )


def _paypal_base_url() -> str:
    env = (getattr(settings, "PAYPAL_ENV", "sandbox") or "sandbox").strip().lower()
    if env in {"live", "production", "prod"}:
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def _token_cache_key() -> str:
    env = (getattr(settings, "PAYPAL_ENV", "sandbox") or "sandbox").strip().lower()
    return f"paypal:oauth:partner:{env}"


def _get_access_token() -> str:
    cached = cache.get(_token_cache_key())
    if cached:
        return str(cached)

    client_id = (getattr(settings, "PAYPAL_CLIENT_ID", "") or "").strip()
    client_secret = (getattr(settings, "PAYPAL_CLIENT_SECRET", "") or "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("PayPal API credentials are not configured.")

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
        raise RuntimeError("PayPal access token missing.")
    expires_in = int(payload.get("expires_in") or 300)
    cache.set(_token_cache_key(), token, timeout=max(60, expires_in - 60))
    return token


def _paypal_request(*, method: str, path: str, json_payload: dict | None = None) -> dict:
    token = _get_access_token()
    r = requests.request(
        method=method.upper(),
        url=f"{_paypal_base_url()}{path}",
        json=json_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=18,
    )
    r.raise_for_status()
    if not r.content:
        return {}
    return r.json() or {}


def create_partner_referral(*, request, tracking_id: str = "") -> tuple[str, str]:
    """
    Start PayPal seller onboarding via Partner Referrals API.
    Returns (action_url, tracking_id).
    """
    if not paypal_partner_onboarding_enabled():
        raise RuntimeError("PayPal partner onboarding is not configured.")

    tracking = (tracking_id or "").strip() or f"seller-{uuid.uuid4().hex[:24]}"

    return_url = request.build_absolute_uri(reverse("payments:paypal_connect_return"))
    refresh_url = request.build_absolute_uri(reverse("payments:paypal_connect_refresh"))
    cancel_url = request.build_absolute_uri(reverse("payments:paypal_connect_status"))

    client_id = (getattr(settings, "PAYPAL_CLIENT_ID", "") or "").strip()

    payload = {
        "tracking_id": tracking,
        "products": ["PPCP"],
        "legal_consents": [{"type": "SHARE_DATA_CONSENT", "granted": True}],
        "operations": [
            {
                "operation": "API_INTEGRATION",
                "api_integration_preference": {
                    "rest_api_integration": {
                        "integration_method": "PAYPAL",
                        "integration_type": "THIRD_PARTY",
                        "third_party_details": {
                            "features": ["PAYMENT", "REFUND"],
                            "partner_client_id": client_id,
                        },
                    }
                },
            }
        ],
        "partner_config_override": {
            "return_url": return_url,
            "return_url_description": "Return to Local Market NE",
            "show_add_credit_card": True,
            "action_renewal_url": refresh_url,
        },
        "collected_consents": [{"type": "SHARE_DATA_CONSENT", "granted": True}],
    }

    data = _paypal_request(method="POST", path="/v2/customer/partner-referrals", json_payload=payload)

    action_url = ""
    for link in (data.get("links") or []):
        rel = str((link or {}).get("rel") or "").strip().lower()
        if rel in {"action_url", "approve"}:
            action_url = str((link or {}).get("href") or "").strip()
            if action_url:
                break

    if not action_url:
        raise RuntimeError("PayPal onboarding link was not returned.")

    return action_url, tracking


def get_merchant_integration_status(*, seller_merchant_id: str) -> dict[str, Any]:
    """
    Best-effort fetch of seller merchant integration status under this partner.
    """
    partner_mid = (getattr(settings, "PAYPAL_PARTNER_MERCHANT_ID", "") or "").strip()
    seller_mid = (seller_merchant_id or "").strip()
    if not partner_mid or not seller_mid:
        return {}

    path = f"/v1/customer/partners/{partner_mid}/merchant-integrations/{seller_mid}"
    return _paypal_request(method="GET", path=path)

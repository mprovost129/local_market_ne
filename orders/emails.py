# orders/emails.py
from __future__ import annotations

from typing import Any, Mapping, Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Order, _site_base_url, _absolute_static_url


def _send_email(*, to_email: str, subject: str, template_html: str, context: Mapping[str, Any]) -> bool:
    to_email = (to_email or "").strip()
    if not to_email:
        return False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "SERVER_EMAIL", "") or None
    html_body = render_to_string(template_html, dict(context))
    text_body = strip_tags(html_body)

    msg = EmailMultiAlternatives(subject=subject, body=text_body, from_email=from_email, to=[to_email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)
    return True


def send_order_failed_email(*, order: Order, reason: str) -> bool:
    # buyer email can be user email or guest_email
    to_email = ""
    if getattr(order, "buyer", None) and getattr(order.buyer, "email", ""):
        to_email = order.buyer.email
    elif getattr(order, "guest_email", ""):
        to_email = order.guest_email

    ctx = {
        "order": order,
        "reason": reason,
        "site_base_url": _site_base_url(),
        "logo_url": _absolute_static_url("images/localmarketne_icon.svg"),
    }
    return _send_email(
        to_email=to_email,
        subject="Order processing issue",
        template_html="emails/order_failed.html",
        context=ctx,
    )


def send_payout_email(
    *,
    order: Order,
    seller,
    payout_cents: int,
    balance_before_cents: int,
    transfer_id: str = "",
) -> bool:
    to_email = getattr(seller, "email", "") or ""
    seller_name = getattr(seller, "username", "") or getattr(seller, "get_full_name", lambda: "")() or "Seller"

    ctx = {
        "order": order,
        "seller": seller,
        "seller_name": seller_name,
        "payout_cents": int(payout_cents),
        "balance_before_cents": int(balance_before_cents),
        "transfer_id": transfer_id,
        "site_base_url": _site_base_url(),
        "logo_url": _absolute_static_url("images/localmarketne_icon.svg"),
    }
    return _send_email(
        to_email=to_email,
        subject="Payout sent",
        template_html="emails/payout_sent.html",
        context=ctx,
    )

# orders/views.py

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import F, Q, Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from cart.cart import Cart
from core.throttle import throttle
from core.throttle_rules import CHECKOUT_START, ORDER_SET_FULFILLMENT, BUYER_CONFIRM_FULFILLMENT, BUYER_OFFPLATFORM_SENT
from core.recaptcha import require_recaptcha_v3
from core.qr import qr_data_uri
from payments.utils import seller_is_stripe_ready, money_to_cents
from products.models import Product
from products.permissions import is_owner_user, is_seller_user, seller_required

from .models import Order, OrderItem, OrderEvent
from .services import create_order_from_cart, refresh_fulfillment_task_for_seller
from .stripe_service import create_checkout_session_for_order

from legal.models import LegalDocument
from legal.services import record_acceptance_for_doc_types

logger = logging.getLogger(__name__)

CHECKOUT_PLACE_RULE = CHECKOUT_START
CHECKOUT_START_RULE = CHECKOUT_START
SET_FULFILLMENT_RULE = ORDER_SET_FULFILLMENT
BUYER_CONFIRM_RULE = BUYER_CONFIRM_FULFILLMENT
BUYER_OFFPLATFORM_RULE = BUYER_OFFPLATFORM_SENT

# order endpoints are GETs and can be abused to inflate metrics or waste bandwidth.

def _token_from_request(request) -> str:
    return (request.POST.get("t") or request.GET.get("t") or "").strip()


def _redirect_order_detail(order: Order, request=None):
    """Redirect to order detail, preserving guest token access when applicable."""
    if getattr(order, "is_guest", False):
        token = ""
        if request is not None:
            token = _token_from_request(request)
        token = token or str(getattr(order, "order_token", "") or "")
        if token:
            return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={token}")
    return redirect("orders:detail", order_id=order.pk)


def _normalize_guest_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if not email:
        return ""
    try:
        validate_email(email)
    except ValidationError:
        return ""
    return email


def _is_owner_request(request) -> bool:
    try:
        return bool(request.user.is_authenticated and is_owner_user(request.user))
    except Exception:
        return False


def _safe_checkout_enabled() -> bool:
    """Best-effort SiteConfig lookup; if anything fails, default to enabled."""
    try:
        from core.config import is_checkout_enabled

        return bool(is_checkout_enabled())
    except Exception:
        return True


def _safe_checkout_disabled_message() -> str:
    try:
        from core.config import get_checkout_disabled_message

        return str(get_checkout_disabled_message())
    except Exception:
        return "Checkout is temporarily unavailable. Please try again soon."


def _user_can_access_order(request, order: Order) -> bool:
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        return True

    if getattr(order, "buyer_id", None):
        return request.user.is_authenticated and request.user.id == order.buyer_id

    t = _token_from_request(request)
    return bool(t) and str(t) == str(getattr(order, "order_token", ""))


def _order_has_unready_sellers(request, order: Order) -> list[str]:
    """
    IMPORTANT: Owner bypass is based on request.user.
    """
    if _is_owner_request(request):
        return []

    bad: list[str] = []
    for item in order.items.select_related("seller").all():
        seller = getattr(item, "seller", None)
        if seller and not seller_is_stripe_ready(seller):
            bad.append(getattr(seller, "username", str(getattr(seller, "pk", ""))))

    seen: set[str] = set()
    out: list[str] = []
    for u in bad:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _cart_has_unready_sellers(request, cart: Cart) -> list[str]:
    """
    IMPORTANT: Owner bypass is based on request.user.
    """
    if _is_owner_request(request):
        return []

    bad: list[str] = []
    for line in cart.lines():
        product = getattr(line, "product", None)
        seller = getattr(product, "seller", None)
        if seller and not seller_is_stripe_ready(seller):
            bad.append(getattr(seller, "username", str(getattr(seller, "pk", ""))))

    seen: set[str] = set()
    out: list[str] = []
    for u in bad:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _cart_inactive_titles(cart: Cart) -> list[str]:
    bad: list[str] = []
    for line in cart.lines():
        p = getattr(line, "product", None)
        if not p:
            continue
        if not getattr(p, "is_active", True):
            bad.append(getattr(p, "title", str(getattr(p, "pk", ""))))
    seen = set()
    out: list[str] = []
    for t in bad:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _order_inactive_titles(order: Order) -> list[str]:
    bad: list[str] = []
    for item in order.items.select_related("product").all():
        p = getattr(item, "product", None)
        if not p:
            bad.append("Unknown item")
            continue
        if not getattr(p, "is_active", True):
            bad.append(getattr(p, "title", str(getattr(p, "pk", ""))))
    seen = set()
    out: list[str] = []
    for t in bad:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _money_text_from_cents(cents: int) -> str:
    return f"{Decimal(int(cents or 0)) / Decimal('100'):.2f}"


def _order_seller_groups(order: Order):
    groups: dict[int, dict] = {}
    for item in order.items.select_related("seller", "seller__profile", "product").all():
        if item.is_tip:
            continue
        sid = int(item.seller_id)
        if sid not in groups:
            prof = getattr(item.seller, "profile", None)
            company = (getattr(prof, "shop_name", "") or "").strip() if prof else ""
            groups[sid] = {
                "seller_id": sid,
                "seller": item.seller,
                "company_name": company or item.seller.username,
                "items": [],
                "tip_cents": 0,
                "subtotal_cents": 0,
            }
        groups[sid]["items"].append(item)
        groups[sid]["subtotal_cents"] += int(item.line_total_cents or 0)

    for tip in order.items.select_related("seller").filter(is_tip=True):
        sid = int(tip.seller_id)
        if sid not in groups:
            prof = getattr(tip.seller, "profile", None)
            company = (getattr(prof, "shop_name", "") or "").strip() if prof else ""
            groups[sid] = {
                "seller_id": sid,
                "seller": tip.seller,
                "company_name": company or tip.seller.username,
                "items": [],
                "tip_cents": 0,
                "subtotal_cents": 0,
            }
        groups[sid]["tip_cents"] += int(tip.line_total_cents or 0)

    rows = []
    for _, g in sorted(groups.items(), key=lambda x: str(x[1]["company_name"]).lower()):
        g["tip_dollars"] = _money_text_from_cents(int(g["tip_cents"]))
        rows.append(g)
    return rows



def _require_age_18_or_redirect(request, *, next_url: str = ""):
    """Pack BK: Buyer age gating removed; seller age is confirmed during seller onboarding."""
    return None


    # Auth users: require profile flag
    if request.user.is_authenticated:
        try:
            prof = getattr(request.user, "profile", None)
            if prof and getattr(prof, "is_age_18_confirmed", False):
                return None
        except Exception:
            pass
        messages.error(request, "Please confirm you are 18+ in your profile to continue.")
        url = reverse("accounts:profile")
        if next_url:
            url = f"{url}?next={next_url}"
        return redirect(url)

    # Guests: require explicit checkbox in POST
    if request.method == "POST":
        if (request.POST.get("confirm_age_18") or "").strip() == "1":
            return None
    messages.error(request, "You must confirm you are 18+ to continue.")
    if next_url:
        return redirect(next_url)
    return redirect("cart:detail")


def _require_no_prohibited_items_or_redirect(request, *, order: Order, next_url: str = ""):
    """Block checkout if the order contains prohibited categories."""
    try:
        items = getattr(order, "items", None)
        if items is None:
            return None
        for it in order.items.all():
            p = getattr(it, "product", None)
            if not p:
                continue
            cat = getattr(p, "category", None)
            sub = getattr(p, "subcategory", None)
            if (cat and getattr(cat, "is_prohibited", False)) or (sub and getattr(sub, "is_prohibited", False)):
                messages.error(request, "This order contains an item in a prohibited category and cannot be checked out.")
                return redirect("cart:detail")
    except Exception:
        return None
    return None

def _require_legal_acceptance_or_redirect(request, *, guest_email: str = "", next_url: str = ""):
    return None


@require_POST
@throttle(CHECKOUT_PLACE_RULE)
@require_recaptcha_v3("checkout_place_order")
def place_order(request):
    """Create an order from cart and redirect to checkout review/payment selection."""
    cart = Cart(request)
    if cart.count_items() == 0:
        messages.info(request, "Your cart is empty.")
        return redirect("cart:detail")

    inactive_titles = _cart_inactive_titles(cart)
    if inactive_titles:
        messages.error(
            request,
            "Some items in your cart are no longer available: " + ", ".join(inactive_titles),
        )
        return redirect("cart:detail")

    bad_sellers = _cart_has_unready_sellers(request, cart)
    if bad_sellers:
        messages.error(
            request,
            "One or more sellers in your cart haven’t completed payout setup yet: " + ", ".join(bad_sellers),
        )
        return redirect("cart:detail")

    guest_email = ""
    if not request.user.is_authenticated:
        guest_email = _normalize_guest_email(request.POST.get("guest_email") or "")
        if not guest_email:
            messages.error(request, "Please enter a valid email to checkout as a guest.")
            return redirect("cart:detail")

    age_check = _require_age_18_or_redirect(request, next_url=reverse('cart:detail'))
    if age_check is not None:
        return age_check

    # Pack V: record acceptance of required legal docs at checkout.
    # We treat the "By placing an order..." notice as explicit agreement.
    doc_types = list(
        (
            LegalDocument.DocType.TERMS,
            LegalDocument.DocType.PRIVACY,
            LegalDocument.DocType.REFUND,
            LegalDocument.DocType.CONTENT,
        )
    )
    try:
        has_service = False
        for line in cart.lines():
            p = getattr(line, "product", None)
            if p and getattr(p, "kind", None) == Product.Kind.SERVICE:
                has_service = True
                break
        if has_service:
            doc_types.append(LegalDocument.DocType.SERVICES_POLICY)

        record_acceptance_for_doc_types(
            request=request,
            user=request.user,
            guest_email=guest_email,
            doc_types=doc_types,
        )
    except ValidationError as e:
        messages.error(request, str(e) or "Legal documents are not available right now.")
        return redirect("cart:detail")
    except Exception:
        logger.exception("Failed to record legal acceptance")
        messages.error(request, "We couldn't record legal acceptance right now. Please try again.")
        return redirect("cart:detail")

    try:
        order = create_order_from_cart(cart, buyer=request.user, guest_email=guest_email)
    except (ValueError, ValidationError) as e:
        messages.error(request, str(e) or "Your cart can’t be checked out right now.")
        return redirect("cart:detail")

    # If this is a free order, complete immediately (no Stripe)
    if int(order.total_cents or 0) <= 0:
        order.mark_paid(payment_intent_id="FREE")
        cart.clear()
        messages.success(request, "Your order is complete.")
        if order.is_guest:
            return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.order_token}")
        return _redirect_order_detail(order, request)
    # Move to checkout review page (buyer can choose payment + adjust tip there).
    cart.clear()
    messages.info(request, "Order created. Review by seller and choose payment method to continue.")
    if order.is_guest:
        return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.order_token}")
    return redirect("orders:detail", order_id=order.pk)


def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related(
            "items",
            "items__seller",
            "items__refund_request",
            "items__product",
        ),
        pk=order_id,
    )

    if not _user_can_access_order(request, order):
        if order.buyer_id and not request.user.is_authenticated:
            return redirect("accounts:login")
        raise Http404("Not found")

    # LocalMarketNE v1: no service file orders.
    can_order = False
    has_digital_assets = False
    shipping_timeline = None
    local_timeline = None
    # (intentionally no order loop)

    if order.requires_shipping:
        shipped = False
        delivered = False
        for item in order.items.all():
            if not item.requires_shipping:
                continue
            if item.fulfillment_status == item.FulfillmentStatus.DELIVERED:
                delivered = True
                shipped = True
                break
            if item.fulfillment_status == item.FulfillmentStatus.SHIPPED:
                shipped = True

        shipping_timeline = {
            "paid": order.status == Order.Status.PAID,
            "shipped": shipped,
            "delivered": delivered,
        }

    # Pickup/Delivery timeline (non-shipping physical items)
    has_local = False
    local_ready = False
    local_delivered = False
    for item in order.items.all():
        if item.is_service or item.is_tip:
            continue
        if item.requires_shipping:
            continue
        # physical pickup/delivery items
        has_local = True
        if item.fulfillment_status == OrderItem.FulfillmentStatus.DELIVERED:
            local_delivered = True
            local_ready = True
        elif item.fulfillment_status == OrderItem.FulfillmentStatus.READY:
            local_ready = True

    if has_local:
        local_timeline = {
            "paid": order.status == Order.Status.PAID,
            "ready": local_ready,
            "delivered": local_delivered,
        }

    # Off-platform QR codes (optional, seller-controlled toggles)
    offline_qr_by_seller = {}  # seller_id -> data uri
    offline_label_by_seller = {}  # seller_id -> display label/handle/url
    any_venmo = any_paypal = any_zelle = any_cashapp = False
    try:
        pm = (order.payment_method or "").strip()
        for oi in order.items.select_related("seller", "seller__profile").all():
            prof = getattr(oi.seller, "profile", None)
            if not prof:
                continue
            venmo = (getattr(prof, "venmo_handle", "") or "").strip()
            paypal = (getattr(prof, "paypal_me_url", "") or "").strip()
            zelle = (getattr(prof, "zelle_contact", "") or "").strip()
            cashapp = (getattr(prof, "cashapp_handle", "") or "").strip()
            if venmo:
                any_venmo = True
            if paypal:
                any_paypal = True
            if zelle:
                any_zelle = True
            if cashapp:
                any_cashapp = True

            data = None
            label = None
            if pm == Order.PaymentMethod.VENMO and venmo and getattr(prof, "show_venmo_qr_checkout", False):
                label = f"@{venmo.lstrip('@')}"
                data = qr_data_uri(f"https://venmo.com/{venmo.lstrip('@')}")
            elif pm == Order.PaymentMethod.PAYPAL and paypal and getattr(prof, "show_paypal_qr_checkout", False):
                label = paypal
                data = qr_data_uri(paypal)
            elif pm == Order.PaymentMethod.ZELLE and zelle and getattr(prof, "show_zelle_qr_checkout", False):
                label = zelle
                data = qr_data_uri(zelle)
            elif pm == getattr(Order.PaymentMethod, "CASHAPP", "cashapp") and cashapp and getattr(prof, "show_cashapp_qr_checkout", False):
                label = f"${cashapp.lstrip('$')}"
                data = qr_data_uri(f"https://cash.app/${cashapp.lstrip('$')}")

            if data:
                offline_qr_by_seller[oi.seller_id] = data
                offline_label_by_seller[oi.seller_id] = label or ""
    except Exception:
        offline_qr_by_seller = {}
        offline_label_by_seller = {}
        any_venmo = any_paypal = any_zelle = any_cashapp = False


    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "order_token": _token_from_request(request),
            "can_order": can_order,
            "has_digital_assets": has_digital_assets,
            "shipping_timeline": shipping_timeline,
            "local_timeline": local_timeline,
            "stripe_publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
            "checkout_enabled": _is_owner_request(request) or _safe_checkout_enabled(),
            "checkout_disabled_message": _safe_checkout_disabled_message(),
            "offline_qr_by_seller": offline_qr_by_seller,
            "offline_label_by_seller": offline_label_by_seller,
            "any_venmo": any_venmo,
            "any_paypal": any_paypal,
            "any_zelle": any_zelle,
            "any_cashapp": any_cashapp,
            "seller_groups": _order_seller_groups(order),
        },
    )


@require_POST
@throttle(SET_FULFILLMENT_RULE)
def order_update_tips(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "items__seller", "items__product"),
        pk=order_id,
    )
    if not _user_can_access_order(request, order):
        if order.buyer_id and not request.user.is_authenticated:
            return redirect("accounts:login")
        raise Http404("Not found")

    if order.status != Order.Status.PENDING:
        messages.info(request, "Tips can only be updated before payment.")
        return _redirect_order_detail(order, request)

    seller_ids: set[int] = set(
        int(item.seller_id)
        for item in order.items.filter(is_tip=False).only("seller_id")
    )

    order.items.filter(is_tip=True).delete()

    created = 0
    for sid in seller_ids:
        raw = (request.POST.get(f"tip_seller_{sid}") or "").strip()
        if raw == "":
            continue
        try:
            val = Decimal(raw.replace("$", "").replace(",", ""))
        except (InvalidOperation, ValueError):
            continue
        if val <= 0:
            continue
        tip_cents = int(money_to_cents(str(val)))
        if tip_cents <= 0:
            continue

        base_item = (
            order.items.filter(seller_id=sid, is_tip=False)
            .select_related("product", "seller")
            .first()
        )
        if not base_item:
            continue

        OrderItem.objects.create(
            order=order,
            product=base_item.product,
            seller=base_item.seller,
            title_snapshot="Tip",
            sku_snapshot="",
            unit_price_cents_snapshot=tip_cents,
            quantity=1,
            line_total_cents=tip_cents,
            tax_cents=0,
            marketplace_fee_cents=0,
            seller_net_cents=tip_cents,
            is_service=False,
            is_tip=True,
            fulfillment_mode_snapshot="tip",
            delivery_fee_cents_snapshot=0,
            shipping_fee_cents_snapshot=0,
            pickup_instructions_snapshot="",
            lead_time_days_snapshot=None,
        )
        created += 1

    # order was loaded with prefetch_related("items"); invalidate stale cache
    # so totals include newly created tip rows.
    try:
        if hasattr(order, "_prefetched_objects_cache"):
            order._prefetched_objects_cache.pop("items", None)
    except Exception:
        pass
    order.recompute_totals()
    order.save(
        update_fields=[
            "subtotal_cents",
            "tax_cents",
            "shipping_cents",
            "total_cents",
            "kind",
            "updated_at",
        ]
    )
    messages.success(request, f"Tip updated for {created} seller(s).")
    return _redirect_order_detail(order, request)


@require_POST
@throttle(SET_FULFILLMENT_RULE)
def order_set_fulfillment(request, order_id):
    """Persist buyer fulfillment choices for goods items before payment."""
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "items__product"),
        pk=order_id,
    )
    if not _user_can_access_order(request, order):
        raise Http404("Not found")

    if request.method != "POST":
        return _redirect_order_detail(order, request)

    # Update each goods item based on posted radio values
    changed = False
    shipping_total = 0

    for oi in order.items.select_related("product").all():
        if oi.is_tip or oi.is_service:
            continue

        method = (request.POST.get(f"fulfillment_{oi.pk}") or "").strip().lower()
        product = oi.product

        allowed = set()
        if getattr(product, "pickup_enabled", False):
            allowed.add(OrderItem.FulfillmentMethod.PICKUP)
        if getattr(product, "delivery_enabled", False):
            allowed.add(OrderItem.FulfillmentMethod.DELIVERY)
        if getattr(product, "shipping_enabled", False):
            allowed.add(OrderItem.FulfillmentMethod.SHIPPING)

        # Default if not chosen
        if not method:
            method = next(iter(allowed), OrderItem.FulfillmentMethod.PICKUP)

        if method not in allowed:
            messages.error(request, f"Invalid fulfillment choice for {product.title}.")
            return _redirect_order_detail(order, request)

        oi.fulfillment_method = method
        oi.pickup_instructions_snapshot = (product.pickup_instructions or "") if method == OrderItem.FulfillmentMethod.PICKUP else ""
        oi.delivery_fee_cents_snapshot = int(product.delivery_fee_cents or 0) if method == OrderItem.FulfillmentMethod.DELIVERY else 0
        oi.shipping_fee_cents_snapshot = int(product.shipping_fee_cents or 0) if method == OrderItem.FulfillmentMethod.SHIPPING else 0
        oi.save(update_fields=[
            "fulfillment_mode_snapshot",
            "pickup_instructions_snapshot",
            "delivery_fee_cents_snapshot",
            "shipping_fee_cents_snapshot",
        ])
        changed = True

        # Delivery/shipping ZIP validation (best-effort; v1 uses ZIP prefix approximation)
        def _zip5(raw: str) -> str:
            raw = (raw or "").strip()
            digits = "".join([c for c in raw if c.isdigit()])
            return digits[:5]

        buyer_zip = _zip5(order.shipping_postal_code or "")
        if not buyer_zip and order.buyer_id:
            try:
                buyer_zip = _zip5(order.buyer.profile.zip_code or "")
            except Exception:
                buyer_zip = ""

        if method in {OrderItem.FulfillmentMethod.DELIVERY, OrderItem.FulfillmentMethod.SHIPPING} and not buyer_zip:
            messages.error(
                request,
                "Please add your ZIP code to your profile (or shipping address) before choosing delivery/shipping.",
            )
            return _redirect_order_detail(order, request)

        if method == OrderItem.FulfillmentMethod.DELIVERY:
            seller_zip = ""
            try:
                seller_zip = _zip5(oi.seller.profile.zip_code or "")
            except Exception:
                seller_zip = ""

            radius = int(getattr(product, "delivery_radius_miles", 0) or 0)

            # Approximation: if the first 3 ZIP digits match, treat as local.
            same_prefix = True
            if seller_zip and len(seller_zip) >= 3 and buyer_zip and len(buyer_zip) >= 3:
                same_prefix = seller_zip[:3] == buyer_zip[:3]

            if radius > 0 and buyer_zip and seller_zip and not same_prefix:
                messages.error(
                    request,
                    "This seller’s delivery radius does not cover your ZIP code. Choose pickup or shipping instead.",
                )
                return _redirect_order_detail(order, request)

        if method == OrderItem.FulfillmentMethod.DELIVERY:
            shipping_total += oi.delivery_fee_cents_snapshot
        elif method == OrderItem.FulfillmentMethod.SHIPPING:
            shipping_total += oi.shipping_fee_cents_snapshot

    if changed:
        order.shipping_cents = int(shipping_total)
        order.recompute_totals()
        order.save(update_fields=["shipping_cents", "subtotal_cents", "total_cents", "kind", "updated_at"])
        messages.success(request, "Fulfillment choices saved.")

    return _redirect_order_detail(order, request)


@require_POST
@throttle(CHECKOUT_START_RULE)
@require_recaptcha_v3("checkout_start")
def checkout_start(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "items__seller", "items__product"),
        pk=order_id,
    )

    if not _user_can_access_order(request, order):
        if order.buyer_id and not request.user.is_authenticated:
            return redirect("accounts:login")
        raise Http404("Not found")

    guest_email = getattr(order, "guest_email", "") or ""
    legal_redirect = _require_legal_acceptance_or_redirect(
        request,
        guest_email=guest_email,
        next_url=reverse("orders:detail", kwargs={"order_id": order.pk})
        + (f"?t={order.order_token}" if order.is_guest else ""),
    )
    if legal_redirect is not None:
        return legal_redirect

    age_check = _require_age_18_or_redirect(request, next_url=reverse('orders:detail', kwargs={'order_id': order.pk}))
    if age_check is not None:
        return age_check


    policy_check = _require_no_prohibited_items_or_redirect(request, order=order)
    if policy_check is not None:
        return policy_check

    # Emergency kill switch: allow browsing, but block checkout.
    try:
        from core.config import get_checkout_disabled_message, is_checkout_enabled

        if not is_checkout_enabled() and not _is_owner_request(request):
            messages.error(request, get_checkout_disabled_message())
            return _redirect_order_detail(order, request)
    except Exception:
        # If config load fails, do NOT hard-block checkout.
        pass

    if order.status != Order.Status.PENDING:
        messages.info(request, "This order is not payable.")
        return _redirect_order_detail(order, request)

    # Native analytics funnel event (Pack AK): checkout started
    # Best-effort + throttled per session+order to avoid duplicates.
    try:
        sk = f"lmne_event_checkout_started_{order.pk}"
        if not request.session.get(sk):
            from analytics.models import AnalyticsEvent
            from analytics.services import log_event_from_request

            log_event_from_request(
                request,
                event_type=AnalyticsEvent.EventType.CHECKOUT_STARTED,
                path=(request.path or "/")[:512],
                status_code=200,
                meta={
                    "order_id": str(order.pk),
                    "is_guest": bool(getattr(order, "is_guest", False)),
                    "total_cents": int(getattr(order, "total_cents", 0) or 0),
                },
            )
            request.session[sk] = True
            request.session.modified = True
    except Exception:
        pass

    
    # Require fulfillment selections for goods items (pickup/delivery/shipping) before payment.
    goods_items = [oi for oi in order.items.all() if (not oi.is_tip and not oi.is_service)]
    if goods_items:
        missing = [oi for oi in goods_items if not (oi.fulfillment_method or "").strip()]
        if missing:
            messages.info(request, "Please choose fulfillment options for your items before payment.")
            return _redirect_order_detail(order, request)

    payment_method = (request.POST.get("payment_method") or "stripe").strip().lower()

    # If any service line requires a Stripe deposit, force Stripe payment at checkout.
    requires_stripe_deposit = order.items.filter(product__kind=Product.Kind.SERVICE).exclude(product__service_deposit_cents=0).exists()
    if requires_stripe_deposit and payment_method != Order.PaymentMethod.STRIPE:
        messages.error(request, "This order includes a service deposit, which must be paid via Stripe.")
        return _redirect_order_detail(order, request)

    if payment_method and payment_method != Order.PaymentMethod.STRIPE:
        order.payment_method = payment_method if payment_method in dict(Order.PaymentMethod.choices) else Order.PaymentMethod.VENMO
        order.status = Order.Status.AWAITING_PAYMENT
        order.save(update_fields=["payment_method", "status", "updated_at"])
        messages.success(request, "Order placed. Follow the payment instructions to complete payment.")
        return _redirect_order_detail(order, request)

    if order.items.count() == 0:
        messages.error(request, "Order has no items.")
        return _redirect_order_detail(order, request)

    inactive_titles = _order_inactive_titles(order)
    if inactive_titles and not _is_owner_request(request):
        messages.error(
            request,
            "One or more items in this order are no longer available: " + ", ".join(inactive_titles),
        )
        return _redirect_order_detail(order, request)

    bad_sellers = _order_has_unready_sellers(request, order)
    if bad_sellers:
        messages.error(
            request,
            "One or more sellers in this order haven’t completed payout setup yet: " + ", ".join(bad_sellers),
        )
        return _redirect_order_detail(order, request)

    if int(order.total_cents or 0) <= 0:
        order.mark_paid(payment_intent_id="FREE")
        messages.success(request, "Your order is complete.")
        return _redirect_order_detail(order, request)

    try:
        session = create_checkout_session_for_order(request=request, order=order)
    except Exception:
        logger.exception("Checkout start failed for order=%s", order.pk)
        messages.error(request, "We couldn't start checkout right now. Please try again.")
        return _redirect_order_detail(order, request)
    return redirect(session.url)


def checkout_success(request):
    session_id = (request.GET.get("session_id") or "").strip()
    if not session_id:
        messages.info(request, "Checkout completed. If your order doesn't update immediately, refresh in a moment.")
        return redirect("home")

    order = Order.objects.filter(stripe_session_id=session_id).first()

    order_detail_url = ""
    if order:
        if order.is_guest:
            order_detail_url = f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={order.order_token}"
        else:
            order_detail_url = reverse("orders:detail", kwargs={"order_id": order.pk})

    return render(request, "orders/checkout_success.html", {"order": order, "order_detail_url": order_detail_url})


def checkout_cancel(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    if not _user_can_access_order(request, order):
        if order.buyer_id and not request.user.is_authenticated:
            return redirect("accounts:login")
        raise Http404("Not found")
    if order.status in {Order.Status.PENDING, Order.Status.AWAITING_PAYMENT}:
        order.mark_canceled(note="Checkout canceled by buyer")
        messages.info(request, "Checkout canceled.")
    else:
        messages.info(request, "This order can no longer be canceled from checkout.")
    return _redirect_order_detail(order, request)




def my_orders(request):
    qs = (
        Order.objects.filter(buyer=request.user)
        .prefetch_related("items", "items__product")
        .order_by("-created_at")
    )
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(request, "orders/my_orders.html", {"page_obj": page, "orders": page.object_list})

@login_required
def seller_orders_list(request):
    """Seller fulfillment queue.

    Shows PAID orders and the seller's *physical* line items that still require action.
    Primary view is the pending queue (unfulfilled physical items).
    """
    user = request.user
    if not (is_seller_user(user) or is_owner_user(user)):
        messages.info(request, "You don’t have access to seller orders.")
        return redirect("dashboards:consumer")

    status = (request.GET.get("status") or "pending").strip().lower()
    if status not in {"pending", "ready", "out_for_delivery", "picked_up", "shipped", "delivered", "all"}:
        status = "pending"

    # NOTE: `requires_shipping` is a Python @property, not a DB field. For Local Market NE,
    # seller fulfillment includes physical goods regardless of fulfillment mode (pickup/delivery/shipping).
    # Exclude service items and tips, and exclude digital fulfillment.
    qs = (
        OrderItem.objects.filter(order__status=Order.Status.PAID, order__paid_at__isnull=False)
        .filter(is_service=False, is_tip=False)
        .exclude(fulfillment_mode_snapshot__iexact="digital")
        .select_related("order", "product", "seller")
        .order_by("-order__paid_at", "-created_at")
    )

    if not is_owner_user(user):
        qs = qs.filter(seller=user)

    if status == "pending":
        qs = qs.filter(fulfillment_status=OrderItem.FulfillmentStatus.PENDING)
    elif status == "ready":
        qs = qs.filter(fulfillment_status=OrderItem.FulfillmentStatus.READY)
    elif status == "out_for_delivery":
        qs = qs.filter(fulfillment_status=OrderItem.FulfillmentStatus.OUT_FOR_DELIVERY)
    elif status == "picked_up":
        qs = qs.filter(fulfillment_status=OrderItem.FulfillmentStatus.PICKED_UP)
    elif status == "shipped":
        qs = qs.filter(fulfillment_status=OrderItem.FulfillmentStatus.SHIPPED)
    elif status == "delivered":
        qs = qs.filter(fulfillment_status=OrderItem.FulfillmentStatus.DELIVERED)

    # Counters for tabs (seller-scoped)
    base_counter_qs = (
        OrderItem.objects.filter(order__status=Order.Status.PAID, order__paid_at__isnull=False)
        .filter(is_service=False, is_tip=False)
        .exclude(fulfillment_mode_snapshot__iexact="digital")
    )
    if not is_owner_user(user):
        base_counter_qs = base_counter_qs.filter(seller=user)

    counts = base_counter_qs.aggregate(
        pending=Count("id", filter=Q(fulfillment_status=OrderItem.FulfillmentStatus.PENDING)),
        ready=Count("id", filter=Q(fulfillment_status=OrderItem.FulfillmentStatus.READY)),
        out_for_delivery=Count("id", filter=Q(fulfillment_status=OrderItem.FulfillmentStatus.OUT_FOR_DELIVERY)),
        picked_up=Count("id", filter=Q(fulfillment_status=OrderItem.FulfillmentStatus.PICKED_UP)),
        shipped=Count("id", filter=Q(fulfillment_status=OrderItem.FulfillmentStatus.SHIPPED)),
        delivered=Count("id", filter=Q(fulfillment_status=OrderItem.FulfillmentStatus.DELIVERED)),
        total=Count("id"),
    )

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page") or 1)

    return render(
        request,
        "orders/seller_orders_list.html",
        {
            "page_obj": page,
            "items": page.object_list,
            "status": status,
            "counts": counts,
        },
    )

@login_required
@require_POST

def seller_payments_queue(request):
    """Seller queue for off-platform payments awaiting confirmation."""
    user = request.user
    if not (is_seller_user(user) or is_owner_user(user)):
        messages.info(request, "You don’t have access to seller payments.")
        return redirect("dashboards:consumer")

    from .models import OrderItem, Order

    qs = (
        OrderItem.objects.select_related("order", "product", "order__buyer")
        .filter(seller=user, order__status=Order.Status.AWAITING_PAYMENT)
        .exclude(order__payment_method=Order.PaymentMethod.STRIPE)
        .order_by("-order__created_at")
    )

    # group by order for display
    orders = {}
    for item in qs:
        orders.setdefault(item.order_id, {"order": item.order, "items": []})["items"].append(item)

    context = {
        "page_title": "Payments (Awaiting confirmation)",
        "orders": [v for v in orders.values()],
    }
    return render(request, "orders/seller_payments_queue.html", context)

@require_POST
@throttle(BUYER_CONFIRM_RULE)
def mark_item_delivered_buyer(request, order_id, item_id):
    """Buyer confirms they received a physical item.

    Rules:
    - Access: logged-in buyer OR guest with token.
    - Shipping items: can confirm after seller marks SHIPPED.
    - Pickup/Delivery items: can confirm after seller marks READY.
    """
    order = get_object_or_404(Order, id=order_id)

    token = (request.POST.get("t") or request.GET.get("t") or "").strip()
    if order.is_guest:
        if not token or token != str(order.order_token):
            raise Http404("Not found")
    else:
        if not request.user.is_authenticated or request.user.id != order.buyer_id:
            raise Http404("Not found")

    item = get_object_or_404(OrderItem, id=item_id, order=order)

    if item.is_service or item.is_tip:
        raise Http404("Not found")

    if getattr(order, "status", "") != Order.Status.PAID:
        messages.info(request, "This order isn’t paid yet.")
        return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.id})}" + (f"?t={order.order_token}" if order.is_guest else ""))

    required_status = OrderItem.FulfillmentStatus.SHIPPED if item.requires_shipping else OrderItem.FulfillmentStatus.READY
    if item.fulfillment_status != required_status:
        messages.info(request, "This item can only be confirmed after the seller marks it ready/shipped.")
        return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.id})}" + (f"?t={order.order_token}" if order.is_guest else ""))

    item.fulfillment_status = OrderItem.FulfillmentStatus.DELIVERED
    item.save(update_fields=["fulfillment_status"])

    try:
        OrderEvent.objects.create(
            order=order,
            type=OrderEvent.Type.NOTE,
            message="Buyer confirmed delivery.",
            meta={"order_item_id": str(item.id), "method": item.fulfillment_method},
        )
    except Exception:
        pass

    # Mark seller task done if present
    try:
        refresh_fulfillment_task_for_seller(order=order, seller_id=item.seller_id)
    except Exception:
        pass

    messages.success(request, "Thanks — confirmed.")
    return redirect(f"{reverse('orders:detail', kwargs={'order_id': order.id})}" + (f"?t={order.order_token}" if order.is_guest else ""))


def _ensure_seller_can_access_order(request, order: Order) -> None:
    """
    Seller can access an order if at least one line item belongs to them.
    Owner/admin is allowed too (if you have that concept, the decorator likely handles it).
    """
    qs = OrderItem.objects.filter(order=order, seller=request.user)
    if not qs.exists():
        raise Http404()


def _seller_line_item_or_404(request, order: Order, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order=order)
    if getattr(item, "seller_id", None) != request.user.id:
        raise Http404()
    return item


@login_required
@seller_required
def seller_order_detail(request, order_id):
    """
    Seller view of a single order: shows only this seller's line items.
    """
    order = get_object_or_404(Order, id=order_id)
    _ensure_seller_can_access_order(request, order)

    seller_items = (
        OrderItem.objects.filter(order=order, seller=request.user)
        .select_related("product")
        .order_by("created_at")
    )

    # Useful rollups for template
    has_physical = any((not getattr(i, "is_service", False) and not getattr(i, "is_tip", False)) for i in seller_items)
    has_digital = False  # LMNE has no digital downloads

    context = {
        "order": order,
        "items": seller_items,
        "seller_items": seller_items,
        "has_physical": has_physical,
        "has_digital": has_digital,
    }
    return render(request, "orders/seller_orders_detail.html", context)


@login_required
@seller_required
@require_POST
def mark_item_shipped(request, order_id, item_id):
    """
    Seller marks a physical line item as shipped.
    """
    order = get_object_or_404(Order, id=order_id)
    _ensure_seller_can_access_order(request, order)

    item = _seller_line_item_or_404(request, order, item_id)

    # Guardrails
    if getattr(item, "is_service", False) or getattr(item, "is_tip", False) or not getattr(item, "requires_shipping", False):
        raise Http404()

    # Only for paid orders
    if getattr(order, "status", "") != getattr(Order, "Status", Order).PAID:
        # Works whether Order.Status exists or not
        messages.info(request, "This order isn’t paid yet.")
        return redirect("orders:seller_order_detail", order_id=order.id)

    # Mark shipped
    if hasattr(item, "mark_shipped"):
        item.mark_shipped()
    else:
        # Fallback: set fulfillment_status + timestamp fields if they exist
        if hasattr(OrderItem, "FulfillmentStatus") and hasattr(item, "fulfillment_status"):
            item.fulfillment_status = OrderItem.FulfillmentStatus.SHIPPED
        if hasattr(item, "shipped_at"):
            from django.utils import timezone
            item.shipped_at = timezone.now()
        item.save(update_fields=[f for f in ["fulfillment_status", "shipped_at"] if hasattr(item, f)])

    messages.success(request, "Marked as shipped.")
    return redirect("orders:seller_order_detail", order_id=order.id)


@login_required
@seller_required
@require_POST
def mark_item_delivered(request, order_id, item_id):
    """
    Seller marks a physical line item as delivered (optional workflow).
    Buyer-confirm-delivered also exists separately.
    """
    order = get_object_or_404(Order, id=order_id)
    _ensure_seller_can_access_order(request, order)

    item = _seller_line_item_or_404(request, order, item_id)

    # Guardrails
    if getattr(item, "is_service", False) or getattr(item, "is_tip", False) or not getattr(item, "requires_shipping", False):
        raise Http404()

    if getattr(order, "status", "") != getattr(Order, "Status", Order).PAID:
        messages.info(request, "This order isn’t paid yet.")
        return redirect("orders:seller_order_detail", order_id=order.id)

    # Optional guard: only allow delivered after shipped
    if hasattr(OrderItem, "FulfillmentStatus") and hasattr(item, "fulfillment_status"):
        if item.fulfillment_status != OrderItem.FulfillmentStatus.SHIPPED:
            messages.info(request, "Mark shipped first.")
            return redirect("orders:seller_order_detail", order_id=order.id)

    # Mark delivered
    if hasattr(item, "mark_delivered"):
        item.mark_delivered()
    else:
        if hasattr(OrderItem, "FulfillmentStatus") and hasattr(item, "fulfillment_status"):
            item.fulfillment_status = OrderItem.FulfillmentStatus.DELIVERED
        if hasattr(item, "delivered_at"):
            from django.utils import timezone
            item.delivered_at = timezone.now()
        item.save(update_fields=[f for f in ["fulfillment_status", "delivered_at"] if hasattr(item, f)])

    messages.success(request, "Marked as delivered.")
    return redirect("orders:seller_order_detail", order_id=order.id)



@require_POST
@throttle(BUYER_OFFPLATFORM_RULE)
def buyer_mark_offplatform_sent(request, order_id):
    """Buyer indicates they've sent an off-platform payment (informational)."""
    order = get_object_or_404(Order, id=order_id)

    # Access: logged-in buyer OR guest with token.
    token = (request.POST.get("t") or request.GET.get("t") or "").strip()
    if order.is_guest:
        if not token or token != str(order.order_token):
            raise Http404("Not found")
    else:
        if not request.user.is_authenticated or request.user.id != order.buyer_id:
            raise Http404("Not found")

    if request.method != "POST":
        return _redirect_order_detail(order, request)

    if order.status != Order.Status.AWAITING_PAYMENT or order.payment_method == Order.PaymentMethod.STRIPE:
        messages.info(request, "This order isn’t awaiting an off-platform payment.")
        return _redirect_order_detail(order, request)

    note = (request.POST.get("offplatform_note") or "").strip()
    if len(note) > 2000:
        note = note[:2000]

    order.offplatform_sent_at = timezone.now()
    order.offplatform_note = note
    order.save(update_fields=["offplatform_sent_at", "offplatform_note", "updated_at"])

    try:
        OrderEvent.objects.create(order=order, type=OrderEvent.Type.WARNING, message=f"Buyer marked off-platform payment sent ({order.payment_method}).")
    except Exception:
        pass

    messages.success(request, "Thanks — the seller will confirm once payment is received.")
    return _redirect_order_detail(order, request)


@login_required
@seller_required
@require_POST
def seller_confirm_payment(request, order_id):
    """Seller confirms off-platform payment (Venmo/PayPal/Zelle) was received."""
    order = get_object_or_404(Order, id=order_id)
    _ensure_seller_can_access_order(request, order)

    if order.status != Order.Status.AWAITING_PAYMENT:
        messages.info(request, "This order is not awaiting payment.")
        return redirect("orders:seller_order_detail", order_id=order.id)

    if order.payment_method == Order.PaymentMethod.STRIPE:
        messages.info(request, "Stripe orders are confirmed automatically after payment.")
        return redirect("orders:seller_order_detail", order_id=order.id)

    order.mark_paid(payment_intent_id=f"OFFPLATFORM:{order.payment_method}", note="Seller confirmed off-platform payment received.")
    messages.success(request, "Payment confirmed. Order marked paid.")
    return redirect("orders:seller_order_detail", order_id=order.id)


@login_required
@seller_required
@require_POST
def seller_set_item_status(request, order_id, item_id):
    """Seller updates fulfillment status for a single physical goods line item."""
    order = get_object_or_404(Order, id=order_id)
    _ensure_seller_can_access_order(request, order)
    item = _seller_line_item_or_404(request, order, item_id)

    if item.is_tip or item.is_service:
        raise Http404()

    method = (item.fulfillment_method or "").strip()
    if method not in {
        OrderItem.FulfillmentMethod.PICKUP,
        OrderItem.FulfillmentMethod.DELIVERY,
        OrderItem.FulfillmentMethod.SHIPPING,
    }:
        raise Http404()

    if order.status != Order.Status.PAID:
        messages.info(request, "This order isn’t paid yet.")
        return redirect("orders:seller_order_detail", order_id=order.id)

    new_status = (request.POST.get("fulfillment_status") or "").strip()

    prev_status = item.fulfillment_status

    allowed = {c[0] for c in OrderItem.FulfillmentStatus.choices}
    if new_status not in allowed:
        messages.error(request, "Invalid fulfillment status.")
        return redirect("orders:seller_order_detail", order_id=order.id)

    # Restrict by fulfillment method
    if method == OrderItem.FulfillmentMethod.PICKUP:
        ok = {OrderItem.FulfillmentStatus.PENDING, OrderItem.FulfillmentStatus.READY, OrderItem.FulfillmentStatus.PICKED_UP}
    elif method == OrderItem.FulfillmentMethod.DELIVERY:
        ok = {OrderItem.FulfillmentStatus.PENDING, OrderItem.FulfillmentStatus.OUT_FOR_DELIVERY, OrderItem.FulfillmentStatus.DELIVERED}
    else:  # shipping
        ok = {OrderItem.FulfillmentStatus.PENDING, OrderItem.FulfillmentStatus.SHIPPED, OrderItem.FulfillmentStatus.DELIVERED}

    if new_status not in ok:
        messages.error(request, "That status isn’t valid for this fulfillment method.")
        return redirect("orders:seller_order_detail", order_id=order.id)

    item.fulfillment_status = new_status

    update_fields = ["fulfillment_status"]

    # If shipping, allow optional tracking fields when marking shipped.
    if method == OrderItem.FulfillmentMethod.SHIPPING and new_status == OrderItem.FulfillmentStatus.SHIPPED:
        carrier = (request.POST.get("tracking_carrier") or request.POST.get("carrier") or "").strip()
        # Some templates use a select named "carrier" with an optional "carrier_other" free-text input.
        if carrier.lower() in {"other", ""}:
            carrier = (request.POST.get("carrier_other") or request.POST.get("tracking_carrier_other") or "").strip()
        number = (request.POST.get("tracking_number") or "").strip()
        if carrier:
            item.tracking_carrier = carrier
            update_fields.append("tracking_carrier")
        if number:
            item.tracking_number = number
            update_fields.append("tracking_number")
        if not item.shipped_at:
            item.shipped_at = timezone.now()
            update_fields.append("shipped_at")

    # Delivered timestamp
    if new_status == OrderItem.FulfillmentStatus.DELIVERED and not item.delivered_at:
        item.delivered_at = timezone.now()
        update_fields.append("delivered_at")

    update_fields.append("updated_at")
    item.save(update_fields=update_fields)

    # Keep SellerFulfillmentTask rows in sync (mark done when delivered/canceled).
    try:
        from .services import refresh_fulfillment_task_for_seller
        refresh_fulfillment_task_for_seller(order=order, seller_id=request.user.id)
    except Exception:
        pass

    # Email buyer when shipping item is marked shipped (with optional tracking)
    if method == OrderItem.FulfillmentMethod.SHIPPING and new_status == OrderItem.FulfillmentStatus.SHIPPED and prev_status != new_status:
        try:
            from orders.models import _send_buyer_item_shipped_email
            _send_buyer_item_shipped_email(order, item)
        except Exception:
            pass

    try:
        OrderEvent.objects.create(order=order, type=OrderEvent.Type.WARNING, message=f"Seller set {item.product_id} fulfillment_status={new_status}")
    except Exception:
        pass

    messages.success(request, "Fulfillment status updated.")
    return redirect("orders:seller_order_detail", order_id=order.id)


@login_required
def seller_update_order_note(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    _ensure_seller_can_access_order(request, order)

    if request.method != "POST":
        return redirect("orders:seller_order_detail", order_id=order.id)

    note = (request.POST.get("seller_internal_note") or "").strip()
    if len(note) > 4000:
        note = note[:4000]

    order.seller_internal_note = note
    order.save(update_fields=["seller_internal_note", "updated_at"])
    messages.success(request, "Internal note saved.")
    return redirect("orders:seller_order_detail", order_id=order.id)


# cart/views.py
from __future__ import annotations

import logging
from typing import List, Tuple

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.throttle import throttle
from core.throttle_rules import CART_MUTATE
from core.config import get_checkout_disabled_message, get_site_config, is_checkout_enabled
from payments.utils import seller_is_stripe_ready
from products.models import Product, ProductEngagementEvent
from products.permissions import is_owner_user

from .cart import Cart

logger = logging.getLogger(__name__)


def get_remaining_product_limit(product, user):
    """
    Get per-order purchase cap for a product.

    Returns:
        int: Max quantity allowed in cart for this product.
    """
    try:
        if getattr(product, "kind", None) == Product.Kind.SERVICE:
            return 1
    except Exception:
        pass

    cap = 20
    if getattr(product, "kind", None) == Product.Kind.GOOD and not getattr(product, "is_made_to_order", False):
        stock = int(getattr(product, "stock_qty", 0) or 0)
        if stock > 0:
            cap = min(cap, stock)
    return max(1, int(cap))


def _prune_blocked_items(request, cart: Cart) -> Tuple[List[str], List[str]]:
    """
    Remove inactive items and return (removed_titles, unready_sellers).
    """
    removed_titles = _prune_inactive_items(cart)
    unready_sellers = _cart_unready_sellers(request, cart)
    return removed_titles, unready_sellers


# ============================================================
# Throttle rules
# ============================================================
CART_ADD_RULE = CART_MUTATE
CART_UPDATE_RULE = CART_MUTATE
CART_REMOVE_RULE = CART_MUTATE
CART_CLEAR_RULE = CART_MUTATE


# ============================================================
# Helpers
# ============================================================
def _is_owner_request(request) -> bool:
    try:
        return bool(request.user.is_authenticated and is_owner_user(request.user))
    except Exception:
        return False


def _clamp_quantity(qty: int) -> int:
    # Keep it simple for v1. You can add per-product max later.
    return max(1, min(qty, 20))


def _seller_block_reason(*, request, product: Product) -> str | None:
    """
    Return a human-readable reason if a product cannot be purchased.

    IMPORTANT:
    - Owner bypass is based on request.user (not the product's seller).
    - Seller readiness is enforced server-side at place_order / checkout_start too.
    """
    if _is_owner_request(request):
        return None

    if (not getattr(product, "is_active", True)) or (getattr(getattr(product, "category", None), "is_prohibited", False)) or (getattr(getattr(product, "subcategory", None), "is_prohibited", False)):
        return "This item is not available right now."


    # Policy enforcement (Pack Z)
    try:
        cat = getattr(product, "category", None)
        sub = getattr(product, "subcategory", None)
        if cat and getattr(cat, "is_prohibited", False):
            return "This item’s category is prohibited on Local Market NE."
        if sub and getattr(sub, "is_prohibited", False):
            return "This item’s subcategory is prohibited on Local Market NE."
    except Exception:
        pass

    return None


import contextlib

def _enforce_service_quantity(product: Product, quantity: int) -> int:
    """
    Service items must always be qty=1.
    """
    with contextlib.suppress(Exception):
        if getattr(product, "kind", None) == Product.Kind.SERVICE:
            return 1
    return quantity


def _log_add_to_cart_throttled(request, *, product: Product) -> None:
    """
    Log ADD_TO_CART with a simple session throttle to avoid spam.
    (One per session per product.)
    """
    try:
        key = f"lmne_event_add_to_cart_{product.pk}"
        if request.session.get(key):
            return
        ProductEngagementEvent.objects.create(product=product, kind=ProductEngagementEvent.Kind.ADD_TO_CART, user=request.user if request.user.is_authenticated else None, session_key=getattr(request.session,'session_key','') or '')

        # Native analytics funnel event (Pack AK)
        try:
            from analytics.services import log_event_from_request
            from analytics.models import AnalyticsEvent

            log_event_from_request(
                request,
                event_type=AnalyticsEvent.EventType.ADD_TO_CART,
                path=(request.path or "/")[:512],
                status_code=200,
                meta={
                    "product_id": int(product.pk),
                    "seller_id": int(getattr(getattr(product, "seller", None), "pk", 0) or 0),
                },
            )
        except Exception:
            pass

        request.session[key] = True
        request.session.modified = True
    except Exception:
        return


def _prune_inactive_items(cart: Cart) -> List[str]:
    """
    Remove items that are no longer available (inactive/deleted).
    Returns removed product titles.
    """
    removed_titles: List[str] = []
    for line in cart.lines():
        product = line.product
        if (not getattr(product, "is_active", True)) or (getattr(getattr(product, "category", None), "is_prohibited", False)) or (getattr(getattr(product, "subcategory", None), "is_prohibited", False)):
            cart.remove(product)
            removed_titles.append(getattr(product, "title", str(product.pk)))
    return removed_titles


def _cart_unready_sellers(request, cart: Cart) -> List[str]:
    """
    Return list of seller usernames that are not ready for payouts.
    IMPORTANT: Does NOT remove items — just used to block checkout.
    """
    if _is_owner_request(request):
        return []

    unready: List[str] = []
    for line in cart.lines():
        product = line.product
        seller = getattr(product, "seller", None)
        if seller and not seller_is_stripe_ready(seller):
            unready.append(getattr(seller, "username", str(getattr(seller, "pk", ""))))

    seen = set()
    out: List[str] = []
    for u in unready:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


# ============================================================
# Views
# ============================================================
def cart_detail(request):
    cart = Cart(request)

    # IMPORTANT: do NOT auto-remove unready sellers from cart.
    # Only block checkout. (Online store behavior.)
    removed_titles, unready_sellers = _prune_blocked_items(request, cart)
    if removed_titles:
        messages.warning(
            request,
            "Some items were removed from your cart because they can’t be checked out right now: "
            + ", ".join(removed_titles),
        )

    cart_lines = cart.lines()

    has_service_items = False
    for line in cart_lines:
        try:
            if getattr(line.product, "kind", None) == Product.Kind.SERVICE:
                has_service_items = True
                break
        except Exception:
            continue

    subtotal = cart.items_subtotal()
    tips_total = cart.tips_total()
    grand_total = cart.grand_total()

    checkout_enabled = bool(is_checkout_enabled() or _is_owner_request(request))
    can_checkout = bool(cart_lines) and not bool(unready_sellers) and checkout_enabled


    # Pack BK: buyer age gating removed (sellers confirm 18+ during onboarding)
    age_18_required = False
    age_18_confirmed = True
    age_gate_text = ""

    return render(
        request,
        "cart/cart_detail.html",
        {
            "cart": cart,
            "cart_lines": cart_lines,
            "subtotal": subtotal,
            "tips_total": tips_total,
            "grand_total": grand_total,
            "unready_sellers": unready_sellers,
            "can_checkout": can_checkout,
            "checkout_enabled": checkout_enabled,
            "checkout_disabled_message": get_checkout_disabled_message() if not checkout_enabled else "",
            "has_service_items": has_service_items,
            # ✅ correct enum constant for template comparisons
            "KIND_SERVICE": Product.Kind.SERVICE,
            "age_18_required": age_18_required,
            "age_18_confirmed": age_18_confirmed,
            "age_gate_text": age_gate_text,
        },
    )


@require_POST
@throttle(CART_ADD_RULE)
def cart_add(request):
    cart = Cart(request)

    product_id = (request.POST.get("product_id") or "").strip()
    qty_raw = (request.POST.get("quantity") or "1").strip()
    custom_colors = (request.POST.get("custom_colors") or "").strip()
    buyer_notes_raw = (request.POST.get("buyer_notes") or "").strip()
    buyer_notes = buyer_notes_raw[:1000]

    if custom_colors:
        color_note = f"Color(s) requested: {custom_colors}"
        buyer_notes = f"{color_note}\n{buyer_notes}" if buyer_notes else color_note

    # Tip
    tip_amount_raw = (request.POST.get("tip_amount") or "").strip()
    is_tip = False
    tip_amount = "0"
    if tip_amount_raw:
        # keep as string; cart will normalize safely
        tip_amount = tip_amount_raw
        try:
            is_tip = float(tip_amount_raw) > 0
        except Exception:
            is_tip = False

    try:
        quantity = int(qty_raw)
    except Exception:
        quantity = 1

    product = get_object_or_404(
        Product.objects.select_related("seller", "category").prefetch_related("images"),
        pk=product_id,
        is_active=True,
    )

    if (reason := _seller_block_reason(request=request, product=product)):
        messages.error(request, reason)
        return redirect(product.get_absolute_url())

    quantity = _clamp_quantity(quantity)
    forced = _enforce_service_quantity(product, quantity)
    if forced != quantity:
        quantity = forced
        messages.info(request, "Service items are limited to 1 per cart.")

    # Enforce purchase limit
    remaining_limit = get_remaining_product_limit(product, request.user)

    in_cart_qty = next((line.quantity for line in cart.lines() if line.product.pk == product.pk), 0)

    if remaining_limit is not None:
        # remaining_limit means "how many more you can buy"
        allowed_additional = max(0, int(remaining_limit) - int(in_cart_qty))
        if allowed_additional <= 0:
            messages.error(request, "You have reached the purchase limit for this product.")
            return redirect(product.get_absolute_url())

        if quantity > allowed_additional:
            quantity = allowed_additional
            messages.warning(
                request,
                f"You can only add {allowed_additional} more of this product due to the purchase limit."
            )

    # Stock enforcement for non-made-to-order goods
    if getattr(product, 'kind', None) == Product.Kind.GOOD and not getattr(product, 'is_made_to_order', False):
        available = int(getattr(product, 'stock_qty', 0) or 0)
        allowed_additional = max(0, available - int(in_cart_qty))
        if allowed_additional <= 0:
            messages.error(request, 'This item is currently out of stock.')
            return redirect(product.get_absolute_url())
        if quantity > allowed_additional:
            quantity = allowed_additional
            messages.warning(request, f'Only {allowed_additional} left in stock. Updated your quantity.')

    if quantity > 0:
        cart.add(product, quantity=quantity, buyer_notes=buyer_notes, is_tip=is_tip, tip_amount=tip_amount)
        _log_add_to_cart_throttled(request, product=product)
        if is_tip:
            messages.success(request, "Added to cart (with tip).")
        else:
            messages.success(request, "Added to cart.")

    if next_url := (request.POST.get("next") or "").strip():
        return redirect(next_url)

    referer = (request.META.get("HTTP_REFERER") or "").strip()
    return redirect(referer) if referer else redirect(product.get_absolute_url())


@require_POST
@throttle(CART_UPDATE_RULE)
def cart_update(request):
    cart = Cart(request)

    product_id = (request.POST.get("product_id") or "").strip()
    qty_raw = (request.POST.get("quantity") or "1").strip()
    buyer_notes = (request.POST.get("buyer_notes") or "").strip()[:1000]

    # Tip update support (optional)
    tip_amount_raw = (request.POST.get("tip_amount") or "").strip()

    try:
        quantity = int(qty_raw)
    except Exception:
        quantity = 1

    product = get_object_or_404(Product.objects.select_related("seller"), pk=product_id)

    if not product.is_active:
        cart.remove(product)
        messages.info(request, "Item removed (no longer available).")
        return redirect("cart:detail")

    if reason := _seller_block_reason(request=request, product=product):
        # keep it in cart (blocked) if unready; remove only if inactive (handled above)
        if "payout setup" in reason.lower():
            messages.error(request, reason)
            return redirect("cart:detail")
        cart.remove(product)
        messages.error(request, f"Removed from cart: {reason}")
        return redirect("cart:detail")

    quantity = _clamp_quantity(quantity)
    forced = _enforce_service_quantity(product, quantity)
    if forced != quantity:
        quantity = forced
        messages.info(request, "Service items are limited to 1 per cart.")

    # Enforce purchase limit
    remaining_limit = get_remaining_product_limit(product, request.user)
    if remaining_limit is not None:
        max_allowed = int(remaining_limit)
        if max_allowed <= 0:
            cart.set_quantity(product, 0)
            messages.error(request, "You have reached the purchase limit for this product.")
            return redirect("cart:detail")

        if quantity > max_allowed:
            quantity = max_allowed
            messages.warning(request, f"You can only have {max_allowed} of this product due to the purchase limit.")

    # Stock enforcement for non-made-to-order goods
    if getattr(product, "kind", None) == Product.Kind.GOOD and not getattr(product, "is_made_to_order", False):
        available = int(getattr(product, "stock_qty", 0) or 0)
        if available <= 0:
            cart.remove(product)
            messages.error(request, "This item is currently out of stock and was removed from your cart.")
            return redirect("cart:detail")
        if quantity > available:
            quantity = available
            messages.warning(request, f"Only {available} left in stock. Updated your quantity.")

    if quantity > 0:
        cart.set_quantity(product, quantity)
        if "buyer_notes" in request.POST:
            cart.set_notes(product, buyer_notes)

        # Tip change/remove if field present
        if "tip_amount" in request.POST:
            cart.set_tip(product, tip_amount_raw)

        messages.success(request, "Cart updated.")
    else:
        cart.set_quantity(product, 0)
        messages.info(request, "Item removed.")
    return redirect("cart:detail")


@require_POST
@throttle(CART_REMOVE_RULE)
def cart_remove(request, product_id: int):
    cart = Cart(request)
    product = get_object_or_404(Product, pk=product_id)
    cart.remove(product)
    messages.info(request, "Item removed.")
    return redirect("cart:detail")


@require_POST
@throttle(CART_CLEAR_RULE)
def cart_clear(request):
    cart = Cart(request)
    cart.clear()
    messages.info(request, "Cart cleared.")
    return redirect("cart:detail")

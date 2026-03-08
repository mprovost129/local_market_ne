# orders/services.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.config import get_site_config
from payments.services_fee_waiver import get_effective_marketplace_sales_percent_for_seller
from payments.utils import money_to_cents
from products.models import Product

from .models import Order, OrderEvent, OrderItem, SellerFulfillmentTask


@dataclass(frozen=True)
class ShippingSnapshot:
    name: str = ""
    phone: str = ""
    line1: str = ""
    line2: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _iter_cart_items(cart_or_items) -> Iterable:
    if hasattr(cart_or_items, "lines") and callable(getattr(cart_or_items, "lines")):
        return cart_or_items.lines()
    return cart_or_items


def _cents_round(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _pct_to_rate(pct: Decimal) -> Decimal:
    try:
        return Decimal(pct) / Decimal("100")
    except Exception:
        return Decimal("0")


def _compute_marketplace_fee_cents(*, gross_cents: int, sales_rate: Decimal) -> int:
    gross = Decimal(int(gross_cents))
    fee = gross * (sales_rate or Decimal("0"))
    return max(0, _cents_round(fee))


@transaction.atomic
def create_order_from_cart(
    cart_or_items=None,
    *,
    cart_items=None,
    buyer,
    guest_email: str,
    currency: str = "usd",
    shipping: Optional[ShippingSnapshot] = None,
) -> Order:
    """Create an Order + OrderItems from a session Cart.

    Pack AH notes:
      - Tips are stored as separate OrderItem rows with is_tip=True.
      - Tip lines bypass marketplace fee and do not affect shipping.
      - Inventory is reserved at order creation for non-made-to-order goods.
    """

    items_iterable = cart_items if cart_items is not None else cart_or_items

    buyer_obj = buyer if getattr(buyer, "is_authenticated", False) else None
    guest_email = normalize_email(guest_email)

    if buyer_obj is None and not guest_email:
        raise ValueError("Guest checkout requires a valid email address.")

    cfg = get_site_config()
    default_sales_pct = Decimal(getattr(cfg, "marketplace_sales_percent", Decimal("0.00")) or Decimal("0.00"))
    try:
        platform_fee_cents = max(0, int(getattr(cfg, "platform_fee_cents", 0) or 0))
    except Exception:
        platform_fee_cents = 0

    order = Order.objects.create(
        buyer=buyer_obj,
        guest_email=guest_email if buyer_obj is None else "",
        currency=(currency or "usd").lower(),
        status=Order.Status.PENDING,
        marketplace_sales_percent_snapshot=default_sales_pct,
        platform_fee_cents_snapshot=platform_fee_cents,
    )

    if shipping:
        order.shipping_name = shipping.name
        order.shipping_phone = shipping.phone
        order.shipping_line1 = shipping.line1
        order.shipping_line2 = shipping.line2
        order.shipping_city = shipping.city
        order.shipping_state = shipping.state
        order.shipping_postal_code = shipping.postal_code
        order.shipping_country = shipping.country

    items = list(_iter_cart_items(items_iterable))

    # Inventory reservation for goods that are not made-to-order
    stock_reserve: dict[int, int] = {}

    # Build OrderItem rows
    order_items: list[OrderItem] = []

    for line in items:
        product = getattr(line, "product", None)
        if product is None:
            raise ValueError("Cart line missing product.")

        # Seller account must be active (suspension enforcement)
        seller = getattr(product, "seller", None)
        if seller is None:
            raise ValueError(f"Product {getattr(product, 'pk', '')} has no seller.")
        if hasattr(seller, "is_active") and not seller.is_active:
            raise ValidationError("A seller in your cart is currently unavailable.")

        # Policy enforcement (Pack Z) — block prohibited items
        cat = getattr(product, "category", None)
        sub = getattr(product, "subcategory", None)
        if cat and getattr(cat, "is_prohibited", False):
            raise ValidationError("Your cart contains a prohibited item category.")
        if sub and getattr(sub, "is_prohibited", False):
            raise ValidationError("Your cart contains a prohibited item subcategory.")
        # Pack BK: buyer age gating removed; sellers confirm 18+ during onboarding

        qty = int(getattr(line, "quantity", 1) or 1)
        if getattr(product, "kind", "") == Product.Kind.SERVICE:
            qty = 1

        unit_price_cents = money_to_cents(getattr(line, "unit_price", None))
        gross_cents = max(0, int(qty) * int(unit_price_cents))

        # Reserve inventory for physical goods that are NOT made-to-order.
        if getattr(product, "kind", "") == Product.Kind.GOOD and not getattr(product, "is_made_to_order", False):
            stock_reserve[int(product.id)] = stock_reserve.get(int(product.id), 0) + int(qty)

        # Marketplace fee uses per-seller effective percent (fee waiver => 0%)
        effective_pct = get_effective_marketplace_sales_percent_for_seller(seller_user=seller)
        effective_rate = _pct_to_rate(effective_pct)

        marketplace_fee_cents = _compute_marketplace_fee_cents(gross_cents=gross_cents, sales_rate=effective_rate)
        seller_net_cents = max(0, gross_cents - marketplace_fee_cents)

        # Base fulfillment defaults (buyer will pick later for goods)
        fulfillment_mode = "pickup"
        delivery_fee = 0
        ship_fee = 0
        pickup_instructions = ""

        if getattr(product, "kind", "") == Product.Kind.GOOD:
            # Default to pickup if enabled, else delivery, else shipping
            if getattr(product, "fulfillment_pickup_enabled", True):
                fulfillment_mode = "pickup"
                pickup_instructions = str(getattr(product, "pickup_instructions", "") or "")
            elif getattr(product, "fulfillment_delivery_enabled", False):
                fulfillment_mode = "delivery"
                delivery_fee = int(getattr(product, "delivery_fee_cents", 0) or 0)
            elif getattr(product, "fulfillment_shipping_enabled", False):
                fulfillment_mode = "shipping"
                ship_fee = int(getattr(product, "shipping_fee_cents", 0) or 0)
        else:
            fulfillment_mode = "service"

        order_items.append(
            OrderItem(
                order=order,
                product=product,
                seller=seller,
                title_snapshot=str(getattr(product, "title", "") or ""),
                sku_snapshot="",
                unit_price_cents_snapshot=int(unit_price_cents),
                quantity=int(qty),
                line_total_cents=int(gross_cents),
                tax_cents=0,
                marketplace_fee_cents=int(marketplace_fee_cents),
                seller_net_cents=int(seller_net_cents),
                is_service=bool(getattr(product, "kind", "") == Product.Kind.SERVICE),
                is_tip=False,
                fulfillment_mode_snapshot=str(fulfillment_mode),
                delivery_fee_cents_snapshot=int(delivery_fee) if delivery_fee else 0,
                shipping_fee_cents_snapshot=int(ship_fee) if ship_fee else 0,
                pickup_instructions_snapshot=str(pickup_instructions),
                lead_time_days_snapshot=int(getattr(product, "lead_time_days", 0) or 0) or None,
            )
        )

        # Tip line (optional)
        tip_amount = getattr(line, "tip_amount", None)
        tip_cents = money_to_cents(tip_amount) if tip_amount else 0
        if tip_cents > 0:
            order_items.append(
                OrderItem(
                    order=order,
                    product=product,
                    seller=seller,
                    title_snapshot="Tip",
                    sku_snapshot="",
                    unit_price_cents_snapshot=int(tip_cents),
                    quantity=1,
                    line_total_cents=int(tip_cents),
                    tax_cents=0,
                    marketplace_fee_cents=0,
                    seller_net_cents=int(tip_cents),
                    is_service=False,
                    is_tip=True,
                    fulfillment_mode_snapshot="tip",
                    delivery_fee_cents_snapshot=0,
                    shipping_fee_cents_snapshot=0,
                    pickup_instructions_snapshot="",
                    lead_time_days_snapshot=None,
                )
            )

    # Inventory reservation
    if stock_reserve:
        locked = {int(p.id): p for p in Product.objects.select_for_update().filter(id__in=list(stock_reserve.keys()))}
        for pid, needed in stock_reserve.items():
            prod = locked.get(int(pid))
            if not prod:
                raise ValueError("A product in your cart is no longer available.")
            if int(prod.stock_qty or 0) < int(needed):
                raise ValueError(f"Insufficient stock for '{prod.title}'. Available: {int(prod.stock_qty or 0)}.")

        for pid, needed in stock_reserve.items():
            prod = locked[int(pid)]
            prod.stock_qty = int(prod.stock_qty or 0) - int(needed)
            prod.save(update_fields=["stock_qty", "updated_at"] if hasattr(prod, "updated_at") else ["stock_qty"])

        order.inventory_reserved = True
        order.inventory_released = False

    OrderItem.objects.bulk_create(order_items)

    order.recompute_totals()
    order.save(
        update_fields=[
            "subtotal_cents",
            "tax_cents",
            "shipping_cents",
            "total_cents",
            "kind",
            "shipping_name",
            "shipping_phone",
            "shipping_line1",
            "shipping_line2",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country",
            "inventory_reserved",
            "inventory_released",
            "updated_at",
        ]
    )

    try:
        OrderEvent.objects.create(order=order, type=OrderEvent.Type.ORDER_CREATED, message="")
    except Exception:
        pass

    return order


@transaction.atomic
def ensure_fulfillment_tasks_for_paid_order(*, order: Order) -> None:
    """Create SellerFulfillmentTask rows per physical order item (non-service, non-tip)."""
    for item in order.items.select_related("seller").all():
        if item.is_service or item.is_tip:
            continue
        # Only create tasks for goods that require fulfillment (pickup/delivery/shipping)
        SellerFulfillmentTask.objects.get_or_create(
            order_item=item,
            defaults={
                "seller": item.seller,
                "is_done": False,
                "done_at": None,
                "created_at": timezone.now(),
            },
        )


@transaction.atomic
def refresh_fulfillment_task_for_seller(*, order: Order, seller_id) -> None:
    """Best-effort helper called by seller fulfillment endpoints."""
    qs = (
        order.items.filter(seller_id=seller_id)
        .select_related("fulfillment_task")
    )
    for item in qs:
        try:
            task = item.fulfillment_task
        except Exception:
            task = None
        if not task:
            continue

        if item.fulfillment_status in {OrderItem.FulfillmentStatus.DELIVERED, OrderItem.FulfillmentStatus.CANCELED}:
            if not task.is_done:
                task.is_done = True
                task.done_at = timezone.now()
                task.save(update_fields=["is_done", "done_at"])

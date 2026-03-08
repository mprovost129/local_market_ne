from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from payments.services_fee_waiver import get_effective_marketplace_sales_percent_for_seller

from core.config import get_site_config
from orders.models import Order, OrderItem


@transaction.atomic
def create_deposit_order_for_appointment(ar):
    """Create an Order for a required Stripe deposit and link it to an AppointmentRequest.

    Notes:
    - v1: deposit is collected via Stripe only
    - Marketplace fee applies to the deposit amount (same as goods/services sales)
    """
    if not ar.requires_deposit:
        raise ValueError("Appointment does not require a deposit.")

    deposit_cents = int(ar.deposit_cents_snapshot or 0)
    if deposit_cents <= 0:
        raise ValueError("Invalid deposit.")

    # Create an order with a single line representing the deposit.
    cfg = get_site_config()
    default_pct = getattr(cfg, "marketplace_sales_percent", Decimal("0.00")) or Decimal("0.00")

    order = Order.objects.create(
        buyer=ar.buyer,
        guest_email="",
        currency="usd",
        status=Order.Status.PENDING,
        payment_method=Order.PaymentMethod.STRIPE,
        marketplace_sales_percent_snapshot=default_pct,
        platform_fee_cents_snapshot=0,
        kind=Order.Kind.PHYSICAL,
    )

    seller = ar.seller

    # Marketplace fee (respect fee waiver)
    effective_pct = get_effective_marketplace_sales_percent_for_seller(seller_user=seller)
    # Match marketplace fee rounding used elsewhere (ROUND_HALF_UP at cent level).
    # Convert percent to basis points: 10.00% => 1000 bps
    bps = int(Decimal(effective_pct) * Decimal("100"))
    fee_cents = int((int(deposit_cents) * bps + 5000) // 10000)
    if fee_cents < 0:
        fee_cents = 0
    if fee_cents > deposit_cents:
        fee_cents = deposit_cents

    net_cents = max(0, deposit_cents - fee_cents)

    # OrderItem uses snapshot-safe fields; do not pass legacy fields like unit_price_cents or requires_shipping.
    OrderItem.objects.create(
        order=order,
        product=ar.service,
        seller=seller,
        title_snapshot=str(getattr(ar.service, "title", ""))[:255],
        sku_snapshot=str(getattr(ar.service, "sku", ""))[:80],
        unit_price_cents_snapshot=int(deposit_cents),
        quantity=1,
        line_total_cents=int(deposit_cents),
        is_service=True,
        is_tip=False,
        fulfillment_mode_snapshot="pickup",
        pickup_instructions_snapshot=f"Service deposit for appointment request #{ar.pk}",
        marketplace_fee_cents=int(fee_cents),
        seller_net_cents=int(net_cents),
    )

    order.recompute_totals()
    order.save(update_fields=["subtotal_cents", "tax_cents", "shipping_cents", "total_cents", "kind", "updated_at"])
    return order

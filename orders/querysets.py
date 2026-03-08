from __future__ import annotations

from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce

from .models import OrderEvent


def annotate_order_reconciliation(qs):
    """Annotate an Order queryset with reconciliation aggregates + mismatch flags.

    Adds the following annotations:
      - items_qty_agg
      - seller_count_agg
      - items_gross_cents_agg
      - marketplace_fee_cents_agg
      - seller_net_cents_agg
      - expected_fee_cents_agg
      - expected_net_cents_agg
      - totals_mismatch
      - ledger_mismatch
      - paid_missing_stripe_ids
      - paid_missing_transfer_event
      - has_transfer_event
      - payout_skipped_unready_seller

    Notes:
      - Expected fee/net uses exact ROUND_HALF_UP semantics by integer math, matching admin logic.
      - This assumes Order.items is the authoritative ledger source.
    """

    # items gross: sum(quantity * unit_price_cents_snapshot)
    line_total_expr = ExpressionWrapper(
        F("items__quantity") * F("items__unit_price_cents_snapshot"),
        output_field=IntegerField(),
    )

    qs = qs.annotate(
        items_qty_agg=Coalesce(Sum("items__quantity"), Value(0), output_field=IntegerField()),
        seller_count_agg=Coalesce(Count("items__seller", distinct=True), Value(0), output_field=IntegerField()),
        items_gross_cents_agg=Coalesce(Sum(line_total_expr), Value(0), output_field=IntegerField()),
        marketplace_fee_cents_agg=Coalesce(Sum("items__marketplace_fee_cents"), Value(0), output_field=IntegerField()),
        seller_net_cents_agg=Coalesce(Sum("items__seller_net_cents"), Value(0), output_field=IntegerField()),
    )

    # transfer marker
    transfer_exists = OrderEvent.objects.filter(order_id=OuterRef("pk"), type=OrderEvent.Type.TRANSFER_CREATED)
    qs = qs.annotate(has_transfer_event=Exists(transfer_exists))

    # payout skipped marker
    skipped_unready_exists = (
        OrderEvent.objects.filter(order_id=OuterRef("pk"), type=OrderEvent.Type.WARNING, message__icontains="transfer skipped")
        .filter(message__icontains="not ready")
    )
    qs = qs.annotate(payout_skipped_unready_seller=Exists(skipped_unready_exists))

    # Expected fee/net with integer math.
    # marketplace_sales_percent_snapshot stored like 8.00 (Decimal)
    # Convert to basis points: 8.00% => 800 bps
    bps = Cast(F("marketplace_sales_percent_snapshot") * Value(100), IntegerField())

    expected_fee_cents = ExpressionWrapper(
        (F("items_gross_cents_agg") * bps + Value(5000)) / Value(10000),
        output_field=IntegerField(),
    )

    qs = qs.annotate(
        expected_fee_cents_agg=Coalesce(expected_fee_cents, Value(0), output_field=IntegerField()),
    ).annotate(
        expected_net_cents_agg=Coalesce(
            F("items_gross_cents_agg") - F("expected_fee_cents_agg"),
            Value(0),
            output_field=IntegerField(),
        ),
    )

    # flags
    qs = qs.annotate(
        totals_mismatch=Case(
            When(subtotal_cents=F("items_gross_cents_agg"), then=Value(False)),
            default=Value(True),
            output_field=BooleanField(),
        ),
        ledger_mismatch=Case(
            When(
                marketplace_fee_cents_agg=F("expected_fee_cents_agg"),
                seller_net_cents_agg=F("expected_net_cents_agg"),
                then=Value(False),
            ),
            default=Value(True),
            output_field=BooleanField(),
        ),
    )

    # paid missing stripe ids (ignore FREE PI)
    qs = qs.annotate(
        paid_missing_stripe_ids=Case(
            When(paid_at__isnull=True, then=Value(False)),
            When(stripe_payment_intent_id__exact="FREE", then=Value(False)),
            When(stripe_session_id__exact="", then=Value(True)),
            When(stripe_payment_intent_id__exact="", then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
        paid_missing_transfer_event=Case(
            When(paid_at__isnull=True, then=Value(False)),
            When(stripe_payment_intent_id__exact="FREE", then=Value(False)),
            When(has_transfer_event=True, then=Value(False)),
            When(payout_skipped_unready_seller=True, then=Value(False)),
            default=Value(True),
            output_field=BooleanField(),
        ),
    )

    return qs

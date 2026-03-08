from __future__ import annotations

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Verify money-loop invariants.

    This is a *data* check against the database. It is designed to catch regressions
    where totals or per-line ledgers drift from the snapshot-based accounting model.

    Invariants checked (paid orders):
      1) Order totals match recompute logic.
      2) For every line item: marketplace_fee_cents + seller_net_cents == line_total_cents.
    """

    help = "Verify money-loop invariants for recent paid orders."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Number of most-recent paid orders to sample (default: 200).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output JSON payload.",
        )

    def handle(self, *args, **options):
        from orders.models import Order, OrderItem

        limit = int(options.get("limit") or 200)
        emit_json = bool(options.get("json"))

        sample = list(
            Order.objects.filter(status=Order.Status.PAID)
            .order_by("-paid_at")
            .only("id", "subtotal_cents", "tax_cents", "shipping_cents", "total_cents")[:limit]
        )

        bad_orders: list[str] = []
        bad_items: int = 0
        checked_items: int = 0

        for o in sample:
            items = list(
                OrderItem.objects.filter(order=o)
                .only(
                    "line_total_cents",
                    "tax_cents",
                    "shipping_fee_cents_snapshot",
                    "delivery_fee_cents_snapshot",
                    "marketplace_fee_cents",
                    "seller_net_cents",
                )
            )

            subtotal = sum(int(i.line_total_cents or 0) for i in items)
            shipping = sum(
                int(i.shipping_fee_cents_snapshot or 0) + int(i.delivery_fee_cents_snapshot or 0)
                for i in items
            )
            tax = sum(int(i.tax_cents or 0) for i in items)
            total = max(0, int(subtotal) + int(shipping) + int(tax))

            if (
                int(o.subtotal_cents or 0) != subtotal
                or int(o.shipping_cents or 0) != shipping
                or int(o.tax_cents or 0) != tax
                or int(o.total_cents or 0) != total
            ):
                bad_orders.append(str(o.id))

            for i in items:
                checked_items += 1
                gross = int(i.line_total_cents or 0)
                fee = int(i.marketplace_fee_cents or 0)
                net = int(i.seller_net_cents or 0)
                if fee + net != gross:
                    bad_items += 1

        ok = (len(bad_orders) == 0) and (bad_items == 0)
        payload = {
            "ok": ok,
            "sampled_paid_orders": len(sample),
            "checked_items": checked_items,
            "bad_orders_count": len(bad_orders),
            "bad_items_count": bad_items,
            "bad_orders": bad_orders[:25],
        }

        if emit_json:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(self.style.SUCCESS("Money loop check: OK") if ok else self.style.ERROR("Money loop check: FAIL"))
            self.stdout.write(
                f"Sampled paid orders: {payload['sampled_paid_orders']} | Checked items: {payload['checked_items']}"
            )
            if payload["bad_orders_count"]:
                self.stdout.write(self.style.ERROR(f"Bad orders: {payload['bad_orders_count']}"))
                for oid in payload["bad_orders"]:
                    self.stdout.write(self.style.ERROR(f"- {oid}"))
            if payload["bad_items_count"]:
                self.stdout.write(self.style.ERROR(f"Bad items: {payload['bad_items_count']}"))

        if not ok:
            raise SystemExit(2)

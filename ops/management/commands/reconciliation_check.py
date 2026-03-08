from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order
from orders.querysets import annotate_order_reconciliation


class Command(BaseCommand):
    help = "Run order/Stripe reconciliation checks and emit alert-friendly output."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Lookback window on order created_at (default: 30 days).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Maximum orders to inspect after filters (default: 500).",
        )
        parser.add_argument(
            "--status",
            default="",
            help="Optional status filter (e.g. paid, awaiting_payment).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit JSON only.",
        )
        parser.add_argument(
            "--fail-on-mismatch",
            action="store_true",
            help="Exit non-zero when mismatches are found (for cron/CI alerting).",
        )

    def handle(self, *args, **options):
        days = max(1, int(options.get("days") or 30))
        limit = max(1, int(options.get("limit") or 500))
        status = (options.get("status") or "").strip().lower()
        emit_json = bool(options.get("json"))
        fail_on_mismatch = bool(options.get("fail_on_mismatch"))

        since = timezone.now() - timezone.timedelta(days=days)

        qs = annotate_order_reconciliation(
            Order.objects.select_related("buyer").filter(created_at__gte=since)
        ).order_by("-created_at")
        if status:
            qs = qs.filter(status=status)

        rows = list(qs[:limit])
        mismatch_rows = [
            o
            for o in rows
            if bool(getattr(o, "totals_mismatch", False))
            or bool(getattr(o, "ledger_mismatch", False))
            or bool(getattr(o, "paid_missing_stripe_ids", False))
            or bool(getattr(o, "paid_missing_transfer_event", False))
        ]

        payload = {
            "ok": len(mismatch_rows) == 0,
            "window_days": days,
            "status_filter": status or "(all)",
            "inspected_orders": len(rows),
            "mismatches_total": len(mismatch_rows),
            "counts": {
                "totals_mismatch": sum(1 for o in rows if bool(getattr(o, "totals_mismatch", False))),
                "ledger_mismatch": sum(1 for o in rows if bool(getattr(o, "ledger_mismatch", False))),
                "paid_missing_stripe_ids": sum(1 for o in rows if bool(getattr(o, "paid_missing_stripe_ids", False))),
                "paid_missing_transfer_event": sum(1 for o in rows if bool(getattr(o, "paid_missing_transfer_event", False))),
            },
            "mismatches": [
                {
                    "order_id": str(o.pk),
                    "status": str(o.status),
                    "paid_at": o.paid_at.isoformat() if getattr(o, "paid_at", None) else "",
                    "totals_mismatch": bool(getattr(o, "totals_mismatch", False)),
                    "ledger_mismatch": bool(getattr(o, "ledger_mismatch", False)),
                    "paid_missing_stripe_ids": bool(getattr(o, "paid_missing_stripe_ids", False)),
                    "paid_missing_transfer_event": bool(getattr(o, "paid_missing_transfer_event", False)),
                }
                for o in mismatch_rows[:100]
            ],
        }

        if emit_json:
            self.stdout.write(json.dumps(payload, sort_keys=True, indent=2))
        else:
            if payload["ok"]:
                self.stdout.write(self.style.SUCCESS("Reconciliation check: OK"))
            else:
                self.stdout.write(self.style.ERROR("Reconciliation check: FAIL"))
            self.stdout.write(
                "Inspected={inspected_orders} | Mismatches={mismatches_total} | Counts={counts}".format(
                    **payload
                )
            )
            if mismatch_rows:
                self.stdout.write("Top mismatches:")
                for row in payload["mismatches"][:10]:
                    self.stdout.write(
                        f"- {row['order_id']} status={row['status']} "
                        f"totals={row['totals_mismatch']} ledger={row['ledger_mismatch']} "
                        f"missing_ids={row['paid_missing_stripe_ids']} "
                        f"missing_transfer={row['paid_missing_transfer_event']}"
                    )

        if fail_on_mismatch and mismatch_rows:
            raise SystemExit(2)

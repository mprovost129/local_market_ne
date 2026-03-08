from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import StripeWebhookEvent
from orders.webhooks import process_stripe_event_dict


class Command(BaseCommand):
    help = "Replay stored Stripe webhook events for recovery/runbook workflows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Lookback window on webhook event created_at (default: 7 days).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Max events to replay (default: 200).",
        )
        parser.add_argument(
            "--status",
            default="received,error",
            help="Comma-separated statuses to replay (default: received,error).",
        )
        parser.add_argument(
            "--event-type",
            default="",
            help="Optional exact event type filter (e.g. checkout.session.completed).",
        )
        parser.add_argument(
            "--stripe-event-id",
            default="",
            help="Optional specific Stripe event id to replay.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Select and report replay candidates without mutating state.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit JSON only.",
        )
        parser.add_argument(
            "--fail-on-error",
            action="store_true",
            help="Exit non-zero if any replay fails.",
        )

    def handle(self, *args, **options):
        days = max(1, int(options.get("days") or 7))
        limit = max(1, int(options.get("limit") or 200))
        status_raw = (options.get("status") or "received,error").strip()
        event_type = (options.get("event_type") or "").strip()
        stripe_event_id = (options.get("stripe_event_id") or "").strip()
        dry_run = bool(options.get("dry_run"))
        emit_json = bool(options.get("json"))
        fail_on_error = bool(options.get("fail_on_error"))

        statuses = [s.strip() for s in status_raw.split(",") if s.strip()]
        if not statuses:
            statuses = ["received", "error"]

        since = timezone.now() - timezone.timedelta(days=days)
        qs = StripeWebhookEvent.objects.filter(created_at__gte=since).order_by("created_at")
        if statuses:
            qs = qs.filter(status__in=statuses)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if stripe_event_id:
            qs = qs.filter(stripe_event_id=stripe_event_id)

        rows = list(qs[:limit])
        replayed = 0
        failed = 0
        skipped = 0
        failures: list[dict[str, str]] = []

        for ev in rows:
            payload = getattr(ev, "raw_json", None)
            if not isinstance(payload, dict) or not payload.get("id"):
                skipped += 1
                failures.append(
                    {
                        "stripe_event_id": ev.stripe_event_id,
                        "error": "missing/invalid raw_json payload",
                    }
                )
                continue

            if dry_run:
                replayed += 1
                continue

            try:
                process_stripe_event_dict(event=payload, webhook_event=ev, source="ops_replay")
                replayed += 1
            except Exception as e:
                failed += 1
                failures.append(
                    {
                        "stripe_event_id": ev.stripe_event_id,
                        "error": str(e),
                    }
                )

        result = {
            "ok": failed == 0,
            "dry_run": dry_run,
            "window_days": days,
            "selected": len(rows),
            "replayed": replayed,
            "failed": failed,
            "skipped": skipped,
            "failures": failures[:100],
        }

        if emit_json:
            self.stdout.write(json.dumps(result, sort_keys=True, indent=2))
        else:
            if result["ok"]:
                self.stdout.write(self.style.SUCCESS("Webhook replay: OK"))
            else:
                self.stdout.write(self.style.ERROR("Webhook replay: FAIL"))
            self.stdout.write(
                f"Selected={result['selected']} Replayed={result['replayed']} "
                f"Failed={result['failed']} Skipped={result['skipped']}"
            )
            for item in result["failures"][:10]:
                self.stdout.write(f"- {item['stripe_event_id']}: {item['error']}")

        if fail_on_error and failed > 0:
            raise SystemExit(2)

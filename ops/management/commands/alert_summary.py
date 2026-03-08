from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from ops.alerts import build_alert_summary


class Command(BaseCommand):
    help = "Emit machine-readable ops alert summary for cron/monitoring."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Recent window in hours for time-bound alerts (default: 24).",
        )
        parser.add_argument(
            "--reconciliation-days",
            type=int,
            default=7,
            help="Lookback days for reconciliation mismatch scan (default: 7).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit JSON only.",
        )
        parser.add_argument(
            "--fail-on-alert",
            action="store_true",
            help="Exit non-zero when status is warning/critical.",
        )

    def handle(self, *args, **options):
        hours = max(1, int(options.get("hours") or 24))
        reconciliation_days = max(1, int(options.get("reconciliation_days") or 7))
        emit_json = bool(options.get("json"))
        fail_on_alert = bool(options.get("fail_on_alert"))

        payload = build_alert_summary(hours=hours, reconciliation_days=reconciliation_days)
        status = str(payload.get("status") or "ok")

        if emit_json:
            self.stdout.write(json.dumps(payload, sort_keys=True, indent=2))
        else:
            if status == "ok":
                self.stdout.write(self.style.SUCCESS("Alert summary: OK"))
            elif status == "warning":
                self.stdout.write(self.style.WARNING("Alert summary: WARNING"))
            else:
                self.stdout.write(self.style.ERROR("Alert summary: CRITICAL"))
            self.stdout.write(f"Metrics: {payload['metrics']}")
            if critical_reasons:
                self.stdout.write(f"Critical: {', '.join(critical_reasons)}")
            if warning_reasons:
                self.stdout.write(f"Warning: {', '.join(warning_reasons)}")

        if fail_on_alert and status != "ok":
            raise SystemExit(2)

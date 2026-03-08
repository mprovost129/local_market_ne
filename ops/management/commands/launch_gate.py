from __future__ import annotations

import json
from io import StringIO

from django.core.management import BaseCommand, call_command

from ops.alerts import build_alert_summary


class Command(BaseCommand):
    help = "Single launch gate aggregating smoke, money loop, reconciliation, and alert summary checks."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Emit JSON output.")
        parser.add_argument(
            "--fail-on-warning",
            action="store_true",
            help="Exit non-zero when overall status is warning.",
        )
        parser.add_argument("--skip-smoke", action="store_true", help="Skip smoke_check.")
        parser.add_argument("--skip-money-loop", action="store_true", help="Skip money_loop_check.")
        parser.add_argument("--skip-reconciliation", action="store_true", help="Skip reconciliation_check.")
        parser.add_argument("--skip-alert-summary", action="store_true", help="Skip alert_summary evaluation.")
        parser.add_argument(
            "--money-loop-limit",
            type=int,
            default=200,
            help="Sample size for money_loop_check (default: 200).",
        )
        parser.add_argument(
            "--reconciliation-days",
            type=int,
            default=30,
            help="Lookback days for reconciliation_check (default: 30).",
        )
        parser.add_argument(
            "--reconciliation-limit",
            type=int,
            default=500,
            help="Max orders for reconciliation_check (default: 500).",
        )
        parser.add_argument(
            "--alert-hours",
            type=int,
            default=24,
            help="Window hours for alert summary (default: 24).",
        )
        parser.add_argument(
            "--alert-reconciliation-days",
            type=int,
            default=7,
            help="Reconciliation window days for alert summary (default: 7).",
        )

    def handle(self, *args, **options):
        emit_json = bool(options.get("json"))
        fail_on_warning = bool(options.get("fail_on_warning"))
        results: list[dict] = []

        def _critical(name: str, detail: dict):
            results.append({"name": name, "status": "critical", "detail": detail})

        def _ok(name: str, detail: dict):
            results.append({"name": name, "status": "ok", "detail": detail})

        # 1) Smoke
        if not bool(options.get("skip_smoke")):
            try:
                call_command("smoke_check", checks=True, db=True, quiet=True, verbosity=0)
                _ok("smoke_check", {"ok": True})
            except SystemExit as e:
                _critical("smoke_check", {"ok": False, "exit": int(getattr(e, "code", 1) or 1)})
            except Exception as e:
                _critical("smoke_check", {"ok": False, "error": str(e)})

        # 2) Money loop
        if not bool(options.get("skip_money_loop")):
            out = StringIO()
            money_loop_limit = int(options.get("money_loop_limit") or 200)
            try:
                call_command("money_loop_check", limit=money_loop_limit, json=True, stdout=out, verbosity=0)
                payload = json.loads(out.getvalue() or "{}")
                _ok("money_loop_check", payload)
            except SystemExit as e:
                payload = {}
                try:
                    payload = json.loads(out.getvalue() or "{}")
                except Exception:
                    pass
                _critical(
                    "money_loop_check",
                    {
                        "ok": False,
                        "exit": int(getattr(e, "code", 2) or 2),
                        "payload": payload,
                    },
                )
            except Exception as e:
                _critical("money_loop_check", {"ok": False, "error": str(e)})

        # 3) Reconciliation
        if not bool(options.get("skip_reconciliation")):
            out = StringIO()
            reconciliation_days = int(options.get("reconciliation_days") or 30)
            reconciliation_limit = int(options.get("reconciliation_limit") or 500)
            try:
                call_command(
                    "reconciliation_check",
                    days=reconciliation_days,
                    limit=reconciliation_limit,
                    json=True,
                    stdout=out,
                    verbosity=0,
                )
                payload = json.loads(out.getvalue() or "{}")
                if bool(payload.get("ok", False)):
                    _ok("reconciliation_check", payload)
                else:
                    _critical("reconciliation_check", payload)
            except SystemExit as e:
                payload = {}
                try:
                    payload = json.loads(out.getvalue() or "{}")
                except Exception:
                    pass
                _critical(
                    "reconciliation_check",
                    {
                        "ok": False,
                        "exit": int(getattr(e, "code", 2) or 2),
                        "payload": payload,
                    },
                )
            except Exception as e:
                _critical("reconciliation_check", {"ok": False, "error": str(e)})

        # 4) Alert summary
        if not bool(options.get("skip_alert_summary")):
            alert_hours = int(options.get("alert_hours") or 24)
            alert_reconciliation_days = int(options.get("alert_reconciliation_days") or 7)
            try:
                payload = build_alert_summary(
                    hours=alert_hours,
                    reconciliation_days=alert_reconciliation_days,
                )
                status = str(payload.get("status") or "ok")
                if status == "ok":
                    _ok("alert_summary", payload)
                elif status == "warning":
                    results.append({"name": "alert_summary", "status": "warning", "detail": payload})
                else:
                    _critical("alert_summary", payload)
            except Exception as e:
                _critical("alert_summary", {"ok": False, "error": str(e)})

        critical_count = sum(1 for r in results if r["status"] == "critical")
        warning_count = sum(1 for r in results if r["status"] == "warning")
        if critical_count:
            overall = "critical"
        elif warning_count:
            overall = "warning"
        else:
            overall = "ok"

        payload = {
            "status": overall,
            "ok": overall == "ok",
            "critical_count": critical_count,
            "warning_count": warning_count,
            "results": results,
        }

        if emit_json:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            if overall == "ok":
                self.stdout.write(self.style.SUCCESS("Launch gate: OK"))
            elif overall == "warning":
                self.stdout.write(self.style.WARNING("Launch gate: WARNING"))
            else:
                self.stdout.write(self.style.ERROR("Launch gate: CRITICAL"))
            for row in results:
                self.stdout.write(f"- {row['name']}: {row['status']}")

        if overall == "critical":
            raise SystemExit(2)
        if fail_on_warning and overall == "warning":
            raise SystemExit(2)

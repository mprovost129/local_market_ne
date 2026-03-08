from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Run RC-oriented checks and emit a single consolidated report. "
        "This is a convenience wrapper around rc_check, url_reverse_audit, "
        "template_deadend_audit, flow_check, and money_loop_check."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200, help="Max findings to include for audits.")
        parser.add_argument("--money-limit", type=int, default=200, help="Max paid orders to sample for money loop check.")
        parser.add_argument("--json", action="store_true", help="Output JSON payload only.")
        parser.add_argument("--strict", action="store_true", help="Exit non-zero if any component fails.")
        parser.add_argument("--quiet", action="store_true", help="Reduce human output (still prints summary).")

    def _run_json(self, name: str, **kwargs):
        buf = StringIO()
        try:
            call_command(name, stdout=buf, stderr=buf, **kwargs)
            raw = buf.getvalue().strip()
            # Commands that support --json emit a JSON object to stdout.
            data = json.loads(raw) if raw.startswith("{") else {"ok": True, "raw": raw}
            return {"ok": True, "data": data}
        except SystemExit as e:
            raw = buf.getvalue().strip()
            try:
                data = json.loads(raw) if raw.startswith("{") else {"ok": False, "raw": raw}
            except Exception:
                data = {"ok": False, "raw": raw}
            return {"ok": False, "exit_code": int(getattr(e, "code", 2) or 2), "data": data}

    def handle(self, *args, **options):
        limit = int(options.get("limit") or 200)
        money_limit = int(options.get("money_limit") or 200)
        emit_json = bool(options.get("json"))
        strict = bool(options.get("strict"))
        quiet = bool(options.get("quiet"))

        report = {
            "ok": True,
            "components": {},
        }

        # Core gate checks (settings + routes + db reachability) — already includes audits,
        # but we keep explicit audits here to produce counts even when non-strict.
        report["components"]["stripe_config_check"] = self._run_json("stripe_config_check", quiet=True)
        report["components"]["rc_check"] = self._run_json("rc_check", json=True, checks=True, db=True, quiet=True)
        report["components"]["url_reverse_audit"] = self._run_json("url_reverse_audit", json=True, limit=limit, quiet=True)
        report["components"]["template_deadend_audit"] = self._run_json("template_deadend_audit", json=True, limit=limit, quiet=True)
        # Minimal in-app flow smoke check (creates tiny objects and hits key pages).
        report["components"]["flow_check"] = self._run_json("flow_check", strict=True)
        report["components"]["money_loop_check"] = self._run_json("money_loop_check", json=True, limit=money_limit)

        for comp in report["components"].values():
            if not comp.get("ok"):
                report["ok"] = False

        if emit_json:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        else:
            # Human summary
            self.stdout.write(self.style.MIGRATE_HEADING("RC report"))
            for name, comp in report["components"].items():
                ok = bool(comp.get("ok"))
                badge = self.style.SUCCESS("OK") if ok else self.style.ERROR("FAIL")
                details = ""
                data = comp.get("data") or {}
                if isinstance(data, dict) and "count" in data:
                    details = f" (count={data.get('count')})"
                self.stdout.write(f"- {name}: {badge}{details}")
            if not quiet:
                self.stdout.write("")
                self.stdout.write("Tip: run individual commands for details:")
                self.stdout.write("  - python manage.py url_reverse_audit --strict")
                self.stdout.write("  - python manage.py template_deadend_audit --strict")
                self.stdout.write("  - python manage.py money_loop_check --limit 200")
                self.stdout.write("  - python manage.py rc_check --checks --db")

        if strict and not report["ok"]:
            raise SystemExit(2)

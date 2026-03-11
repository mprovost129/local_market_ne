# core/management/commands/launch_check.py
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from core.launch_checks import as_dict, run_launch_checks


class Command(BaseCommand):
    help = "Run launch readiness checks (settings, integrations, and core invariants)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Output JSON instead of human text.")

    def handle(self, *args, **options):
        results = run_launch_checks()
        payload = as_dict(results)

        if options.get("json"):
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        ok = payload["ok"]
        self.stdout.write(self.style.SUCCESS("Launch checks: OK") if ok else self.style.ERROR("Launch checks: FAIL"))
        for r in payload["results"]:
            line = f"- {r['key']}: {'OK' if r['ok'] else 'FAIL'} - {r['message']}"
            self.stdout.write(self.style.SUCCESS(line) if r["ok"] else self.style.ERROR(line))

        if not ok:
            raise SystemExit(1)

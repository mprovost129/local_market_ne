from __future__ import annotations

import json

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Run a release-candidate (RC) check bundle.

    Single command intended for pre-deploy gating.

    Runs:
      - smoke_check (optionally with system checks + DB ping)
      - launch_check (settings posture + core invariants)
      - template_deadend_audit (warns on obvious dead ends; strict optional)
    """

    help = "Run RC checks (smoke_check + launch_check)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Output JSON payload.")
        parser.add_argument("--checks", action="store_true", help="Run Django system checks as part of smoke_check.")
        parser.add_argument("--db", action="store_true", help="Run a lightweight DB ping as part of smoke_check.")
        parser.add_argument("--quiet", action="store_true", help="Reduce human output.")
        parser.add_argument(
            "--deadends-strict",
            action="store_true",
            help="Fail RC check if template dead-end audit finds issues.",
        )

    def handle(self, *args, **options):
        emit_json = bool(options.get("json"))
        run_checks = bool(options.get("checks"))
        run_db = bool(options.get("db"))
        quiet = bool(options.get("quiet"))
        strict_deadends = bool(options.get("deadends_strict"))

        bundle: dict = {
            "ok": True,
            "checks": {
                "stripe_config_check": {"ok": True},
                "smoke_check": {"ok": True},
                "launch_check": {"ok": True},
                "template_deadend_audit": {"ok": True},
                "url_reverse_audit": {"ok": True},
            },
        }

        # 0) Stripe config sanity (warn-only here; run `stripe_config_check --strict` if you want hard gating)
        try:
            call_command("stripe_config_check", quiet=quiet)
        except SystemExit as exc:
            # Should only happen if called with --strict, but record anyway.
            bundle["checks"]["stripe_config_check"]["ok"] = False
            bundle["checks"]["stripe_config_check"]["code"] = int(getattr(exc, "code", 1) or 1)
        except Exception as exc:
            bundle["checks"]["stripe_config_check"]["ok"] = False
            bundle["checks"]["stripe_config_check"]["error"] = str(exc)

        # 1) smoke_check
        try:
            smoke_kwargs: dict = {"quiet": quiet}
            if run_checks:
                smoke_kwargs["checks"] = True
            if run_db:
                smoke_kwargs["db"] = True
            call_command("smoke_check", **smoke_kwargs)
        except SystemExit as exc:
            bundle["checks"]["smoke_check"]["ok"] = False
            bundle["checks"]["smoke_check"]["code"] = int(getattr(exc, "code", 1) or 1)
        except Exception as exc:
            bundle["checks"]["smoke_check"]["ok"] = False
            bundle["checks"]["smoke_check"]["error"] = str(exc)

        # 2) launch_check
        try:
            call_command("launch_check")
        except SystemExit as exc:
            bundle["checks"]["launch_check"]["ok"] = False
            bundle["checks"]["launch_check"]["code"] = int(getattr(exc, "code", 1) or 1)
        except Exception as exc:
            bundle["checks"]["launch_check"]["ok"] = False
            bundle["checks"]["launch_check"]["error"] = str(exc)

        # 3) template dead-end audit (non-fatal by default)
        try:
            call_command("template_deadend_audit", strict=strict_deadends, quiet=quiet)
        except SystemExit as exc:
            # Only fails when strict is requested.
            bundle["checks"]["template_deadend_audit"]["ok"] = False
            bundle["checks"]["template_deadend_audit"]["code"] = int(getattr(exc, "code", 1) or 1)
        except Exception as exc:
            bundle["checks"]["template_deadend_audit"]["ok"] = False
            bundle["checks"]["template_deadend_audit"]["error"] = str(exc)

        # 4) URL reverse audit (literal route names only; non-fatal)
        try:
            call_command("url_reverse_audit", quiet=quiet)
        except SystemExit as exc:
            bundle["checks"]["url_reverse_audit"]["ok"] = False
            bundle["checks"]["url_reverse_audit"]["code"] = int(getattr(exc, "code", 1) or 1)
        except Exception as exc:
            bundle["checks"]["url_reverse_audit"]["ok"] = False
            bundle["checks"]["url_reverse_audit"]["error"] = str(exc)

        bundle["ok"] = bool(bundle["checks"]["smoke_check"]["ok"]) and bool(bundle["checks"]["launch_check"]["ok"]) and (
            bool(bundle["checks"]["template_deadend_audit"]["ok"]) or not strict_deadends
        )

        if emit_json:
            self.stdout.write(json.dumps(bundle, indent=2, sort_keys=True))
        else:
            headline = "RC checks: OK" if bundle["ok"] else "RC checks: FAIL"
            self.stdout.write(self.style.SUCCESS(headline) if bundle["ok"] else self.style.ERROR(headline))
            for key in ("stripe_config_check", "smoke_check", "launch_check", "template_deadend_audit", "url_reverse_audit"):
                ok = bool(bundle["checks"][key]["ok"])
                line = f"- {key}: {'OK' if ok else 'FAIL'}"
                self.stdout.write(self.style.SUCCESS(line) if ok else self.style.ERROR(line))

        if not bundle["ok"]:
            raise SystemExit(2)

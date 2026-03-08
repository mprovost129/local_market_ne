from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    name: str
    detail: str


class Command(BaseCommand):
    help = "Verify Stripe configuration (keys + webhook routes) for RC/go-live."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero if any required Stripe config is missing.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only print failures.",
        )

    def handle(self, *args, **options):
        strict: bool = bool(options.get("strict"))
        quiet: bool = bool(options.get("quiet"))

        def _present(val: str | None) -> bool:
            return bool(val and str(val).strip())

        results: list[CheckResult] = []

        # Keys
        results.append(
            CheckResult(
                ok=_present(getattr(settings, "STRIPE_SECRET_KEY", None)),
                name="STRIPE_SECRET_KEY",
                detail="Server secret key set" if _present(getattr(settings, "STRIPE_SECRET_KEY", None)) else "Missing",
            )
        )
        results.append(
            CheckResult(
                ok=_present(getattr(settings, "STRIPE_PUBLISHABLE_KEY", None)),
                name="STRIPE_PUBLISHABLE_KEY",
                detail="Publishable key set" if _present(getattr(settings, "STRIPE_PUBLISHABLE_KEY", None)) else "Missing",
            )
        )
        results.append(
            CheckResult(
                ok=_present(getattr(settings, "STRIPE_WEBHOOK_SECRET", None)),
                name="STRIPE_WEBHOOK_SECRET",
                detail="Checkout webhook secret set" if _present(getattr(settings, "STRIPE_WEBHOOK_SECRET", None)) else "Missing",
            )
        )
        results.append(
            CheckResult(
                ok=_present(getattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", None)),
                name="STRIPE_CONNECT_WEBHOOK_SECRET",
                detail="Connect webhook secret set" if _present(getattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", None)) else "Missing",
            )
        )

        # Webhook routes (reverse check)
        for route_name in ("orders:stripe_webhook", "payments:stripe_connect_webhook"):
            try:
                path = reverse(route_name)
                results.append(CheckResult(ok=True, name=route_name, detail=f"Reverse OK: {path}"))
            except NoReverseMatch:
                results.append(CheckResult(ok=False, name=route_name, detail="NoReverseMatch (route missing)"))

        failed = [r for r in results if not r.ok]

        if not quiet:
            self.stdout.write(self.style.MIGRATE_HEADING("Stripe config check"))

        for r in results:
            if quiet and r.ok:
                continue
            prefix = self.style.SUCCESS("OK") if r.ok else self.style.ERROR("FAIL")
            self.stdout.write(f"[{prefix}] {r.name}: {r.detail}")

        if failed and strict:
            raise SystemExit(2)

        return "ok" if not failed else "warnings"

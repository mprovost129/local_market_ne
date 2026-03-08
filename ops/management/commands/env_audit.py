from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand


def _val(name: str) -> str:
    return (os.getenv(name) or "").strip()


class Command(BaseCommand):
    help = "Audit environment variables for common deploy/runtime expectations (prod + Render)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero if any required variables are missing.",
        )

    def handle(self, *args, **options):
        strict: bool = bool(options.get("strict"))

        # ---- Baseline expectations (any environment)
        required_any = [
            "DJANGO_SECRET_KEY",
        ]

        # ---- Production-ish expectations
        required_prod: list[str] = []
        if not getattr(settings, "DEBUG", True):
            # In prod we drive hosts/origins from PRIMARY_DOMAIN.
            required_prod.append("PRIMARY_DOMAIN")

        # ---- Stripe
        # Publishable key is accepted as either STRIPE_PUBLIC_KEY or STRIPE_PUBLISHABLE_KEY
        stripe_required_secret = "STRIPE_SECRET_KEY"
        stripe_required_pub = ("STRIPE_PUBLIC_KEY", "STRIPE_PUBLISHABLE_KEY")
        stripe_recommended = [
            "STRIPE_WEBHOOK_SECRET",
            "STRIPE_CONNECT_WEBHOOK_SECRET",
        ]

        # ---- Email (recommended)
        email_recommended = [
            "DEFAULT_FROM_EMAIL",
            "EMAIL_HOST",
            "EMAIL_HOST_USER",
            "EMAIL_HOST_PASSWORD",
        ]

        # ---- S3
        use_s3 = bool(getattr(settings, "USE_S3", False))
        s3_required: list[str] = []
        if use_s3:
            s3_required = [
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_S3_MEDIA_BUCKET",
                "AWS_S3_REGION_NAME",
            ]

        # ---- reCAPTCHA
        recaptcha_enabled = _val("RECAPTCHA_ENABLED").lower() in {"1", "true", "yes", "y", "on"}
        recaptcha_required: list[str] = []
        if recaptcha_enabled:
            recaptcha_required = [
                "RECAPTCHA_V3_SITE_KEY",
                "RECAPTCHA_V3_SECRET_KEY",
            ]

        # ---- Database
        db_recommended = ["DATABASE_URL"]

        def check_vars(label: str, names: list[str], required: bool) -> int:
            missing = [n for n in names if not _val(n)]
            present = [n for n in names if _val(n)]
            self.stdout.write(self.style.MIGRATE_HEADING(label))
            for n in present:
                self.stdout.write(self.style.SUCCESS(f"  OK   {n}"))
            for n in missing:
                if required:
                    self.stdout.write(self.style.ERROR(f"  MISS {n}"))
                else:
                    self.stdout.write(self.style.WARNING(f"  WARN {n}"))
            return len(missing) if required else 0

        total_required_missing = 0

        total_required_missing += check_vars("Required (all envs)", required_any, required=True)

        if required_prod:
            total_required_missing += check_vars("Required (prod)", required_prod, required=True)

        # Stripe required checks with alias handling
        self.stdout.write(self.style.MIGRATE_HEADING("Required (Stripe)"))
        if _val(stripe_required_secret):
            self.stdout.write(self.style.SUCCESS(f"  OK   {stripe_required_secret}"))
        else:
            self.stdout.write(self.style.ERROR(f"  MISS {stripe_required_secret}"))
            total_required_missing += 1

        if any(_val(k) for k in stripe_required_pub):
            self.stdout.write(self.style.SUCCESS("  OK   STRIPE_PUBLIC_KEY (or STRIPE_PUBLISHABLE_KEY)"))
        else:
            self.stdout.write(self.style.ERROR("  MISS STRIPE_PUBLIC_KEY (or STRIPE_PUBLISHABLE_KEY)"))
            total_required_missing += 1

        check_vars("Recommended (Stripe webhooks)", stripe_recommended, required=False)
        check_vars("Recommended (Email)", email_recommended, required=False)
        check_vars("Recommended (DB URL)", db_recommended, required=False)

        if s3_required:
            total_required_missing += check_vars("Required (S3)", s3_required, required=True)

        if recaptcha_required:
            total_required_missing += check_vars("Required (reCAPTCHA)", recaptcha_required, required=True)

        if total_required_missing:
            msg = f"Missing required env vars: {total_required_missing}"
            if strict:
                raise SystemExit(msg)
            self.stdout.write(self.style.ERROR(msg))
        else:
            self.stdout.write(self.style.SUCCESS("All required env vars present."))

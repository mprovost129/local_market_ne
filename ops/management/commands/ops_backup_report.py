from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Emit a small ops snapshot about backups and environment configuration.

    This is intentionally lightweight and does NOT attempt to access provider APIs.
    It exists to give operators a consistent "what should be configured" report.
    """

    help = "Print a backup/config snapshot for ops runbooks (JSON by default)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--text",
            action="store_true",
            help="Print a human-friendly text report instead of JSON.",
        )

    def handle(self, *args, **opts):
        payload = {
            "debug": bool(getattr(settings, "DEBUG", False)),
            "allowed_hosts": list(getattr(settings, "ALLOWED_HOSTS", []) or []),
            "use_s3": bool(getattr(settings, "USE_S3", False)),
            "default_file_storage": str(getattr(settings, "DEFAULT_FILE_STORAGE", "")),
            "static_url": str(getattr(settings, "STATIC_URL", "/static/")),
            "media_url": str(getattr(settings, "MEDIA_URL", "/media/")),
            "email_backend": str(getattr(settings, "EMAIL_BACKEND", "")),
            "default_from_email": str(getattr(settings, "DEFAULT_FROM_EMAIL", "")),
            "stripe_configured": bool(getattr(settings, "STRIPE_SECRET_KEY", "")),
            "recaptcha_enabled": bool(getattr(settings, "RECAPTCHA_V3_SITE_KEY", "")),
            "notes": [
                "Database backups are managed by your hosting provider (Render/Postgres).",
                "For S3 media: enable bucket versioning + lifecycle rules in AWS.",
                "Run `python manage.py rc_check --checks --db` before each deploy.",
            ],
        }

        if opts.get("text"):
            lines = []
            lines.append(f"DEBUG: {payload['debug']}")
            lines.append(f"ALLOWED_HOSTS: {', '.join(payload['allowed_hosts']) or '(empty)'}")
            lines.append(f"Media backend: {'s3' if payload['use_s3'] else 'local'}")
            lines.append(f"EMAIL_BACKEND: {payload['email_backend'] or '(not set)'}")
            lines.append(f"DEFAULT_FROM_EMAIL: {payload['default_from_email'] or '(not set)'}")
            lines.append(f"Stripe configured: {'yes' if payload['stripe_configured'] else 'no'}")
            lines.append(f"reCAPTCHA enabled: {'yes' if payload['recaptcha_enabled'] else 'no'}")
            lines.append("Notes:")
            for n in payload["notes"]:
                lines.append(f"- {n}")
            self.stdout.write("\n".join(lines) + "\n")
            return

        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")

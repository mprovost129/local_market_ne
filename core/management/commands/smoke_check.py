from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.core.management.base import SystemCheckError
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import NoReverseMatch, reverse


def _db_ping() -> list[str]:
    """Run a few safe ORM queries to confirm DB + migrations are in place."""

    failures: list[str] = []

    try:
        from core.models import SiteConfig

        SiteConfig.objects.count()
    except Exception as exc:
        failures.append(f"DB check failed: core.SiteConfig query ({exc})")

    try:
        from catalog.models import Category

        Category.objects.count()
    except Exception as exc:
        failures.append(f"DB check failed: catalog.Category query ({exc})")

    try:
        from orders.models import Order

        Order.objects.count()
    except Exception as exc:
        failures.append(f"DB check failed: orders.Order query ({exc})")

    return failures


class Command(BaseCommand):
    """Run a fast, local end-to-end smoke test.

    This is intentionally lightweight (no external services) and is designed to
    catch "dead-end" regressions quickly after code changes.
    """

    help = "Run a fast end-to-end smoke test (URLs + templates)."

    CRITICAL_ROUTES = [
        # Public
        "healthz",
        "core:version",
        "core:home",
        "products:list",
        "products:services",
        "products:top_sellers",
        "core:about",
        "core:help",
        "core:faqs",
        "core:tips",
        # Legal (dedicated app/namespace)
        "legal:index",
        "legal:privacy",
        "legal:terms",
        # Auth/Dashboards
        "accounts:login",
        "dashboards:consumer",
        "dashboards:seller",
        "dashboards:admin_ops",
        # Ops
        "ops:dashboard",
        "ops:launch_check",
        "ops:error_events",
    ]

    CRITICAL_TEMPLATES = [
        "base.html",
        "products/product_list.html",
        "products/services_list.html",
        "dashboards/consumer_dashboard.html",
        "dashboards/seller_dashboard.html",
        "dashboards/admin_ops.html",
        "ops/dashboard.html",
        "ops/launch_check.html",
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only output failures (non-zero exit if any failures).",
        )
        parser.add_argument(
            "--checks",
            action="store_true",
            help="Run Django system checks (no external services).",
        )
        parser.add_argument(
            "--db",
            action="store_true",
            help="Run a tiny DB/migrations ping using a few ORM queries.",
        )

    def handle(self, *args, **options):
        quiet = bool(options.get("quiet"))
        run_checks = bool(options.get("checks"))
        run_db = bool(options.get("db"))

        failures: list[str] = []

        # 0) Django system checks (optional)
        if run_checks:
            try:
                call_command("check", verbosity=0)
            except SystemCheckError as exc:
                failures.append(f"Django system check failed ({exc})")
            except Exception as exc:
                failures.append(f"Django system check errored ({exc})")

        # 1) URL reversals (route wiring)
        for name in self.CRITICAL_ROUTES:
            try:
                reverse(name)
            except NoReverseMatch as exc:
                failures.append(f"URL reverse failed: {name} ({exc})")

        # 2) Template compilation
        for tpl in self.CRITICAL_TEMPLATES:
            try:
                get_template(tpl)
            except TemplateDoesNotExist as exc:
                failures.append(f"Template missing: {tpl} ({exc})")
            except Exception as exc:  # TemplateSyntaxError and friends
                failures.append(f"Template failed to compile: {tpl} ({exc})")

        # 3) DB ping (optional)
        if run_db:
            failures.extend(_db_ping())

        if failures:
            if not quiet:
                self.stdout.write(self.style.ERROR("Smoke check FAILED"))
            for msg in failures:
                self.stdout.write(self.style.ERROR(f"- {msg}"))
            raise SystemExit(2)

        if not quiet:
            self.stdout.write(self.style.SUCCESS("Smoke check OK"))
            self.stdout.write(
                "Checked: %d routes, %d templates"
                % (len(self.CRITICAL_ROUTES), len(self.CRITICAL_TEMPLATES))
            )

            extras: list[str] = []
            if run_checks:
                extras.append("django-check")
            if run_db:
                extras.append("db")
            if extras:
                self.stdout.write("Extras: " + ", ".join(extras))

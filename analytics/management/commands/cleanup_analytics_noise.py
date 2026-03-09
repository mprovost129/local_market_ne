from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from analytics.models import AnalyticsEvent
from core.config import get_site_config


_NOISY_UA_SUBSTRINGS: tuple[str, ...] = (
    "bot",
    "spider",
    "crawl",
    "slurp",
    "facebookexternalhit",
    "whatsapp",
    "telegrambot",
    "discordbot",
    "twitterbot",
    "uptimerobot",
    "pingdom",
    "statuscake",
    "datadog",
    "go-http-client",
    "python-requests",
    "curl/",
    "postmanruntime",
)


class Command(BaseCommand):
    help = (
        "Delete noisy native analytics events (bots/monitors/HEAD/admin-path noise). "
        "Use --dry-run first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Only scan events from the last N days (default: 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without deleting.",
        )
        parser.add_argument(
            "--all-time",
            action="store_true",
            help="Ignore --days and scan the entire analytics table.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff = now - timedelta(days=max(1, int(options.get("days") or 30)))
        dry_run = bool(options.get("dry_run"))
        all_time = bool(options.get("all_time"))

        cfg = get_site_config()
        primary_host = (getattr(cfg, "analytics_primary_host", "") or "").strip().lower()
        if not primary_host:
            base = (getattr(settings, "SITE_BASE_URL", "") or "").strip()
            try:
                primary_host = (urlparse(base).hostname or "").strip().lower()
            except Exception:
                primary_host = ""

        base_qs = AnalyticsEvent.objects.all()
        if not all_time:
            base_qs = base_qs.filter(created_at__gte=cutoff)

        noisy_q = Q(is_bot=True) | Q(user_agent="") | Q(method="HEAD")
        noisy_q |= Q(path__startswith="/admin/") | Q(path__startswith="/dashboard/")

        for s in _NOISY_UA_SUBSTRINGS:
            noisy_q |= Q(user_agent__icontains=s)

        if primary_host:
            noisy_q |= ~Q(host=primary_host)

        # Only clean pageviews; keep non-pageview operational signals.
        target_qs = base_qs.filter(event_type=AnalyticsEvent.EventType.PAGEVIEW).filter(noisy_q)

        total = target_qs.count()
        self.stdout.write(f"Target noisy pageviews: {total}")
        if not all_time:
            self.stdout.write(f"Window start: {cutoff.isoformat()}")
        if primary_host:
            self.stdout.write(f"Primary host filter: {primary_host}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run only. No rows deleted."))
            return

        deleted = target_qs.delete()[0]
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} noisy analytics events."))


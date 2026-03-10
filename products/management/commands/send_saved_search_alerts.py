from __future__ import annotations

import os
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from notifications.services import notify_email_and_in_app, notify_in_app_only
from products.models import Product, SavedSearchAlert


class Command(BaseCommand):
    help = "Send saved-search alerts for new matching listings (in-app, optionally email)."
    HEARTBEAT_CACHE_KEY = "ops:saved_search_alerts:last_run"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=int(os.getenv("SAVED_SEARCH_ALERTS_LIMIT", "500") or 500),
            help="Max saved searches to evaluate.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Preview only; do not send or persist.")
        parser.add_argument(
            "--enabled",
            action="store_true",
            default=(os.getenv("SAVED_SEARCH_ALERTS_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}),
            help="Enable dispatch. Defaults from SAVED_SEARCH_ALERTS_ENABLED (1/0).",
        )

    def handle(self, *args, **opts):
        enabled = bool(opts.get("enabled"))
        if not enabled:
            self.stdout.write("saved_search_alerts disabled (set SAVED_SEARCH_ALERTS_ENABLED=1 or pass --enabled).")
            return

        limit = max(1, int(opts.get("limit") or 500))
        dry_run = bool(opts.get("dry_run"))
        now = timezone.now()

        searches = (
            SavedSearchAlert.objects.select_related("user")
            .filter(is_active=True, user__is_active=True)
            .order_by("last_notified_at", "created_at")[:limit]
        )

        checked = 0
        alerted = 0
        for s in searches:
            checked += 1
            since = s.last_notified_at or s.created_at
            qs = Product.objects.filter(is_active=True, kind=s.kind, created_at__gt=since)

            if s.query:
                q = s.query.strip()
                qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q))
            if s.category_id_filter:
                cid = int(s.category_id_filter)
                qs = qs.filter(Q(category_id=cid) | Q(subcategory_id=cid))
            if s.zip_prefix:
                qs = qs.filter(seller__profile__zip_code__istartswith=s.zip_prefix)
            if s.kind == SavedSearchAlert.Kind.SERVICE and int(s.radius_miles or 0) > 0:
                qs = qs.filter(seller__profile__service_radius_miles__gte=int(s.radius_miles))

            # Do not notify users about their own newly published listings.
            qs = qs.exclude(seller_id=s.user_id)

            matches = list(qs.order_by("-created_at")[:3])
            match_count = len(matches)
            if match_count == 0:
                continue

            params: dict[str, str] = {}
            if s.query:
                params["q"] = s.query
            if s.category_id_filter:
                params["category"] = str(s.category_id_filter)
            if s.zip_prefix:
                params["zip"] = s.zip_prefix
            if s.kind == SavedSearchAlert.Kind.SERVICE and int(s.radius_miles or 0) > 0:
                params["radius"] = str(int(s.radius_miles))
            if s.sort:
                params["sort"] = s.sort
            route = "products:services" if s.kind == SavedSearchAlert.Kind.SERVICE else "products:list"
            action_url = reverse(route)
            if params:
                action_url = f"{action_url}?{urlencode(params)}"
            absolute_action_url = self._abs_url(action_url)

            title = f"New local {s.get_kind_display().lower()} match your saved search"
            names = ", ".join(p.title for p in matches[:2])
            body = f"{match_count} new listing(s) found. {names}" if names else f"{match_count} new listing(s) found."

            if dry_run:
                self.stdout.write(f"[dry-run] user={s.user_id} search={s.id} matches={match_count} -> {action_url}")
            else:
                payload = {"saved_search_id": s.id, "match_count": match_count}
                if s.email_enabled:
                    notify_email_and_in_app(
                        user=s.user,
                        kind="SYSTEM",
                        email_subject=title[:160],
                        email_template_html="emails/saved_search_alert.html",
                        email_template_txt="emails/saved_search_alert.txt",
                        context={
                            "subject": title[:160],
                            "title": title[:160],
                            "body": body[:800],
                            "match_count": match_count,
                            "action_url": absolute_action_url,
                            "logo_url": self._abs_url("/static/images/local_market_logo.png"),
                        },
                        title=title[:160],
                        body=body[:800],
                        action_url=action_url,
                        payload=payload,
                    )
                else:
                    notify_in_app_only(
                        user=s.user,
                        kind="SYSTEM",
                        title=title[:160],
                        body=body[:800],
                        action_url=action_url,
                        payload=payload,
                    )
                s.last_notified_at = now
                s.save(update_fields=["last_notified_at", "updated_at"])
                alerted += 1

        self._write_heartbeat(
            ran_at=now,
            checked=checked,
            alerted=alerted,
            dry_run=dry_run,
            limit=limit,
        )
        self.stdout.write(f"checked={checked} alerted={alerted} dry_run={dry_run}")

    def _abs_url(self, path: str) -> str:
        base = (getattr(settings, "SITE_BASE_URL", "") or "").rstrip("/")
        if not base:
            return path
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{base}{path}"

    def _write_heartbeat(self, *, ran_at, checked: int, alerted: int, dry_run: bool, limit: int) -> None:
        payload = {
            "ran_at": ran_at.isoformat(),
            "checked": int(checked or 0),
            "alerted": int(alerted or 0),
            "dry_run": bool(dry_run),
            "limit": int(limit or 0),
        }
        # Keep 7 days of heartbeat visibility for ops investigation.
        cache.set(self.HEARTBEAT_CACHE_KEY, payload, timeout=7 * 24 * 60 * 60)

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from accounts.geo import lookup_zip_centroid
from accounts.models import Profile


class Command(BaseCommand):
    help = "Backfill private profile geo coordinates from ZIP codes (best effort)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200, help="Max profiles to process.")
        parser.add_argument("--seller-only", action="store_true", help="Process seller profiles only.")

    def handle(self, *args, **options):
        limit = max(1, int(options.get("limit") or 200))
        seller_only = bool(options.get("seller_only"))

        qs = Profile.objects.filter(
            zip_code__isnull=False,
        ).exclude(zip_code="")
        qs = qs.filter(Q(private_latitude__isnull=True) | Q(private_longitude__isnull=True))
        if seller_only:
            qs = qs.filter(is_seller=True)
        qs = qs.order_by("id")[:limit]

        checked = 0
        updated = 0
        skipped = 0
        for p in qs:
            checked += 1
            centroid = lookup_zip_centroid(p.zip_code)
            if not centroid:
                skipped += 1
                continue
            lat, lng = centroid
            p.private_latitude = lat
            p.private_longitude = lng
            p.private_geo_updated_at = timezone.now()
            p.save(update_fields=["private_latitude", "private_longitude", "private_geo_updated_at", "updated_at"])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"backfill_profile_geo complete: checked={checked}, updated={updated}, skipped={skipped}"
            )
        )

from __future__ import annotations

"""End-to-end-ish flow smoke checks.

This is NOT a replacement for manual QA. It exists to catch the class of
"I clicked a page and got a 500/NoReverseMatch/FieldError" regressions that
have bitten us repeatedly during the RC hardening packs.

It creates a tiny set of objects (user/profile, categories, listing) and then
uses Django's test client to request key pages and perform a basic cart add.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category
from products.models import Product


class Command(BaseCommand):
    help = "Run a minimal end-to-end flow smoke check (pages + cart add)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep",
            action="store_true",
            help="Do not delete created test objects (useful for local inspection).",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero if any check fails.",
        )

    def handle(self, *args, **options):
        keep = bool(options.get("keep"))
        strict = bool(options.get("strict"))

        failures: list[str] = []

        def _fail(msg: str):
            failures.append(msg)
            self.stderr.write(self.style.ERROR(f"FAIL: {msg}"))

        def _ok(msg: str):
            self.stdout.write(self.style.SUCCESS(f"OK: {msg}"))

        # ------------------------------------------------------------------
        # Create minimal fixture objects
        # ------------------------------------------------------------------
        User = get_user_model()
        ts = timezone.now().strftime("%H%M%S")
        username = f"flowcheck_{ts}"
        password = "flowcheck_password_123"
        user = User.objects.create_user(username=username, password=password)

        # Ensure profile exists and is a seller, verified, and policy-confirmed.
        profile = getattr(user, "profile", None)
        if profile is None:
            _fail("User.profile was not created by signals")
        else:
            profile.email_verified = True
            profile.is_seller = True
            profile.is_age_18_confirmed = True
            profile.seller_prohibited_items_ack = True
            profile.public_city = "Providence"
            profile.public_state = "RI"
            profile.shop_name = "Flow Check Shop"
            profile.save(update_fields=[
                "email_verified",
                "is_seller",
                "is_age_18_confirmed",
                "seller_prohibited_items_ack",
                "public_city",
                "public_state",
                "shop_name",
            ])

        # Categories
        cat_root = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Flow Products",
            slug=f"flow-products-{ts}",
        )
        cat_sub = Category.objects.create(
            type=Category.CategoryType.GOOD,
            parent=cat_root,
            name="Flow Sub",
            slug=f"flow-sub-{ts}",
        )

        # Listing
        listing = Product.objects.create(
            seller=user,
            kind=Product.Kind.GOOD,
            title=f"Flow Listing {ts}",
            short_description="Flow check item",
            description="Flow check item",
            category=cat_root,
            subcategory=cat_sub,
            price=Decimal("12.34"),
            is_active=True,
            stock_qty=5,
            fulfillment_pickup_enabled=True,
            fulfillment_delivery_enabled=False,
            fulfillment_shipping_enabled=True,
            shipping_fee_cents=499,
        )

        # ------------------------------------------------------------------
        # Client checks
        # ------------------------------------------------------------------
        c = Client()
        c.force_login(user)

        def _get(name: str, kwargs=None, expect=(200, 302)):
            try:
                url = reverse(name, kwargs=kwargs or {})
            except Exception as e:
                _fail(f"reverse({name}) failed: {e}")
                return
            resp = c.get(url)
            if resp.status_code not in expect:
                _fail(f"GET {name} -> {resp.status_code} (expected {expect})")
            else:
                _ok(f"GET {name} ({resp.status_code})")

        # Public + dashboards
        _get("products:list")
        _get("products:detail", kwargs={"pk": listing.pk, "slug": listing.slug})
        _get("cart:detail")
        _get("dashboards:consumer")
        _get("dashboards:seller")
        _get("products:seller_list")
        _get("products:seller_create")

        # Cart add (POST)
        try:
            add_url = reverse("cart:add")
            resp = c.post(add_url, {"product_id": listing.pk, "qty": 1}, follow=True)
            if resp.status_code != 200:
                _fail(f"POST cart:add follow -> {resp.status_code} (expected 200)")
            else:
                _ok("POST cart:add (follow 200)")
        except Exception as e:
            _fail(f"POST cart:add raised: {e}")

        # ------------------------------------------------------------------
        # Cleanup
        # ------------------------------------------------------------------
        if not keep:
            try:
                listing.delete()
            except Exception:
                pass
            try:
                cat_sub.delete()
            except Exception:
                pass
            try:
                cat_root.delete()
            except Exception:
                pass
            try:
                user.delete()
            except Exception:
                pass

        if failures:
            self.stderr.write(self.style.ERROR(f"Flow check completed with {len(failures)} failure(s)."))
            if strict:
                raise SystemExit(2)
        else:
            self.stdout.write(self.style.SUCCESS("Flow check passed."))

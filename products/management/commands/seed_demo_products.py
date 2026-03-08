# products/management/commands/seed_demo_products.py
from __future__ import annotations

import base64
import random
import struct
import zlib
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from products.models import Product, ProductImage

# Optional models in your project
try:
    from payments.models import SellerStripeAccount
except Exception:  # pragma: no cover
    SellerStripeAccount = None  # type: ignore

try:
    from catalog.models import Category
except Exception:  # pragma: no cover
    Category = None  # type: ignore


# Fallback 1x1 PNG in case dynamic image generation fails for any reason.
_ONE_BY_ONE_PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    return length + chunk_type + data + crc


def _solid_png_bytes(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Generate a simple solid-color RGB PNG without external dependencies (Pillow)."""
    r, g, b = rgb
    width = max(1, int(width))
    height = max(1, int(height))

    # Raw image data for color type 2 (RGB), 8-bit depth.
    pixel = bytes((r, g, b))
    row = pixel * width
    raw = b"".join((b"\x00" + row) for _ in range(height))  # filter byte 0 per row
    compressed = zlib.compress(raw, level=9)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return signature + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", compressed) + _png_chunk(b"IEND", b"")


class Command(BaseCommand):
    help = "Seed fake products + services + generated placeholder pictures for local smoke testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--products",
            type=int,
            default=16,
            help="Total listings to create (default 16). Split between products and services.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo users/products created by this command before reseeding.",
        )

    def handle(self, *args, **options):
        total_products: int = max(2, int(options["products"]))
        reset: bool = bool(options["reset"])

        with transaction.atomic():
            seller_ready = self._get_or_create_user(
                username="demo_seller_ready",
                email="demo_seller_ready@example.com",
                password="demo12345",
                is_staff=True,
            )
            seller_not_ready = self._get_or_create_user(
                username="demo_seller_not_ready",
                email="demo_seller_not_ready@example.com",
                password="demo12345",
                is_staff=True,
            )

            if reset:
                self._reset_demo_data({seller_ready.id, seller_not_ready.id})

            self._ensure_seller_ready_flag(seller_ready)

            goods_cat = self._get_or_create_category_for_kind("GOOD", name="Demo Products")
            services_cat = self._get_or_create_category_for_kind("SERVICE", name="Demo Services")

            # Split listings roughly evenly
            n_goods = total_products // 2
            n_services = total_products - n_goods

            created = 0
            created += self._seed_products_for_kind(
                seller=seller_ready,
                kind=Product.Kind.GOOD,
                category=goods_cat,
                count=max(1, n_goods // 2),
                title_prefix="Handmade Product",
                price_base=Decimal("24.99"),
                featured=True,
            )
            created += self._seed_products_for_kind(
                seller=seller_not_ready,
                kind=Product.Kind.GOOD,
                category=goods_cat,
                count=max(1, n_goods - (n_goods // 2)),
                title_prefix="Market Product",
                price_base=Decimal("19.99"),
                featured=False,
            )
            created += self._seed_products_for_kind(
                seller=seller_ready,
                kind=Product.Kind.SERVICE,
                category=services_cat,
                count=max(1, n_services // 2),
                title_prefix="Home Service",
                price_base=Decimal("49.99"),
                featured=False,
            )
            created += self._seed_products_for_kind(
                seller=seller_not_ready,
                kind=Product.Kind.SERVICE,
                category=services_cat,
                count=max(1, n_services - (n_services // 2)),
                title_prefix="Local Service",
                price_base=Decimal("39.99"),
                featured=False,
            )

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write("Demo logins:")
        self.stdout.write("  demo_seller_ready / demo12345  (Stripe-ready where supported)")
        self.stdout.write("  demo_seller_not_ready / demo12345")
        self.stdout.write(f"Created/ensured ~{created} listings + generated images.")

    def _get_or_create_user(self, *, username: str, email: str, password: str, is_staff: bool) -> Any:
        User = get_user_model()

        # Try to find by username or email
        user = User.objects.filter(username=username).first()
        if not user:
            user = User.objects.filter(email=email).first()

        if user:
            # Ensure basics
            if getattr(user, "username", None) != username:
                try:
                    user.username = username  # type: ignore[attr-defined]
                except Exception:
                    pass
            if getattr(user, "email", None) != email:
                try:
                    user.email = email
                except Exception:
                    pass
            try:
                user.is_staff = bool(is_staff)
            except Exception:
                pass
            user.save()
            return user

        # Create
        try:
            user = User.objects.create_user(username=username, email=email, password=password)
        except TypeError:
            # If custom user creation differs, fallback to minimal create + set_password
            user = User(username=username, email=email)
            user.set_password(password)
            user.save()

        try:
            user.is_staff = bool(is_staff)
            user.save()
        except Exception:
            pass

        return user

    def _reset_demo_data(self, seller_ids: set[int]) -> None:
        # Delete demo products for our demo sellers
        qs = Product.objects.filter(seller_id__in=seller_ids)
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.WARNING(f"Reset: deleted {count} existing demo products."))

    def _ensure_seller_ready_flag(self, seller) -> None:
        if SellerStripeAccount is None:
            self.stdout.write(self.style.WARNING("SellerStripeAccount model not available; skipping ready flag."))
            return

        try:
            SellerStripeAccount.objects.update_or_create(
                user_id=seller.id,
                defaults={
                    "charges_enabled": True,
                    "payouts_enabled": True,
                    "details_submitted": True,
                },
            )
        except Exception:
            self.stdout.write(self.style.WARNING("Could not set Stripe readiness flags (schema mismatch)."))

    def _get_or_create_category_for_kind(self, kind: str, *, name: str):
        """
        Best-effort:
        - Prefer existing categories for the requested kind/type.
        - If none exist and Category model is compatible, create a simple root category.
        """
        if Category is None:
            self.stdout.write(self.style.WARNING("Category model not available; cannot attach categories."))
            return None

        # First: try to find anything matching kind.
        # Category.type choices are GOOD / SERVICE.
        cat = None
        try:
            cat = Category.objects.filter(type=kind).order_by("id").first()
        except Exception:
            cat = None

        if cat:
            return cat

        # Try to create a minimal category. This depends on your schema.
        data = {}
        # Common fields
        if hasattr(Category, "name"):
            data["name"] = name
        if hasattr(Category, "slug"):
            data["slug"] = slugify(name)
        if hasattr(Category, "type"):
            data["type"] = kind
        # Tree fields (optional)
        if hasattr(Category, "parent_id"):
            data["parent_id"] = None

        try:
            return Category.objects.create(**data)
        except Exception:
            self.stdout.write(self.style.WARNING(f"Could not auto-create Category for kind={kind}; using first available."))
            try:
                return Category.objects.order_by("id").first()
            except Exception:
                return None

    def _seed_products_for_kind(
        self,
        *,
        seller,
        kind: str,
        category,
        count: int,
        title_prefix: str,
        price_base: Decimal,
        featured: bool,
    ) -> int:
        goods_names = [
            "Rustic Wooden Shelf",
            "Soy Wax Candle Set",
            "Ceramic Coffee Mug",
            "Macrame Wall Hanging",
            "Organic Soap Bundle",
            "Knit Beanie",
            "Leather Key Holder",
            "Farmhouse Planter",
        ]
        service_names = [
            "Lawn Mowing Visit",
            "Dog Walking Session",
            "Mobile Car Detailing",
            "Home Office Setup Help",
            "TV Mount Installation",
            "Seasonal Yard Cleanup",
            "Handyman Hour",
            "Beginner Guitar Lesson",
        ]
        image_palette = [
            (229, 115, 115),
            (244, 143, 177),
            (129, 199, 132),
            (77, 182, 172),
            (100, 181, 246),
            (149, 117, 205),
            (255, 183, 77),
            (161, 136, 127),
        ]

        created = 0
        for i in range(1, count + 1):
            if kind == Product.Kind.SERVICE:
                base_name = service_names[(i - 1) % len(service_names)]
            else:
                base_name = goods_names[(i - 1) % len(goods_names)]

            title = f"{title_prefix}: {base_name} #{i}"
            slug = slugify(title)[:180]

            # Ensure uniqueness per seller+slug
            existing = Product.objects.filter(seller_id=seller.id, slug=slug).first()
            if existing:
                p = existing
                p.title = title
                p.kind = kind
                if category is not None:
                    p.category = category
                p.price = price_base + Decimal(i)
                p.is_free = False
                p.is_active = True
                p.is_featured = bool(featured and i <= 2)
                p.is_trending = bool(i == 1)  # seed a couple manual trending flags
                p.short_description = "Fake listing for local testing."
                if kind == Product.Kind.SERVICE:
                    p.description = "Demo service listing with generated fake photo for UI testing."
                    p.service_duration_minutes = 60
                    p.service_cancellation_policy = "Cancel at least 24 hours before appointment for full refund."
                    p.service_cancellation_window_hours = 24
                    p.service_deposit_cents = 1500
                else:
                    p.description = "Demo product listing with generated fake photo for UI testing."
                    p.stock_qty = max(1, 10 - i)
                    p.is_made_to_order = bool(i % 4 == 0)
                    p.lead_time_days = 5 if p.is_made_to_order else None
                    p.fulfillment_pickup_enabled = True
                    p.fulfillment_delivery_enabled = bool(i % 2 == 0)
                    p.fulfillment_shipping_enabled = bool(i % 3 == 0)
                    p.delivery_radius_miles = 10 if p.fulfillment_delivery_enabled else None
                    p.delivery_fee_cents = 499 if p.fulfillment_delivery_enabled else 0
                    p.shipping_fee_cents = 899 if p.fulfillment_shipping_enabled else 0
                p.save()
            else:
                kwargs: dict[str, Any] = dict(
                    seller_id=seller.id,
                    kind=kind,
                    title=title,
                    slug=slug,
                    short_description="Fake listing for local testing.",
                    description="Demo listing generated by seed_demo_products for UI testing.",
                    price=price_base + Decimal(i),
                    is_free=False,
                    is_active=True,
                    is_featured=bool(featured and i <= 2),
                    is_trending=bool(i == 1),
                )
                if category is not None:
                    kwargs["category"] = category

                if kind == Product.Kind.SERVICE:
                    kwargs.update(
                        service_duration_minutes=60,
                        service_cancellation_policy="Cancel at least 24 hours before appointment for full refund.",
                        service_cancellation_window_hours=24,
                        service_deposit_cents=1500,
                    )
                else:
                    pickup_enabled = True
                    delivery_enabled = bool(i % 2 == 0)
                    shipping_enabled = bool(i % 3 == 0)
                    kwargs.update(
                        stock_qty=max(1, 10 - i),
                        is_made_to_order=bool(i % 4 == 0),
                        lead_time_days=5 if i % 4 == 0 else None,
                        fulfillment_pickup_enabled=pickup_enabled,
                        fulfillment_delivery_enabled=delivery_enabled,
                        fulfillment_shipping_enabled=shipping_enabled,
                        delivery_radius_miles=10 if delivery_enabled else None,
                        delivery_fee_cents=499 if delivery_enabled else 0,
                        shipping_fee_cents=899 if shipping_enabled else 0,
                    )

                p = Product.objects.create(**kwargs)

            # Ensure an image exists
            if not p.images.exists():
                img_name = f"demo_{p.kind.lower()}_{p.id}.png"
                color = random.choice(image_palette)
                try:
                    fake_png = _solid_png_bytes(640, 420, color)
                except Exception:
                    fake_png = _ONE_BY_ONE_PNG
                content = ContentFile(fake_png, name=img_name)
                ProductImage.objects.create(
                    product=p,
                    image=content,
                    alt_text=p.title,
                    is_primary=True,
                    sort_order=0,
                )

            created += 1

        return created

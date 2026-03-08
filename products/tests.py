from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category
from orders.models import Order, OrderItem
from payments.models import SellerStripeAccount
from products.models import Product
from products.services.trending import get_trending_badge_ids


User = get_user_model()


@override_settings(
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class ListingFlowTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            username="seller_listing",
            email="seller_listing@example.com",
            password="pw123456",
        )
        prof = self.seller.profile
        prof.is_seller = True
        prof.email_verified = True
        prof.shop_name = "Seller Listing Co"
        prof.save(update_fields=["is_seller", "email_verified", "shop_name", "updated_at"])

        SellerStripeAccount.objects.create(
            user=self.seller,
            stripe_account_id="acct_listing_ready",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
        )

        self.consumer = User.objects.create_user(
            username="consumer_listing",
            email="consumer_listing@example.com",
            password="pw123456",
        )
        cprof = self.consumer.profile
        cprof.email_verified = True
        cprof.save(update_fields=["email_verified", "updated_at"])

        self.goods_category = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Goods Test",
            slug=f"goods-test-{uuid4().hex[:8]}",
            is_active=True,
        )

    def test_invalid_listing_post_stays_on_correct_step_for_missing_title(self):
        self.client.force_login(self.seller)

        resp = self.client.post(
            reverse("products:seller_create"),
            data={
                "kind": Product.Kind.GOOD,
                "category": self.goods_category.id,
                "subcategory": "",
                "title": "",
                "short_description": "short desc",
                "description": "full description",
                "price": "12.00",
                "stock_qty": "3",
                "fulfillment_pickup_enabled": "on",
                "is_active": "on",
            },
        )

        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn('data-initial-step="3"', html)
        self.assertIn('data-first-error-field="title"', html)
        self.assertIn("This field is required", html)

    def test_listing_create_visible_in_seller_list_and_storefront_and_buyable(self):
        self.client.force_login(self.seller)

        resp = self.client.post(
            reverse("products:seller_create"),
            data={
                "kind": Product.Kind.GOOD,
                "category": self.goods_category.id,
                "subcategory": "",
                "title": "Maple Candle",
                "short_description": "Hand-poured candle",
                "description": "A detailed candle description.",
                "price": "15.00",
                "stock_qty": "7",
                "fulfillment_pickup_enabled": "on",
                "is_active": "on",
                "is_free": "",
                "slug": "",
            },
        )

        self.assertEqual(resp.status_code, 302)
        created = Product.objects.get(title="Maple Candle", seller=self.seller)
        self.assertTrue(created.is_active)
        self.assertIn(reverse("products:seller_images", kwargs={"pk": created.pk}), resp["Location"])

        seller_list = self.client.get(reverse("products:seller_list"))
        self.assertContains(seller_list, "Maple Candle")

        self.client.logout()
        storefront = self.client.get(reverse("products:seller_shop", kwargs={"seller_id": self.seller.id}))
        self.assertContains(storefront, "Maple Candle")

        self.client.force_login(self.consumer)
        detail = self.client.get(reverse("products:detail", kwargs={"pk": created.pk, "slug": created.slug}))
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.context["can_buy"])
        self.assertContains(detail, "Add to cart")

    def test_paid_purchases_feed_trending_badge_membership(self):
        p1 = Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Trending Product",
            category=self.goods_category,
            price=Decimal("25.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_pickup_enabled=True,
        )
        Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Regular Product",
            category=self.goods_category,
            price=Decimal("10.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_pickup_enabled=True,
        )

        order = Order.objects.create(
            buyer=self.consumer,
            status=Order.Status.PAID,
            payment_method=Order.PaymentMethod.STRIPE,
            paid_at=timezone.now(),
            total_cents=2500,
            subtotal_cents=2500,
        )
        OrderItem.objects.create(
            order=order,
            product=p1,
            seller=self.seller,
            title_snapshot=p1.title,
            unit_price_cents_snapshot=2500,
            quantity=1,
            line_total_cents=2500,
            seller_net_cents=2500,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="pickup",
        )

        cache.clear()
        badge_ids = get_trending_badge_ids(top_n=1, since_days=30)
        self.assertIn(p1.id, badge_ids)
        listing = self.client.get(reverse("products:list"))
        self.assertContains(listing, "Trending")

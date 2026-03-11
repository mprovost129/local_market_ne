from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category
from notifications.models import EmailDeliveryAttempt, Notification
from orders.models import Order, OrderItem
from payments.models import SellerStripeAccount
from products.models import Product, SavedSearchAlert
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
        prof.public_city = "Providence"
        prof.zip_code = "02860"
        prof.save(update_fields=["is_seller", "email_verified", "shop_name", "public_city", "zip_code", "updated_at"])

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
        self.service_category = Category.objects.create(
            type=Category.CategoryType.SERVICE,
            name="Services Test",
            slug=f"services-test-{uuid4().hex[:8]}",
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

    def test_product_card_shows_seller_city(self):
        Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="City Card Product",
            category=self.goods_category,
            price=Decimal("9.99"),
            is_active=True,
            stock_qty=5,
            fulfillment_pickup_enabled=True,
        )
        resp = self.client.get(reverse("products:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Providence")

    def test_seller_storefront_applies_branding_when_enabled(self):
        profile = self.seller.profile
        profile.storefront_theme_enabled = True
        profile.storefront_layout = "catalog"
        profile.storefront_primary_color = "#3A6B3A"
        profile.save(update_fields=["storefront_theme_enabled", "storefront_layout", "storefront_primary_color", "updated_at"])

        Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Branded Store Product",
            category=self.goods_category,
            price=Decimal("11.00"),
            is_active=True,
            stock_qty=2,
            fulfillment_pickup_enabled=True,
        )

        resp = self.client.get(reverse("products:seller_shop", kwargs={"seller_id": self.seller.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "seller-shop--custom")
        self.assertContains(resp, "seller-shop--layout-catalog")
        self.assertContains(resp, "--seller-accent: #3A6B3A")

    def test_products_list_filters_by_seller_zip(self):
        other_seller = User.objects.create_user(
            username="seller_zip_other",
            email="seller_zip_other@example.com",
            password="pw123456",
        )
        other_profile = other_seller.profile
        other_profile.is_seller = True
        other_profile.email_verified = True
        other_profile.zip_code = "02108"
        other_profile.save(update_fields=["is_seller", "email_verified", "zip_code", "updated_at"])

        Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Zip Matched Product",
            category=self.goods_category,
            price=Decimal("12.00"),
            is_active=True,
            stock_qty=3,
            fulfillment_pickup_enabled=True,
        )
        Product.objects.create(
            seller=other_seller,
            kind=Product.Kind.GOOD,
            title="Zip Other Product",
            category=self.goods_category,
            price=Decimal("13.00"),
            is_active=True,
            stock_qty=3,
            fulfillment_pickup_enabled=True,
        )

        resp = self.client.get(reverse("products:list"), {"zip": "02860"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Zip Matched Product")
        self.assertNotContains(resp, "Zip Other Product")

    def test_services_list_filters_by_seller_zip(self):
        other_seller = User.objects.create_user(
            username="seller_service_zip_other",
            email="seller_service_zip_other@example.com",
            password="pw123456",
        )
        other_profile = other_seller.profile
        other_profile.is_seller = True
        other_profile.email_verified = True
        other_profile.zip_code = "02108"
        other_profile.save(update_fields=["is_seller", "email_verified", "zip_code", "updated_at"])

        Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.SERVICE,
            title="Zip Matched Service",
            category=self.service_category,
            price=Decimal("50.00"),
            is_active=True,
            service_duration_minutes=60,
        )
        Product.objects.create(
            seller=other_seller,
            kind=Product.Kind.SERVICE,
            title="Zip Other Service",
            category=self.service_category,
            price=Decimal("50.00"),
            is_active=True,
            service_duration_minutes=60,
        )

        resp = self.client.get(reverse("products:services"), {"zip": "02860"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Zip Matched Service")
        self.assertNotContains(resp, "Zip Other Service")

    def test_products_sort_price_low_orders_results(self):
        Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Expensive Product",
            category=self.goods_category,
            price=Decimal("30.00"),
            is_active=True,
            stock_qty=3,
            fulfillment_pickup_enabled=True,
        )
        Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Affordable Product",
            category=self.goods_category,
            price=Decimal("5.00"),
            is_active=True,
            stock_qty=3,
            fulfillment_pickup_enabled=True,
        )

        resp = self.client.get(reverse("products:list"), {"sort": "price_low", "zip": "02860"})
        self.assertEqual(resp.status_code, 200)
        rows = list(resp.context["products"])
        titles = [p.title for p in rows]
        self.assertIn("Affordable Product", titles)
        self.assertIn("Expensive Product", titles)
        self.assertLess(titles.index("Affordable Product"), titles.index("Expensive Product"))

    def test_saved_search_create_and_remove(self):
        self.client.force_login(self.consumer)
        create_resp = self.client.post(
            reverse("products:saved_search_create"),
            data={
                "kind": "GOOD",
                "q": "candle",
                "zip": "02860",
                "sort": "local",
            },
        )
        self.assertEqual(create_resp.status_code, 302)
        saved = SavedSearchAlert.objects.filter(user=self.consumer, kind=SavedSearchAlert.Kind.GOOD).first()
        self.assertIsNotNone(saved)
        self.assertEqual(saved.query, "candle")
        self.assertEqual(saved.zip_prefix, "02860")

        remove_resp = self.client.post(reverse("products:saved_search_delete", kwargs={"pk": saved.id}))
        self.assertEqual(remove_resp.status_code, 302)
        self.assertFalse(SavedSearchAlert.objects.filter(pk=saved.id).exists())

    def test_saved_search_update_toggles_flags(self):
        saved = SavedSearchAlert.objects.create(
            user=self.consumer,
            kind=SavedSearchAlert.Kind.GOOD,
            query="candle",
            zip_prefix="02860",
            sort="local",
            is_active=True,
            email_enabled=False,
        )
        self.client.force_login(self.consumer)
        resp = self.client.post(
            reverse("products:saved_search_update", kwargs={"pk": saved.id}),
            data={"email_enabled": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        saved.refresh_from_db()
        self.assertFalse(saved.is_active)
        self.assertTrue(saved.email_enabled)

    def test_saved_search_alert_command_creates_in_app_notification(self):
        saved = SavedSearchAlert.objects.create(
            user=self.consumer,
            kind=SavedSearchAlert.Kind.GOOD,
            query="Maple",
            zip_prefix="02860",
            sort="local",
        )
        Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Maple Birdhouse",
            short_description="Local handmade birdhouse",
            category=self.goods_category,
            price=Decimal("35.00"),
            is_active=True,
            stock_qty=3,
            fulfillment_pickup_enabled=True,
        )

        call_command("send_saved_search_alerts", limit=50)

        self.assertTrue(Notification.objects.filter(user=self.consumer, payload__saved_search_id=saved.id).exists())
        saved.refresh_from_db()
        self.assertIsNotNone(saved.last_notified_at)

    def test_saved_search_alert_command_email_enabled_creates_email_attempt(self):
        SavedSearchAlert.objects.create(
            user=self.consumer,
            kind=SavedSearchAlert.Kind.GOOD,
            query="Maple",
            zip_prefix="02860",
            sort="local",
            email_enabled=True,
        )
        Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Maple Planter",
            short_description="Handmade planter",
            category=self.goods_category,
            price=Decimal("22.00"),
            is_active=True,
            stock_qty=3,
            fulfillment_pickup_enabled=True,
        )

        call_command("send_saved_search_alerts", limit=50)

        notif = Notification.objects.filter(user=self.consumer).order_by("-created_at").first()
        self.assertIsNotNone(notif)
        self.assertTrue(notif.email_subject)
        self.assertTrue(EmailDeliveryAttempt.objects.filter(notification=notif).exists())

    def test_saved_search_alert_command_skips_user_own_listings(self):
        saved = SavedSearchAlert.objects.create(
            user=self.seller,
            kind=SavedSearchAlert.Kind.GOOD,
            query="Maple",
            zip_prefix="02860",
            sort="local",
        )
        Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Maple Coaster Set",
            short_description="Maple wood coasters",
            category=self.goods_category,
            price=Decimal("20.00"),
            is_active=True,
            stock_qty=4,
            fulfillment_pickup_enabled=True,
        )

        call_command("send_saved_search_alerts", limit=50)

        self.assertFalse(Notification.objects.filter(user=self.seller, payload__saved_search_id=saved.id).exists())

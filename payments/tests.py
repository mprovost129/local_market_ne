from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from decimal import Decimal

from catalog.models import Category
from core.models import SiteConfig
from payments.models import SellerFeePlan, SellerFeeWaiver, SellerStripeAccount
from payments.services_fee_waiver import get_effective_marketplace_sales_percent_for_seller
from products.models import Product


User = get_user_model()


class ConnectReturnRedirectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="seller_return",
            email="seller_return@example.com",
            password="pw123456",
        )
        profile = self.user.profile
        profile.is_seller = True
        profile.email_verified = True
        profile.save(update_fields=["is_seller", "email_verified", "updated_at"])
        self.client.force_login(self.user)

    def test_connect_return_redirects_ready_seller_to_listings(self):
        SellerStripeAccount.objects.create(
            user=self.user,
            stripe_account_id="acct_ready_123",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
        )

        with patch("payments.views._refresh_connect_status", return_value=None):
            resp = self.client.get(reverse("payments:connect_return"))

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("products:seller_list"))

    def test_connect_return_redirects_unready_seller_to_connect_status(self):
        SellerStripeAccount.objects.create(
            user=self.user,
            stripe_account_id="acct_not_ready_123",
            details_submitted=False,
            charges_enabled=False,
            payouts_enabled=False,
        )

        with patch("payments.views._refresh_connect_status", return_value=None):
            resp = self.client.get(reverse("payments:connect_return"))

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("payments:connect_status"))


class SellerFeeWaiverStartTriggerTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            username="seller_waiver_trigger",
            email="seller_waiver_trigger@example.com",
            password="pw123456",
        )
        profile = self.seller.profile
        profile.is_seller = True
        profile.email_verified = True
        profile.save(update_fields=["is_seller", "email_verified", "updated_at"])

        self.category = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Waiver Test Category",
            slug="waiver-test-category",
            is_active=True,
        )

    def test_waiver_does_not_start_at_stripe_row_creation(self):
        SellerStripeAccount.objects.create(
            user=self.seller,
            stripe_account_id="acct_waiver_not_started",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
        )
        self.assertFalse(SellerFeeWaiver.objects.filter(user=self.seller).exists())

    def test_waiver_starts_on_first_live_listing(self):
        SellerStripeAccount.objects.create(
            user=self.seller,
            stripe_account_id="acct_waiver_first_live",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
        )

        listing = Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Draft listing",
            category=self.category,
            price="10.00",
            stock_qty=1,
            fulfillment_pickup_enabled=True,
            is_active=False,
        )
        self.assertFalse(SellerFeeWaiver.objects.filter(user=self.seller).exists())

        listing.is_active = True
        listing.save(update_fields=["is_active"])
        self.assertEqual(SellerFeeWaiver.objects.filter(user=self.seller).count(), 1)

        listing.is_active = False
        listing.save(update_fields=["is_active"])
        listing.is_active = True
        listing.save(update_fields=["is_active"])
        self.assertEqual(SellerFeeWaiver.objects.filter(user=self.seller).count(), 1)


class SellerFeePlanOverrideTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            username="seller_fee_plan_test",
            email="seller_fee_plan_test@example.com",
            password="pw123456",
        )
        cfg, _ = SiteConfig.objects.get_or_create(pk=1)
        cfg.marketplace_sales_percent = Decimal("10.00")
        cfg.seller_fee_waiver_enabled = True
        cfg.save()

    def test_default_percent_when_no_plan_or_waiver(self):
        pct = get_effective_marketplace_sales_percent_for_seller(seller_user=self.seller)
        self.assertEqual(pct, Decimal("10.00"))

    def test_waiver_sets_effective_percent_to_zero(self):
        SellerFeeWaiver.ensure_for_seller(user=self.seller, waiver_days=30)
        pct = get_effective_marketplace_sales_percent_for_seller(seller_user=self.seller)
        self.assertEqual(pct, Decimal("0.00"))

    def test_active_fixed_plan_overrides_waiver(self):
        SellerFeeWaiver.ensure_for_seller(user=self.seller, waiver_days=30)
        SellerFeePlan.objects.create(
            user=self.seller,
            is_active=True,
            custom_sales_percent=Decimal("3.50"),
            discount_percent=Decimal("0.00"),
        )
        pct = get_effective_marketplace_sales_percent_for_seller(seller_user=self.seller)
        self.assertEqual(pct, Decimal("3.50"))

    def test_discount_plan_applies_to_global_percent(self):
        SellerFeePlan.objects.create(
            user=self.seller,
            is_active=True,
            custom_sales_percent=None,
            discount_percent=Decimal("25.00"),
        )
        pct = get_effective_marketplace_sales_percent_for_seller(seller_user=self.seller)
        self.assertEqual(pct, Decimal("7.50"))

    def test_discount_100_percent_comps_fee(self):
        SellerFeePlan.objects.create(
            user=self.seller,
            is_active=True,
            custom_sales_percent=None,
            discount_percent=Decimal("100.00"),
        )
        pct = get_effective_marketplace_sales_percent_for_seller(seller_user=self.seller)
        self.assertEqual(pct, Decimal("0.00"))

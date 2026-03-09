from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category
from payments.models import SellerFeeWaiver, SellerStripeAccount
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

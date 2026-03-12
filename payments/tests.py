from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from decimal import Decimal

from catalog.models import Category
from core.models import SiteConfig
from payments.models import SellerFeeInvoice, SellerFeePlan, SellerFeeWaiver, SellerStripeAccount
from orders.models import Order
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


class SellerFeeInvoiceFlowTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            username="seller_fee_invoice",
            email="seller_fee_invoice@example.com",
            password="pw123456",
        )
        prof = self.seller.profile
        prof.is_seller = True
        prof.email_verified = True
        prof.save(update_fields=["is_seller", "email_verified", "updated_at"])
        self.client.force_login(self.seller)

        self.order = Order.objects.create(
            buyer=None,
            guest_email="buyer@example.com",
            status=Order.Status.PAID,
            payment_method=Order.PaymentMethod.VENMO,
        )

    def test_fees_dashboard_shows_open_invoices(self):
        SellerFeeInvoice.objects.create(
            seller=self.seller,
            order=self.order,
            amount_cents=425,
            status=SellerFeeInvoice.Status.OPEN,
            payment_method_snapshot=Order.PaymentMethod.VENMO,
        )
        resp = self.client.get(reverse("payments:fees_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Marketplace Fees Due")
        self.assertEqual(resp.context["open_total_cents"], 425)

    def test_fees_pay_now_creates_checkout_and_tags_open_invoices(self):
        inv = SellerFeeInvoice.objects.create(
            seller=self.seller,
            order=self.order,
            amount_cents=500,
            status=SellerFeeInvoice.Status.OPEN,
            payment_method_snapshot=Order.PaymentMethod.PAYPAL,
        )

        fake_session = SimpleNamespace(id="cs_fee_123", url="https://checkout.stripe.test/fees")
        fake_stripe = SimpleNamespace(
            checkout=SimpleNamespace(
                Session=SimpleNamespace(create=lambda **kwargs: fake_session)
            )
        )
        with patch("payments.views._stripe", return_value=fake_stripe):
            resp = self.client.post(reverse("payments:fees_pay_now"))

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "https://checkout.stripe.test/fees")
        inv.refresh_from_db()
        self.assertEqual(inv.stripe_session_id, "cs_fee_123")

    def test_fees_success_marks_invoices_paid(self):
        inv = SellerFeeInvoice.objects.create(
            seller=self.seller,
            order=self.order,
            amount_cents=500,
            status=SellerFeeInvoice.Status.OPEN,
            payment_method_snapshot=Order.PaymentMethod.PAYPAL,
            stripe_session_id="cs_fee_200",
        )
        fake_stripe = SimpleNamespace(
            checkout=SimpleNamespace(
                Session=SimpleNamespace(retrieve=lambda _sid: SimpleNamespace(payment_status="paid", payment_intent="pi_fee_200"))
            )
        )
        with patch("payments.views._stripe", return_value=fake_stripe):
            resp = self.client.get(reverse("payments:fees_success") + "?session_id=cs_fee_200")

        self.assertEqual(resp.status_code, 302)
        inv.refresh_from_db()
        self.assertEqual(inv.status, SellerFeeInvoice.Status.PAID)
        self.assertEqual(inv.stripe_payment_intent_id, "pi_fee_200")

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

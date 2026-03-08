from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile
from catalog.models import Category
from orders.models import Order, OrderItem
from orders.stripe_service import create_checkout_session_for_order
from orders.views import _order_seller_groups
from payments.models import SellerStripeAccount
from products.models import Product


User = get_user_model()


class CheckoutFlowTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(username="buyer", email="buyer@example.com", password="pw123456")
        self.seller1 = User.objects.create_user(username="seller1", email="s1@example.com", password="pw123456")
        self.seller2 = User.objects.create_user(username="seller2", email="s2@example.com", password="pw123456")

        p1, _ = Profile.objects.get_or_create(user=self.seller1)
        p1.shop_name = "Acme Studio"
        p1.is_seller = True
        p1.save(update_fields=["shop_name", "is_seller", "updated_at"])

        p2, _ = Profile.objects.get_or_create(user=self.seller2)
        p2.shop_name = ""
        p2.is_seller = True
        p2.save(update_fields=["shop_name", "is_seller", "updated_at"])

        SellerStripeAccount.objects.create(
            user=self.seller1,
            stripe_account_id="acct_seller1",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
        )
        SellerStripeAccount.objects.create(
            user=self.seller2,
            stripe_account_id="acct_seller2",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
        )

        self.category = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Goods",
            slug="goods",
            is_active=True,
        )

        self.prod1 = Product.objects.create(
            seller=self.seller1,
            kind=Product.Kind.GOOD,
            title="Handmade Candle",
            category=self.category,
            price=Decimal("15.00"),
            is_active=True,
            stock_qty=20,
            fulfillment_pickup_enabled=True,
        )
        self.prod2 = Product.objects.create(
            seller=self.seller2,
            kind=Product.Kind.GOOD,
            title="Soap Bar",
            category=self.category,
            price=Decimal("5.00"),
            is_active=True,
            stock_qty=20,
            fulfillment_pickup_enabled=True,
        )

    def _create_pending_order(self, *, buyer=True, guest_email="guest@example.com"):
        order = Order.objects.create(
            buyer=self.buyer if buyer else None,
            guest_email="" if buyer else guest_email,
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.STRIPE,
        )
        OrderItem.objects.create(
            order=order,
            product=self.prod1,
            seller=self.seller1,
            title_snapshot=self.prod1.title,
            unit_price_cents_snapshot=1500,
            quantity=2,
            line_total_cents=3000,
            seller_net_cents=3000,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="pickup",
        )
        OrderItem.objects.create(
            order=order,
            product=self.prod2,
            seller=self.seller2,
            title_snapshot=self.prod2.title,
            unit_price_cents_snapshot=500,
            quantity=1,
            line_total_cents=500,
            seller_net_cents=500,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="pickup",
        )
        order.recompute_totals()
        order.save(update_fields=["subtotal_cents", "tax_cents", "shipping_cents", "total_cents", "kind", "updated_at"])
        return order

    def test_order_detail_groups_by_seller_and_uses_company_fallback(self):
        order = self._create_pending_order()
        groups = _order_seller_groups(order)

        self.assertEqual(len(groups), 2)
        by_seller = {g["seller_id"]: g for g in groups}
        self.assertEqual(by_seller[self.seller1.id]["company_name"], "Acme Studio")
        self.assertEqual(by_seller[self.seller2.id]["company_name"], "seller2")
        self.assertEqual(sum(it.quantity for it in by_seller[self.seller1.id]["items"]), 2)
        self.assertEqual(by_seller[self.seller1.id]["subtotal_cents"], 3000)
        self.assertEqual(by_seller[self.seller2.id]["subtotal_cents"], 500)

    def test_update_tips_changes_order_total_per_seller(self):
        order = self._create_pending_order()
        self.client.force_login(self.buyer)

        resp = self.client.post(
            reverse("orders:update_tips", kwargs={"order_id": order.pk}),
            data={
                f"tip_seller_{self.seller1.id}": "4.25",
                f"tip_seller_{self.seller2.id}": "1.00",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(str(order.pk), resp.get("Location", ""))

        order.refresh_from_db()
        tip_lines = list(order.items.filter(is_tip=True).order_by("seller_id"))
        self.assertEqual(order.items.filter(is_tip=True).count(), 2, resp.get("Location", ""))
        self.assertEqual(len(tip_lines), 2)
        self.assertEqual(tip_lines[0].line_total_cents, 425)
        self.assertEqual(tip_lines[1].line_total_cents, 100)
        self.assertEqual(order.total_cents, 3000 + 500 + 425 + 100)

    def test_guest_update_tips_non_pending_redirect_preserves_token(self):
        order = self._create_pending_order(buyer=False)
        order.status = Order.Status.AWAITING_PAYMENT
        order.save(update_fields=["status", "updated_at"])

        resp = self.client.post(
            reverse("orders:update_tips", kwargs={"order_id": order.pk}),
            data={
                "t": str(order.order_token),
                f"tip_seller_{self.seller1.id}": "2.00",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"?t={order.order_token}", resp["Location"])

    @override_settings(RECAPTCHA_ENABLED=False)
    def test_checkout_session_uses_item_quantity_and_tip_lines(self):
        order = self._create_pending_order()
        OrderItem.objects.create(
            order=order,
            product=self.prod1,
            seller=self.seller1,
            title_snapshot="Tip",
            unit_price_cents_snapshot=250,
            quantity=1,
            line_total_cents=250,
            seller_net_cents=250,
            is_service=False,
            is_tip=True,
            fulfillment_mode_snapshot="tip",
        )
        order.recompute_totals()
        order.save(update_fields=["subtotal_cents", "tax_cents", "shipping_cents", "total_cents", "kind", "updated_at"])

        captured: dict = {}

        class _SessionApi:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.test/session")

        fake_stripe = SimpleNamespace(checkout=SimpleNamespace(Session=_SessionApi))

        with patch("orders.stripe_service._stripe", return_value=fake_stripe):
            session = create_checkout_session_for_order(
                order=order,
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )

        self.assertEqual(session.id, "cs_test_123")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.AWAITING_PAYMENT)
        self.assertEqual(order.stripe_session_id, "cs_test_123")

        by_name = {}
        for li in captured["line_items"]:
            name = li["price_data"]["product_data"]["name"]
            by_name[name] = li["quantity"]

        self.assertEqual(by_name["Handmade Candle"], 2)
        self.assertEqual(by_name["Soap Bar"], 1)
        self.assertEqual(by_name["Tip"], 1)

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from requests import HTTPError

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile
from catalog.models import Category
from core.config import get_site_config
from orders.models import Order, OrderEvent, OrderItem, StripeWebhookEvent
from payments.models import SellerFeeInvoice
from orders.stripe_service import create_checkout_session_for_order, create_transfers_for_paid_order
from orders.paypal_service import capture_paypal_order, create_paypal_order_for_checkout
from orders.webhooks import process_stripe_event_dict
from orders.views import _order_seller_groups
from payments.models import SellerPayPalAccount, SellerStripeAccount
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
        order.platform_fee_cents_snapshot = 199
        order.save(update_fields=["platform_fee_cents_snapshot", "updated_at"])
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
        self.assertEqual(by_name["Marketplace service fee"], 1)

    def test_create_order_from_cart_snapshots_platform_fee_and_includes_in_total(self):
        from orders.services import create_order_from_cart

        cfg = get_site_config(use_cache=False)
        cfg.platform_fee_cents = 250
        cfg.save(update_fields=["platform_fee_cents", "updated_at"])

        line = SimpleNamespace(product=self.prod1, quantity=2, unit_price=Decimal("15.00"), tip_amount=Decimal("0.00"))
        order = create_order_from_cart(cart_items=[line], buyer=self.buyer, guest_email="")

        self.assertEqual(order.platform_fee_cents_snapshot, 250)
        self.assertEqual(order.subtotal_cents, 3000)
        self.assertEqual(order.total_cents, 3250)

    @override_settings(RECAPTCHA_ENABLED=False)
    def test_offplatform_method_requires_all_sellers_support(self):
        order = self._create_pending_order()
        self.client.force_login(self.buyer)

        p1 = self.seller1.profile
        p2 = self.seller2.profile
        p1.venmo_handle = "sellerone"
        p2.venmo_handle = ""
        p1.save(update_fields=["venmo_handle", "updated_at"])
        p2.save(update_fields=["venmo_handle", "updated_at"])

        resp = self.client.post(
            reverse("orders:checkout_start", kwargs={"order_id": order.pk}),
            data={"payment_method": "venmo"},
            follow=True,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertContains(resp, "Not all sellers in this order accept Venmo")

    def test_order_detail_exposes_offplatform_support_flags(self):
        order = self._create_pending_order()
        self.client.force_login(self.buyer)

        p1 = self.seller1.profile
        p2 = self.seller2.profile
        p1.paypal_me_url = "https://paypal.me/seller1"
        p2.paypal_me_url = "https://paypal.me/seller2"
        p1.zelle_contact = "seller1@example.com"
        p2.zelle_contact = ""
        p1.save(update_fields=["paypal_me_url", "zelle_contact", "updated_at"])
        p2.save(update_fields=["paypal_me_url", "zelle_contact", "updated_at"])

        resp = self.client.get(reverse("orders:detail", kwargs={"order_id": order.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_paypal"])
        self.assertTrue(resp.context["any_paypal"])
        self.assertFalse(resp.context["can_zelle"])

    def test_awaiting_payment_builds_paypal_me_link_with_amount(self):
        order = self._create_pending_order()
        order.status = Order.Status.AWAITING_PAYMENT
        order.payment_method = Order.PaymentMethod.PAYPAL
        order.save(update_fields=["status", "payment_method", "updated_at"])
        self.client.force_login(self.buyer)

        p1 = self.seller1.profile
        p2 = self.seller2.profile
        p1.paypal_me_url = "paypal.me/seller1"
        p2.paypal_me_url = "paypal.me/seller2"
        p1.save(update_fields=["paypal_me_url", "updated_at"])
        p2.save(update_fields=["paypal_me_url", "updated_at"])

        resp = self.client.get(reverse("orders:detail", kwargs={"order_id": order.pk}))
        self.assertEqual(resp.status_code, 200)
        link_map = resp.context["offline_link_by_seller"]
        self.assertIn("/30.00", link_map[self.seller1.id])
        self.assertIn("/5.00", link_map[self.seller2.id])

    def test_seller_confirm_offplatform_logs_manual_fee_due_warning(self):
        order = self._create_pending_order()
        order.status = Order.Status.AWAITING_PAYMENT
        order.payment_method = Order.PaymentMethod.VENMO
        order.platform_fee_cents_snapshot = 150
        order.save(update_fields=["status", "payment_method", "platform_fee_cents_snapshot", "updated_at"])

        self.client.force_login(self.seller1)
        resp = self.client.post(reverse("orders:seller_confirm_payment", kwargs={"order_id": order.pk}))
        self.assertEqual(resp.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertTrue(
            OrderEvent.objects.filter(
                order=order,
                type=OrderEvent.Type.WARNING,
                message__icontains="manual collection",
            ).exists()
        )
        self.assertTrue(
            SellerFeeInvoice.objects.filter(order=order, seller=self.seller1, status=SellerFeeInvoice.Status.OPEN).exists()
        )

    @override_settings(RECAPTCHA_ENABLED=False, PAYPAL_CLIENT_ID="test-paypal-id", PAYPAL_CLIENT_SECRET="test-paypal-secret")
    def test_paypal_native_checkout_redirects_to_paypal_approval(self):
        order = self._create_pending_order()
        self.client.force_login(self.buyer)
        SellerPayPalAccount.objects.create(
            user=self.seller1,
            paypal_merchant_id="M_S1",
            payments_receivable=True,
            primary_email_confirmed=True,
        )
        SellerPayPalAccount.objects.create(
            user=self.seller2,
            paypal_merchant_id="M_S2",
            payments_receivable=True,
            primary_email_confirmed=True,
        )

        with patch("orders.views.create_paypal_order_for_checkout", return_value="https://www.paypal.com/checkoutnow?token=abc123"):
            resp = self.client.post(
                reverse("orders:checkout_start", kwargs={"order_id": order.pk}),
                data={"payment_method": "paypal"},
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "https://www.paypal.com/checkoutnow?token=abc123")

    @override_settings(RECAPTCHA_ENABLED=False, PAYPAL_CLIENT_ID="test-paypal-id", PAYPAL_CLIENT_SECRET="test-paypal-secret")
    def test_paypal_checkout_blocks_when_seller_not_paypal_connected(self):
        order = self._create_pending_order()
        self.client.force_login(self.buyer)
        SellerPayPalAccount.objects.create(
            user=self.seller1,
            paypal_merchant_id="M_S1",
            payments_receivable=True,
            primary_email_confirmed=True,
        )
        resp = self.client.post(
            reverse("orders:checkout_start", kwargs={"order_id": order.pk}),
            data={"payment_method": "paypal"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "haven't completed PayPal onboarding")

    @override_settings(PAYPAL_CLIENT_ID="test-paypal-id", PAYPAL_CLIENT_SECRET="test-paypal-secret")
    def test_paypal_return_captures_and_marks_paid(self):
        order = self._create_pending_order()
        order.status = Order.Status.AWAITING_PAYMENT
        order.payment_method = Order.PaymentMethod.PAYPAL
        order.paypal_order_id = "PAYPAL-ORDER-1"
        order.save(update_fields=["status", "payment_method", "paypal_order_id", "updated_at"])
        self.client.force_login(self.buyer)

        with patch("orders.views.capture_paypal_order", return_value=(True, "CAPTURE-1")):
            resp = self.client.get(
                reverse("orders:paypal_return", kwargs={"order_id": order.pk}),
                {"token": "PAYPAL-ORDER-1"},
            )

        self.assertEqual(resp.status_code, 302)

    def test_seller_payments_queue_page_loads_on_get(self):
        self.client.force_login(self.seller1)
        resp = self.client.get(reverse("orders:seller_payments_queue"))
        self.assertEqual(resp.status_code, 200)

    @override_settings(PAYPAL_CLIENT_ID="test-paypal-id", PAYPAL_CLIENT_SECRET="test-paypal-secret")
    def test_capture_paypal_order_handles_already_captured_race(self):
        order = self._create_pending_order()
        order.payment_method = Order.PaymentMethod.PAYPAL
        order.paypal_order_id = "PAYPAL-ORDER-1"
        order.save(update_fields=["payment_method", "paypal_order_id", "updated_at"])

        with patch(
            "orders.paypal_service._paypal_request",
            side_effect=[
                HTTPError("capture already processed"),
                {
                    "status": "COMPLETED",
                    "purchase_units": [
                        {"payments": {"captures": [{"id": "CAPTURE-ALREADY-1"}]}},
                    ],
                },
            ],
        ):
            ok, info = capture_paypal_order(order=order, paypal_order_id="PAYPAL-ORDER-1")

        self.assertTrue(ok)
        self.assertEqual(info, "CAPTURE-ALREADY-1")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.paypal_capture_id, "CAPTURE-ALREADY-1")

    def test_paypal_webhook_updates_capture_id_even_if_order_already_paid(self):
        order = self._create_pending_order()
        order.status = Order.Status.PAID
        order.payment_method = Order.PaymentMethod.PAYPAL
        order.paypal_order_id = "PAYPAL-ORDER-1"
        order.save(update_fields=["status", "payment_method", "paypal_order_id", "updated_at"])

        payload = {
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": "CAPTURE-WEBHOOK-1",
                "supplementary_data": {
                    "related_ids": {"order_id": "PAYPAL-ORDER-1"},
                },
            },
        }
        resp = self.client.post(
            reverse("orders:paypal_webhook"),
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.paypal_capture_id, "CAPTURE-WEBHOOK-1")

    @override_settings(PAYPAL_CLIENT_ID="test-paypal-id", PAYPAL_CLIENT_SECRET="test-paypal-secret")
    def test_create_paypal_order_builds_per_seller_purchase_units(self):
        order = self._create_pending_order()
        order.platform_fee_cents_snapshot = 125
        order.recompute_totals()
        order.save(update_fields=["platform_fee_cents_snapshot", "subtotal_cents", "tax_cents", "shipping_cents", "total_cents", "kind", "updated_at"])
        self.client.force_login(self.buyer)
        SellerPayPalAccount.objects.create(
            user=self.seller1,
            paypal_merchant_id="M_S1",
            payments_receivable=True,
            primary_email_confirmed=True,
        )
        SellerPayPalAccount.objects.create(
            user=self.seller2,
            paypal_merchant_id="M_S2",
            payments_receivable=True,
            primary_email_confirmed=True,
        )
        request = self.client.request().wsgi_request

        captured_payload: dict = {}
        fake_response = {
            "id": "PO-123",
            "links": [{"rel": "approve", "href": "https://www.paypal.com/checkoutnow?token=PO-123"}],
        }

        def _fake_paypal_request(*, method, path, json_payload=None, headers=None):
            if method == "POST" and path == "/v2/checkout/orders":
                captured_payload.update(json_payload or {})
                return fake_response
            return {}

        with patch("orders.paypal_service._paypal_request", side_effect=_fake_paypal_request):
            approve_url = create_paypal_order_for_checkout(request=request, order=order)

        self.assertEqual(approve_url, "https://www.paypal.com/checkoutnow?token=PO-123")
        units = captured_payload.get("purchase_units") or []
        self.assertEqual(len(units), 2)
        self.assertEqual(sum(int(Decimal(u["amount"]["value"]) * 100) for u in units), int(order.total_cents))
        self.assertTrue(all("payee" in u and u["payee"].get("merchant_id") for u in units))


class WebhookIdempotencyTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(username="wh_buyer", email="wh_buyer@example.com", password="pw123456")
        self.seller = User.objects.create_user(username="wh_seller", email="wh_seller@example.com", password="pw123456")

        p, _ = Profile.objects.get_or_create(user=self.seller)
        p.is_seller = True
        p.email_verified = True
        p.save(update_fields=["is_seller", "email_verified", "updated_at"])

        SellerStripeAccount.objects.create(
            user=self.seller,
            stripe_account_id="acct_wh_seller",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
        )

        cat = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Webhook Goods",
            slug="webhook-goods",
            is_active=True,
        )
        product = Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Webhook Item",
            category=cat,
            price=Decimal("10.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_pickup_enabled=True,
        )

        self.order = Order.objects.create(
            buyer=self.buyer,
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.STRIPE,
            subtotal_cents=1000,
            total_cents=1000,
        )
        OrderItem.objects.create(
            order=self.order,
            product=product,
            seller=self.seller,
            title_snapshot=product.title,
            unit_price_cents_snapshot=1000,
            quantity=1,
            line_total_cents=1000,
            marketplace_fee_cents=0,
            seller_net_cents=1000,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="pickup",
        )

    def test_duplicate_checkout_completed_reprocess_creates_single_transfer(self):
        webhook_event = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_dup_1",
            event_type="checkout.session.completed",
            livemode=False,
            status="received",
            raw_json={},
        )
        event_payload = {
            "id": "evt_dup_1",
            "type": "checkout.session.completed",
            "livemode": False,
            "data": {
                "object": {
                    "id": "cs_dup_1",
                    "payment_intent": "pi_dup_1",
                    "metadata": {"order_id": str(self.order.pk)},
                }
            },
        }

        fake_transfer = SimpleNamespace(id="tr_dup_1")
        fake_stripe = SimpleNamespace(Transfer=SimpleNamespace(create=lambda **kwargs: fake_transfer))
        with patch("orders.stripe_service._stripe", return_value=fake_stripe):
            process_stripe_event_dict(event=event_payload, webhook_event=webhook_event, source="replay")
            process_stripe_event_dict(event=event_payload, webhook_event=webhook_event, source="replay")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(
            OrderEvent.objects.filter(order=self.order, type=OrderEvent.Type.TRANSFER_CREATED).count(),
            1,
        )

    def test_transfer_creation_uses_latest_charge_as_source_transaction(self):
        self.order.status = Order.Status.PAID
        self.order.stripe_payment_intent_id = "pi_src_1"
        self.order.save(update_fields=["status", "stripe_payment_intent_id", "updated_at"])

        captured: dict = {}

        class _TransferApi:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return SimpleNamespace(id="tr_src_1")

        class _PaymentIntentApi:
            @staticmethod
            def retrieve(_pi, expand=None):
                return {"id": "pi_src_1", "latest_charge": "ch_src_1"}

        fake_stripe = SimpleNamespace(Transfer=_TransferApi, PaymentIntent=_PaymentIntentApi)

        with patch("orders.stripe_service._stripe", return_value=fake_stripe):
            create_transfers_for_paid_order(order=self.order)

        self.assertEqual(captured.get("source_transaction"), "ch_src_1")

    def test_transfer_creation_logs_warning_when_seller_not_ready(self):
        # Remove seller Stripe account so payout is skipped after payment.
        SellerStripeAccount.objects.filter(user=self.seller).delete()
        self.order.status = Order.Status.PAID
        self.order.stripe_payment_intent_id = "pi_skip_1"
        self.order.save(update_fields=["status", "stripe_payment_intent_id", "updated_at"])

        fake_stripe = SimpleNamespace(Transfer=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(id="unused")))
        with patch("orders.stripe_service._stripe", return_value=fake_stripe):
            create_transfers_for_paid_order(order=self.order)

        self.assertTrue(
            OrderEvent.objects.filter(
                Q(order=self.order)
                & Q(type=OrderEvent.Type.WARNING)
                & Q(message__icontains="transfer skipped")
                & Q(message__icontains="not ready")
            ).exists()
        )

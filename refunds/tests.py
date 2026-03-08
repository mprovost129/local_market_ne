from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Profile
from catalog.models import Category
from orders.models import Order, OrderEvent, OrderItem
from products.models import Product
from refunds.models import RefundRequest
from refunds.services import create_refund_request, seller_decide, trigger_refund

User = get_user_model()


class RefundMoneyFlowTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(username="refund_buyer", email="refund_buyer@example.com", password="pw123456")
        self.seller = User.objects.create_user(username="refund_seller", email="refund_seller@example.com", password="pw123456")

        sprof, _ = Profile.objects.get_or_create(user=self.seller)
        sprof.is_seller = True
        sprof.email_verified = True
        sprof.save(update_fields=["is_seller", "email_verified", "updated_at"])

        cat = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Refund Goods",
            slug="refund-goods",
            is_active=True,
        )
        self.product = Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Refundable Item",
            category=cat,
            price=Decimal("20.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_shipping_enabled=True,
            shipping_fee_cents=400,
        )

        self.order = Order.objects.create(
            buyer=self.buyer,
            status=Order.Status.PAID,
            paid_at=timezone.now(),
            payment_method=Order.PaymentMethod.STRIPE,
            stripe_session_id="cs_ref_1",
            stripe_payment_intent_id="pi_ref_1",
            subtotal_cents=2000,
            shipping_cents=400,
            tax_cents=100,
            total_cents=2500,
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            seller=self.seller,
            title_snapshot=self.product.title,
            unit_price_cents_snapshot=2000,
            quantity=1,
            line_total_cents=2000,
            tax_cents=100,
            shipping_fee_cents_snapshot=400,
            marketplace_fee_cents=200,
            seller_net_cents=1800,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="shipping",
        )
        OrderEvent.objects.create(
            order=self.order,
            type=OrderEvent.Type.TRANSFER_CREATED,
            message="tr_ref_1",
            meta={
                "seller_id": int(self.seller.id),
                "transfer_id": "tr_ref_1",
                "amount_cents": 1800,
            },
        )

    def test_refund_flow_processes_refund_and_transfer_reversal(self):
        rr = create_refund_request(
            order=self.order,
            item=self.item,
            requester_user=self.buyer,
            requester_email=self.buyer.email,
            reason=RefundRequest.Reason.DAMAGED,
            notes="Package arrived crushed",
        )
        self.assertEqual(rr.status, RefundRequest.Status.REQUESTED)

        rr = seller_decide(rr=rr, actor_user=self.seller, approve=True, note="Approved")
        self.assertEqual(rr.status, RefundRequest.Status.APPROVED)

        with patch("refunds.services.create_stripe_refund_for_request", return_value="re_123"), patch(
            "refunds.stripe_service.create_stripe_transfer_reversal_for_request",
            return_value="trr_123",
        ):
            rr = trigger_refund(rr=rr, actor_user=self.seller, request_id="req_1")

        rr.refresh_from_db()
        self.assertEqual(rr.status, RefundRequest.Status.REFUNDED)
        self.assertEqual(rr.stripe_refund_id, "re_123")
        self.assertEqual(rr.transfer_reversal_id, "trr_123")
        self.assertEqual(rr.transfer_reversal_amount_cents, 1800)
        self.assertTrue(
            OrderEvent.objects.filter(order=self.order, type=OrderEvent.Type.TRANSFER_REVERSED).exists()
        )

    def test_create_refund_request_blocks_non_shipping_item(self):
        self.item.fulfillment_mode_snapshot = "pickup"
        self.item.save(update_fields=["fulfillment_mode_snapshot"])

        with self.assertRaisesMessage(ValidationError, "physical items"):
            create_refund_request(
                order=self.order,
                item=self.item,
                requester_user=self.buyer,
                requester_email=self.buyer.email,
                reason=RefundRequest.Reason.OTHER,
            )

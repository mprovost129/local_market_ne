from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
import os

from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category
from core.admin_filters import SellerCompanyFilter as CoreSellerCompanyFilter, UserCompanyFilter
from notifications.admin import EmailAttemptUserCompanyFilter, NotificationUserCompanyFilter
from notifications.models import EmailDeliveryAttempt, Notification
from orders.admin import OrderAdmin
from orders.models import Order, OrderEvent, OrderItem, StripeWebhookEvent
from ops import views as ops_views
from payments.admin import SellerCompanyFilter as SellerBalanceCompanyFilter
from payments.models import SellerBalanceEntry, SellerStripeAccount
from products.models import Product
from products.admin import ProductAdmin
from qa.admin import QASellerCompanyFilter
from qa.models import ProductQuestionMessage, ProductQuestionReport, ProductQuestionThread
from appointments.models import AppointmentRequest
from appointments.admin import AppointmentRequestAdmin
from ops.models import AuditLog
from refunds.models import RefundRequest
from refunds.admin import RefundRequestAdmin


User = get_user_model()


class ReconciliationCommandTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            username="ops_seller",
            email="ops_seller@example.com",
            password="pw123456",
        )
        sprof = self.seller.profile
        sprof.is_seller = True
        sprof.email_verified = True
        sprof.save(update_fields=["is_seller", "email_verified", "updated_at"])

        self.buyer = User.objects.create_user(
            username="ops_buyer",
            email="ops_buyer@example.com",
            password="pw123456",
        )

        cat = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Ops Goods",
            slug="ops-goods",
            is_active=True,
        )
        self.product = Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Ops Product",
            category=cat,
            price=Decimal("12.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_pickup_enabled=True,
        )

    def _create_paid_order(self, *, valid: bool):
        order = Order.objects.create(
            buyer=self.buyer,
            status=Order.Status.PAID,
            payment_method=Order.PaymentMethod.STRIPE,
            paid_at=timezone.now(),
            stripe_session_id="cs_ok_1" if valid else "",
            stripe_payment_intent_id="pi_ok_1" if valid else "",
            subtotal_cents=1200 if valid else 999,  # mismatch when invalid
            shipping_cents=0,
            tax_cents=0,
            total_cents=1200 if valid else 999,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            seller=self.seller,
            title_snapshot=self.product.title,
            unit_price_cents_snapshot=1200,
            quantity=1,
            line_total_cents=1200,
            marketplace_fee_cents=0,
            seller_net_cents=1200,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="pickup",
        )
        if valid:
            OrderEvent.objects.create(
                order=order,
                type=OrderEvent.Type.TRANSFER_CREATED,
                message="tr_ok_1",
                meta={"seller_id": int(self.seller.id), "amount_cents": 1200},
            )
        return order

    def test_reconciliation_check_json_ok_with_clean_data(self):
        self._create_paid_order(valid=True)
        out = StringIO()
        call_command("reconciliation_check", days=30, limit=100, json=True, stdout=out)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mismatches_total"], 0)

    def test_reconciliation_check_json_detects_mismatch(self):
        self._create_paid_order(valid=False)
        out = StringIO()
        call_command("reconciliation_check", days=30, limit=100, json=True, stdout=out)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertGreaterEqual(payload["mismatches_total"], 1)
        self.assertGreaterEqual(payload["counts"]["totals_mismatch"], 1)

    def test_reconciliation_check_fail_on_mismatch_exits_nonzero(self):
        self._create_paid_order(valid=False)
        out = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command("reconciliation_check", days=30, limit=100, fail_on_mismatch=True, stdout=out)
        self.assertEqual(getattr(ctx.exception, "code", None), 2)

    def test_reconciliation_check_ignores_missing_stripe_fields_for_offplatform_paid(self):
        order = Order.objects.create(
            buyer=self.buyer,
            status=Order.Status.PAID,
            payment_method=Order.PaymentMethod.VENMO,
            paid_at=timezone.now(),
            stripe_session_id="",
            stripe_payment_intent_id="",
            subtotal_cents=1200,
            shipping_cents=0,
            tax_cents=0,
            total_cents=1200,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            seller=self.seller,
            title_snapshot=self.product.title,
            unit_price_cents_snapshot=1200,
            quantity=1,
            line_total_cents=1200,
            marketplace_fee_cents=0,
            seller_net_cents=1200,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="pickup",
        )
        out = StringIO()
        call_command("reconciliation_check", days=30, limit=100, status="paid", json=True, stdout=out)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["counts"]["paid_missing_stripe_ids"], 0)
        self.assertEqual(payload["counts"]["paid_missing_transfer_event"], 0)


class WebhookReplayCommandTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            username="replay_seller",
            email="replay_seller@example.com",
            password="pw123456",
        )
        sprof = self.seller.profile
        sprof.is_seller = True
        sprof.email_verified = True
        sprof.save(update_fields=["is_seller", "email_verified", "updated_at"])

        self.buyer = User.objects.create_user(
            username="replay_buyer",
            email="replay_buyer@example.com",
            password="pw123456",
        )

        cat = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Replay Goods",
            slug="replay-goods",
            is_active=True,
        )
        product = Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Replay Product",
            category=cat,
            price=Decimal("9.00"),
            is_active=True,
            stock_qty=5,
            fulfillment_pickup_enabled=True,
        )

        # Use off-platform payment method to avoid external Stripe transfer calls in tests.
        self.order = Order.objects.create(
            buyer=self.buyer,
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.VENMO,
            subtotal_cents=900,
            total_cents=900,
        )
        OrderItem.objects.create(
            order=self.order,
            product=product,
            seller=self.seller,
            title_snapshot=product.title,
            unit_price_cents_snapshot=900,
            quantity=1,
            line_total_cents=900,
            marketplace_fee_cents=0,
            seller_net_cents=900,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="pickup",
        )

    def test_webhook_replay_dry_run_does_not_mutate_order(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_replay_dry_1",
            event_type="checkout.session.completed",
            livemode=False,
            status="received",
            raw_json={
                "id": "evt_replay_dry_1",
                "type": "checkout.session.completed",
                "livemode": False,
                "data": {
                    "object": {
                        "id": "cs_replay_dry_1",
                        "payment_intent": "pi_replay_dry_1",
                        "metadata": {"order_id": str(self.order.pk)},
                    }
                },
            },
        )

        out = StringIO()
        call_command("replay_stripe_webhooks", days=7, limit=10, dry_run=True, json=True, stdout=out)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["replayed"], 1)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_webhook_replay_processes_checkout_completed(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_replay_live_1",
            event_type="checkout.session.completed",
            livemode=False,
            status="received",
            raw_json={
                "id": "evt_replay_live_1",
                "type": "checkout.session.completed",
                "livemode": False,
                "data": {
                    "object": {
                        "id": "cs_replay_live_1",
                        "payment_intent": "pi_replay_live_1",
                        "metadata": {"order_id": str(self.order.pk)},
                    }
                },
            },
        )

        out = StringIO()
        call_command(
            "replay_stripe_webhooks",
            days=7,
            limit=10,
            stripe_event_id="evt_replay_live_1",
            json=True,
            stdout=out,
        )
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["replayed"], 1)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)


class AlertSummaryCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alert_user",
            email="alert_user@example.com",
            password="pw123456",
        )
        prof = self.user.profile
        prof.email_verified = True
        prof.save(update_fields=["email_verified", "updated_at"])

    def test_alert_summary_ok_when_no_signals(self):
        out = StringIO()
        call_command("alert_summary", hours=24, reconciliation_days=7, json=True, stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")

    def test_alert_summary_critical_when_webhook_errors_present(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_alert_err_1",
            event_type="checkout.session.completed",
            livemode=False,
            status="error",
            raw_json={"id": "evt_alert_err_1", "type": "checkout.session.completed"},
        )
        out = StringIO()
        call_command("alert_summary", hours=24, reconciliation_days=7, json=True, stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "critical")
        self.assertIn("webhook_errors_recent", payload["critical_reasons"])

    def test_alert_summary_text_mode_runs_without_name_error(self):
        out = StringIO()
        call_command("alert_summary", hours=24, reconciliation_days=7, stdout=out)
        rendered = out.getvalue()
        self.assertIn("Alert summary", rendered)

    def test_alert_summary_warning_when_saved_search_scheduler_heartbeat_stale(self):
        env = {
            "SAVED_SEARCH_ALERTS_MONITOR_ENABLED": "1",
            "SAVED_SEARCH_ALERTS_ENABLED": "1",
            "SAVED_SEARCH_ALERTS_EXPECTED_INTERVAL_MINUTES": "15",
        }
        with patch.dict(os.environ, env, clear=False):
            cache.delete("ops:saved_search_alerts:last_run")
            out = StringIO()
            call_command("alert_summary", hours=24, reconciliation_days=7, json=True, stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "warning")
        self.assertIn("saved_search_scheduler_stale", payload["warning_reasons"])


class LaunchGateCommandTests(TestCase):
    def test_launch_gate_ok_when_all_checks_pass(self):
        def _fake_call_command(*args, **kwargs):
            name = args[0] if args else ""
            if name == "money_loop_check":
                kwargs["stdout"].write(json.dumps({"ok": True}))
            elif name == "reconciliation_check":
                kwargs["stdout"].write(json.dumps({"ok": True, "mismatches_total": 0}))

        with patch("ops.management.commands.launch_gate.call_command", side_effect=_fake_call_command), patch(
            "ops.management.commands.launch_gate.build_alert_summary",
            return_value={"status": "ok", "metrics": {}},
        ):
            out = StringIO()
            call_command("launch_gate", json=True, stdout=out)
            payload = json.loads(out.getvalue())

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["critical_count"], 0)

    def test_launch_gate_warning_fail_on_warning(self):
        def _fake_call_command(*args, **kwargs):
            name = args[0] if args else ""
            if name == "money_loop_check":
                kwargs["stdout"].write(json.dumps({"ok": True}))
            elif name == "reconciliation_check":
                kwargs["stdout"].write(json.dumps({"ok": True, "mismatches_total": 0}))

        with patch("ops.management.commands.launch_gate.call_command", side_effect=_fake_call_command), patch(
            "ops.management.commands.launch_gate.build_alert_summary",
            return_value={"status": "warning", "metrics": {}, "warning_reasons": ["x"]},
        ):
            out = StringIO()
            with self.assertRaises(SystemExit) as ctx:
                call_command("launch_gate", json=True, fail_on_warning=True, stdout=out)
            self.assertEqual(getattr(ctx.exception, "code", None), 2)

    def test_launch_gate_critical_when_smoke_fails(self):
        def _fake_call_command(*args, **kwargs):
            name = args[0] if args else ""
            if name == "smoke_check":
                raise SystemExit(2)
            if name == "money_loop_check":
                kwargs["stdout"].write(json.dumps({"ok": True}))
            elif name == "reconciliation_check":
                kwargs["stdout"].write(json.dumps({"ok": True, "mismatches_total": 0}))

        with patch("ops.management.commands.launch_gate.call_command", side_effect=_fake_call_command), patch(
            "ops.management.commands.launch_gate.build_alert_summary",
            return_value={"status": "ok", "metrics": {}},
        ):
            out = StringIO()
            with self.assertRaises(SystemExit) as ctx:
                call_command("launch_gate", json=True, stdout=out)
            self.assertEqual(getattr(ctx.exception, "code", None), 2)


class AlertsSummaryViewTests(TestCase):
    def setUp(self):
        self.ops_user = User.objects.create_user(
            username="ops_view_user",
            email="ops_view_user@example.com",
            password="pw123456",
        )
        ops_group, _ = Group.objects.get_or_create(name="ops")
        self.ops_user.groups.add(ops_group)

    def test_requires_ops_auth(self):
        resp = self.client.get(reverse("ops:alerts_summary"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp["Location"])

    def test_returns_json_for_ops_user(self):
        self.client.force_login(self.ops_user)
        resp = self.client.get(reverse("ops:alerts_summary"))
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("status", payload)
        self.assertIn("metrics", payload)


class WebhooksBulkReprocessViewTests(TestCase):
    def setUp(self):
        self.ops_user = User.objects.create_user(
            username="ops_bulk_user",
            email="ops_bulk_user@example.com",
            password="pw123456",
        )
        ops_group, _ = Group.objects.get_or_create(name="ops")
        self.ops_user.groups.add(ops_group)
        prof = self.ops_user.profile
        prof.is_owner = True
        prof.save(update_fields=["is_owner", "updated_at"])

    def test_requires_auth(self):
        resp = self.client.post(reverse("ops:webhooks_reprocess_filtered"), data={"status": "error"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp["Location"])

    def test_bulk_reprocess_updates_webhook_and_writes_audit(self):
        ev = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_bulk_1",
            event_type="customer.created",
            livemode=False,
            status="error",
            raw_json={
                "id": "evt_bulk_1",
                "type": "customer.created",
                "livemode": False,
                "data": {"object": {"id": "cus_123"}},
            },
        )

        self.client.force_login(self.ops_user)
        resp = self.client.post(
            reverse("ops:webhooks_reprocess_filtered"),
            data={
                "status": "error",
                "event_type": "customer.created",
                "session_id": "",
                "order_id": "",
                "days": "14",
                "limit": "10",
            },
        )
        self.assertEqual(resp.status_code, 302)

        ev.refresh_from_db()
        self.assertEqual(ev.status, "ignored")
        self.assertTrue(ev.deliveries.count() >= 1)

        self.assertTrue(
            AuditLog.objects.filter(verb="Bulk reprocessed Stripe webhooks").exists()
        )


class RunbookCommandsViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.ops_user = User.objects.create_user(
            username="ops_runbook_user",
            email="ops_runbook_user@example.com",
            password="pw123456",
        )
        ops_group, _ = Group.objects.get_or_create(name="ops")
        self.ops_user.groups.add(ops_group)

    def test_reconciliation_check_route_runs_command_and_audits(self):
        self.client.force_login(self.ops_user)

        def _fake_call_command(*args, **kwargs):
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write(json.dumps({"ok": True, "inspected_orders": 5, "mismatches_total": 0}))

        with patch("ops.views.call_command", side_effect=_fake_call_command) as mocked:
            resp = self.client.post(
                reverse("ops:runbook_run_reconciliation_check"),
                data={"reconciliation_days": "14", "reconciliation_limit": "200"},
            )

        self.assertEqual(resp.status_code, 302)
        mocked.assert_called_once()
        self.assertTrue(
            AuditLog.objects.filter(
                verb="Run reconciliation_check",
                action="other",
            ).exists()
        )

    def test_alert_summary_route_runs_command_and_audits(self):
        self.client.force_login(self.ops_user)

        def _fake_call_command(*args, **kwargs):
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write(json.dumps({"status": "warning", "metrics": {}, "critical_reasons": [], "warning_reasons": ["x"]}))

        with patch("ops.views.call_command", side_effect=_fake_call_command) as mocked:
            resp = self.client.post(
                reverse("ops:runbook_run_alert_summary"),
                data={"alert_hours": "12", "alert_reconciliation_days": "3"},
            )

        self.assertEqual(resp.status_code, 302)
        mocked.assert_called_once()
        self.assertTrue(
            AuditLog.objects.filter(
                verb="Run alert_summary",
                action="other",
            ).exists()
        )

    def test_launch_gate_route_runs_command_and_audits(self):
        self.client.force_login(self.ops_user)

        def _fake_call_command(*args, **kwargs):
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write(
                    json.dumps(
                        {"status": "warning", "critical_count": 0, "warning_count": 1, "results": []}
                    )
                )

        with patch("ops.views.call_command", side_effect=_fake_call_command) as mocked:
            resp = self.client.post(
                reverse("ops:runbook_run_launch_gate"),
                data={
                    "money_loop_limit": "100",
                    "reconciliation_days": "14",
                    "reconciliation_limit": "300",
                    "alert_hours": "12",
                    "alert_reconciliation_days": "3",
                    "fail_on_warning": "1",
                },
            )

        self.assertEqual(resp.status_code, 302)
        mocked.assert_called_once()
        self.assertTrue(
            AuditLog.objects.filter(
                verb="Run launch_gate",
                action="other",
            ).exists()
        )

    def test_runbook_page_shows_last_run_results(self):
        AuditLog.objects.create(
            actor=self.ops_user,
            action="other",
            verb="Run reconciliation_check",
            reason="days=7 limit=100",
            after_json={"ok": True, "result": {"inspected_orders": 12, "mismatches_total": 0}},
        )
        AuditLog.objects.create(
            actor=self.ops_user,
            action="other",
            verb="Run alert_summary",
            reason="hours=24 reconciliation_days=7",
            after_json={"ok": False, "result": {"status": "warning"}},
        )

        request = self.factory.get(reverse("ops:runbook"))
        request.user = self.ops_user

        with patch("ops.views.render", return_value=HttpResponse("ok")) as mocked_render:
            resp = ops_views.runbook(request)

        self.assertEqual(resp.status_code, 200)
        _, _, ctx = mocked_render.call_args.args
        rows = ctx["runbook_last_runs"]
        by_command = {row["command"]: row for row in rows}

        self.assertIn("reconciliation_check", by_command)
        self.assertIn("alert_summary", by_command)
        self.assertIn("launch_gate", by_command)
        self.assertEqual(by_command["reconciliation_check"]["summary"], "inspected=12 mismatches=0")
        self.assertEqual(by_command["alert_summary"]["summary"], "status=warning")
        self.assertEqual(
            by_command["launch_gate"]["rerun_params_text"],
            "money_loop_limit=200 reconciliation_days=30 reconciliation_limit=500 alert_hours=24 alert_reconciliation_days=7 fail_on_warning=0",
        )
        self.assertEqual(
            by_command["reconciliation_check"]["rerun_params"],
            {"reconciliation_days": 7, "reconciliation_limit": 100},
        )
        self.assertEqual(
            by_command["reconciliation_check"]["rerun_params_text"],
            "reconciliation_days=7 reconciliation_limit=100",
        )
        self.assertEqual(
            by_command["alert_summary"]["rerun_params"],
            {"alert_hours": 24, "alert_reconciliation_days": 7},
        )
        self.assertEqual(
            by_command["alert_summary"]["rerun_params_text"],
            "alert_hours=24 alert_reconciliation_days=7",
        )


class CompanyScopeViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        self.ops_user = User.objects.create_user(
            username="ops_company_user",
            email="ops_company_user@example.com",
            password="pw123456",
        )
        ops_group, _ = Group.objects.get_or_create(name="ops")
        self.ops_user.groups.add(ops_group)

        self.buyer = User.objects.create_user(
            username="company_buyer",
            email="company_buyer@example.com",
            password="pw123456",
        )
        self.seller_a = User.objects.create_user(
            username="seller_alpha",
            email="seller_alpha@example.com",
            password="pw123456",
        )
        self.seller_b = User.objects.create_user(
            username="seller_beta",
            email="seller_beta@example.com",
            password="pw123456",
        )
        self.seller_a.profile.is_seller = True
        self.seller_a.profile.shop_name = "Alpha Studio"
        self.seller_a.profile.save(update_fields=["is_seller", "shop_name", "updated_at"])
        self.seller_b.profile.is_seller = True
        self.seller_b.profile.shop_name = "Beta Workshop"
        self.seller_b.profile.save(update_fields=["is_seller", "shop_name", "updated_at"])

        cat = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Company Goods",
            slug="company-goods",
            is_active=True,
        )
        prod_a = Product.objects.create(
            seller=self.seller_a,
            kind=Product.Kind.GOOD,
            title="Alpha Item",
            category=cat,
            price=Decimal("10.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_shipping_enabled=True,
        )
        prod_b = Product.objects.create(
            seller=self.seller_b,
            kind=Product.Kind.GOOD,
            title="Beta Item",
            category=cat,
            price=Decimal("11.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_shipping_enabled=True,
        )

        self.order_a = Order.objects.create(
            buyer=self.buyer,
            status=Order.Status.PAID,
            payment_method=Order.PaymentMethod.STRIPE,
            paid_at=timezone.now(),
            subtotal_cents=1000,
            total_cents=1000,
        )
        self.item_a = OrderItem.objects.create(
            order=self.order_a,
            product=prod_a,
            seller=self.seller_a,
            title_snapshot=prod_a.title,
            unit_price_cents_snapshot=1000,
            quantity=1,
            line_total_cents=1000,
            seller_net_cents=1000,
            marketplace_fee_cents=0,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="shipping",
        )

        self.order_b = Order.objects.create(
            buyer=self.buyer,
            status=Order.Status.PAID,
            payment_method=Order.PaymentMethod.STRIPE,
            paid_at=timezone.now(),
            subtotal_cents=1100,
            total_cents=1100,
        )
        self.item_b = OrderItem.objects.create(
            order=self.order_b,
            product=prod_b,
            seller=self.seller_b,
            title_snapshot=prod_b.title,
            unit_price_cents_snapshot=1100,
            quantity=1,
            line_total_cents=1100,
            seller_net_cents=1100,
            marketplace_fee_cents=0,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="shipping",
        )

        self.rr_a = RefundRequest.objects.create(
            order=self.order_a,
            order_item=self.item_a,
            seller=self.seller_a,
            buyer=self.buyer,
            requester_email=self.buyer.email,
            reason=RefundRequest.Reason.DAMAGED,
            status=RefundRequest.Status.REQUESTED,
            line_subtotal_cents_snapshot=1000,
            tax_cents_allocated_snapshot=0,
            shipping_cents_allocated_snapshot=0,
            total_refund_cents_snapshot=1000,
        )
        self.rr_b = RefundRequest.objects.create(
            order=self.order_b,
            order_item=self.item_b,
            seller=self.seller_b,
            buyer=self.buyer,
            requester_email=self.buyer.email,
            reason=RefundRequest.Reason.DAMAGED,
            status=RefundRequest.Status.REQUESTED,
            line_subtotal_cents_snapshot=1100,
            tax_cents_allocated_snapshot=0,
            shipping_cents_allocated_snapshot=0,
            total_refund_cents_snapshot=1100,
        )

    def test_orders_list_company_filter_by_id(self):
        request = self.factory.get(reverse("ops:orders_list"), {"company": str(self.seller_a.id)})
        request.user = self.ops_user
        with patch("ops.views.render", return_value=HttpResponse("ok")) as mocked_render:
            resp = ops_views.orders_list(request)
        self.assertEqual(resp.status_code, 200)
        _, _, ctx = mocked_render.call_args.args
        got_ids = {str(o.id) for o in ctx["page_obj"].object_list}
        self.assertIn(str(self.order_a.id), got_ids)
        self.assertNotIn(str(self.order_b.id), got_ids)

    def test_refund_requests_queue_company_filter_by_name(self):
        request = self.factory.get(reverse("ops:refund_requests_queue"), {"company": "Alpha"})
        request.user = self.ops_user
        with patch("ops.views.render", return_value=HttpResponse("ok")) as mocked_render:
            resp = ops_views.refund_requests_queue(request)
        self.assertEqual(resp.status_code, 200)
        _, _, ctx = mocked_render.call_args.args
        got_ids = {str(rr.id) for rr in ctx["page_obj"].object_list}
        self.assertIn(str(self.rr_a.id), got_ids)
        self.assertNotIn(str(self.rr_b.id), got_ids)

    def test_reconciliation_list_company_filter(self):
        request = self.factory.get(reverse("ops:reconciliation_list"), {"company": str(self.seller_b.id)})
        request.user = self.ops_user
        with patch("ops.views.render", return_value=HttpResponse("ok")) as mocked_render:
            resp = ops_views.reconciliation_list(request)
        self.assertEqual(resp.status_code, 200)
        _, _, ctx = mocked_render.call_args.args
        got_ids = {str(o.id) for o in ctx["page_obj"].object_list}
        self.assertIn(str(self.order_b.id), got_ids)
        self.assertNotIn(str(self.order_a.id), got_ids)


class AdminCompanyFilterTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.buyer = User.objects.create_user(username="adm_buyer", email="adm_buyer@example.com", password="pw123456")
        self.seller_a = User.objects.create_user(username="adm_alpha", email="adm_alpha@example.com", password="pw123456")
        self.seller_b = User.objects.create_user(username="adm_beta", email="adm_beta@example.com", password="pw123456")
        self.seller_a.profile.is_seller = True
        self.seller_a.profile.shop_name = "Alpha Company"
        self.seller_a.profile.save(update_fields=["is_seller", "shop_name", "updated_at"])
        self.seller_b.profile.is_seller = True
        self.seller_b.profile.shop_name = "Beta Company"
        self.seller_b.profile.save(update_fields=["is_seller", "shop_name", "updated_at"])

        cat = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Admin Filter Goods",
            slug="admin-filter-goods",
            is_active=True,
        )
        service_cat = Category.objects.create(
            type=Category.CategoryType.SERVICE,
            name="Admin Filter Services",
            slug="admin-filter-services",
            is_active=True,
        )
        self.prod_a = Product.objects.create(
            seller=self.seller_a,
            kind=Product.Kind.GOOD,
            title="Alpha Product",
            category=cat,
            price=Decimal("9.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_shipping_enabled=True,
        )
        self.prod_b = Product.objects.create(
            seller=self.seller_b,
            kind=Product.Kind.GOOD,
            title="Beta Product",
            category=cat,
            price=Decimal("9.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_shipping_enabled=True,
        )
        self.service_a = Product.objects.create(
            seller=self.seller_a,
            kind=Product.Kind.SERVICE,
            title="Alpha Service",
            category=service_cat,
            price=Decimal("25.00"),
            is_active=True,
            stock_qty=0,
            service_duration_minutes=60,
            service_deposit_cents=500,
        )

        self.order_a = Order.objects.create(
            buyer=self.buyer,
            status=Order.Status.PAID,
            payment_method=Order.PaymentMethod.STRIPE,
            paid_at=timezone.now(),
            subtotal_cents=900,
            total_cents=900,
        )
        self.order_b = Order.objects.create(
            buyer=self.buyer,
            status=Order.Status.PAID,
            payment_method=Order.PaymentMethod.STRIPE,
            paid_at=timezone.now(),
            subtotal_cents=900,
            total_cents=900,
        )

        self.item_a = OrderItem.objects.create(
            order=self.order_a,
            product=self.prod_a,
            seller=self.seller_a,
            title_snapshot=self.prod_a.title,
            unit_price_cents_snapshot=900,
            quantity=1,
            line_total_cents=900,
            seller_net_cents=900,
            marketplace_fee_cents=0,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="shipping",
        )
        self.item_b = OrderItem.objects.create(
            order=self.order_b,
            product=self.prod_b,
            seller=self.seller_b,
            title_snapshot=self.prod_b.title,
            unit_price_cents_snapshot=900,
            quantity=1,
            line_total_cents=900,
            seller_net_cents=900,
            marketplace_fee_cents=0,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="shipping",
        )

        self.rr_a = RefundRequest.objects.create(
            order=self.order_a,
            order_item=self.item_a,
            seller=self.seller_a,
            buyer=self.buyer,
            requester_email=self.buyer.email,
            reason=RefundRequest.Reason.OTHER,
            status=RefundRequest.Status.REQUESTED,
            line_subtotal_cents_snapshot=900,
            tax_cents_allocated_snapshot=0,
            shipping_cents_allocated_snapshot=0,
            total_refund_cents_snapshot=900,
        )
        self.rr_b = RefundRequest.objects.create(
            order=self.order_b,
            order_item=self.item_b,
            seller=self.seller_b,
            buyer=self.buyer,
            requester_email=self.buyer.email,
            reason=RefundRequest.Reason.OTHER,
            status=RefundRequest.Status.REQUESTED,
            line_subtotal_cents_snapshot=900,
            tax_cents_allocated_snapshot=0,
            shipping_cents_allocated_snapshot=0,
            total_refund_cents_snapshot=900,
        )

        SellerStripeAccount.objects.create(user=self.seller_a, stripe_account_id="acct_admin_a")
        SellerStripeAccount.objects.create(user=self.seller_b, stripe_account_id="acct_admin_b")
        SellerBalanceEntry.objects.create(
            seller=self.seller_a,
            amount_cents=100,
            reason=SellerBalanceEntry.Reason.ADJUSTMENT,
            order=self.order_a,
            order_item=self.item_a,
            note="alpha",
        )
        SellerBalanceEntry.objects.create(
            seller=self.seller_b,
            amount_cents=100,
            reason=SellerBalanceEntry.Reason.ADJUSTMENT,
            order=self.order_b,
            order_item=self.item_b,
            note="beta",
        )

        self.appt_a = AppointmentRequest.objects.create(
            service=self.service_a,
            buyer=self.buyer,
            seller=self.seller_a,
            requested_start=timezone.now() + timezone.timedelta(days=1),
            requested_end=timezone.now() + timezone.timedelta(days=1, hours=1),
            status=AppointmentRequest.Status.REQUESTED,
        )

        self.thread_a = ProductQuestionThread.objects.create(product=self.prod_a, buyer=self.buyer, subject="Alpha Q")
        self.msg_a = ProductQuestionMessage.objects.create(thread=self.thread_a, author=self.buyer, body="Question")
        self.report_a = ProductQuestionReport.objects.create(
            message=self.msg_a,
            reporter=self.buyer,
            reason=ProductQuestionReport.Reason.OTHER,
            status=ProductQuestionReport.Status.OPEN,
            details="x",
        )
        thread_b = ProductQuestionThread.objects.create(product=self.prod_b, buyer=self.buyer, subject="Beta Q")
        msg_b = ProductQuestionMessage.objects.create(thread=thread_b, author=self.buyer, body="Question B")
        self.report_b = ProductQuestionReport.objects.create(
            message=msg_b,
            reporter=self.buyer,
            reason=ProductQuestionReport.Reason.OTHER,
            status=ProductQuestionReport.Status.OPEN,
            details="y",
        )

        self.notification_a = Notification.objects.create(
            user=self.seller_a,
            kind=Notification.Kind.SYSTEM,
            title="Alpha Notice",
            body="a",
        )
        self.notification_b = Notification.objects.create(
            user=self.seller_b,
            kind=Notification.Kind.SYSTEM,
            title="Beta Notice",
            body="b",
        )
        self.email_attempt_a = EmailDeliveryAttempt.objects.create(
            notification=self.notification_a,
            to_email=self.seller_a.email,
            subject="A",
            status=EmailDeliveryAttempt.Status.SENT,
        )
        self.email_attempt_b = EmailDeliveryAttempt.objects.create(
            notification=self.notification_b,
            to_email=self.seller_b.email,
            subject="B",
            status=EmailDeliveryAttempt.Status.SENT,
        )

    def test_product_admin_company_filter_by_id(self):
        request = self.factory.get("/admin/products/product/", {"seller_company": str(self.seller_a.id)})
        model_admin = ProductAdmin(Product, admin.site)
        filt = CoreSellerCompanyFilter(request, {}, Product, model_admin)
        filt.used_parameters[filt.parameter_name] = str(self.seller_a.id)
        qs = filt.queryset(request, Product.objects.all())
        got_ids = set(qs.values_list("id", flat=True))
        self.assertIn(self.prod_a.id, got_ids)
        self.assertIn(self.service_a.id, got_ids)
        self.assertNotIn(self.prod_b.id, got_ids)

    def test_refund_admin_company_filter_by_id(self):
        request = self.factory.get("/admin/refunds/refundrequest/", {"seller_company": str(self.seller_a.id)})
        model_admin = RefundRequestAdmin(RefundRequest, admin.site)
        filt = CoreSellerCompanyFilter(request, {}, RefundRequest, model_admin)
        filt.used_parameters[filt.parameter_name] = str(self.seller_a.id)
        qs = filt.queryset(request, RefundRequest.objects.all())
        got = {str(x.id) for x in qs}
        self.assertIn(str(self.rr_a.id), got)
        self.assertNotIn(str(self.rr_b.id), got)

    def test_stripe_account_user_company_filter(self):
        request = self.factory.get("/admin/payments/sellerstripeaccount/", {"user_company": str(self.seller_b.id)})
        filt = UserCompanyFilter(
            request,
            {},
            SellerStripeAccount,
            admin.site._registry[SellerStripeAccount],
        )
        filt.used_parameters[filt.parameter_name] = str(self.seller_b.id)
        qs = filt.queryset(request, SellerStripeAccount.objects.all())
        self.assertEqual(list(qs.values_list("user_id", flat=True)), [self.seller_b.id])

    def test_seller_balance_company_filter(self):
        request = self.factory.get("/admin/payments/sellerbalanceentry/", {"seller_company": str(self.seller_b.id)})
        filt = SellerBalanceCompanyFilter(
            request,
            {},
            SellerBalanceEntry,
            admin.site._registry[SellerBalanceEntry],
        )
        filt.used_parameters[filt.parameter_name] = str(self.seller_b.id)
        qs = filt.queryset(request, SellerBalanceEntry.objects.all())
        self.assertEqual(list(qs.values_list("seller_id", flat=True)), [self.seller_b.id])

    def test_appointment_admin_company_filter(self):
        request = self.factory.get("/admin/appointments/appointmentrequest/", {"seller_company": str(self.seller_a.id)})
        model_admin = AppointmentRequestAdmin(AppointmentRequest, admin.site)
        filt = CoreSellerCompanyFilter(request, {}, AppointmentRequest, model_admin)
        filt.used_parameters[filt.parameter_name] = str(self.seller_a.id)
        qs = filt.queryset(request, AppointmentRequest.objects.all())
        self.assertEqual(list(qs.values_list("seller_id", flat=True)), [self.seller_a.id])

    def test_qa_thread_company_filter(self):
        request = self.factory.get("/admin/qa/productquestionthread/", {"seller_company": str(self.seller_a.id)})
        filt = QASellerCompanyFilter(
            request,
            {},
            ProductQuestionThread,
            admin.site._registry[ProductQuestionThread],
        )
        filt.used_parameters[filt.parameter_name] = str(self.seller_a.id)
        qs = filt.queryset(request, ProductQuestionThread.objects.all())
        self.assertEqual(list(qs.values_list("product__seller_id", flat=True).distinct()), [self.seller_a.id])

    def test_notification_user_company_filter(self):
        request = self.factory.get("/admin/notifications/notification/", {"user_company": str(self.seller_b.id)})
        filt = NotificationUserCompanyFilter(
            request,
            {},
            Notification,
            admin.site._registry[Notification],
        )
        filt.used_parameters[filt.parameter_name] = str(self.seller_b.id)
        qs = filt.queryset(request, Notification.objects.all())
        user_ids = list(qs.values_list("user_id", flat=True))
        self.assertTrue(user_ids)
        self.assertEqual(set(user_ids), {self.seller_b.id})
        self.assertIn(self.notification_b.id, set(qs.values_list("id", flat=True)))

    def test_email_attempt_user_company_filter(self):
        request = self.factory.get("/admin/notifications/emaildeliveryattempt/", {"user_company": str(self.seller_a.id)})
        filt = EmailAttemptUserCompanyFilter(
            request,
            {},
            EmailDeliveryAttempt,
            admin.site._registry[EmailDeliveryAttempt],
        )
        filt.used_parameters[filt.parameter_name] = str(self.seller_a.id)
        qs = filt.queryset(request, EmailDeliveryAttempt.objects.all())
        user_ids = list(qs.values_list("notification__user_id", flat=True))
        self.assertTrue(user_ids)
        self.assertEqual(set(user_ids), {self.seller_a.id})
        self.assertIn(self.email_attempt_a.id, set(qs.values_list("id", flat=True)))


class DangerousActionPermissionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.ops_user = User.objects.create_user(
            username="ops_limited",
            email="ops_limited@example.com",
            password="pw123456",
        )
        ops_group, _ = Group.objects.get_or_create(name="ops")
        ops_group.permissions.clear()
        self.ops_user.groups.add(ops_group)

        self.owner_user = User.objects.create_user(
            username="owner_user",
            email="owner_user@example.com",
            password="pw123456",
        )
        owner_prof = self.owner_user.profile
        owner_prof.is_owner = True
        owner_prof.save(update_fields=["is_owner", "updated_at"])

        self.delegated_user = User.objects.create_user(
            username="delegated_user",
            email="delegated_user@example.com",
            password="pw123456",
        )
        self.delegated_user.groups.add(ops_group)

        cat = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Danger Goods",
            slug="danger-goods",
            is_active=True,
        )
        seller = User.objects.create_user(username="danger_seller", email="danger_seller@example.com", password="pw123456")
        sprof = seller.profile
        sprof.is_seller = True
        sprof.email_verified = True
        sprof.save(update_fields=["is_seller", "email_verified", "updated_at"])
        prod = Product.objects.create(
            seller=seller,
            kind=Product.Kind.GOOD,
            title="Danger Item",
            category=cat,
            price=Decimal("10.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_pickup_enabled=True,
        )
        self.order = Order.objects.create(
            status=Order.Status.PAID,
            payment_method=Order.PaymentMethod.STRIPE,
            subtotal_cents=1000,
            total_cents=1000,
            paid_at=timezone.now(),
            stripe_session_id="cs_danger",
            stripe_payment_intent_id="pi_danger",
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=prod,
            seller=seller,
            title_snapshot=prod.title,
            unit_price_cents_snapshot=1000,
            quantity=1,
            line_total_cents=1000,
            marketplace_fee_cents=0,
            seller_net_cents=1000,
            is_service=False,
            is_tip=False,
            fulfillment_mode_snapshot="pickup",
        )
        self.webhook = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_danger_1",
            event_type="customer.created",
            livemode=False,
            status="error",
            raw_json={"id": "evt_danger_1", "type": "customer.created", "data": {"object": {"id": "cus_x"}}},
        )

        self.perm_reprocess_webhooks = Permission.objects.get(codename="can_reprocess_webhooks")
        self.perm_retry_payouts = Permission.objects.get(codename="can_retry_payouts")
        self.perm_trigger_refunds = Permission.objects.get(codename="can_trigger_refunds")

    def test_ops_webhook_bulk_reprocess_denied_for_non_owner_ops(self):
        self.client.force_login(self.ops_user)
        resp = self.client.post(
            reverse("ops:webhooks_reprocess_filtered"),
            data={"status": "error", "days": "14", "limit": "10"},
        )
        self.assertEqual(resp.status_code, 302)
        self.webhook.refresh_from_db()
        self.assertEqual(self.webhook.status, "error")

    def test_ops_order_retry_transfers_denied_for_non_owner_ops(self):
        self.client.force_login(self.ops_user)
        resp = self.client.post(reverse("ops:order_retry_transfers", kwargs={"pk": self.order.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            OrderEvent.objects.filter(order=self.order, type=OrderEvent.Type.TRANSFER_CREATED).exists()
        )

    def test_refund_admin_action_denied_for_non_owner(self):
        rr = RefundRequest.objects.create(
            order=self.order,
            order_item=self.order_item,
            seller=self.order_item.seller,
            requester_email="buyer@example.com",
            reason=RefundRequest.Reason.OTHER,
            status=RefundRequest.Status.APPROVED,
            line_subtotal_cents_snapshot=1000,
            tax_cents_allocated_snapshot=0,
            shipping_cents_allocated_snapshot=0,
            total_refund_cents_snapshot=1000,
        )
        request = self.factory.post("/admin/refunds/refundrequest/")
        request.user = self.ops_user
        admin_instance = RefundRequestAdmin(RefundRequest, admin.site)

        with patch.object(admin_instance, "message_user") as msg_mock, patch("refunds.services.trigger_refund") as trigger_mock, patch("refunds.admin.messages.success"), patch("refunds.admin.messages.info"), patch("refunds.admin.messages.error"):
            admin_instance.admin_trigger_refund(request, RefundRequest.objects.filter(pk=rr.pk))

        trigger_mock.assert_not_called()
        msg_mock.assert_called()

    def test_order_admin_retry_action_denied_for_non_owner(self):
        request = self.factory.post("/admin/orders/order/")
        request.user = self.ops_user
        admin_instance = OrderAdmin(Order, admin.site)

        with patch.object(admin_instance, "message_user") as msg_mock, patch("orders.admin.create_transfers_for_paid_order") as retry_mock:
            admin_instance.retry_payout_transfers(request, Order.objects.filter(pk=self.order.pk))

        retry_mock.assert_not_called()
        msg_mock.assert_called()

    def test_ops_webhook_bulk_reprocess_allowed_with_explicit_permission(self):
        self.delegated_user.user_permissions.add(self.perm_reprocess_webhooks)
        self.client.force_login(self.delegated_user)
        resp = self.client.post(
            reverse("ops:webhooks_reprocess_filtered"),
            data={"status": "error", "days": "14", "limit": "10"},
        )
        self.assertEqual(resp.status_code, 302)
        self.webhook.refresh_from_db()
        self.assertEqual(self.webhook.status, "ignored")

    def test_ops_order_retry_transfers_allowed_with_explicit_permission(self):
        self.delegated_user.user_permissions.add(self.perm_retry_payouts)
        self.client.force_login(self.delegated_user)

        with patch("ops.views.create_transfers_for_paid_order") as retry_mock:
            resp = self.client.post(reverse("ops:order_retry_transfers", kwargs={"pk": self.order.pk}))

        self.assertEqual(resp.status_code, 302)
        retry_mock.assert_called_once()

    def test_refund_admin_action_allowed_with_explicit_permission(self):
        self.delegated_user.user_permissions.add(self.perm_trigger_refunds)
        rr = RefundRequest.objects.create(
            order=self.order,
            order_item=self.order_item,
            seller=self.order_item.seller,
            requester_email="buyer@example.com",
            reason=RefundRequest.Reason.OTHER,
            status=RefundRequest.Status.APPROVED,
            line_subtotal_cents_snapshot=1000,
            tax_cents_allocated_snapshot=0,
            shipping_cents_allocated_snapshot=0,
            total_refund_cents_snapshot=1000,
        )
        request = self.factory.post("/admin/refunds/refundrequest/")
        request.user = self.delegated_user
        admin_instance = RefundRequestAdmin(RefundRequest, admin.site)

        with patch.object(admin_instance, "message_user") as msg_mock, patch("refunds.services.trigger_refund") as trigger_mock, patch("refunds.admin.messages.success"), patch("refunds.admin.messages.info"), patch("refunds.admin.messages.error"):
            admin_instance.admin_trigger_refund(request, RefundRequest.objects.filter(pk=rr.pk))

        trigger_mock.assert_called_once()

    def test_order_admin_retry_action_allowed_with_explicit_permission(self):
        self.delegated_user.user_permissions.add(self.perm_retry_payouts)
        request = self.factory.post("/admin/orders/order/")
        request.user = self.delegated_user
        admin_instance = OrderAdmin(Order, admin.site)

        with patch.object(admin_instance, "message_user") as msg_mock, patch("orders.admin.create_transfers_for_paid_order") as retry_mock:
            admin_instance.retry_payout_transfers(request, Order.objects.filter(pk=self.order.pk))

        retry_mock.assert_called_once()
        self.assertTrue(msg_mock.called)

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category
from payments.models import SellerFeeWaiver
from products.models import Product


User = get_user_model()


class StartSellingFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="consumer1",
            email="consumer1@example.com",
            password="pw123456",
        )
        self.client.force_login(self.user)

    def test_start_selling_marks_seller_and_redirects_verified_user_to_connect_status(self):
        profile = self.user.profile
        profile.email_verified = True
        profile.save(update_fields=["email_verified", "updated_at"])

        resp = self.client.post(reverse("dashboards:start_selling"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("payments:connect_status"))

        profile.refresh_from_db()
        self.assertTrue(profile.is_seller)

    def test_start_selling_marks_seller_and_redirects_unverified_to_verify_with_next(self):
        profile = self.user.profile
        profile.email_verified = False
        profile.save(update_fields=["email_verified", "updated_at"])

        resp = self.client.post(reverse("dashboards:start_selling"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:verify_email_status"), resp["Location"])
        self.assertIn(reverse("payments:connect_status"), resp["Location"])

        profile.refresh_from_db()
        self.assertTrue(profile.is_seller)


class SellerBulkActivateWaiverTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            username="seller_bulk_activate",
            email="seller_bulk_activate@example.com",
            password="pw123456",
        )
        profile = self.seller.profile
        profile.is_seller = True
        profile.email_verified = True
        profile.save(update_fields=["is_seller", "email_verified", "updated_at"])

        self.category = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Bulk Activate Category",
            slug="bulk-activate-category",
            is_active=True,
        )
        self.product = Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Bulk Draft Listing",
            category=self.category,
            price="12.00",
            stock_qty=2,
            fulfillment_pickup_enabled=True,
            is_active=False,
        )
        self.client.force_login(self.seller)

    def test_bulk_activate_starts_waiver_for_first_live_listing(self):
        self.assertFalse(SellerFeeWaiver.objects.filter(user=self.seller).exists())

        resp = self.client.post(
            reverse("dashboards:seller"),
            data={"bulk_action": "activate", "selected_ids": [str(self.product.id)]},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("dashboards:seller"))
        self.assertEqual(SellerFeeWaiver.objects.filter(user=self.seller).count(), 1)


class AdminOpsPanelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner_ops_panel",
            email="owner_ops_panel@example.com",
            password="pw123456",
        )
        prof = self.owner.profile
        prof.is_owner = True
        prof.email_verified = True
        prof.save(update_fields=["is_owner", "email_verified", "updated_at"])
        self.client.force_login(self.owner)

    def test_admin_ops_renders_automations_health_panel(self):
        resp = self.client.get(reverse("dashboards:admin_ops"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Automations Health")
        self.assertContains(resp, "Saved search scheduler")

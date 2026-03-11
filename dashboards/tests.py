from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category
from core.models import SiteConfig
from dashboards.forms import SiteConfigForm
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

    def test_seller_dashboard_renders_without_legacy_product_relations(self):
        resp = self.client.get(reverse("dashboards:seller"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Seller dashboard")


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


class AdminSettingsSaveTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner_settings_test",
            email="owner_settings_test@example.com",
            password="pw123456",
        )
        prof = self.owner.profile
        prof.is_owner = True
        prof.email_verified = True
        prof.save(update_fields=["is_owner", "email_verified", "updated_at"])
        self.client.force_login(self.owner)
        SiteConfig.objects.get_or_create(pk=1)

    def test_admin_settings_post_persists_core_fields(self):
        cfg = SiteConfig.objects.get(pk=1)
        form = SiteConfigForm(instance=cfg)
        data = {}
        for name, field in form.fields.items():
            val = form.initial.get(name, getattr(cfg, name, field.initial))
            if isinstance(field, forms.BooleanField):
                if bool(val):
                    data[name] = "on"
                continue
            if val is None:
                data[name] = ""
            elif isinstance(val, (list, tuple)):
                data[name] = ",".join([str(x) for x in val])
            else:
                data[name] = str(val)

        data.update(
            {
                "marketplace_sales_percent": "10.00",
                "platform_fee_cents": "15",
                "allowed_shipping_countries_csv": "US,CA",
                "free_digital_listing_cap": "3",
                "checkout_enabled": "on",
                "checkout_disabled_message": "Temporarily paused",
                "analytics_retention_days": "90",
                "google_analytics_dashboard_url": "analytics.google.com/reporting",
                "ga_measurement_id": "G-TEST1234",
                "seller_prohibited_items_notice": "No drugs, alcohol, or weapons.",
                "seller_requires_age_18": "on",
                "support_email": "support@example.com",
                "home_hero_title": "Shop local first",
                "home_hero_subtitle": "Support people in your community",
                "facebook_url": "facebook.com/localmarketne",
                "instagram_url": "",
                "tiktok_url": "",
                "youtube_url": "",
                "x_url": "",
                "linkedin_url": "",
            }
        )

        resp = self.client.post(
            reverse("dashboards:admin_settings"),
            data=data,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("dashboards:admin_settings"))

        cfg = SiteConfig.objects.get(pk=1)
        self.assertEqual(str(cfg.marketplace_sales_percent), "10.00")
        self.assertEqual(cfg.platform_fee_cents, 15)
        self.assertEqual(cfg.allowed_shipping_countries, ["US", "CA"])
        self.assertEqual(cfg.support_email, "support@example.com")
        self.assertEqual(cfg.home_hero_title, "Shop local first")
        # URL auto-normalization should prepend https:// when missing.
        self.assertEqual(cfg.facebook_url, "https://facebook.com/localmarketne")
        self.assertEqual(
            cfg.google_analytics_dashboard_url,
            "https://analytics.google.com/reporting",
        )

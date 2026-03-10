"""Core test suite.

We keep a small set of fast, high-signal tests that catch common regressions.

Pack AZ: Template integrity compilation pass.
"""

from django.test import SimpleTestCase, TestCase, override_settings
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import reverse

from core.models import ContactMessage, WaitlistEntry


class TemplateIntegrityTests(SimpleTestCase):
    """Ensure key templates compile (catches TemplateSyntaxError early)."""

    TEMPLATES_TO_COMPILE = [
        # Global layout
        "base.html",
        "partials/navbar.html",
        "partials/footer.html",
        # Dashboards
        "dashboards/consumer_dashboard.html",
        "dashboards/seller_dashboard.html",
        # Products browsing
        "products/product_list.html",
        "products/services_list.html",
        "products/_category_sidebar.html",
        # Orders
        "orders/order_detail.html",
        "orders/seller_orders_list.html",
        "orders/seller/order_detail.html",
        # Ops
        "ops/dashboard.html",
        "ops/funnel.html",
        "ops/failed_emails.html",
        "ops/health.html",
        "ops/webhooks_list.html",
        "ops/reconciliation_list.html",
    ]

    def test_templates_compile(self):
        missing = []
        for name in self.TEMPLATES_TO_COMPILE:
            try:
                get_template(name)
            except TemplateDoesNotExist:
                missing.append(name)
        if missing:
            self.fail(f"Missing templates: {', '.join(missing)}")


class RecaptchaPublicFormsTests(TestCase):
    @override_settings(
        RECAPTCHA_ENABLED=True,
        RECAPTCHA_V3_SITE_KEY="test-site-key",
        RECAPTCHA_V3_SECRET_KEY="test-secret-key",
    )
    def test_contact_post_requires_recaptcha_token(self):
        url = reverse("core:contact")
        resp = self.client.post(
            url,
            data={
                "name": "Tester",
                "email": "tester@example.com",
                "subject": "Hello",
                "message": "Test message",
            },
            HTTP_REFERER=url,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], url)
        self.assertEqual(ContactMessage.objects.count(), 0)

    @override_settings(
        RECAPTCHA_ENABLED=True,
        RECAPTCHA_V3_SITE_KEY="test-site-key",
        RECAPTCHA_V3_SECRET_KEY="test-secret-key",
    )
    def test_waitlist_post_requires_recaptcha_token(self):
        url = reverse("core:waitlist")
        resp = self.client.post(
            url,
            data={"email": "waitlist@example.com"},
            HTTP_REFERER=url,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], url)
        self.assertEqual(WaitlistEntry.objects.count(), 0)


class UrlNameIntegrityTests(SimpleTestCase):
    """Keep critical named routes aligned with launch/deploy checks."""

    def test_critical_named_routes_reverse(self):
        names = [
            "dashboards:consumer",
            "dashboards:seller",
            "dashboards:admin_ops",
            "products:list",
            "products:services",
            "products:top_sellers",
            "cart:view",
        ]
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(reverse(name))


class HomePageRenderTests(TestCase):
    def test_home_page_renders(self):
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Local Market NE")

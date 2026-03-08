"""Core test suite.

We keep a small set of fast, high-signal tests that catch common regressions.

Pack AZ: Template integrity compilation pass.
"""

from django.test import SimpleTestCase
from django.template import TemplateDoesNotExist
from django.template.loader import get_template


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

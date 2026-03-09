from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category
from products.models import Product


User = get_user_model()


class CartRecaptchaTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            username="cartseller",
            email="cartseller@example.com",
            password="pw123456",
        )
        cat = Category.objects.create(
            type=Category.CategoryType.GOOD,
            name="Cart Goods",
            slug="cart-goods",
            is_active=True,
        )
        self.product = Product.objects.create(
            seller=self.seller,
            kind=Product.Kind.GOOD,
            title="Cart Product",
            category=cat,
            price=Decimal("12.00"),
            is_active=True,
            stock_qty=10,
            fulfillment_pickup_enabled=True,
        )

    @override_settings(
        RECAPTCHA_ENABLED=True,
        RECAPTCHA_V3_SITE_KEY="test-site-key",
        RECAPTCHA_V3_SECRET_KEY="test-secret-key",
    )
    def test_cart_add_requires_recaptcha_token(self):
        url = reverse("cart:add")
        resp = self.client.post(
            url,
            data={"product_id": self.product.pk, "quantity": 1},
            HTTP_REFERER=self.product.get_absolute_url(),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], self.product.get_absolute_url())

        session = self.client.session
        self.assertFalse(bool(session.get("lmne_cart_v1")))

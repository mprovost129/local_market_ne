from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from payments.models import SellerStripeAccount


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


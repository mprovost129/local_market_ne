from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


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


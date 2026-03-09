from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


User = get_user_model()


class VerifyEmailRedirectTests(TestCase):
    def test_verify_email_confirm_redirects_authenticated_user_to_consumer_dashboard(self):
        user = User.objects.create_user(
            username="verifyuser",
            email="verifyuser@example.com",
            password="pw123456",
        )
        profile = user.profile
        profile.email_verified = False
        profile.email_verification_token = uuid.uuid4()
        profile.save(update_fields=["email_verified", "email_verification_token", "updated_at"])

        self.client.force_login(user)
        resp = self.client.get(
            reverse("accounts:verify_email_confirm", kwargs={"token": str(profile.email_verification_token)})
        )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("dashboards:consumer"))

        profile.refresh_from_db()
        self.assertTrue(profile.email_verified)
        self.assertIsNone(profile.email_verification_token)


class RecaptchaLoginTests(TestCase):
    @override_settings(
        RECAPTCHA_ENABLED=True,
        RECAPTCHA_V3_SITE_KEY="test-site-key",
        RECAPTCHA_V3_SECRET_KEY="test-secret-key",
    )
    def test_login_post_requires_recaptcha_token(self):
        user = User.objects.create_user(
            username="loginuser",
            email="loginuser@example.com",
            password="pw123456",
        )
        self.assertIsNotNone(user.pk)
        url = reverse("accounts:login")
        resp = self.client.post(
            url,
            data={"username": "loginuser", "password": "pw123456"},
            HTTP_REFERER=url,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], url)

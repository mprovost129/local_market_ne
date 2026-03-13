from __future__ import annotations

import uuid
from unittest.mock import patch

from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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


class ProfileAvatarUploadFailureTests(TestCase):
    def test_profile_post_handles_storage_failure_without_500(self):
        user = User.objects.create_user(
            username="avataruser",
            email="avataruser@example.com",
            password="pw123456",
        )
        self.client.force_login(user)

        # Tiny valid GIF payload so ImageField validation passes.
        avatar = SimpleUploadedFile(
            "avatar.gif",
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02L\x01\x00;",
            content_type="image/gif",
        )

        err = ClientError({"Error": {"Code": "AccessDenied", "Message": "Denied"}}, "PutObject")
        with patch("accounts.views.ConsumerProfileForm.save", side_effect=err):
            resp = self.client.post(
                reverse("accounts:profile"),
                data={"first_name": "Avatar", "avatar": avatar},
            )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("accounts:profile"))


class RegisterFlowTests(TestCase):
    def test_register_redirects_to_consumer_dashboard(self):
        resp = self.client.post(
            reverse("accounts:register"),
            data={
                "username": "newconsumer",
                "email": "newconsumer@example.com",
                "password1": "SuperStrongPass123!",
                "password2": "SuperStrongPass123!",
                "confirm_age_18": "on",
                "recaptcha_token": "test-token",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("dashboards:consumer"))

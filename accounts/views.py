# accounts/views.py
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods
from botocore.exceptions import BotoCoreError, ClientError

from core.throttle import throttle
from core.throttle_rules import AUTH_LOGIN, AUTH_REGISTER
from core.recaptcha import require_recaptcha_v3
from .forms import RegisterForm, UsernameAuthenticationForm, ProfileForm
from .services import send_email_verification
from .geo import lookup_zip_centroid
from .models import Profile


logger = logging.getLogger(__name__)


# ----------------------------
# Throttle rules (tune anytime)
# ----------------------------
AUTH_LOGIN_RULE = AUTH_LOGIN
AUTH_REGISTER_RULE = AUTH_REGISTER


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    if request.method == "POST":
        # throttle only the POST attempt
        return _login_post(request)

    form = UsernameAuthenticationForm(request)
    return render(request, "accounts/login.html", {"form": form})


@require_POST
@throttle(AUTH_LOGIN_RULE)
@require_recaptcha_v3("login")
def _login_post(request):
    form = UsernameAuthenticationForm(request, data=request.POST)
    if form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, "Welcome back.")
        next_url = request.POST.get("next") or request.GET.get("next") or reverse("core:home")
        return redirect(next_url)

    # Optional: generic message to avoid hinting “user exists”
    messages.error(request, "Invalid credentials.")
    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("accounts:login")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    if request.method == "POST":
        return _register_post(request)

    form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


@require_POST
@throttle(AUTH_REGISTER_RULE)
@require_recaptcha_v3("register")
def _register_post(request):
    form = RegisterForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please correct the form.")
        return render(request, "accounts/register.html", {"form": form})

    user = form.save()
    login(request, user)
    messages.success(request, "Account created.")

    # Send verification email (best-effort)
    try:
        send_email_verification(request=request, user=user)
    except Exception:
        pass

    # If user registered as seller, gate onboarding behind verified email
    if form.cleaned_data.get("register_as_seller"):
        if getattr(getattr(user, "profile", None), "email_verified", False):
            messages.info(request, "Let's set up your seller account with Stripe.")
            return redirect("payments:connect_start")

        messages.warning(request, "Verify your email to start Stripe onboarding.")
        return redirect(reverse("accounts:verify_email_status") + "?next=" + reverse("payments:connect_start"))

    return redirect("accounts:profile")


@login_required
def profile_view(request):
    # Profile is created via signal; assume it exists.
    profile = request.user.profile

    if request.method == "POST":
        before_zip = (profile.zip_code or "").strip()

        form = ProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
        if form.is_valid():
            try:
                form.save()
            except (BotoCoreError, ClientError, OSError):
                # Keep the request user-facing when media storage is temporarily unavailable.
                logger.exception("Profile avatar upload failed", extra={"user_id": request.user.id})
                messages.error(request, "Profile picture upload failed. Please try again in a moment.")
                return redirect("accounts:profile")

            # Keep private geo centroid in sync with ZIP (best effort).
            try:
                after_zip = (profile.zip_code or "").strip()
                if not after_zip:
                    profile.private_latitude = None
                    profile.private_longitude = None
                    profile.private_geo_updated_at = timezone.now()
                    profile.save(update_fields=["private_latitude", "private_longitude", "private_geo_updated_at", "updated_at"])
                elif after_zip != before_zip or profile.private_latitude is None or profile.private_longitude is None:
                    centroid = lookup_zip_centroid(after_zip)
                    if centroid:
                        lat, lng = centroid
                        profile.private_latitude = lat
                        profile.private_longitude = lng
                        profile.private_geo_updated_at = timezone.now()
                        profile.save(
                            update_fields=[
                                "private_latitude",
                                "private_longitude",
                                "private_geo_updated_at",
                                "updated_at",
                            ]
                        )
            except Exception:
                # Do not block profile updates on geo lookup failures.
                logger.info("Profile geo centroid lookup skipped/failed", extra={"user_id": request.user.id})

            messages.success(request, "Profile updated.")

            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=profile, user=request.user)

    return render(request, "accounts/profile.html", {"form": form, "profile": profile})


@login_required
@require_http_methods(["GET", "POST"])
def verify_email_status(request):
    """Show verification status and allow resending the verification email."""
    profile = request.user.profile

    if request.method == "POST":
        try:
            send_email_verification(request=request, user=request.user)
            messages.success(request, "Verification email sent. Check your inbox.")
        except Exception:
            messages.error(request, "Unable to send verification email right now.")

        next_url = request.POST.get("next") or request.GET.get("next") or reverse("accounts:profile")
        return redirect(next_url)

    return render(
        request,
        "accounts/verify_email_status.html",
        {
            "profile": profile,
            "is_verified": bool(getattr(profile, "email_verified", False)),
            "next": request.GET.get("next") or "",
        },
    )




@login_required
@require_POST
@throttle(AUTH_REGISTER)  # reuse conservative throttle bucket for resend
def verify_email_resend(request):
    """POST-only alias endpoint to resend verification email.

    This exists to avoid dead links (e.g. /accounts/verify-email/resend/) and to keep
    the resend behavior consistent with verify_email_status().
    """
    profile = request.user.profile
    if getattr(profile, "email_verified", False):
        messages.info(request, "Your email is already verified.")
        return redirect(request.POST.get("next") or reverse("accounts:profile"))

    try:
        send_email_verification(request=request, user=request.user)
        messages.success(request, "Verification email sent. Check your inbox.")
    except Exception:
        messages.error(request, "Unable to send verification email right now.")

    return redirect(request.POST.get("next") or reverse("accounts:verify_email_status"))


@require_http_methods(["GET"])
def verify_email_confirm(request, token: str):
    """Confirm email verification from token link."""
    try:
        profile = Profile.objects.select_related("user").get(email_verification_token=token)
    except Profile.DoesNotExist:
        messages.error(request, "Invalid or expired verification link.")
        return redirect("accounts:login")

    profile.email_verified = True
    profile.email_verification_token = None
    profile.save(update_fields=["email_verified", "email_verification_token", "updated_at"])

    # If already logged in as this user, keep session.
    if request.user.is_authenticated and request.user.id == profile.user_id:
        messages.success(request, "Email verified.")
        next_url = request.GET.get("next") or reverse("dashboards:consumer")
        return redirect(next_url)

    messages.success(request, "Email verified. Please log in.")
    return redirect("accounts:login")

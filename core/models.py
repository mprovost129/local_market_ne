# core/models.py
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models


class SiteConfig(models.Model):
    """
    DB-backed site settings (singleton).

    STRICT RULE:
    - Any site setting MUST live here (so it's editable via Django admin/dashboard).
    - No "settings.py constants" for runtime-tunable business rules.
    """

    # -------------------------
    # Site-wide Promo Banner (above navbar, sitewide)
    # -------------------------
    promo_banner_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, show a promo banner above the navbar sitewide.",
    )
    promo_banner_text = models.CharField(
        max_length=240,
        blank=True,
        default="",
        help_text="Text shown in the promo banner. Keep it short.",
    )

    # -------------------------
    # Home Page Banner (home page only)
    # -------------------------
    home_banner_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, show a banner on the home page (only).",
    )
    home_banner_text = models.CharField(
        max_length=240,
        blank=True,
        default="",
        help_text="Text shown in the home page banner. Keep it short.",
    )

    
    # -------------------------
    # Store Operations (Announcements / Maintenance)
    # -------------------------
    site_announcement_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, show a site-wide announcement bar below the promo banner.",
    )
    site_announcement_text = models.CharField(
        max_length=240,
        blank=True,
        default="",
        help_text="Announcement text shown sitewide. Keep it short.",
    )

    maintenance_mode_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, non-staff visitors see a maintenance page (OPS/Staff can still access the site).",
    )
    maintenance_mode_message = models.CharField(
        max_length=240,
        blank=True,
        default="We’re performing maintenance. Please check back soon.",
        help_text="Message shown on the maintenance page.",
    )

    checkout_enabled = models.BooleanField(
        default=True,
        help_text=(
            "If disabled, checkout is blocked sitewide (browsing still works). "
            "Use for emergency rollback or payment incident response."
        ),
    )
    checkout_disabled_message = models.CharField(
        max_length=240,
        blank=True,
        default="Checkout is temporarily unavailable. Please try again soon.",
        help_text="Message shown when checkout is disabled.",
    )

    # -------------------------
    # Environment Banner (test/staging safety)
    # -------------------------
    environment_banner_enabled = models.BooleanField(
        default=False,
        help_text=(
            "If enabled, show an environment banner sitewide (useful for staging or test mode warnings). "
            "A test-mode Stripe key in production will also trigger an automatic warning banner."
        ),
    )
    environment_banner_text = models.CharField(
        max_length=240,
        blank=True,
        default="",
        help_text="Text shown in the environment banner. Keep it short.",
    )

    # -------------------------
    # Waitlist (Coming Soon / marketing)
    # -------------------------
    waitlist_enabled = models.BooleanField(
        default=True,
        help_text="If enabled, the public waitlist signup page is available.",
    )
    waitlist_send_confirmation = models.BooleanField(
        default=False,
        help_text="If enabled, send a confirmation email to new waitlist signups.",
    )
    waitlist_admin_notify_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, notify the admin address when a new waitlist entry is created.",
    )
    waitlist_admin_email = models.EmailField(
        blank=True,
        default="",
        help_text="Admin email to notify for new waitlist signups (used only if admin notify is enabled).",
    )
    waitlist_confirmation_subject = models.CharField(
        max_length=160,
        blank=True,
        default="You’re on the Local Market NE waitlist",
        help_text="Subject for the waitlist confirmation email.",
    )
    waitlist_confirmation_body = models.TextField(
        blank=True,
        default=(
            "Thanks for joining the Local Market NE waitlist!\n\n"
            "We’ll email you when we launch.\n\n"
            "— Local Market NE"
        ),
        help_text="Body for the waitlist confirmation email (plain text).",
    )
    # -------------------------
    # Support / Contact
    # -------------------------
    support_email = models.EmailField(
        blank=True,
        default="",
        help_text="Public support email shown on Contact/Help pages (optional).",
    )
    support_form_enabled = models.BooleanField(
        default=True,
        help_text="If enabled, the Contact form is available to the public.",
    )
    support_store_messages = models.BooleanField(
        default=True,
        help_text="If enabled, Contact form submissions are stored in the database for staff review.",
    )
    support_send_email = models.BooleanField(
        default=True,
        help_text="If enabled, Contact form submissions are emailed to the support address (best-effort).",
    )
    support_admin_notify_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, notify the admin address when a new Contact message is received.",
    )
    support_admin_email = models.EmailField(
        blank=True,
        default="",
        help_text="Optional admin email to notify for Contact messages (used only if admin notify is enabled).",
    )
    support_auto_reply_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, send a basic auto-reply to the sender confirming receipt (best-effort).",
    )
    support_auto_reply_subject = models.CharField(
        max_length=160,
        blank=True,
        default="We received your message",
        help_text="Subject for the support auto-reply email (if enabled).",
    )
    support_auto_reply_body = models.TextField(
        blank=True,
        default=(
            "Thanks for reaching out to Local Market NE.\n\n"
            "We received your message and will get back to you as soon as possible.\n\n"
            "— Local Market NE"
        ),
        help_text="Body for the support auto-reply email (plain text).",
    )
    

    featured_seller_usernames = models.JSONField(
        default=list,
        blank=True,
        help_text="List of seller usernames to feature on the home page (optional).",
    )
    featured_category_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of category IDs to feature on the home page (optional).",
    )

# -------------------------
    # Seller fee waiver (on platform cut only; Stripe fees still apply)
    # -------------------------
    seller_fee_waiver_enabled = models.BooleanField(
        default=True,
        help_text="If enabled, new sellers receive a temporary 0% marketplace cut.",
    )
    seller_fee_waiver_days = models.PositiveIntegerField(
        default=30,
        help_text="Length of new-seller fee waiver window in days.",
    )

    # -------------------------
    # Affiliate / Amazon Associates (sitewide)
    # -------------------------
    affiliate_links_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, show affiliate product links (e.g., Amazon Associates) in the store sidebar.",
    )
    affiliate_links_title = models.CharField(
        max_length=80,
        blank=True,
        default="Recommended Products",
        help_text="Sidebar section heading for affiliate links.",
    )
    affiliate_disclosure_text = models.CharField(
        max_length=240,
        blank=True,
        default="As an Amazon Associate I earn from qualifying purchases.",
        help_text="Short disclosure shown under the affiliate links (recommended).",
    )
    affiliate_links = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of links shown in the sidebar. Example item: "
            "{'label':'SUNLU PLA 1kg','url':'https://...','note':'Budget PLA+'} "
            "(label+url required; note optional)."
        ),
    )

    # Home page hero (marketing copy)
    home_hero_title = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Home page hero headline (left side).",
    )
    home_hero_subtitle = models.TextField(
        blank=True,
        default="",
        help_text="Home page hero paragraph (left side).",
    )

    # -------------------------
    # SEO / Sharing defaults
    # -------------------------
    seo_default_description = models.CharField(
        max_length=240,
        blank=True,
        default="",
        help_text="Default meta description used sitewide (can be overridden per page).",
    )
    seo_default_og_image_url = models.URLField(
        blank=True,
        default="",
        help_text="Absolute URL for the default OG/Twitter sharing image. Leave blank to use the bundled default.",
    )
    seo_twitter_handle = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Optional Twitter/X handle (without @) for twitter:site.",
    )

    # -------------------------
    # Analytics & Ads (managed)
    # -------------------------
    ga_measurement_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Optional GA4 Measurement ID (e.g., G-XXXX). Leave blank to disable.",
    )

    adsense_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, inject Google AdSense script sitewide.",
    )
    adsense_client_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="AdSense client id (e.g., ca-pub-...). Used only if AdSense is enabled.",
    )

    # Marketplace fee: percent of seller gross (e.g. 15.00 -> 15%)
    marketplace_sales_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("8.00"),
        help_text="Percent of sales withheld by the marketplace (e.g., 15.00 = 15%).",
    )

    # Optional fixed platform fee in cents (kept here even if you start at 0)
    platform_fee_cents = models.PositiveIntegerField(
        default=0,
        help_text="Optional fixed fee in cents added to each order (0 disables).",
    )

    # Currency defaults
    default_currency = models.CharField(
        max_length=8,
        default="usd",
        help_text="Default currency (Stripe-style), e.g. 'usd'.",
    )

    # Seller publishing policy (v1): allow a small number of free FILE listings
    # for sellers before Stripe onboarding is required.
    free_digital_listing_cap = models.PositiveIntegerField(
        default=5,
        help_text=(
            "Maximum number of active FREE FILE listings a seller may publish without Stripe onboarding. "
            "Set to 0 to require Stripe before any FREE FILE listings can be published."
        ),
    )

    # Shipping configuration
    # Store as JSON to avoid Postgres ArrayField dependency issues.
    allowed_shipping_countries = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allowed country codes for shipping (e.g. ['US']).",
    )

    # -------------------------
    # Age gating (v1)
    # -------------------------
    require_age_18 = models.BooleanField(
        default=True,
        help_text="(Deprecated) Previously gated buyers. Use seller age confirmation for seller onboarding.",
    )
    age_gate_text = models.CharField(
        max_length=240,
        blank=True,
        default="You must be 18+ to use this marketplace.",
        help_text="(Deprecated) Legacy buyer age gate message.",
    )

    # Seller onboarding policy (v1)
    seller_requires_age_18 = models.BooleanField(
        default=True,
        help_text="If enabled, sellers must confirm they are 18+ before starting Stripe onboarding.",
    )
    seller_prohibited_items_notice = models.CharField(
        max_length=240,
        blank=True,
        default="No tobacco, alcohol, or firearms are allowed on Local Market NE.",
        help_text="Shown to sellers during onboarding as a reminder of prohibited items.",
    )

    plausible_shared_url = models.URLField(
        blank=True,
        default="",
        help_text="Plausible shared dashboard URL (read-only). Example: https://plausible.io/share/<site>?auth=...",
    )

    google_analytics_dashboard_url = models.URLField(
        blank=True,
        default="",
        help_text="Google Analytics dashboard URL (for quick access from the admin dashboard).",
    )

    # -------------------------
    # Native Analytics (server-side, v1)
    # -------------------------
    analytics_enabled = models.BooleanField(
        default=True,
        help_text="If enabled, record lightweight pageview analytics for the admin dashboard.",
    )
    analytics_retention_days = models.PositiveIntegerField(
        default=90,
        help_text="How many days of analytics events to retain (pruned by management command).",
    )

    analytics_exclude_staff = models.BooleanField(
        default=True,
        help_text="If enabled, exclude staff/admin browsing from native analytics.",
    )
    analytics_exclude_admin_paths = models.BooleanField(
        default=True,
        help_text="If enabled, exclude /admin/ and /dashboard/ paths from native analytics.",
    )

    analytics_primary_host = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional: restrict native analytics reports to this host (e.g. localmarketne.com). Leave blank for all hosts.",
    )
    analytics_primary_environment = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Optional: restrict native analytics reports to this environment (e.g. production). Leave blank for all.",
    )

    # -------------------------
    # Theme / Branding (Palette A + Light/Dark)
    # -------------------------
    class ThemeMode(models.TextChoices):
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    theme_default_mode = models.CharField(
        max_length=10,
        choices=ThemeMode.choices,
        default=ThemeMode.LIGHT,
        help_text="Default mode for new visitors (users may toggle).",
    )

    # Brand tokens (Palette A)
    theme_primary = models.CharField(
        max_length=20,
        default="#F97316",  # burnt orange
        help_text="Primary action color (hex).",
    )
    theme_accent = models.CharField(
        max_length=20,
        default="#F97316",  # same as primary keeps it tight
        help_text="Accent color (hex).",
    )
    theme_success = models.CharField(
        max_length=20,
        default="#16A34A",
        help_text="Success color (hex).",
    )
    theme_danger = models.CharField(
        max_length=20,
        default="#DC2626",
        help_text="Danger color (hex).",
    )

    # Light mode surfaces
    theme_light_bg = models.CharField(
        max_length=20,
        default="#F9FAFB",
        help_text="Light mode background (hex).",
    )
    theme_light_surface = models.CharField(
        max_length=20,
        default="#FFFFFF",
        help_text="Light mode surface/card background (hex).",
    )
    theme_light_text = models.CharField(
        max_length=20,
        default="#111827",
        help_text="Light mode text color (hex).",
    )
    theme_light_text_muted = models.CharField(
        max_length=20,
        default="#6B7280",
        help_text="Light mode muted text (hex).",
    )
    theme_light_border = models.CharField(
        max_length=20,
        default="#E5E7EB",
        help_text="Light mode border color (hex).",
    )

    # Dark mode surfaces
    theme_dark_bg = models.CharField(
        max_length=20,
        default="#0B1220",
        help_text="Dark mode background (hex).",
    )
    theme_dark_surface = models.CharField(
        max_length=20,
        default="#111B2E",
        help_text="Dark mode surface/card background (hex).",
    )
    theme_dark_text = models.CharField(
        max_length=20,
        default="#EAF0FF",
        help_text="Dark mode text color (hex).",
    )
    theme_dark_text_muted = models.CharField(
        max_length=20,
        default="#9FB0D0",
        help_text="Dark mode muted text (hex).",
    )
    theme_dark_border = models.CharField(
        max_length=20,
        default="#22304D",
        help_text="Dark mode border color (hex).",
    )

    # Social media links (optional)
    facebook_url = models.URLField(blank=True, default="", help_text="Optional Facebook page URL for footer icon.")
    instagram_url = models.URLField(blank=True, default="", help_text="Optional Instagram profile URL for footer icon.")
    tiktok_url = models.URLField(blank=True, default="", help_text="Optional TikTok profile URL for footer icon.")
    youtube_url = models.URLField(blank=True, default="", help_text="Optional YouTube channel URL for footer icon.")
    x_url = models.URLField(blank=True, default="", help_text="Optional X (Twitter) profile URL for footer icon.")
    linkedin_url = models.URLField(blank=True, default="", help_text="Optional LinkedIn page URL for footer icon.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Config"
        verbose_name_plural = "Site Config"

    # Appointments
    appointment_reminders_enabled = models.BooleanField(default=True)
    appointment_reminder_hours_before = models.PositiveIntegerField(default=24)

    def __str__(self) -> str:
        return "SiteConfig"

    @property
    def allowed_shipping_countries_csv(self) -> str:
        try:
            codes = self.allowed_shipping_countries or []
            if not isinstance(codes, list):
                return ""
            cleaned = [str(x).strip().upper() for x in codes if str(x).strip()]
            return ",".join(cleaned)
        except Exception:
            return ""

    def clean(self) -> None:
        # Normalize JSON list field and defaults.
        try:
            codes = self.allowed_shipping_countries
            if not codes:
                self.allowed_shipping_countries = ["US"]
            elif isinstance(codes, list):
                cleaned = [str(x).strip().upper() for x in codes if str(x).strip()]
                self.allowed_shipping_countries = cleaned or ["US"]
            else:
                self.allowed_shipping_countries = ["US"]
        except Exception:
            self.allowed_shipping_countries = ["US"]

        # Clamp percent to sane bounds
        try:
            pct = Decimal(self.marketplace_sales_percent or Decimal("0"))
        except Exception:
            pct = Decimal("0")

        if pct < 0:
            self.marketplace_sales_percent = Decimal("0.00")
        elif pct > 100:
            self.marketplace_sales_percent = Decimal("100.00")

        # Clamp waiver days to sane bounds
        try:
            d = int(self.seller_fee_waiver_days or 0)
        except Exception:
            d = 0
        if d < 0:
            self.seller_fee_waiver_days = 0
        elif d > 365:
            self.seller_fee_waiver_days = 365

        # Banner housekeeping: clear text if checkbox is not checked
        self.promo_banner_text = (self.promo_banner_text or "").strip()
        if not self.promo_banner_enabled:
            self.promo_banner_text = ""

        self.home_banner_text = (self.home_banner_text or "").strip()
        if not self.home_banner_enabled:
            self.home_banner_text = ""


        # Site announcement housekeeping
        self.site_announcement_text = (self.site_announcement_text or "").strip()
        if not self.site_announcement_enabled:
            self.site_announcement_text = ""

        # Maintenance message housekeeping
        self.maintenance_mode_message = (self.maintenance_mode_message or "").strip() or "We’re performing maintenance. Please check back soon."

        # Featured lists normalization
        try:
            raw_users = self.featured_seller_usernames or []
            if isinstance(raw_users, list):
                cleaned_users = [str(u).strip() for u in raw_users if str(u).strip()]
                self.featured_seller_usernames = cleaned_users
            else:
                self.featured_seller_usernames = []
        except Exception:
            self.featured_seller_usernames = []

        try:
            raw_cats = self.featured_category_ids or []
            if isinstance(raw_cats, list):
                cleaned_ids = []
                for x in raw_cats:
                    try:
                        cleaned_ids.append(int(x))
                    except Exception:
                        continue
                self.featured_category_ids = cleaned_ids
            else:
                self.featured_category_ids = []
        except Exception:
            self.featured_category_ids = []

        # Affiliate links normalization
        self.affiliate_links_title = (self.affiliate_links_title or "").strip() or "Recommended Local Resources"
        self.affiliate_disclosure_text = (self.affiliate_disclosure_text or "").strip()

        cleaned_links: list[dict[str, str]] = []
        try:
            raw = self.affiliate_links or []
            if isinstance(raw, list):
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get("label", "") or "").strip()
                    url = str(item.get("url", "") or "").strip()
                    note = str(item.get("note", "") or "").strip()
                    if not label or not url:
                        continue
                    cleaned_links.append({"label": label, "url": url, "note": note})
        except Exception:
            cleaned_links = []

        self.affiliate_links = cleaned_links

        # If disabled, keep data but ensure title is sane; you can decide later to blank it.
        # We won't auto-clear links so you can toggle on/off without losing work.

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Enforce singleton row (pk=1) so dashboard/admin always edit the same record.
        if not self.pk or self.pk != 1:
            self.pk = 1

        self.clean()
        super().save(*args, **kwargs)

        # STRICT cache invalidation (no stale settings)
        try:
            from .config import invalidate_site_config_cache

            invalidate_site_config_cache()
        except Exception:
            pass

class StaffActionLog(models.Model):
    """Staff/admin action log (v1: moderation + sensitive actions).

    Provides a minimal audit trail for actions taken by staff, including Q&A moderation.
    """

    class Action(models.TextChoices):
        QA_REPORT_RESOLVED = "qa_report_resolved", "Q&A report resolved"
        QA_MESSAGE_REMOVED = "qa_message_removed", "Q&A message removed"
        USER_SUSPENDED = "user_suspended", "User suspended"
        USER_UNSUSPENDED = "user_unsuspended", "User unsuspended"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_actions",
        help_text="Staff user who performed the action.",
    )

    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)

    # Optional targets
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_actions_targeted",
    )
    qa_report = models.ForeignKey(
        "qa.ProductQuestionReport",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_actions",
    )
    qa_message = models.ForeignKey(
        "qa.ProductQuestionMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_actions",
    )

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    # Appointments
    appointment_reminders_enabled = models.BooleanField(default=True)
    appointment_reminder_hours_before = models.PositiveIntegerField(default=24)

    def __str__(self) -> str:
        return f"StaffAction<{self.pk}> {self.action}"



class WaitlistEntry(models.Model):
    """Simple email waitlist signup used by Coming Soon pages.

    This is intentionally minimal (v1): capture interest without creating a full marketing stack.
    """

    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    source_path = models.CharField(max_length=200, blank=True, default="")
    user_agent = models.CharField(max_length=240, blank=True, default="")
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    def __str__(self) -> str:
        return self.email


class ContactMessage(models.Model):
    """Public contact form submission (v1).

    Stored for staff review and (optionally) emailed to support.
    """

    name = models.CharField(max_length=120, blank=True, default="")
    email = models.EmailField()
    subject = models.CharField(max_length=160, blank=True, default="")
    message = models.TextField(max_length=4000)

    created_at = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_messages",
    )

    source_path = models.CharField(max_length=200, blank=True, default="")
    user_agent = models.CharField(max_length=240, blank=True, default="")
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    class SLATag(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    sla_tag = models.CharField(
        max_length=20,
        choices=SLATag.choices,
        default=SLATag.NORMAL,
        help_text="Internal triage label for response urgency.",
    )

    internal_notes = models.TextField(blank=True, default="")

    last_responded_at = models.DateTimeField(blank=True, null=True)
    last_responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responded_contact_messages",
    )
    response_count = models.PositiveIntegerField(default=0)

    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_contact_messages",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        base = self.email
        if self.subject:
            base = f"{base} — {self.subject}"
        return base


class SupportResponseTemplate(models.Model):
    """Staff-facing canned responses for the Support Inbox."""

    title = models.CharField(max_length=120)
    subject = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField(max_length=6000)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class SupportOutboundEmailLog(models.Model):
    """Audit-friendly record of outbound support emails (v1).

    This is intentionally minimal: we capture what we attempted to send and whether
    it succeeded, so staff can reconcile "did we reply" without relying solely on
    external email logs.
    """

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    contact_message = models.ForeignKey(
        ContactMessage,
        on_delete=models.CASCADE,
        related_name="outbound_emails",
    )

    to_email = models.EmailField()
    from_email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField(max_length=8000)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SENT)
    error_text = models.TextField(blank=True, default="")

    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_outbound_emails",
    )
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self) -> str:
        return f"SupportOutboundEmailLog<{self.pk}> {self.to_email} ({self.status})"


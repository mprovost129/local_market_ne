# dashboards/forms.py
from __future__ import annotations

from typing import Any

from django import forms

from core.models import SiteConfig


class SiteConfigForm(forms.ModelForm):
    """
    Dashboard Admin Settings form for the singleton SiteConfig.

    IMPORTANT:
    - This form must persist changes reliably (no Django-admin required).
    - We keep a couple of "UI helper" fields (CSV / repeated rows) and translate
      them into real model fields in save().
    """

    allowed_shipping_countries_csv = forms.CharField(
        required=False,
        help_text="Comma-separated country codes (e.g. US,CA). Leave blank to default to US.",
        widget=forms.TextInput(attrs={"class": "form-control bg-white", "placeholder": "US"}),
    )

    # Affiliate links (friendly UI) -> stored as JSON list in SiteConfig.affiliate_links
    AFFILIATE_LINK_ROWS = 10

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Ensure core styling for common fields
        for name, field in self.fields.items():
            # Don't stomp explicit widget classes
            cls = field.widget.attrs.get("class", "")
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", ("form-control " + cls).strip())

        # Support email styling
        if "support_email" in self.fields:
            self.fields["support_email"].widget.attrs.update(
                {"class": "form-control bg-white", "placeholder": "support@localmarketne.com"}
            )

        # Add repeated affiliate link rows
        self._add_affiliate_link_fields()

        inst: SiteConfig | None = getattr(self, "instance", None)
        if inst and inst.pk:
            countries = getattr(inst, "allowed_shipping_countries", None) or ["US"]
            self.fields["allowed_shipping_countries_csv"].initial = ",".join([str(x).strip() for x in countries if str(x).strip()])

            # Populate affiliate link rows
            links = list(getattr(inst, "affiliate_links", None) or [])
            for idx, item in enumerate(links[: self.AFFILIATE_LINK_ROWS], start=1):
                if not isinstance(item, dict):
                    continue
                self.fields[f"affiliate_link_{idx}_label"].initial = str(item.get("label", "") or "")
                self.fields[f"affiliate_link_{idx}_url"].initial = str(item.get("url", "") or "")
                self.fields[f"affiliate_link_{idx}_note"].initial = str(item.get("note", "") or "")

    def _add_affiliate_link_fields(self) -> None:
        for i in range(1, self.AFFILIATE_LINK_ROWS + 1):
            self.fields[f"affiliate_link_{i}_label"] = forms.CharField(
                required=False,
                widget=forms.TextInput(attrs={"class": "form-control bg-white", "placeholder": "Title"}),
            )
            self.fields[f"affiliate_link_{i}_url"] = forms.URLField(
                required=False,
                widget=forms.URLInput(attrs={"class": "form-control bg-white", "placeholder": "https://…"}),
            )
            self.fields[f"affiliate_link_{i}_note"] = forms.CharField(
                required=False,
                widget=forms.TextInput(attrs={"class": "form-control bg-white", "placeholder": "Optional details"}),
            )

    class Meta:
        model = SiteConfig
        fields = [
            # Promo banner (sitewide above navbar)
            "promo_banner_enabled",
            "promo_banner_text",

            # Home page banner (home page only)
            "home_banner_enabled",
            "home_banner_text",

            # Site announcement / maintenance
            "site_announcement_enabled",
            "site_announcement_text",
            "maintenance_mode_enabled",
            "maintenance_mode_message",
            "checkout_enabled",
            "checkout_disabled_message",

            # Environment banner
            "environment_banner_enabled",
            "environment_banner_text",

            # Seller waiver promo
            "seller_fee_waiver_enabled",
            "seller_fee_waiver_days",

            # Affiliate / Amazon Associates
            "affiliate_links_enabled",
            "affiliate_links_title",
            "affiliate_disclosure_text",

            # Marketplace
            "marketplace_sales_percent",
            "platform_fee_cents",
            "free_digital_listing_cap",

            # Currency / shipping
            "default_currency",
            "allowed_shipping_countries_csv",

            # Analytics
            "google_analytics_dashboard_url",
            "analytics_enabled",
            "analytics_retention_days",
            "analytics_exclude_staff",
            "analytics_exclude_admin_paths",
            "analytics_primary_host",
            "analytics_primary_environment",
            "ga_measurement_id",
            "plausible_shared_url",
            "adsense_enabled",
            "adsense_client_id",

            # Seller onboarding policy
            "seller_requires_age_18",
            "seller_prohibited_items_notice",

            # Support
            "support_email",
            "support_form_enabled",
            "support_store_messages",
            "support_send_email",
            "support_admin_notify_enabled",
            "support_admin_email",
            "support_auto_reply_enabled",
            "support_auto_reply_subject",
            "support_auto_reply_body",

            # Waitlist
            "waitlist_enabled",
            "waitlist_send_confirmation",
            "waitlist_admin_notify_enabled",
            "waitlist_admin_email",
            "waitlist_confirmation_subject",
            "waitlist_confirmation_body",

            # Home hero (these are model fields)
            "home_hero_title",
            "home_hero_subtitle",

            # SEO
            "seo_default_description",
            "seo_default_og_image_url",
            "seo_twitter_handle",

            # Theme
            "theme_default_mode",
            "theme_primary",
            "theme_accent",
            "theme_success",
            "theme_danger",
            "theme_light_bg",
            "theme_light_surface",
            "theme_light_text",
            "theme_light_text_muted",
            "theme_light_border",
            "theme_dark_bg",
            "theme_dark_surface",
            "theme_dark_text",
            "theme_dark_text_muted",
            "theme_dark_border",

            # Social
            "facebook_url",
            "instagram_url",
            "tiktok_url",
            "youtube_url",
            "x_url",
            "linkedin_url",
        ]

        widgets = {
            "promo_banner_text": forms.TextInput(attrs={"class": "form-control", "placeholder": "Example: Sellers pay 0% fees for 30 days!"}),
            "home_banner_text": forms.TextInput(attrs={"class": "form-control", "placeholder": "Example: First 30 days FREE!"}),
            "seller_fee_waiver_days": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 365}),
            "marketplace_sales_percent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0, "max": 100}),
            "platform_fee_cents": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "free_digital_listing_cap": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 1000}),
            "analytics_retention_days": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 3650}),
            "seo_default_og_image_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://…/og.png"}),
            "home_hero_subtitle": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "support_auto_reply_body": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "waitlist_confirmation_body": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def clean_allowed_shipping_countries_csv(self) -> list[str]:
        raw = (self.cleaned_data.get("allowed_shipping_countries_csv") or "").strip()
        if not raw:
            return ["US"]
        parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
        return parts or ["US"]

    def _build_affiliate_links(self) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        for i in range(1, self.AFFILIATE_LINK_ROWS + 1):
            label = (self.cleaned_data.get(f"affiliate_link_{i}_label") or "").strip()
            url = (self.cleaned_data.get(f"affiliate_link_{i}_url") or "").strip()
            note = (self.cleaned_data.get(f"affiliate_link_{i}_note") or "").strip()
            if not label and not url and not note:
                continue
            if not label or not url:
                raise forms.ValidationError("Each affiliate link row must include both a title and a URL.")
            item: dict[str, str] = {"label": label, "url": url}
            if note:
                item["note"] = note
            links.append(item)
        return links

    def save(self, commit: bool = True) -> SiteConfig:
        obj: SiteConfig = super().save(commit=False)

        # Countries -> real JSON model field
        obj.allowed_shipping_countries = self.cleaned_data.get("allowed_shipping_countries_csv") or ["US"]

        # Affiliate links JSON
        obj.affiliate_links = self._build_affiliate_links()

        # Housekeeping (ensure these are consistent even if browser omits unchecked checkboxes)
        obj.promo_banner_text = (obj.promo_banner_text or "").strip()
        if not obj.promo_banner_enabled:
            obj.promo_banner_text = ""

        obj.home_banner_text = (obj.home_banner_text or "").strip()
        if not obj.home_banner_enabled:
            obj.home_banner_text = ""

        obj.site_announcement_text = (obj.site_announcement_text or "").strip()
        if not obj.site_announcement_enabled:
            obj.site_announcement_text = ""

        if commit:
            obj.save()

        return obj

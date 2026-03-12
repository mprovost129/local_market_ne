# accounts/models.py
from __future__ import annotations

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


US_STATES = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
    ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"),
    ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"),
    ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"),
    ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"),
    ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
    ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"),
    ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
    ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"),
    ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"),
    ("WI", "Wisconsin"), ("WY", "Wyoming"),
    ("DC", "District of Columbia"),
]

STORE_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Enter a valid hex color like #2F4F2F.",
)


class Profile(models.Model):
    class StorefrontLayout(models.TextChoices):
        BALANCED = "balanced", "Balanced"
        CATALOG = "catalog", "Catalog focus"
        MINIMAL = "minimal", "Minimal"

    # Public profile fields
    bio = models.TextField(blank=True, help_text="Short public bio/about for your shop.")
    website = models.URLField(blank=True, help_text="Personal or shop website.")
    social_instagram = models.URLField(blank=True, help_text="Instagram profile URL.")
    social_twitter = models.URLField(blank=True, help_text="Twitter/X profile URL.")
    social_facebook = models.URLField(blank=True, help_text="Facebook profile URL.")
    social_youtube = models.URLField(blank=True, help_text="YouTube channel URL.")
    storefront_theme_enabled = models.BooleanField(
        default=False,
        help_text="Allow your storefront to use your custom branding color.",
    )
    storefront_layout = models.CharField(
        max_length=16,
        choices=StorefrontLayout.choices,
        default=StorefrontLayout.BALANCED,
        help_text="Choose a storefront layout style.",
    )
    storefront_primary_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        validators=[STORE_COLOR_VALIDATOR],
        help_text="Storefront accent color in hex (example: #2F4F2F).",
    )
    storefront_logo = models.ImageField(
        upload_to="storefront/logos/",
        blank=True,
        null=True,
        help_text="Optional storefront logo shown on your shop header.",
    )
    storefront_banner = models.ImageField(
        upload_to="storefront/banners/",
        blank=True,
        null=True,
        help_text="Optional storefront banner image shown on your shop header.",
    )

    # Optional off-platform payment handles (shown on shop page + checkout instructions)
    venmo_handle = models.CharField(max_length=64, blank=True, default="", help_text="Optional Venmo handle (no @).")
    paypal_me_url = models.URLField(blank=True, default="", help_text="Optional PayPal.me URL.")
    zelle_contact = models.CharField(max_length=120, blank=True, default="", help_text="Optional Zelle contact (email).")
    cashapp_handle = models.CharField(max_length=64, blank=True, default="", help_text="Optional Cash App handle (no $).")

    # QR display toggles (per-app). Defaults OFF to avoid storefront clutter.
    show_venmo_qr_storefront = models.BooleanField(default=False)
    show_paypal_qr_storefront = models.BooleanField(default=False)
    show_zelle_qr_storefront = models.BooleanField(default=False)
    show_cashapp_qr_storefront = models.BooleanField(default=False)

    # Checkout QR only appears for off-platform payment flow. Defaults OFF.
    show_venmo_qr_checkout = models.BooleanField(default=False)
    show_paypal_qr_checkout = models.BooleanField(default=False)
    show_zelle_qr_checkout = models.BooleanField(default=False)
    show_cashapp_qr_checkout = models.BooleanField(default=False)
    """Marketplace Profile.

    Extends the configured AUTH_USER_MODEL with marketplace-specific profile data and role flags.

    Roles:
      - Consumer: default for any registered user
      - Seller: can list products (requires Stripe onboarding later)
      - Owner/Admin: full permissions; should be your account (can be enforced via superuser/staff too)

    Notes:
      - Public identity is username.
      - Profile is created automatically via signal (Option A).

    Seller identity:
      - Some sellers are individuals; others are a "shop".
      - `shop_name` is an optional *public* label used across the marketplace.
        If blank, we fall back to username.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")

    # Contact / identity
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    # Seller-facing identity (public)
    shop_name = models.CharField(
        max_length=80,
        blank=True,
        help_text="Optional public shop name. If blank, your username is shown.",
    )

    # Seller public location (approximate). Do NOT store exact address here.
    public_city = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional public city shown on your storefront (approximate).",
    )
    public_state = models.CharField(
        max_length=2,
        blank=True,
        choices=US_STATES,
        help_text="Optional public state shown on your storefront (approximate).",
    )
    show_business_address_public = models.BooleanField(
        default=False,
        help_text="If enabled, your business address is shown publicly on your storefront/listings.",
    )

    # Service providers: service area radius (miles). Used for ZIP-based browse matching.
    service_radius_miles = models.PositiveIntegerField(
        default=0,
        help_text="Service providers: service radius in miles (0 = not set).",
    )

    # Used for correspondence; username is public
    email = models.EmailField(blank=True)

    # Email verification (LOCKED: gated actions require verified email)
    email_verified = models.BooleanField(default=False)
    email_verification_token = models.UUIDField(null=True, blank=True, db_index=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)

    # Age gating (v1)
    is_age_18_confirmed = models.BooleanField(default=False)
    age_18_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Seller policy acknowledgements (v1)
    seller_prohibited_items_ack = models.BooleanField(default=False)
    seller_prohibited_items_ack_at = models.DateTimeField(null=True, blank=True)

    phone_regex = RegexValidator(
        regex=r"^[0-9\-\+\(\) ]{7,20}$",
        message="Enter a valid phone number (digits and - + ( ) allowed).",
    )
    phone_1 = models.CharField(max_length=20, blank=True, validators=[phone_regex])
    phone_2 = models.CharField(max_length=20, blank=True, validators=[phone_regex])

    address_1 = models.CharField(max_length=255, blank=True)
    address_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)

    state = models.CharField(max_length=2, blank=True, choices=US_STATES)
    zip_code = models.CharField(max_length=10, blank=True)
    private_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Private seller latitude for internal geo matching. Never shown publicly.",
    )
    private_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Private seller longitude for internal geo matching. Never shown publicly.",
    )
    private_geo_updated_at = models.DateTimeField(null=True, blank=True)

    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    # Role flags
    is_seller = models.BooleanField(default=False)
    is_owner = models.BooleanField(default=False)  # Owner/admin override in UI

    # Stripe (legacy placeholders; primary source of truth is payments.SellerStripeAccount)
    stripe_account_id = models.CharField(max_length=255, blank=True)
    stripe_onboarding_complete = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_seller"]),
            models.Index(fields=["is_owner"]),
            models.Index(fields=["shop_name"]),
            models.Index(fields=["public_state", "public_city"]),
            models.Index(fields=["is_age_18_confirmed"]),
        ]

    def __str__(self) -> str:
        return f"Profile<{self.user.username}>"

    @property
    def display_name(self) -> str:
        # Public identity is username; name is optional
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.user.username

    @property
    def public_seller_name(self) -> str:
        """Public seller label used across the marketplace."""
        return (self.shop_name or "").strip() or self.user.username

    @property
    def public_location_label(self) -> str:
        """Public, approximate seller location label (city/state)."""
        city = (self.public_city or "").strip()
        state = (self.public_state or "").strip()
        if city and state:
            return f"{city}, {state}"
        if city:
            return city
        if state:
            return state
        return ""

    @property
    def public_business_address_label(self) -> str:
        """Public full address label when seller explicitly opts in."""
        if not bool(self.show_business_address_public):
            return ""
        line1 = (self.address_1 or "").strip()
        city = (self.city or "").strip()
        state = (self.state or "").strip()
        postal = (self.zip_code or "").strip()
        if not line1 or not city or not state:
            return ""
        if postal:
            return f"{line1}, {city}, {state} {postal}"
        return f"{line1}, {city}, {state}"

    @property
    def public_location_display(self) -> str:
        """
        Public location text used on cards/storefronts.
        Default is approximate city/state, with optional full business address opt-in.
        """
        full = self.public_business_address_label
        if full:
            return full
        approx = self.public_location_label
        if approx:
            return approx
        city = (self.city or "").strip()
        state = (self.state or "").strip()
        if city and state:
            return f"{city}, {state}"
        return city or state

    @property
    def can_access_seller_dashboard(self) -> bool:
        return self.is_owner or self.user.is_superuser or self.user.is_staff or self.is_seller

    @property
    def can_access_consumer_dashboard(self) -> bool:
        return self.user.is_authenticated

    @property
    def can_access_admin_dashboard(self) -> bool:
        return self.is_owner or self.user.is_superuser or self.user.is_staff

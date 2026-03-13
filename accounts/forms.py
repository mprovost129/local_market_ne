# accounts/forms.py
from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Profile


User = get_user_model()


class UsernameAuthenticationForm(AuthenticationForm):
    """Standard username/password login form (Django default)."""

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "Username"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for _, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = (field.widget.attrs.get("class", "") + " form-check-input").strip()
            else:
                field.widget.attrs["class"] = (field.widget.attrs.get("class", "") + " form-control").strip()


class RegisterForm(UserCreationForm):
    """
    Registration form.

    - username is required (public identity)
    - optional first/last/email
    - all users start as consumers
    - profile stores email (seller onboarding happens later from dashboard)
    """

    first_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "First name"}),
    )
    last_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Last name"}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "Email"}),
    )

    confirm_age_18 = forms.BooleanField(
        required=True,
        initial=False,
        help_text="You must confirm you are 18+ to use the marketplace.",
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for _, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = (field.widget.attrs.get("class", "") + " form-check-input").strip()
            else:
                field.widget.attrs["class"] = (field.widget.attrs.get("class", "") + " form-control").strip()

    def clean(self):
        return super().clean()

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def save(self, commit: bool = True):
        user = super().save(commit=False)

        # Optional identity fields
        user.first_name = (self.cleaned_data.get("first_name") or "").strip()
        user.last_name = (self.cleaned_data.get("last_name") or "").strip()

        email = (self.cleaned_data.get("email") or "").strip()
        if hasattr(user, "email"):
            user.email = email

        if commit:
            user.save()

        # Profile is created via signal; seed it with registration details.
        profile = getattr(user, "profile", None)
        if profile is not None:
            profile.email = email
            profile.is_seller = False
            if bool(self.cleaned_data.get("confirm_age_18")):
                from django.utils import timezone
                profile.is_age_18_confirmed = True
                profile.age_18_confirmed_at = timezone.now()
                profile.save(update_fields=["email", "is_seller", "is_age_18_confirmed", "age_18_confirmed_at", "updated_at"])
            else:
                profile.save(update_fields=["email", "is_seller", "updated_at"])

        return user


class ConsumerProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "first_name",
            "last_name",
            "phone_1",
            "address_1",
            "address_2",
            "city",
            "state",
            "zip_code",
            "avatar",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"placeholder": "Last name"}),
            "phone_1": forms.TextInput(attrs={"placeholder": "Phone 1"}),
            "address_1": forms.TextInput(attrs={"placeholder": "Address 1"}),
            "address_2": forms.TextInput(attrs={"placeholder": "Address 2"}),
            "city": forms.TextInput(attrs={"placeholder": "City"}),
            "zip_code": forms.TextInput(attrs={"placeholder": "ZIP"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Bootstrap-friendly widget styling
        for name, field in list(self.fields.items()):
            if isinstance(field.widget, forms.CheckboxInput):
                cls = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (cls + " form-check-input").strip()
            elif isinstance(field.widget, forms.FileInput):
                cls = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (cls + " form-control").strip()
            else:
                cls = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (cls + " form-control").strip()

        # Owner/admin flags should not be editable here
        if "is_owner" in self.fields:
            self.fields.pop("is_owner")

    def clean(self):
        cleaned = super().clean()
        raw_zip = (cleaned.get("zip_code") or "").strip()
        if raw_zip:
            import re
            if not re.fullmatch(r"^\d{5}(-\d{4})?$", raw_zip):
                self.add_error("zip_code", "Enter a valid ZIP code (e.g., 02860 or 02860-1234).")
        return cleaned


class StoreProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "shop_name",
            "bio",
            "website",
            "social_instagram",
            "social_twitter",
            "social_facebook",
            "social_youtube",
            "storefront_theme_enabled",
            "storefront_layout",
            "storefront_primary_color",
            "storefront_logo",
            "storefront_banner",
            "public_city",
            "public_state",
            "show_business_address_public",
            "service_radius_miles",
            "address_1",
            "address_2",
            "city",
            "state",
            "zip_code",
            "venmo_handle",
            "paypal_me_url",
            "zelle_contact",
            "cashapp_handle",
            "show_venmo_qr_storefront",
            "show_paypal_qr_storefront",
            "show_zelle_qr_storefront",
            "show_cashapp_qr_storefront",
            "show_venmo_qr_checkout",
            "show_paypal_qr_checkout",
            "show_zelle_qr_checkout",
            "show_cashapp_qr_checkout",
        ]
        widgets = {
            "shop_name": forms.TextInput(attrs={"placeholder": "Shop name (optional)"}),
            "bio": forms.Textarea(attrs={"rows": 3, "placeholder": "Short public bio about your shop"}),
            "website": forms.URLInput(attrs={"placeholder": "https://"}),
            "social_instagram": forms.URLInput(attrs={"placeholder": "Instagram URL"}),
            "social_twitter": forms.URLInput(attrs={"placeholder": "Twitter/X URL"}),
            "social_facebook": forms.URLInput(attrs={"placeholder": "Facebook URL"}),
            "social_youtube": forms.URLInput(attrs={"placeholder": "YouTube URL"}),
            "storefront_layout": forms.Select(),
            "storefront_primary_color": forms.TextInput(attrs={"type": "color"}),
            "storefront_logo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "storefront_banner": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "public_city": forms.TextInput(attrs={"placeholder": "Public city (shown on storefront)"}),
            "service_radius_miles": forms.NumberInput(attrs={"min": 0, "placeholder": "0"}),
            "address_1": forms.TextInput(attrs={"placeholder": "Business address line 1"}),
            "address_2": forms.TextInput(attrs={"placeholder": "Business address line 2"}),
            "city": forms.TextInput(attrs={"placeholder": "Business city"}),
            "zip_code": forms.TextInput(attrs={"placeholder": "ZIP"}),
            "venmo_handle": forms.TextInput(attrs={"placeholder": "Venmo handle (no @)"}),
            "paypal_me_url": forms.URLInput(attrs={"placeholder": "PayPal.me URL"}),
            "zelle_contact": forms.TextInput(attrs={"placeholder": "Zelle contact (email)"}),
            "cashapp_handle": forms.TextInput(attrs={"placeholder": "Cash App handle (no $)"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        for _, field in list(self.fields.items()):
            if isinstance(field.widget, forms.CheckboxInput):
                cls = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (cls + " form-check-input").strip()
            elif isinstance(field.widget, forms.FileInput):
                cls = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (cls + " form-control").strip()
            else:
                cls = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (cls + " form-control").strip()

    def clean(self):
        cleaned = super().clean()
        raw_zip = (cleaned.get("zip_code") or "").strip()
        if not raw_zip:
            self.add_error("zip_code", "ZIP code is required for seller accounts.")
            return cleaned
        import re
        if not re.fullmatch(r"^\d{5}(-\d{4})?$", raw_zip):
            self.add_error("zip_code", "Enter a valid ZIP code (e.g., 02860 or 02860-1234).")
        # Keep public city/state populated from business address when omitted.
        if not (cleaned.get("public_city") or "").strip():
            cleaned["public_city"] = (cleaned.get("city") or "").strip()
        if not (cleaned.get("public_state") or "").strip():
            cleaned["public_state"] = (cleaned.get("state") or "").strip()
        return cleaned

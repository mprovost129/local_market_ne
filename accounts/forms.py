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
    - user chooses consumer or seller
    - profile stores email + role flags (seeded at registration; rest optional)
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

    register_as_seller = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Check this if you want to register as a seller (Stripe onboarding required later).",
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
        cleaned_data = super().clean()
        register_as_seller = cleaned_data.get("register_as_seller")
        email = (cleaned_data.get("email") or "").strip()
        
        # Require email if registering as seller
        if register_as_seller and not email:
            raise forms.ValidationError("Email is required when registering as a seller.")
        
        return cleaned_data

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
            profile.is_seller = bool(self.cleaned_data.get("register_as_seller", False))
            if bool(self.cleaned_data.get("confirm_age_18")):
                from django.utils import timezone
                profile.is_age_18_confirmed = True
                profile.age_18_confirmed_at = timezone.now()
                profile.save(update_fields=["email", "is_seller", "is_age_18_confirmed", "age_18_confirmed_at", "updated_at"])
            else:
                profile.save(update_fields=["email", "is_seller", "updated_at"])

        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            # Public seller identity / storefront
            "shop_name",
            "bio",
            "website",
            "social_instagram",
            "social_twitter",
            "social_facebook",
            "social_youtube",
            # Off-platform payment handles (optional)
            "venmo_handle",
            "paypal_me_url",
            "zelle_contact",
            "cashapp_handle",
            # QR display toggles (per app)
            "show_venmo_qr_storefront",
            "show_paypal_qr_storefront",
            "show_zelle_qr_storefront",
            "show_cashapp_qr_storefront",
            "show_venmo_qr_checkout",
            "show_paypal_qr_checkout",
            "show_zelle_qr_checkout",
            "show_cashapp_qr_checkout",
            # Approximate public location
            "public_city",
            "public_state",
            "service_radius_miles",
            "first_name",
            "last_name",
            "email",
            "phone_1",
            "phone_2",
            "address_1",
            "address_2",
            "city",
            "state",
            "zip_code",
            "avatar",
            "is_seller",  # allow opt-in; Stripe gating happens elsewhere
        ]
        widgets = {
            "shop_name": forms.TextInput(attrs={"placeholder": "Shop name (optional)"}),
            "bio": forms.Textarea(attrs={"rows": 3, "placeholder": "Short public bio about your shop"}),
            "website": forms.URLInput(attrs={"placeholder": "https://"}),
            "social_instagram": forms.URLInput(attrs={"placeholder": "Instagram URL"}),
            "social_twitter": forms.URLInput(attrs={"placeholder": "Twitter/X URL"}),
            "social_facebook": forms.URLInput(attrs={"placeholder": "Facebook URL"}),
            "social_youtube": forms.URLInput(attrs={"placeholder": "YouTube URL"}),
            "venmo_handle": forms.TextInput(attrs={"placeholder": "Venmo handle (no @)"}),
            "paypal_me_url": forms.URLInput(attrs={"placeholder": "PayPal.me URL"}),
            "zelle_contact": forms.TextInput(attrs={"placeholder": "Zelle contact (email)"}),
            "cashapp_handle": forms.TextInput(attrs={"placeholder": "Cash App handle (no $)"}),
            "public_city": forms.TextInput(attrs={"placeholder": "Public city (approximate)"}),
            "service_radius_miles": forms.NumberInput(attrs={"min": 0, "placeholder": "0"}),
            "first_name": forms.TextInput(attrs={"placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"placeholder": "Last name"}),
            "email": forms.EmailInput(attrs={"placeholder": "Email"}),
            "phone_1": forms.TextInput(attrs={"placeholder": "Phone 1"}),
            "phone_2": forms.TextInput(attrs={"placeholder": "Phone 2"}),
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

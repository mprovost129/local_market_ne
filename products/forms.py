# products/forms.py
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import List

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.text import slugify

from catalog.models import Category
from .models import Product, ProductImage


def _validate_image(file_obj) -> None:
    if not file_obj:
        return
    name = getattr(file_obj, "name", "") or ""
    ext = Path(name).suffix.lower().lstrip(".")
    if ext not in {"jpg", "jpeg", "png", "webp"}:
        raise ValidationError(f"Unsupported image type .{ext or '?'}")


class MultiFileInput(forms.FileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        attrs = dict(attrs or {})
        attrs["multiple"] = True
        super().__init__(attrs)


class MultiImageField(forms.ImageField):
    """Image field that accepts multiple uploaded files via MultiFileInput."""

    widget = MultiFileInput

    def clean(self, data, initial=None):
        if isinstance(data, (list, tuple)):
            files = list(data)
        elif data:
            files = [data]
        else:
            files = []

        if self.required and not files:
            raise ValidationError("Please select one or more images.")

        cleaned: list = []
        for f in files:
            cleaned.append(super().clean(f, initial))
        return cleaned


class ProductForm(forms.ModelForm):
    # Currency helper inputs (stored as cents on model)
    service_deposit_dollars = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=10,
        help_text="Optional deposit collected at checkout (Stripe).",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
    )
    delivery_fee_dollars = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=10,
        help_text="Optional local delivery fee (only used if delivery is enabled).",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
    )
    shipping_fee_dollars = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=10,
        help_text="Optional shipping fee (only used if shipping is enabled).",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
    )

    class Meta:
        model = Product
        fields = [
            "kind",
            "category",
            "subcategory",
            "title",
            "short_description",
            "description",
            "price",
            "is_free",
            "is_active",
            "slug",
            # goods
            "stock_qty",
            "is_made_to_order",
            "lead_time_days",
            "fulfillment_pickup_enabled",
            "fulfillment_delivery_enabled",
            "fulfillment_shipping_enabled",
            "pickup_instructions",
            "delivery_radius_miles",
            # services
            "service_duration_minutes",
            "service_cancellation_policy",
            "service_cancellation_window_hours",
        ]
        widgets = {
            "kind": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "subcategory": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "short_description": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "is_free": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "stock_qty": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0"}),
            "is_made_to_order": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "lead_time_days": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0"}),
            "fulfillment_pickup_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "fulfillment_delivery_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "fulfillment_shipping_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "pickup_instructions": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "delivery_radius_miles": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0"}),
            "service_duration_minutes": forms.NumberInput(attrs={"class": "form-control", "step": "15", "min": "15"}),
            "service_cancellation_policy": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "service_cancellation_window_hours": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Wire AJAX endpoints for the seller listing form JS.
        self.fields["category"].widget.attrs["data-category-endpoint"] = reverse("catalog:api_categories")
        self.fields["subcategory"].widget.attrs["data-subcategory-endpoint"] = reverse("catalog:api_subcategories")

        # Category pickers (filtered by kind and selected category)
        raw_kind = (
            (self.data.get("kind") if hasattr(self, "data") else None)
            or getattr(getattr(self, "instance", None), "kind", None)
            or Product.Kind.GOOD
        )
        kind = str(raw_kind).upper()
        if kind not in (Product.Kind.GOOD, Product.Kind.SERVICE):
            kind = Product.Kind.GOOD

        # Prevent hidden kind-specific fields from being treated as required.
        is_service = kind == Product.Kind.SERVICE
        self.fields["service_duration_minutes"].required = is_service
        self.fields["service_cancellation_window_hours"].required = is_service

        self.fields["category"].queryset = (
            Category.objects.filter(parent__isnull=True, type=kind, is_active=True)
            .order_by("sort_order", "name")
        )

        # Subcategories should be constrained to the selected category (or empty when none selected).
        selected_category_id = (self.data.get("category") if hasattr(self, "data") else None) or getattr(
            getattr(getattr(self, "instance", None), "category", None), "id", None
        )
        if selected_category_id:
            self.fields["subcategory"].queryset = (
                Category.objects.filter(parent_id=selected_category_id, is_active=True)
                .order_by("sort_order", "name")
            )
        else:
            self.fields["subcategory"].queryset = Category.objects.none()

        # Initialize dollar fields from cents
        inst: Product | None = getattr(self, "instance", None)
        if inst and inst.pk:
            self.fields["service_deposit_dollars"].initial = Decimal(inst.service_deposit_cents or 0) / Decimal("100")
            self.fields["delivery_fee_dollars"].initial = Decimal(inst.delivery_fee_cents or 0) / Decimal("100")
            self.fields["shipping_fee_dollars"].initial = Decimal(inst.shipping_fee_cents or 0) / Decimal("100")
        else:
            self.fields["service_deposit_dollars"].initial = Decimal("0.00")
            self.fields["delivery_fee_dollars"].initial = Decimal("0.00")
            self.fields["shipping_fee_dollars"].initial = Decimal("0.00")

    def clean_slug(self) -> str:
        raw = (self.cleaned_data.get("slug") or "").strip()
        if not raw:
            return ""
        return slugify(raw)

    def clean(self):
        cleaned = super().clean()

        kind = cleaned.get("kind") or Product.Kind.GOOD

        # Category policy enforcement (v1)
        cat = cleaned.get("category")
        sub = cleaned.get("subcategory")
        for c, field in [(cat, "category"), (sub, "subcategory")]:
            if c is None:
                continue
            if getattr(c, "is_prohibited", False):
                self.add_error(field, "This category is prohibited on the marketplace.")


        # Keep price aligned for free listings
        if cleaned.get("is_free"):
            cleaned["price"] = Decimal("0.00")

        # Kind-specific validations
        if kind == Product.Kind.SERVICE:
            dur = cleaned.get("service_duration_minutes") or 0
            if dur <= 0:
                self.add_error("service_duration_minutes", "Service duration is required.")
            elif dur % 15 != 0:
                self.add_error("service_duration_minutes", "Duration must be in 15-minute increments.")

            # Services don't use goods fulfillment; allow but ignore
            # Service deposit stored via dollars field

        if kind == Product.Kind.GOOD:
            if not (
                cleaned.get("fulfillment_pickup_enabled")
                or cleaned.get("fulfillment_delivery_enabled")
                or cleaned.get("fulfillment_shipping_enabled")
            ):
                raise ValidationError("Enable at least one fulfillment option for a product.")
        return cleaned

    def save(self, commit=True):
        obj: Product = super().save(commit=False)

        # Slug behavior:
        # - blank slug => auto-generate from title
        # - custom slug different from auto => mark as manual and preserve
        title = (self.cleaned_data.get("title") or obj.title or "").strip()
        slug_input = (self.cleaned_data.get("slug") or "").strip()
        auto_slug = slugify(title)[:160] or "listing"
        if slug_input:
            obj.slug = slug_input
            obj.slug_is_manual = slug_input != auto_slug
        else:
            obj.slug = auto_slug
            obj.slug_is_manual = False

        # Dollars -> cents (safe)
        dep = self.cleaned_data.get("service_deposit_dollars") or Decimal("0.00")
        del_fee = self.cleaned_data.get("delivery_fee_dollars") or Decimal("0.00")
        ship_fee = self.cleaned_data.get("shipping_fee_dollars") or Decimal("0.00")

        obj.service_deposit_cents = int((dep * 100).quantize(Decimal("1")))
        obj.delivery_fee_cents = int((del_fee * 100).quantize(Decimal("1")))
        obj.shipping_fee_cents = int((ship_fee * 100).quantize(Decimal("1")))

        if commit:
            obj.save()
            self.save_m2m()
        return obj


class ProductImageUploadForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "is_primary"]
        widgets = {
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "alt_text": forms.TextInput(attrs={"class": "form-control"}),
            "is_primary": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_image(self):
        f = self.cleaned_data.get("image")
        _validate_image(f)
        return f


class ProductImageBulkUploadForm(forms.Form):
    images = MultiImageField(required=True, widget=MultiFileInput(attrs={"class": "form-control"}))

    def clean_images(self):
        files = self.cleaned_data.get("images") or []
        if not files:
            raise ValidationError("Please select one or more images.")
        for f in files:
            _validate_image(f)
        return files


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["alt_text", "sort_order"]
        widgets = {
            "alt_text": forms.TextInput(attrs={"class": "form-control"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0"}),
        }

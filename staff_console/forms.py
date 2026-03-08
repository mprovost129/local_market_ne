from __future__ import annotations

from django import forms

from catalog.models import Category
from products.models import Product
from core.models import ContactMessage, SupportResponseTemplate


class ListingPolicyForm(forms.ModelForm):
    reason = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        help_text="Required. This will be stored in the audit log.",
        label="Reason / internal note",
    )

    class Meta:
        model = Product
        fields = ["is_active", "category", "subcategory"]
        widgets = {
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "subcategory": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Restrict subcategory choices to children of selected category.
        # If no category selected yet, show none.
        cat = None
        try:
            cat = self.instance.category
        except Exception:
            cat = None

        if cat:
            self.fields["subcategory"].queryset = Category.objects.filter(parent=cat, is_active=True).order_by("name")
        else:
            self.fields["subcategory"].queryset = Category.objects.none()

        # Only allow active categories
        self.fields["category"].queryset = Category.objects.filter(parent__isnull=True, is_active=True).order_by("type", "name")


class ContactMessageTriageForm(forms.ModelForm):
    """Internal triage fields for staff."""

    class Meta:
        model = ContactMessage
        fields = ["sla_tag", "internal_notes"]
        widgets = {
            "sla_tag": forms.Select(attrs={"class": "form-select"}),
            "internal_notes": forms.Textarea(attrs={"class": "form-control", "rows": 6, "placeholder": "Internal notes (not visible to user)"}),
        }


class SupportReplyForm(forms.Form):
    template = forms.ModelChoiceField(
        queryset=SupportResponseTemplate.objects.filter(is_active=True).order_by("title"),
        required=False,
        empty_label="(Choose a template)",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    subject = forms.CharField(
        required=True,
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    body = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 10}),
    )
    mark_resolved = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    reason = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Audit note (optional)"}),
    )

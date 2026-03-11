#accounts/admin.py
from __future__ import annotations

from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils.html import format_html

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "company_name",
        "shop_name",
        "public_city",
        "public_state",
        "storefront_theme_enabled",
        "storefront_layout",
        "storefront_primary_color",
        "service_radius_miles",
        "is_seller",
        "stripe_onboarding_complete",
        "is_owner",
        "products_count",
        "orders_sold_count",
        "buyers_count",
        "admin_hub_links",
        "created_at",
    )
    list_filter = ("is_seller", "stripe_onboarding_complete", "is_owner", "public_state", "storefront_layout")
    search_fields = ("user__username", "email", "first_name", "last_name", "shop_name", "public_city")
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("user")
        return qs.annotate(
            products_count_agg=Count("user__products", distinct=True),
            orders_sold_count_agg=Count("user__sold_order_items__order", distinct=True),
            buyers_count_agg=Count("user__sold_order_items__order__buyer", distinct=True),
        )

    @admin.display(description="company")
    def company_name(self, obj: Profile) -> str:
        return obj.public_seller_name

    @admin.display(description="products")
    def products_count(self, obj: Profile) -> int:
        return int(getattr(obj, "products_count_agg", 0) or 0)

    @admin.display(description="orders sold")
    def orders_sold_count(self, obj: Profile) -> int:
        return int(getattr(obj, "orders_sold_count_agg", 0) or 0)

    @admin.display(description="buyers")
    def buyers_count(self, obj: Profile) -> int:
        return int(getattr(obj, "buyers_count_agg", 0) or 0)

    @admin.display(description="company hub")
    def admin_hub_links(self, obj: Profile):
        def _safe(name: str, query: str) -> str:
            try:
                return reverse(name) + query
            except NoReverseMatch:
                return ""

        uid = int(obj.user_id)
        links = [
            ("Products", _safe("admin:products_product_changelist", f"?seller_company={uid}")),
            ("Orders", _safe("admin:orders_order_changelist", f"?seller_company={uid}")),
            ("Items", _safe("admin:orders_orderitem_changelist", f"?seller__id__exact={uid}")),
            ("Payouts", _safe("admin:payments_sellerbalanceentry_changelist", f"?seller_company={uid}")),
            ("Refunds", _safe("admin:refunds_refundrequest_changelist", f"?seller_company={uid}")),
            ("Appointments", _safe("admin:appointments_appointmentrequest_changelist", f"?seller__id__exact={uid}")),
        ]
        html = " | ".join(
            [f"<a href='{url}'>{label}</a>" for label, url in links if url]
        )
        return format_html(html or "No linked admin modules")

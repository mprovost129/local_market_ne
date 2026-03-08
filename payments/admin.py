# payments/admin.py

from __future__ import annotations

from django.contrib import admin
from django.db.models import Sum

from core.admin_filters import UserCompanyFilter

from .models import SellerBalanceEntry, SellerStripeAccount


class SellerCompanyFilter(UserCompanyFilter):
    user_field_name = "seller"
    title = "seller company"
    parameter_name = "seller_company"


@admin.register(SellerStripeAccount)
class SellerStripeAccountAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "user_company",
        "stripe_account_id",
        "details_submitted",
        "charges_enabled",
        "payouts_enabled",
        "current_balance",
        "onboarding_started_at",
        "onboarding_completed_at",
        "updated_at",
    )
    search_fields = ("user__username", "user__email", "user__profile__shop_name", "stripe_account_id")
    list_filter = ("details_submitted", "charges_enabled", "payouts_enabled", UserCompanyFilter)

    def current_balance(self, obj):
        total = (
            SellerBalanceEntry.objects.filter(seller=obj.user)
            .aggregate(total=Sum("amount_cents"))
            .get("total")
            or 0
        )
        return f"${total / 100:,.2f}"

    current_balance.short_description = "Balance"

    def user_company(self, obj: SellerStripeAccount) -> str:
        profile = getattr(obj.user, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.user, "username", str(obj.user_id))

    user_company.short_description = "Company"


@admin.register(SellerBalanceEntry)
class SellerBalanceEntryAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "seller",
        "seller_company",
        "amount_cents",
        "reason",
        "order",
        "order_item",
        "note",
    )
    list_filter = ("reason", "created_at", SellerCompanyFilter)
    search_fields = (
        "seller__username",
        "seller__email",
        "seller__profile__shop_name",
        "order__id",
        "note",
    )
    readonly_fields = (
        "seller",
        "amount_cents",
        "reason",
        "order",
        "order_item",
        "note",
        "created_at",
    )

    def seller_company(self, obj: SellerBalanceEntry) -> str:
        profile = getattr(obj.seller, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.seller, "username", str(obj.seller_id))

    seller_company.short_description = "Company"

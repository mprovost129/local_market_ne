# payments/admin.py

from __future__ import annotations

from django.contrib import admin
from django.db.models import Sum

from core.admin_filters import UserCompanyFilter

from .models import SellerBalanceEntry, SellerFeeInvoice, SellerFeePlan, SellerFeeWaiver, SellerStripeAccount


class SellerCompanyFilter(UserCompanyFilter):
    user_field_name = "seller"
    title = "seller company"
    parameter_name = "seller_company"


@admin.register(SellerFeeWaiver)
class SellerFeeWaiverAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "user_company",
        "starts_at",
        "ends_at",
        "is_active_now",
        "updated_at",
    )
    search_fields = ("user__username", "user__email", "user__profile__shop_name")
    list_filter = (UserCompanyFilter,)
    actions = ("extend_7_days", "extend_30_days", "extend_90_days")

    def user_company(self, obj: SellerFeeWaiver) -> str:
        profile = getattr(obj.user, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.user, "username", str(obj.user_id))

    user_company.short_description = "Company"

    def is_active_now(self, obj: SellerFeeWaiver) -> bool:
        return bool(obj.is_active)

    is_active_now.boolean = True
    is_active_now.short_description = "Active"

    @admin.action(description="Extend waiver by 7 days")
    def extend_7_days(self, request, queryset):
        for obj in queryset:
            obj.extend_by_days(days=7)

    @admin.action(description="Extend waiver by 30 days")
    def extend_30_days(self, request, queryset):
        for obj in queryset:
            obj.extend_by_days(days=30)

    @admin.action(description="Extend waiver by 90 days")
    def extend_90_days(self, request, queryset):
        for obj in queryset:
            obj.extend_by_days(days=90)


@admin.register(SellerFeePlan)
class SellerFeePlanAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "user_company",
        "is_active",
        "custom_sales_percent",
        "discount_percent",
        "starts_at",
        "ends_at",
        "is_currently_active",
        "updated_at",
    )
    search_fields = ("user__username", "user__email", "user__profile__shop_name")
    list_filter = ("is_active", UserCompanyFilter)
    readonly_fields = ("created_at", "updated_at", "is_currently_active")
    fieldsets = (
        (
            "Seller",
            {
                "fields": ("user",),
            },
        ),
        (
            "Fee Plan",
            {
                "fields": ("is_active", "custom_sales_percent", "discount_percent", "starts_at", "ends_at", "is_currently_active"),
                "description": (
                    "Use custom_sales_percent for a fixed seller fee (0 = fully comped). "
                    "If custom_sales_percent is blank, discount_percent applies against global fee (100 = fully comped)."
                ),
            },
        ),
        (
            "Notes",
            {
                "fields": ("notes",),
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    def user_company(self, obj: SellerFeePlan) -> str:
        profile = getattr(obj.user, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.user, "username", str(obj.user_id))

    user_company.short_description = "Company"


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


@admin.register(SellerFeeInvoice)
class SellerFeeInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "seller",
        "seller_company",
        "order",
        "amount_cents",
        "status",
        "payment_method_snapshot",
        "paid_at",
    )
    list_filter = ("status", "payment_method_snapshot", SellerCompanyFilter)
    search_fields = (
        "seller__username",
        "seller__email",
        "seller__profile__shop_name",
        "order__id",
        "stripe_session_id",
        "stripe_payment_intent_id",
    )
    readonly_fields = ("created_at", "updated_at")

    def seller_company(self, obj: SellerFeeInvoice) -> str:
        profile = getattr(obj.seller, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.seller, "username", str(obj.seller_id))

    seller_company.short_description = "Company"

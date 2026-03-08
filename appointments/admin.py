from __future__ import annotations

from django.contrib import admin

from core.admin_filters import SellerCompanyFilter

from .models import AppointmentRequest, AvailabilityException, AvailabilityRule


@admin.register(AppointmentRequest)
class AppointmentRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "service",
        "seller_company",
        "seller",
        "buyer",
        "requested_start",
        "requested_end",
        "created_at",
    )
    list_filter = ("status", "created_at", SellerCompanyFilter, "seller", "buyer")
    search_fields = (
        "id",
        "service__title",
        "seller__username",
        "seller__profile__shop_name",
        "buyer__username",
        "buyer__email",
    )
    raw_id_fields = ("service", "seller", "buyer", "order")
    list_select_related = ("service", "seller", "seller__profile", "buyer", "order")

    @admin.display(description="seller company")
    def seller_company(self, obj: AppointmentRequest) -> str:
        profile = getattr(obj.seller, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.seller, "username", str(obj.seller_id))


@admin.register(AvailabilityRule)
class AvailabilityRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "seller_company", "seller", "weekday", "start_time", "end_time", "is_active", "updated_at")
    list_filter = ("is_active", "weekday", SellerCompanyFilter, "seller")
    search_fields = ("seller__username", "seller__profile__shop_name")
    raw_id_fields = ("seller",)

    @admin.display(description="seller company")
    def seller_company(self, obj: AvailabilityRule) -> str:
        profile = getattr(obj.seller, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.seller, "username", str(obj.seller_id))


@admin.register(AvailabilityException)
class AvailabilityExceptionAdmin(admin.ModelAdmin):
    list_display = ("id", "seller_company", "seller", "date", "is_closed", "start_time", "end_time", "updated_at")
    list_filter = ("is_closed", "date", SellerCompanyFilter, "seller")
    search_fields = ("seller__username", "seller__profile__shop_name", "note")
    raw_id_fields = ("seller",)

    @admin.display(description="seller company")
    def seller_company(self, obj: AvailabilityException) -> str:
        profile = getattr(obj.seller, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.seller, "username", str(obj.seller_id))

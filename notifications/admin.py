# notifications/admin.py
from __future__ import annotations

from django.contrib import admin

from core.admin_filters import UserCompanyFilter

from .models import EmailDeliveryAttempt, Notification


class NotificationUserCompanyFilter(UserCompanyFilter):
    user_field_name = "user"
    parameter_name = "user_company"


class EmailAttemptUserCompanyFilter(UserCompanyFilter):
    user_field_name = "notification__user"
    parameter_name = "user_company"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "user_company",
        "user",
        "kind",
        "title",
        "is_read",
        "read_at",
    )
    list_filter = ("kind", "is_read", "created_at", NotificationUserCompanyFilter)
    search_fields = ("id", "user__username", "user__email", "user__profile__shop_name", "title", "body", "email_subject")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "read_at")

    @admin.display(description="user company")
    def user_company(self, obj: Notification) -> str:
        profile = getattr(obj.user, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.user, "username", str(obj.user_id))


@admin.register(EmailDeliveryAttempt)
class EmailDeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "status",
        "to_email",
        "subject",
        "user_company",
        "notification",
    )
    list_filter = ("status", "created_at", EmailAttemptUserCompanyFilter)
    search_fields = (
        "id",
        "to_email",
        "subject",
        "notification__id",
        "notification__user__email",
        "notification__user__username",
        "notification__user__profile__shop_name",
    )
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    @admin.display(description="user company")
    def user_company(self, obj: EmailDeliveryAttempt) -> str:
        user = getattr(getattr(obj, "notification", None), "user", None)
        profile = getattr(user, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(user, "username", str(getattr(getattr(obj, "notification", None), "user_id", "")))

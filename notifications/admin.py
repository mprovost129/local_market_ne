# notifications/admin.py
from __future__ import annotations

from django.contrib import admin

from .models import EmailDeliveryAttempt, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "user",
        "kind",
        "title",
        "is_read",
        "read_at",
    )
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("id", "user__username", "user__email", "title", "body", "email_subject")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "read_at")


@admin.register(EmailDeliveryAttempt)
class EmailDeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "status",
        "to_email",
        "subject",
        "notification",
    )
    list_filter = ("status", "created_at")
    search_fields = ("id", "to_email", "subject", "notification__id", "notification__user__email")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

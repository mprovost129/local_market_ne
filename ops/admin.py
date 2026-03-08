from __future__ import annotations

from django.contrib import admin

from .models import AuditLog, ErrorEvent


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "verb", "target_object_id")
    list_filter = ("action", "created_at")
    search_fields = ("verb", "reason", "target_object_id", "actor__email", "actor__username")
    readonly_fields = (
        "created_at",
        "actor",
        "ip_address",
        "user_agent",
        "action",
        "verb",
        "reason",
        "target_content_type",
        "target_object_id",
        "before_json",
        "after_json",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ErrorEvent)
class ErrorEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "status_code",
        "exception_type",
        "path",
        "request_id",
        "user",
        "is_resolved",
    )
    list_filter = ("is_resolved", "status_code", "created_at")
    search_fields = ("request_id", "path", "exception_type", "message", "user__email", "user__username")
    readonly_fields = (
        "created_at",
        "request_id",
        "path",
        "method",
        "status_code",
        "user",
        "ip_address",
        "user_agent",
        "exception_type",
        "message",
        "traceback",
    )

    fieldsets = (
        (
            "Event",
            {
                "fields": (
                    "created_at",
                    "status_code",
                    "exception_type",
                    "message",
                    "request_id",
                    "path",
                    "method",
                    "user",
                    "ip_address",
                    "user_agent",
                )
            },
        ),
        (
            "Resolution",
            {"fields": ("is_resolved", "resolved_at", "resolved_by", "resolution_notes")},
        ),
        (
            "Traceback",
            {"fields": ("traceback",)},
        ),
    )

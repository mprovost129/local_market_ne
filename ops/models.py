from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditAction(models.TextChoices):
    ORDER_OVERRIDE = "order_override", "Order override"
    SELLER_ACTION = "seller_action", "Seller action"
    MODERATION = "moderation", "Moderation"
    SETTINGS = "settings", "Settings"
    FINANCIAL = "financial", "Financial"
    OTHER = "other", "Other"


class AuditLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ops_audit_logs",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    action = models.CharField(max_length=64, choices=AuditAction.choices, default=AuditAction.OTHER)
    verb = models.CharField(max_length=80, help_text="Human-friendly verb, e.g. 'force_mark_paid'.")
    reason = models.TextField(blank=True)

    # Optional target object
    target_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    target_object_id = models.CharField(max_length=64, null=True, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    before_json = models.JSONField(default=dict, blank=True)
    after_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["verb", "created_at"]),
        ]

    def __str__(self) -> str:
        who = self.actor.email if self.actor and hasattr(self.actor, "email") else (self.actor.username if self.actor else "system")
        return f"{self.created_at:%Y-%m-%d %H:%M} {who} {self.verb}"


class ErrorEvent(models.Model):
    """Captured unhandled errors for ops triage."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    path = models.CharField(max_length=500, blank=True, db_index=True)
    method = models.CharField(max_length=12, blank=True)
    status_code = models.PositiveIntegerField(default=500, db_index=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ops_error_events",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    exception_type = models.CharField(max_length=200, blank=True, db_index=True)
    message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)

    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ops_error_events_resolved",
    )
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_resolved", "created_at"]),
            models.Index(fields=["status_code", "created_at"]),
            models.Index(fields=["exception_type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.status_code} {self.exception_type or 'Error'}"

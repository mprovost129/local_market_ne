from __future__ import annotations

import os

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from notifications.models import EmailDeliveryAttempt
from ops.models import ErrorEvent
from orders.models import Order, StripeWebhookEvent
from orders.querysets import annotate_order_reconciliation
from refunds.models import RefundRequest


SAVED_SEARCH_HEARTBEAT_KEY = "ops:saved_search_alerts:last_run"


def _bool_env(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"})


def build_alert_summary(*, hours: int = 24, reconciliation_days: int = 7) -> dict:
    hours = max(1, int(hours or 24))
    reconciliation_days = max(1, int(reconciliation_days or 7))

    now = timezone.now()
    since_recent = now - timezone.timedelta(hours=hours)
    since_recon = now - timezone.timedelta(days=reconciliation_days)

    open_error_events = ErrorEvent.objects.filter(is_resolved=False).count()
    failed_emails_recent = EmailDeliveryAttempt.objects.filter(
        status=EmailDeliveryAttempt.Status.FAILED,
        created_at__gte=since_recent,
    ).count()
    webhook_errors_recent = StripeWebhookEvent.objects.filter(
        status="error",
        created_at__gte=since_recent,
    ).count()
    webhook_unprocessed_stale = StripeWebhookEvent.objects.filter(
        processed_at__isnull=True,
        created_at__lt=now - timezone.timedelta(minutes=10),
        status__in=["received", "error"],
    ).count()
    open_refund_requests = RefundRequest.objects.filter(status=RefundRequest.Status.REQUESTED).count()

    recon_qs = annotate_order_reconciliation(
        Order.objects.filter(created_at__gte=since_recon)
    )
    reconciliation_mismatches = recon_qs.filter(
        Q(totals_mismatch=True)
        | Q(ledger_mismatch=True)
        | Q(paid_missing_stripe_ids=True)
        | Q(paid_missing_transfer_event=True)
    ).count()

    paid_missing_transfer_recent = recon_qs.filter(
        status=Order.Status.PAID,
        paid_missing_transfer_event=True,
    ).count()

    saved_search_heartbeat = cache.get(SAVED_SEARCH_HEARTBEAT_KEY) or {}
    saved_search_last_run_iso = str(saved_search_heartbeat.get("ran_at") or "").strip()
    saved_search_last_run_at = None
    if saved_search_last_run_iso:
        try:
            saved_search_last_run_at = timezone.datetime.fromisoformat(saved_search_last_run_iso)
            if timezone.is_naive(saved_search_last_run_at):
                saved_search_last_run_at = timezone.make_aware(saved_search_last_run_at, timezone.get_current_timezone())
        except Exception:
            saved_search_last_run_at = None

    monitor_enabled = _bool_env("SAVED_SEARCH_ALERTS_MONITOR_ENABLED", "0")
    dispatch_enabled = _bool_env("SAVED_SEARCH_ALERTS_ENABLED", "1")
    expected_interval_minutes = max(5, int(os.getenv("SAVED_SEARCH_ALERTS_EXPECTED_INTERVAL_MINUTES", "15") or 15))
    saved_search_heartbeat_stale = False
    if monitor_enabled and dispatch_enabled:
        if not saved_search_last_run_at:
            saved_search_heartbeat_stale = True
        else:
            lag_seconds = (now - saved_search_last_run_at).total_seconds()
            saved_search_heartbeat_stale = lag_seconds > (expected_interval_minutes * 60 * 3)

    critical_reasons = []
    warning_reasons = []
    if webhook_errors_recent > 0:
        critical_reasons.append("webhook_errors_recent")
    if reconciliation_mismatches > 0:
        critical_reasons.append("reconciliation_mismatches")
    if open_error_events > 0:
        warning_reasons.append("open_error_events")
    if failed_emails_recent > 0:
        warning_reasons.append("failed_emails_recent")
    if webhook_unprocessed_stale > 0:
        warning_reasons.append("webhook_unprocessed_stale")
    if open_refund_requests > 0:
        warning_reasons.append("open_refund_requests")
    if paid_missing_transfer_recent > 0:
        warning_reasons.append("paid_missing_transfer_recent")
    if saved_search_heartbeat_stale:
        warning_reasons.append("saved_search_scheduler_stale")

    if critical_reasons:
        status = "critical"
    elif warning_reasons:
        status = "warning"
    else:
        status = "ok"

    return {
        "status": status,
        "window_hours": hours,
        "reconciliation_days": reconciliation_days,
        "generated_at": now.isoformat(),
        "metrics": {
            "open_error_events": open_error_events,
            "failed_emails_recent": failed_emails_recent,
            "webhook_errors_recent": webhook_errors_recent,
            "webhook_unprocessed_stale": webhook_unprocessed_stale,
            "open_refund_requests": open_refund_requests,
            "reconciliation_mismatches": reconciliation_mismatches,
            "paid_missing_transfer_recent": paid_missing_transfer_recent,
            "saved_search_scheduler_stale": int(saved_search_heartbeat_stale),
            "saved_search_scheduler_last_run_at": saved_search_last_run_iso,
            "saved_search_scheduler_checked": int(saved_search_heartbeat.get("checked") or 0),
            "saved_search_scheduler_alerted": int(saved_search_heartbeat.get("alerted") or 0),
            "saved_search_scheduler_dry_run": int(bool(saved_search_heartbeat.get("dry_run"))),
        },
        "critical_reasons": critical_reasons,
        "warning_reasons": warning_reasons,
    }

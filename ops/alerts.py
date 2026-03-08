from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from notifications.models import EmailDeliveryAttempt
from ops.models import ErrorEvent
from orders.models import Order, StripeWebhookEvent
from orders.querysets import annotate_order_reconciliation
from refunds.models import RefundRequest


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
        },
        "critical_reasons": critical_reasons,
        "warning_reasons": warning_reasons,
    }

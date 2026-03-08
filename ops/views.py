from __future__ import annotations

from datetime import timedelta
import datetime
import json
import csv
import re
from io import StringIO

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.core.management import call_command
from django.http import JsonResponse
from django.conf import settings

from core.launch_checks import as_dict as launch_as_dict, run_launch_checks
from django.db import models
from django.db.models import Count, Sum, Max, Exists, OuterRef
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from orders.models import Order, OrderItem, OrderEvent, StripeWebhookEvent, StripeWebhookDelivery
from orders.webhooks import process_stripe_event_dict
from orders.stripe_service import create_transfers_for_paid_order
from orders.querysets import annotate_order_reconciliation
from payments.utils import cents_to_money
from payments.services import get_seller_balance_cents
from payments.models import SellerBalanceEntry
from products.models import Product
from qa.models import ProductQuestionReport
from refunds.models import RefundRequest
from notifications.models import EmailDeliveryAttempt, Notification
from notifications.services import resend_notification_email
from products.permissions import can_run_high_risk_action

from .decorators import ops_required
from .models import AuditLog, AuditAction, ErrorEvent
from .services import audit
from .utils import user_is_ops
from .alerts import build_alert_summary


User = get_user_model()


@ops_required
def dashboard(request: HttpRequest) -> HttpResponse:
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    paid_qs = Order.objects.filter(status=Order.Status.PAID)

    # Pack AW: “Money Loop” KPIs (use OrderItem ledger + RefundRequest snapshots)
    # These are the operational numbers ops cares about: gross, marketplace fees, seller net, and refunds.
    items_paid_7d = OrderItem.objects.filter(order__status=Order.Status.PAID, order__paid_at__gte=week_start)
    money_7d = items_paid_7d.aggregate(
        fees_cents=Sum("marketplace_fee_cents"),
        seller_net_cents=Sum("seller_net_cents"),
    )
    fees_7d_cents = int(money_7d.get("fees_cents") or 0)
    seller_net_7d_cents = int(money_7d.get("seller_net_cents") or 0)

    refunds_7d = RefundRequest.objects.filter(status=RefundRequest.Status.REFUNDED, refunded_at__gte=week_start)
    refunds_7d_cents = int(refunds_7d.aggregate(total=Sum("total_refund_cents_snapshot")).get("total") or 0)
    refunds_7d_count = refunds_7d.count()

    gmv_today = paid_qs.filter(paid_at__gte=today_start).aggregate(total=Sum("total_cents")).get("total") or 0
    gmv_7d = paid_qs.filter(paid_at__gte=week_start).aggregate(total=Sum("total_cents")).get("total") or 0
    gmv_30d = paid_qs.filter(paid_at__gte=month_start).aggregate(total=Sum("total_cents")).get("total") or 0

    orders_paid_today = paid_qs.filter(paid_at__gte=today_start).count()
    orders_pending = Order.objects.filter(status__in=[Order.Status.PENDING, Order.Status.AWAITING_PAYMENT]).count()
    orders_refunded_30d = Order.objects.filter(status=Order.Status.REFUNDED, updated_at__gte=month_start).count()

    sellers_count = User.objects.filter(products__isnull=False).distinct().count()
    products_count = Product.objects.count()

    open_qa_reports = ProductQuestionReport.objects.filter(status=ProductQuestionReport.Status.OPEN).count()
    open_refund_requests = RefundRequest.objects.filter(status=RefundRequest.Status.REQUESTED).count()
    open_errors = ErrorEvent.objects.filter(is_resolved=False).count()

    recent_orders = (
        Order.objects.select_related("buyer")
        .order_by("-created_at")[:10]
    )
    recent_audit = AuditLog.objects.select_related("actor").order_by("-created_at")[:10]

    ctx = {
        "gmv_today": gmv_today,
        "gmv_7d": gmv_7d,
        "gmv_30d": gmv_30d,
        "orders_paid_today": orders_paid_today,
        "orders_pending": orders_pending,
        "orders_refunded_30d": orders_refunded_30d,
        "sellers_count": sellers_count,
        "products_count": products_count,
        "open_qa_reports": open_qa_reports,
        "open_refund_requests": open_refund_requests,
        "open_errors": open_errors,
        # Money Loop KPIs (7d)
        "fees_7d_cents": fees_7d_cents,
        "seller_net_7d_cents": seller_net_7d_cents,
        "refunds_7d_cents": refunds_7d_cents,
        "refunds_7d_count": refunds_7d_count,
        "recent_orders": recent_orders,
        "recent_audit": recent_audit,
    }
    return render(request, "ops/dashboard.html", ctx)


@ops_required
def funnel_dashboard(request: HttpRequest) -> HttpResponse:
    """Conversion funnel metrics using native AnalyticsEvent.

    Default: last 7 days. Override with ?days=30, etc.

    Pack AM enhancements:
    - Unique-session funnel (based on first-party session_id).
    - Percent formatting (human readable).
    - Breakouts by host/environment.
    """
    from analytics.models import AnalyticsEvent
    from django.db.models import Case, IntegerField, Max, When

    try:
        days = int((request.GET.get("days") or "7").strip())
    except Exception:
        days = 7
    days = max(1, min(days, 365))

    since = timezone.now() - timedelta(days=days)

    base = AnalyticsEvent.objects.filter(created_at__gte=since)

    # Raw event counts (can include multiple events per session).
    add_to_cart = base.filter(event_type=AnalyticsEvent.EventType.ADD_TO_CART).count()
    checkout_started = base.filter(event_type=AnalyticsEvent.EventType.CHECKOUT_STARTED).count()
    order_paid = base.filter(event_type=AnalyticsEvent.EventType.ORDER_PAID).count()

    def _rate(n: int, d: int) -> float:
        if not d:
            return 0.0
        return float(n) / float(d)

    def _pct(n: int, d: int) -> str:
        return f"{_rate(n, d) * 100.0:.2f}%"

    # Unique-session funnel (first-party session cookie: hc_sid -> AnalyticsEvent.session_id).
    # Group by session_id and compute flags for each stage.
    sessions = (
        base.exclude(session_id="")
        .values("session_id")
        .annotate(
            has_cart=Max(
                Case(
                    When(event_type=AnalyticsEvent.EventType.ADD_TO_CART, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
            has_checkout=Max(
                Case(
                    When(event_type=AnalyticsEvent.EventType.CHECKOUT_STARTED, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
            has_paid=Max(
                Case(
                    When(event_type=AnalyticsEvent.EventType.ORDER_PAID, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
        )
    )

    cart_sessions = sessions.filter(has_cart=1).count()
    checkout_sessions = sessions.filter(has_checkout=1).count()
    paid_sessions = sessions.filter(has_paid=1).count()

    checkout_from_cart_sessions = sessions.filter(has_cart=1, has_checkout=1).count()
    paid_from_checkout_sessions = sessions.filter(has_checkout=1, has_paid=1).count()
    paid_from_cart_sessions = sessions.filter(has_cart=1, has_paid=1).count()
    full_funnel_sessions = sessions.filter(has_cart=1, has_checkout=1, has_paid=1).count()

    # Host/environment breakouts (unique sessions).
    # Note: host/env may be blank in dev; we still show it for debugging.
    by_host_env = (
        base.exclude(session_id="")
        .values("host", "environment", "session_id")
        .annotate(
            has_cart=Max(
                Case(
                    When(event_type=AnalyticsEvent.EventType.ADD_TO_CART, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
            has_checkout=Max(
                Case(
                    When(event_type=AnalyticsEvent.EventType.CHECKOUT_STARTED, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
            has_paid=Max(
                Case(
                    When(event_type=AnalyticsEvent.EventType.ORDER_PAID, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
        )
    )

    # Collapse session rows into host/env aggregates.
    host_env_map: dict[tuple[str, str], dict[str, int]] = {}
    for row in by_host_env:
        key = (row.get("host") or "(blank)", row.get("environment") or "(blank)")
        agg = host_env_map.setdefault(
            key,
            {
                "sessions": 0,
                "cart": 0,
                "checkout": 0,
                "paid": 0,
                "full": 0,
            },
        )
        agg["sessions"] += 1
        if row["has_cart"]:
            agg["cart"] += 1
        if row["has_checkout"]:
            agg["checkout"] += 1
        if row["has_paid"]:
            agg["paid"] += 1
        if row["has_cart"] and row["has_checkout"] and row["has_paid"]:
            agg["full"] += 1

    host_env_rows = []
    for (host, env), agg in sorted(host_env_map.items(), key=lambda x: (-x[1]["sessions"], x[0][0], x[0][1])):
        host_env_rows.append(
            {
                "host": host,
                "environment": env,
                "sessions": agg["sessions"],
                "cart": agg["cart"],
                "checkout": agg["checkout"],
                "paid": agg["paid"],
                "full": agg["full"],
                "rate_checkout_from_cart": _rate(agg["checkout"], agg["cart"]),
                "rate_paid_from_checkout": _rate(agg["paid"], agg["checkout"]),
                "rate_paid_from_cart": _rate(agg["paid"], agg["cart"]),
            }
        )

    ctx = {
        "days": days,
        "since": since,
        "counts": {
            "add_to_cart": add_to_cart,
            "checkout_started": checkout_started,
            "order_paid": order_paid,
        },
        "rates": {
            "checkout_from_cart": _rate(checkout_started, add_to_cart),
            "paid_from_checkout": _rate(order_paid, checkout_started),
            "paid_from_cart": _rate(order_paid, add_to_cart),
        },
        "rates_pct": {
            "checkout_from_cart": _pct(checkout_started, add_to_cart),
            "paid_from_checkout": _pct(order_paid, checkout_started),
            "paid_from_cart": _pct(order_paid, add_to_cart),
        },
        "unique": {
            "cart_sessions": cart_sessions,
            "checkout_sessions": checkout_sessions,
            "paid_sessions": paid_sessions,
            "checkout_from_cart_sessions": checkout_from_cart_sessions,
            "paid_from_checkout_sessions": paid_from_checkout_sessions,
            "paid_from_cart_sessions": paid_from_cart_sessions,
            "full_funnel_sessions": full_funnel_sessions,
        },
        "unique_pct": {
            "checkout_from_cart": _pct(checkout_from_cart_sessions, cart_sessions),
            "paid_from_checkout": _pct(paid_from_checkout_sessions, checkout_sessions),
            "paid_from_cart": _pct(paid_from_cart_sessions, cart_sessions),
            "full_from_cart": _pct(full_funnel_sessions, cart_sessions),
        },
        "host_env_rows": host_env_rows,
    }
    return render(request, "ops/funnel.html", ctx)


@ops_required
def failed_emails(request: HttpRequest) -> HttpResponse:
    """Ops visibility into failed outbound emails + resend tooling."""

    try:
        days = int((request.GET.get("days") or "14").strip())
    except Exception:
        days = 14
    days = max(1, min(days, 365))
    since = timezone.now() - timedelta(days=days)

    q = (request.GET.get("q") or "").strip()
    kind = (request.GET.get("kind") or "").strip()

    qs = (
        EmailDeliveryAttempt.objects.select_related("notification", "notification__user")
        .filter(status=EmailDeliveryAttempt.Status.FAILED, created_at__gte=since)
        .order_by("-created_at")
    )

    if kind:
        qs = qs.filter(notification__kind=kind)

    if q:
        qs = qs.filter(
            models.Q(to_email__icontains=q)
            | models.Q(subject__icontains=q)
            | models.Q(notification__user__email__icontains=q)
            | models.Q(notification__user__username__icontains=q)
            | models.Q(error__icontains=q)
        )

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    # Dropdown kinds
    kinds = list(Notification.Kind.values)

    ctx = {
        "days": days,
        "q": q,
        "kind": kind,
        "kinds": kinds,
        "page_obj": page_obj,
        "total_failed": qs.count(),
    }
    return render(request, "ops/failed_emails.html", ctx)


@ops_required
def failed_email_detail(request: HttpRequest, pk: int) -> HttpResponse:
    attempt = get_object_or_404(
        EmailDeliveryAttempt.objects.select_related("notification", "notification__user"),
        pk=pk,
    )
    n = attempt.notification

    # Show recent attempts for this notification
    attempts = (
        EmailDeliveryAttempt.objects.filter(notification=n)
        .order_by("-created_at")
        .all()[:20]
    )

    ctx = {
        "attempt": attempt,
        "notification": n,
        "attempts": attempts,
    }
    return render(request, "ops/failed_email_detail.html", ctx)


@ops_required
@require_POST
def failed_email_resend(request: HttpRequest, pk: int) -> HttpResponse:
    attempt = get_object_or_404(EmailDeliveryAttempt.objects.select_related("notification"), pk=pk)
    n = attempt.notification

    ok = resend_notification_email(notification=n)
    if ok:
        audit(
            actor=request.user,
            action=AuditAction.OTHER,
            verb="resend_email",
            target_type="Notification",
            target_id=str(n.id),
            reason=f"Resent email for notification {n.id} (attempt {attempt.id}).",
            meta={"attempt_id": attempt.id, "notification_id": n.id},
        )
        messages.success(request, "Email resent (new attempt recorded).")
    else:
        messages.error(request, "Resend failed (new failed attempt recorded).")

    return redirect("ops:failed_email_detail", pk=attempt.id)


@ops_required
def audit_log(request: HttpRequest) -> HttpResponse:
    """
    Ops-grade audit log with filtering and CSV export.
    Query params:
      - q: free-text search (verb/reason/target id/actor)
      - action: AuditAction key
      - verb: substring match
      - actor: user id OR username/email substring
      - date_from/date_to: YYYY-MM-DD (inclusive)
      - format=csv: download export with current filters
    """
    qs = AuditLog.objects.select_related("actor").order_by("-created_at")

    q = (request.GET.get("q") or "").strip()
    action = (request.GET.get("action") or "").strip()
    verb = (request.GET.get("verb") or "").strip()
    actor = (request.GET.get("actor") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    if action:
        qs = qs.filter(action=action)

    if verb:
        qs = qs.filter(verb__icontains=verb)

    if actor:
        # numeric actor id or substring match
        if actor.isdigit():
            qs = qs.filter(actor_id=int(actor))
        else:
            qs = qs.filter(models.Q(actor__username__icontains=actor) | models.Q(actor__email__icontains=actor))

    if q:
        qs = qs.filter(
            models.Q(verb__icontains=q)
            | models.Q(reason__icontains=q)
            | models.Q(target_object_id__icontains=q)
            | models.Q(actor__username__icontains=q)
            | models.Q(actor__email__icontains=q)
        )

    # Date filters (best-effort; inclusive)
    def _parse_date(s: str):
        try:
            return datetime.date.fromisoformat(s)
        except Exception:
            return None

    df = _parse_date(date_from) if date_from else None
    dt = _parse_date(date_to) if date_to else None
    if df:
        start = timezone.make_aware(datetime.datetime.combine(df, datetime.time.min))
        qs = qs.filter(created_at__gte=start)
    if dt:
        end = timezone.make_aware(datetime.datetime.combine(dt, datetime.time.max))
        qs = qs.filter(created_at__lte=end)

    if (request.GET.get("format") or "").lower() == "csv":
        import csv
        from django.http import HttpResponse

        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="ops_audit_log.csv"'
        writer = csv.writer(resp)
        writer.writerow(["created_at", "actor", "action", "verb", "reason", "target_type", "target_id", "ip_address"])
        for a in qs.iterator(chunk_size=2000):
            actor_label = ""
            if a.actor_id:
                actor_label = getattr(a.actor, "email", "") or getattr(a.actor, "username", "") or str(a.actor_id)
            target_type = a.target_content_type.model if a.target_content_type_id else ""
            writer.writerow([
                a.created_at.isoformat(),
                actor_label,
                a.action,
                a.verb,
                a.reason,
                target_type,
                a.target_object_id or "",
                a.ip_address or "",
            ])
        return resp

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)
    ctx = {
        "page_obj": page,
        "q": q,
        "action": action,
        "verb": verb,
        "actor": actor,
        "date_from": date_from,
        "date_to": date_to,
        "actions": AuditAction.choices,
    }
    return render(request, "ops/audit_log.html", ctx)



@ops_required
def orders_list(request: HttpRequest) -> HttpResponse:
    qs = Order.objects.select_related("buyer").prefetch_related("items__seller", "items__seller__profile").order_by("-created_at")

    status = (request.GET.get("status") or "").strip()
    q = (request.GET.get("q") or "").strip()
    company = (request.GET.get("company") or "").strip()
    if status:
        qs = qs.filter(status=status)
    if company:
        if company.isdigit():
            qs = qs.filter(items__seller_id=int(company)).distinct()
        else:
            qs = qs.filter(
                models.Q(items__seller__profile__shop_name__icontains=company)
                | models.Q(items__seller__username__icontains=company)
            ).distinct()
    if q:
        qs = qs.filter(
            models.Q(id__icontains=q)
            | models.Q(buyer__username__icontains=q)
            | models.Q(buyer__email__icontains=q)
            | models.Q(guest_email__icontains=q)
            | models.Q(items__seller__username__icontains=q)
            | models.Q(items__seller__profile__shop_name__icontains=q)
        ).distinct()

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(
        request,
        "ops/orders_list.html",
        {"page_obj": page, "status": status, "q": q, "company": company},
    )


@ops_required
def order_detail(request: HttpRequest, pk) -> HttpResponse:
    order = get_object_or_404(annotate_order_reconciliation(Order.objects.select_related("buyer")), pk=pk)
    items = order.items.select_related("product", "seller").all() if hasattr(order, "items") else []

    # Snapshot + reconciliation summary (safe for ops)
    ctx = {
        "order": order,
        "items": items,
    }
    return render(request, "ops/order_detail.html", ctx)




@ops_required
def webhooks_list(request: HttpRequest) -> HttpResponse:
    """List Stripe webhook events with quick investigation filters."""
    status = (request.GET.get("status") or "").strip() or "error"
    event_type = (request.GET.get("event_type") or "").strip()
    session_id = (request.GET.get("session_id") or "").strip()
    order_id = (request.GET.get("order_id") or "").strip()
    days = int(request.GET.get("days") or 14)

    since = timezone.now() - timedelta(days=days)

    qs = StripeWebhookEvent.objects.filter(created_at__gte=since).order_by("-created_at")

    if status and status != "all":
        qs = qs.filter(status=status)

    if event_type:
        qs = qs.filter(event_type=event_type)

    if session_id:
        qs = qs.filter(deliveries__stripe_session_id=session_id).distinct()

    if order_id:
        qs = qs.filter(deliveries__order_id=order_id).distinct()

    qs = qs.annotate(delivery_count=Count("deliveries"))

    replayable_qs = qs.filter(status__in=["received", "error"])
    replayable_count = replayable_qs.count()

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)

    ctx = {
        "page_obj": page,
        "status": status,
        "event_type": event_type,
        "session_id": session_id,
        "order_id": order_id,
        "days": days,
        "replayable_count": replayable_count,
    }
    return render(request, "ops/webhooks_list.html", ctx)


@ops_required
def webhook_detail(request: HttpRequest, pk: int) -> HttpResponse:
    webhook = get_object_or_404(StripeWebhookEvent, pk=pk)
    deliveries = webhook.deliveries.select_related("order").order_by("-delivered_at")
    pretty = ""
    try:
        pretty = json.dumps(webhook.raw_json, indent=2, sort_keys=True)
    except Exception:
        pretty = str(webhook.raw_json)

    ctx = {
        "webhook": webhook,
        "deliveries": deliveries,
        "pretty_json": pretty,
    }
    return render(request, "ops/webhook_detail.html", ctx)


@require_POST
@ops_required
def webhook_reprocess(request: HttpRequest, pk: int) -> HttpResponse:
    if not can_run_high_risk_action(request.user, "orders.can_reprocess_webhooks"):
        messages.error(request, "You do not have permission to reprocess Stripe webhooks.")
        return redirect("ops:webhooks_list")

    webhook = get_object_or_404(StripeWebhookEvent, pk=pk)
    event = webhook.raw_json if isinstance(webhook.raw_json, dict) else {}

    try:
        process_stripe_event_dict(event=event, webhook_event=webhook, source="ops_reprocess")
        audit(request=request, action=AuditAction.OTHER, verb="Reprocessed Stripe webhook", target=webhook, after={"status": webhook.status})
        messages.success(request, "Webhook reprocessed (idempotent).")
    except Exception as e:
        audit(
            request=request,
            action=AuditAction.OTHER,
            verb="Webhook reprocess failed",
            target=webhook,
            after={"error": str(e)},
        )
        messages.error(request, f"Webhook reprocess failed: {e}")

    return redirect("ops:webhook_detail", pk=webhook.pk)


@require_POST
@ops_required
def webhooks_reprocess_filtered(request: HttpRequest) -> HttpResponse:
    """Bulk reprocess filtered webhook rows from the list page (idempotent)."""
    if not can_run_high_risk_action(request.user, "orders.can_reprocess_webhooks"):
        messages.error(request, "You do not have permission to bulk reprocess Stripe webhooks.")
        return redirect("ops:webhooks_list")

    status = (request.POST.get("status") or "").strip() or "error"
    event_type = (request.POST.get("event_type") or "").strip()
    session_id = (request.POST.get("session_id") or "").strip()
    order_id = (request.POST.get("order_id") or "").strip()
    try:
        days = int(request.POST.get("days") or 14)
    except Exception:
        days = 14
    days = max(1, min(days, 365))

    try:
        limit = int(request.POST.get("limit") or 50)
    except Exception:
        limit = 50
    limit = max(1, min(limit, 200))

    since = timezone.now() - timedelta(days=days)
    qs = StripeWebhookEvent.objects.filter(created_at__gte=since).order_by("-created_at")
    if status and status != "all":
        qs = qs.filter(status=status)
    if event_type:
        qs = qs.filter(event_type=event_type)
    if session_id:
        qs = qs.filter(deliveries__stripe_session_id=session_id).distinct()
    if order_id:
        qs = qs.filter(deliveries__order_id=order_id).distinct()

    qs = qs.filter(status__in=["received", "error"])

    selected = list(qs[:limit])
    replayed = 0
    failed = 0
    last_error = ""
    for webhook in selected:
        event = webhook.raw_json if isinstance(webhook.raw_json, dict) else {}
        try:
            process_stripe_event_dict(event=event, webhook_event=webhook, source="ops_reprocess")
            replayed += 1
        except Exception as e:
            failed += 1
            last_error = str(e)

    audit(
        request=request,
        action=AuditAction.OTHER,
        verb="Bulk reprocessed Stripe webhooks",
        reason=f"status={status} event_type={event_type} session={session_id} order={order_id} days={days} limit={limit}",
        after={"selected": len(selected), "replayed": replayed, "failed": failed},
    )

    if failed:
        messages.warning(
            request,
            f"Reprocessed {replayed}/{len(selected)} webhook(s); {failed} failed."
            + (f" Last error: {last_error}" if last_error else ""),
        )
    else:
        messages.success(request, f"Reprocessed {replayed} webhook(s) (idempotent).")

    return redirect(
        f"{reverse('ops:webhooks_list')}?status={status}&event_type={event_type}&session_id={session_id}&order_id={order_id}&days={days}"
    )


@require_POST
@ops_required
def order_retry_transfers(request: HttpRequest, pk) -> HttpResponse:
    if not can_run_high_risk_action(request.user, "orders.can_retry_payouts"):
        messages.error(request, "You do not have permission to retry payout transfers.")
        return redirect("ops:orders_list")

    order = get_object_or_404(Order, pk=pk)

    try:
        if order.status != Order.Status.PAID:
            raise ValueError("Order is not PAID.")
        create_transfers_for_paid_order(order=order)
        audit(
            request=request,
            action=AuditAction.OTHER,
            verb="Retried Stripe transfers for order",
            target=order,
        )
        messages.success(request, "Transfers retry executed (idempotent).")
    except Exception as e:
        messages.error(request, f"Transfers retry failed: {e}")

    return redirect("ops:order_detail", pk=order.pk)



@ops_required
def sellers_list(request: HttpRequest) -> HttpResponse:
    qs = (
        User.objects.filter(products__isnull=False)
        .select_related("profile")
        .distinct()
        .annotate(
            products_count=Count("products", distinct=True),
            orders_sold_count=Count("sold_order_items__order", distinct=True),
            buyers_count=Count("sold_order_items__order__buyer", distinct=True),
        )
        .order_by("-orders_sold_count", "-products_count", "id")
    )

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            models.Q(username__icontains=q)
            | models.Q(email__icontains=q)
            | models.Q(profile__shop_name__icontains=q)
        )

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(request, "ops/sellers_list.html", {"page_obj": page, "q": q})


@ops_required
def seller_detail(request: HttpRequest, pk: int) -> HttpResponse:
    seller = get_object_or_404(User, pk=pk)
    products = Product.objects.filter(seller=seller).order_by("-created_at")[:50]
    recent_orders = (
        Order.objects.filter(items__seller=seller).distinct().order_by("-created_at")[:50]
    )
    consumer_count = (
        Order.objects.filter(items__seller=seller, buyer__isnull=False)
        .values("buyer_id")
        .distinct()
        .count()
    )

    # Payout reconciliation (seller scoped)
    available_cents = int(get_seller_balance_cents(seller=seller) or 0)

    try:
        seller_transfer_exists = OrderEvent.objects.filter(
            order_id=OuterRef("order_id"),
            type=OrderEvent.Type.TRANSFER_CREATED,
            meta__seller_id=OuterRef("seller_id"),
        )
        pending_items = (
            OrderItem.objects.select_related("order", "product")
            .filter(seller=seller, order__status=Order.Status.PAID)
            .annotate(has_seller_transfer=Exists(seller_transfer_exists))
            .filter(has_seller_transfer=False)
            .order_by("-order__paid_at")[:50]
        )
    except Exception:
        transfer_exists = OrderEvent.objects.filter(
            order_id=OuterRef("order_id"),
            type=OrderEvent.Type.TRANSFER_CREATED,
        )
        pending_items = (
            OrderItem.objects.select_related("order", "product")
            .filter(seller=seller, order__status=Order.Status.PAID)
            .annotate(has_transfer=Exists(transfer_exists))
            .filter(has_transfer=False)
            .order_by("-order__paid_at")[:50]
        )

    pending_cents = int(pending_items.aggregate(total=Sum("seller_net_cents")).get("total") or 0)

    recent_transfers = (
        OrderEvent.objects.select_related("order")
        .filter(type=OrderEvent.Type.TRANSFER_CREATED, meta__seller_id=int(seller.id))
        .order_by("-created_at")[:50]
    )

    mismatch_rows = []
    try:
        paid_orders = (
            OrderItem.objects.filter(seller=seller, order__status=Order.Status.PAID)
            .values("order_id")
            .annotate(
                expected_cents=Sum("seller_net_cents"),
                paid_at=Max("order__paid_at"),
            )
            .order_by("-paid_at")
        )
        order_ids = [row["order_id"] for row in paid_orders]
        transfer_events = (
            OrderEvent.objects.filter(
                type=OrderEvent.Type.TRANSFER_CREATED,
                order_id__in=order_ids,
                meta__seller_id=int(seller.id),
            )
            .values("order_id", "meta")
        )
        actual_by_order = {}
        for ev in transfer_events:
            meta = ev.get("meta") or {}
            amt = int(meta.get("amount_cents") or 0)
            actual_by_order[ev["order_id"]] = actual_by_order.get(ev["order_id"], 0) + amt

        legacy_transfer_order_ids = set(
            OrderEvent.objects.filter(
                type=OrderEvent.Type.TRANSFER_CREATED,
                order_id__in=order_ids,
            )
            .exclude(meta__has_key="seller_id")
            .values_list("order_id", flat=True)
        )

        now = timezone.now()
        for row in paid_orders[:100]:
            oid = row["order_id"]
            expected = int(row.get("expected_cents") or 0)
            actual = int(actual_by_order.get(oid, 0) or 0)
            paid_at = row.get("paid_at")
            is_legacy = oid in legacy_transfer_order_ids

            status = "ok"
            detail = ""
            if expected and actual and expected != actual:
                status = "mismatch"
                detail = "transfer amount differs from expected"
            elif expected and not actual and is_legacy:
                status = "unknown"
                detail = "legacy transfer event missing seller metadata"
            elif expected and not actual and paid_at and (now - paid_at).total_seconds() > 600:
                status = "stuck"
                detail = "paid >10m ago; transfer not recorded"

            if status != "ok":
                mismatch_rows.append(
                    {
                        "order_id": oid,
                        "expected_cents": expected,
                        "actual_cents": actual,
                        "paid_at": paid_at,
                        "status": status,
                        "detail": detail,
                    }
                )
    except Exception:
        mismatch_rows = []

    recent_ledger = (
        SellerBalanceEntry.objects.filter(seller=seller)
        .select_related("order", "order_item")
        .order_by("-created_at")[:20]
    )

    ctx = {
        "seller": seller,
        "company_name": (getattr(getattr(seller, "profile", None), "shop_name", "") or "").strip() or seller.username,
        "products": products,
        "recent_orders": recent_orders,
        "consumer_count": consumer_count,
        "payout_available_cents": available_cents,
        "payout_available": cents_to_money(available_cents, "usd"),
        "pending_payout_cents": pending_cents,
        "pending_payout": cents_to_money(pending_cents, "usd"),
        "pending_items": pending_items,
        "recent_transfers": recent_transfers,
        "mismatch_rows": mismatch_rows,
        "recent_ledger": recent_ledger,
    }
    return render(request, "ops/seller_detail.html", ctx)


@ops_required
def consumers_list(request: HttpRequest) -> HttpResponse:
    qs = (
        User.objects.filter(orders__isnull=False)
        .select_related("profile")
        .distinct()
        .annotate(
            orders_count=Count("orders", distinct=True),
            paid_orders_count=Count("orders", filter=models.Q(orders__status=Order.Status.PAID), distinct=True),
            spent_cents=Sum("orders__total_cents", filter=models.Q(orders__status=Order.Status.PAID)),
        )
        .order_by("-paid_orders_count", "-orders_count", "id")
    )

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            models.Q(username__icontains=q)
            | models.Q(email__icontains=q)
            | models.Q(profile__first_name__icontains=q)
            | models.Q(profile__last_name__icontains=q)
        )

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(request, "ops/consumers_list.html", {"page_obj": page, "q": q})


@ops_required
def consumer_detail(request: HttpRequest, pk: int) -> HttpResponse:
    consumer = get_object_or_404(User.objects.select_related("profile"), pk=pk)

    orders = (
        Order.objects.filter(buyer=consumer)
        .prefetch_related("items", "items__seller", "items__product")
        .order_by("-created_at")[:100]
    )
    refunds = (
        RefundRequest.objects.filter(buyer=consumer)
        .select_related("order", "order_item", "seller")
        .order_by("-created_at")[:100]
    )
    try:
        from appointments.models import AppointmentRequest

        appointments = (
            AppointmentRequest.objects.filter(buyer=consumer)
            .select_related("service", "seller")
            .order_by("-created_at")[:100]
        )
    except Exception:
        appointments = []

    seller_rows = (
        OrderItem.objects.filter(order__buyer=consumer)
        .values("seller_id", "seller__username", "seller__profile__shop_name")
        .annotate(
            orders_count=Count("order_id", distinct=True),
            items_count=Count("id"),
            spend_cents=Sum("line_total_cents"),
        )
        .order_by("-spend_cents")[:50]
    )

    ctx = {
        "consumer": consumer,
        "orders": orders,
        "refunds": refunds,
        "appointments": appointments,
        "seller_rows": seller_rows,
    }
    return render(request, "ops/consumer_detail.html", ctx)


@ops_required
def qa_reports_queue(request: HttpRequest) -> HttpResponse:
    qs = ProductQuestionReport.objects.select_related("message", "reporter", "message__thread", "message__thread__product").order_by("-created_at")
    status = (request.GET.get("status") or ProductQuestionReport.Status.OPEN).strip()
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(request, "ops/qa_reports_queue.html", {"page_obj": page, "status": status})


@require_POST
@ops_required
def qa_report_resolve(request: HttpRequest, pk: int) -> HttpResponse:
    report = get_object_or_404(ProductQuestionReport, pk=pk)
    if report.status == ProductQuestionReport.Status.RESOLVED:
        messages.info(request, "Report is already resolved.")
        return redirect("ops:qa_reports_queue")

    report.status = ProductQuestionReport.Status.RESOLVED
    report.resolved_at = timezone.now()
    report.resolved_by = request.user
    report.save(update_fields=["status", "resolved_at", "resolved_by"])

    audit(
        request=request,
        action=AuditAction.MODERATION,
        verb="qa_report_resolved",
        reason=(request.POST.get("reason") or "").strip(),
        target=report,
        before={"status": ProductQuestionReport.Status.OPEN},
        after={"status": ProductQuestionReport.Status.RESOLVED},
    )

    messages.success(request, "Report marked as resolved.")
    return redirect("ops:qa_reports_queue")


@ops_required
def refund_requests_queue(request: HttpRequest) -> HttpResponse:
    qs = RefundRequest.objects.select_related("order", "buyer", "seller").order_by("-created_at")
    status = (request.GET.get("status") or RefundRequest.Status.REQUESTED).strip()
    company = (request.GET.get("company") or "").strip()
    if status:
        qs = qs.filter(status=status)
    if company:
        if company.isdigit():
            qs = qs.filter(seller_id=int(company))
        else:
            qs = qs.filter(
                models.Q(seller__profile__shop_name__icontains=company)
                | models.Q(seller__username__icontains=company)
            )

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(request, "ops/refund_requests_queue.html", {"page_obj": page, "status": status, "company": company})

@ops_required
def runbook(request: HttpRequest) -> HttpResponse:
    """Ops runbook and backup checklist.

    This is intentionally a human-facing page for daily operations and incident response.
    """
    command_defs = [
        {
            "verb": "Run reconciliation_check",
            "command": "reconciliation_check",
            "defaults": {"reconciliation_days": 30, "reconciliation_limit": 500},
            "aliases": {"days": "reconciliation_days", "limit": "reconciliation_limit"},
            "action_url": reverse("ops:runbook_run_reconciliation_check"),
        },
        {
            "verb": "Run alert_summary",
            "command": "alert_summary",
            "defaults": {"alert_hours": 24, "alert_reconciliation_days": 7},
            "aliases": {"hours": "alert_hours", "reconciliation_days": "alert_reconciliation_days"},
            "action_url": reverse("ops:runbook_run_alert_summary"),
        },
        {
            "verb": "Run launch_gate",
            "command": "launch_gate",
            "defaults": {
                "money_loop_limit": 200,
                "reconciliation_days": 30,
                "reconciliation_limit": 500,
                "alert_hours": 24,
                "alert_reconciliation_days": 7,
                "fail_on_warning": 0,
            },
            "aliases": {},
            "action_url": reverse("ops:runbook_run_launch_gate"),
        },
    ]
    kv_re = re.compile(r"([a-zA-Z_]+)=([0-9]+)")

    def _extract_params(reason: str, defaults: dict[str, int], aliases: dict[str, str]) -> dict[str, int]:
        params = dict(defaults)
        for key, raw in kv_re.findall(reason or ""):
            key = aliases.get(key, key)
            if key in params:
                try:
                    params[key] = int(raw)
                except Exception:
                    continue
        return params

    recent_rows = (
        AuditLog.objects.filter(verb__in=[cfg["verb"] for cfg in command_defs])
        .select_related("actor")
        .order_by("-created_at", "-id")[:30]
    )
    latest_by_verb: dict[str, AuditLog] = {}
    for row in recent_rows:
        if row.verb not in latest_by_verb:
            latest_by_verb[row.verb] = row

    runbook_last_runs = []
    for cfg in command_defs:
        verb = cfg["verb"]
        command_name = cfg["command"]
        row = latest_by_verb.get(verb)
        rerun_params = dict(cfg["defaults"])
        if not row:
            runbook_last_runs.append(
                {
                    "command": command_name,
                    "label": verb,
                    "has_run": False,
                    "status": "n/a",
                    "status_badge": "secondary",
                    "summary": "No runs recorded yet.",
                    "ran_at": None,
                    "actor_label": "",
                    "rerun_params": rerun_params,
                    "rerun_params_text": " ".join([f"{k}={v}" for k, v in rerun_params.items()]),
                    "action_url": cfg["action_url"],
                }
            )
            continue

        after = row.after_json or {}
        ok_flag = after.get("ok", None)
        result = after.get("result", {}) if isinstance(after, dict) else {}
        rerun_params = _extract_params(row.reason, cfg["defaults"], cfg.get("aliases", {}))
        if ok_flag is True:
            status = "ok"
            status_badge = "success"
        elif ok_flag is False:
            status = "issue"
            status_badge = "danger"
        else:
            status = "unknown"
            status_badge = "warning"

        if command_name == "reconciliation_check":
            summary = f"inspected={int(result.get('inspected_orders', 0) or 0)} mismatches={int(result.get('mismatches_total', 0) or 0)}"
        elif command_name == "alert_summary":
            summary = f"status={str(result.get('status') or 'n/a')}"
        elif command_name == "launch_gate":
            summary = (
                f"status={str(result.get('status') or 'n/a')} "
                f"critical={int(result.get('critical_count', 0) or 0)} "
                f"warning={int(result.get('warning_count', 0) or 0)}"
            )
        else:
            summary = ""

        runbook_last_runs.append(
            {
                "command": command_name,
                "label": verb,
                "has_run": True,
                "status": status,
                "status_badge": status_badge,
                "summary": summary,
                "ran_at": row.created_at,
                "actor_label": (row.actor.email if row.actor and getattr(row.actor, "email", "") else (row.actor.username if row.actor else "system")),
                "rerun_params": rerun_params,
                "rerun_params_text": " ".join([f"{k}={v}" for k, v in rerun_params.items()]),
                "action_url": cfg["action_url"],
            }
        )

    ctx = {
        "use_s3": bool(getattr(settings, "USE_S3", False)),
        "email_backend": str(getattr(settings, "EMAIL_BACKEND", "")),
        "default_from_email": str(getattr(settings, "DEFAULT_FROM_EMAIL", "")),
        "stripe_configured": bool(getattr(settings, "STRIPE_SECRET_KEY", "")),
        "runbook_last_runs": runbook_last_runs,
    }
    return render(request, "ops/runbook.html", ctx)


@require_POST
@ops_required
def runbook_run_reconciliation_check(request: HttpRequest) -> HttpResponse:
    """Run reconciliation_check from Ops UI and record result in AuditLog."""
    try:
        days = int((request.POST.get("reconciliation_days") or "30").strip())
    except Exception:
        days = 30
    try:
        limit = int((request.POST.get("reconciliation_limit") or "500").strip())
    except Exception:
        limit = 500
    days = max(1, min(days, 365))
    limit = max(1, min(limit, 2000))

    out = StringIO()
    payload = {}
    ok = True
    err = ""
    try:
        call_command("reconciliation_check", days=days, limit=limit, json=True, stdout=out)
        payload = json.loads(out.getvalue() or "{}")
        ok = bool(payload.get("ok", False))
    except Exception as e:
        ok = False
        err = str(e)

    audit(
        request=request,
        action=AuditAction.OTHER,
        verb="Run reconciliation_check",
        reason=f"days={days} limit={limit}",
        after={
            "ok": ok,
            "error": err,
            "result": payload,
        },
    )

    if ok:
        messages.success(
            request,
            f"reconciliation_check OK. inspected={payload.get('inspected_orders', 0)} mismatches={payload.get('mismatches_total', 0)}",
        )
    else:
        messages.error(
            request,
            "reconciliation_check reported issues."
            + (f" {err}" if err else ""),
        )
    return redirect("ops:runbook")


@require_POST
@ops_required
def runbook_run_alert_summary(request: HttpRequest) -> HttpResponse:
    """Run alert_summary from Ops UI and record result in AuditLog."""
    try:
        hours = int((request.POST.get("alert_hours") or "24").strip())
    except Exception:
        hours = 24
    try:
        reconciliation_days = int((request.POST.get("alert_reconciliation_days") or "7").strip())
    except Exception:
        reconciliation_days = 7
    hours = max(1, min(hours, 720))
    reconciliation_days = max(1, min(reconciliation_days, 365))

    out = StringIO()
    payload = {}
    ok = True
    err = ""
    try:
        call_command(
            "alert_summary",
            hours=hours,
            reconciliation_days=reconciliation_days,
            json=True,
            stdout=out,
        )
        payload = json.loads(out.getvalue() or "{}")
        ok = str(payload.get("status") or "ok") == "ok"
    except Exception as e:
        ok = False
        err = str(e)

    audit(
        request=request,
        action=AuditAction.OTHER,
        verb="Run alert_summary",
        reason=f"hours={hours} reconciliation_days={reconciliation_days}",
        after={
            "ok": ok,
            "error": err,
            "result": payload,
        },
    )

    if ok:
        messages.success(request, "alert_summary OK.")
    else:
        messages.warning(
            request,
            "alert_summary returned warning/critical."
            + (f" {err}" if err else ""),
        )
    return redirect("ops:runbook")


@require_POST
@ops_required
def runbook_run_launch_gate(request: HttpRequest) -> HttpResponse:
    """Run launch_gate from Ops UI and record result in AuditLog."""
    try:
        money_loop_limit = int((request.POST.get("money_loop_limit") or "200").strip())
    except Exception:
        money_loop_limit = 200
    try:
        reconciliation_days = int((request.POST.get("reconciliation_days") or "30").strip())
    except Exception:
        reconciliation_days = 30
    try:
        reconciliation_limit = int((request.POST.get("reconciliation_limit") or "500").strip())
    except Exception:
        reconciliation_limit = 500
    try:
        alert_hours = int((request.POST.get("alert_hours") or "24").strip())
    except Exception:
        alert_hours = 24
    try:
        alert_reconciliation_days = int((request.POST.get("alert_reconciliation_days") or "7").strip())
    except Exception:
        alert_reconciliation_days = 7

    fail_on_warning = (request.POST.get("fail_on_warning") or "").strip().lower() in {"1", "true", "on", "yes"}

    money_loop_limit = max(1, min(money_loop_limit, 2000))
    reconciliation_days = max(1, min(reconciliation_days, 365))
    reconciliation_limit = max(1, min(reconciliation_limit, 5000))
    alert_hours = max(1, min(alert_hours, 720))
    alert_reconciliation_days = max(1, min(alert_reconciliation_days, 365))

    out = StringIO()
    payload = {}
    err = ""
    status = "ok"
    ok = True
    try:
        call_command(
            "launch_gate",
            json=True,
            fail_on_warning=fail_on_warning,
            money_loop_limit=money_loop_limit,
            reconciliation_days=reconciliation_days,
            reconciliation_limit=reconciliation_limit,
            alert_hours=alert_hours,
            alert_reconciliation_days=alert_reconciliation_days,
            stdout=out,
        )
    except SystemExit as e:
        err = f"exit={getattr(e, 'code', None)}"
    except Exception as e:
        err = str(e)

    try:
        payload = json.loads(out.getvalue() or "{}")
        status = str(payload.get("status") or "critical")
    except Exception:
        payload = {}
        status = "critical"
        if not err:
            err = "Invalid launch_gate JSON payload."

    ok = status == "ok"

    audit(
        request=request,
        action=AuditAction.OTHER,
        verb="Run launch_gate",
        reason=(
            f"money_loop_limit={money_loop_limit} reconciliation_days={reconciliation_days} "
            f"reconciliation_limit={reconciliation_limit} alert_hours={alert_hours} "
            f"alert_reconciliation_days={alert_reconciliation_days} fail_on_warning={1 if fail_on_warning else 0}"
        ),
        after={
            "ok": ok,
            "status": status,
            "error": err,
            "result": payload,
        },
    )

    if status == "ok":
        messages.success(request, "launch_gate OK.")
    elif status == "warning":
        messages.warning(request, "launch_gate returned warning state.")
    else:
        messages.error(request, "launch_gate returned critical state.")

    return redirect("ops:runbook")


@ops_required
def alerts_summary(request: HttpRequest) -> JsonResponse:
    """Ops-only JSON alert summary for polling and runbooks."""
    try:
        hours = int((request.GET.get("hours") or "24").strip())
    except Exception:
        hours = 24
    try:
        reconciliation_days = int((request.GET.get("reconciliation_days") or "7").strip())
    except Exception:
        reconciliation_days = 7

    payload = build_alert_summary(hours=hours, reconciliation_days=reconciliation_days)
    return JsonResponse(payload, status=200)


@ops_required
def ops_health(request: HttpRequest) -> HttpResponse:
    """Ops-only health surface.

    Pack BJ:
    - Render a human-friendly HTML page by default.
    - Support ?format=json for automation / quick copy-paste.

    Intended for smoke testing after deploy: confirms key subsystems are configured.
    """
    checks = {
        "debug": bool(getattr(settings, "DEBUG", False)),
        "email_backend": str(getattr(settings, "EMAIL_BACKEND", "")),
        "default_from_email": str(getattr(settings, "DEFAULT_FROM_EMAIL", "")),
        "stripe_configured": bool(getattr(settings, "STRIPE_SECRET_KEY", "")),
        "media_backend": "s3" if getattr(settings, "USE_S3", False) else "local",
        "recaptcha_enabled": bool(getattr(settings, "RECAPTCHA_V3_SITE_KEY", "")),
    }

    ok = True
    if not checks["email_backend"]:
        ok = False
    if not checks["default_from_email"]:
        ok = False

    if (request.GET.get("format") or "").strip().lower() in {"json", "1", "true"}:
        return JsonResponse({"ok": ok, "checks": checks})

    ctx = {
        "ok": ok,
        "checks": checks,
    }
    return render(request, "ops/health.html", ctx)



@ops_required
def launch_check(request: HttpRequest) -> HttpResponse:
    """Human-friendly launch readiness checklist (same logic as management command)."""
    results = run_launch_checks()
    payload = launch_as_dict(results)
    return render(request, "ops/launch_check.html", payload)



def _recon_csv_response(qs, filename: str) -> HttpResponse:
    """Return a CSV export of a reconciliation queryset (capped)."""
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(resp)
    writer.writerow([
        "order_id",
        "created_at",
        "paid_at",
        "status",
        "buyer",
        "guest_email",
        "subtotal_cents",
        "items_gross_cents",
        "expected_fee_cents",
        "items_fee_cents",
        "expected_net_cents",
        "items_net_cents",
        "totals_mismatch",
        "ledger_mismatch",
        "paid_missing_stripe_ids",
        "paid_missing_transfer_event",
        "stripe_session_id",
        "stripe_payment_intent_id",
        "has_transfer_event",
        "payout_skipped_unready_seller",
    ])

    for o in qs[:5000]:
        writer.writerow([
            o.pk,
            o.created_at.isoformat() if getattr(o, "created_at", None) else "",
            o.paid_at.isoformat() if getattr(o, "paid_at", None) else "",
            o.status,
            o.buyer.username if getattr(o, "buyer", None) else "",
            getattr(o, "guest_email", "") or "",
            int(getattr(o, "subtotal_cents", 0) or 0),
            int(getattr(o, "items_gross_cents_agg", 0) or 0),
            int(getattr(o, "expected_fee_cents_agg", 0) or 0),
            int(getattr(o, "marketplace_fee_cents_agg", 0) or 0),
            int(getattr(o, "expected_net_cents_agg", 0) or 0),
            int(getattr(o, "seller_net_cents_agg", 0) or 0),
            bool(getattr(o, "totals_mismatch", False)),
            bool(getattr(o, "ledger_mismatch", False)),
            bool(getattr(o, "paid_missing_stripe_ids", False)),
            bool(getattr(o, "paid_missing_transfer_event", False)),
            getattr(o, "stripe_session_id", "") or "",
            getattr(o, "stripe_payment_intent_id", "") or "",
            bool(getattr(o, "has_transfer_event", False)),
            bool(getattr(o, "payout_skipped_unready_seller", False)),
        ])
    return resp

@ops_required
def reconciliation_list(request: HttpRequest) -> HttpResponse:
    """Financial reconciliation view for paid/awaiting-payment orders.

    Shows snapshot-based expected fee/net vs item ledger totals and basic Stripe markers.
    """
    qs = annotate_order_reconciliation(Order.objects.select_related("buyer")).order_by("-created_at")

    status = (request.GET.get("status") or "").strip()
    company = (request.GET.get("company") or "").strip()
    if status:
        qs = qs.filter(status=status)
    if company:
        if company.isdigit():
            qs = qs.filter(items__seller_id=int(company)).distinct()
        else:
            qs = qs.filter(
                models.Q(items__seller__profile__shop_name__icontains=company)
                | models.Q(items__seller__username__icontains=company)
            ).distinct()

    only_issues = (request.GET.get("issues") or "").strip().lower() in {"1", "true", "yes", "on"}
    if only_issues:
        qs = qs.filter(
            models.Q(totals_mismatch=True)
            | models.Q(ledger_mismatch=True)
            | models.Q(paid_missing_stripe_ids=True)
            | models.Q(paid_missing_transfer_event=True)
        )

    export_format = (request.GET.get("format") or "").strip().lower()
    if export_format == "csv":
        return _recon_csv_response(qs, "reconciliation.csv")

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)

    ctx = {
        "page_obj": page,
        "status": status,
        "company": company,
        "only_issues": only_issues,
    }
    return render(request, "ops/reconciliation_list.html", ctx)


@ops_required
def reconciliation_mismatches(request: HttpRequest) -> HttpResponse:
    qs = annotate_order_reconciliation(Order.objects.select_related("buyer")).order_by("-created_at")

    qs = qs.filter(
        models.Q(totals_mismatch=True)
        | models.Q(ledger_mismatch=True)
        | models.Q(paid_missing_stripe_ids=True)
        | models.Q(paid_missing_transfer_event=True)
    )

    # optional status filter
    status = (request.GET.get("status") or "").strip()
    company = (request.GET.get("company") or "").strip()
    if status:
        qs = qs.filter(status=status)
    if company:
        if company.isdigit():
            qs = qs.filter(items__seller_id=int(company)).distinct()
        else:
            qs = qs.filter(
                models.Q(items__seller__profile__shop_name__icontains=company)
                | models.Q(items__seller__username__icontains=company)
            ).distinct()

    counts = {
        "totals_mismatch": qs.filter(totals_mismatch=True).count(),
        "ledger_mismatch": qs.filter(ledger_mismatch=True).count(),
        "paid_missing_stripe_ids": qs.filter(paid_missing_stripe_ids=True).count(),
        "paid_missing_transfer_event": qs.filter(paid_missing_transfer_event=True).count(),
    }

    export_format = (request.GET.get("format") or "").strip().lower()
    if export_format == "csv":
        return _recon_csv_response(qs, "reconciliation_mismatches.csv")

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)

    ctx = {
        "page_obj": page,
        "status": status,
        "company": company,
        "counts": counts,
    }
    return render(request, "ops/reconciliation_mismatches.html", ctx)


@ops_required
def error_events(request: HttpRequest) -> HttpResponse:
    """List captured 500-class error events."""

    qs = ErrorEvent.objects.select_related("user", "resolved_by").all()

    status = (request.GET.get("status") or "").strip().lower()
    if status == "open":
        qs = qs.filter(is_resolved=False)
    elif status == "resolved":
        qs = qs.filter(is_resolved=True)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            models.Q(request_id__icontains=q)
            | models.Q(path__icontains=q)
            | models.Q(exception_type__icontains=q)
            | models.Q(message__icontains=q)
        )

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "status": status,
    }
    return render(request, "ops/error_events.html", ctx)


@ops_required
def error_event_detail(request: HttpRequest, pk: int) -> HttpResponse:
    ev = get_object_or_404(ErrorEvent.objects.select_related("user", "resolved_by"), pk=pk)
    return render(request, "ops/error_event_detail.html", {"ev": ev})


@ops_required
@require_POST
def error_event_resolve(request: HttpRequest, pk: int) -> HttpResponse:
    ev = get_object_or_404(ErrorEvent, pk=pk)
    notes = (request.POST.get("resolution_notes") or "").strip()
    if not notes:
        messages.error(request, "Resolution notes are required.")
        return redirect("ops:error_event_detail", pk=pk)

    before = {
        "is_resolved": ev.is_resolved,
        "resolved_at": ev.resolved_at.isoformat() if ev.resolved_at else None,
        "resolved_by": ev.resolved_by_id,
        "resolution_notes": ev.resolution_notes,
    }

    ev.is_resolved = True
    ev.resolved_at = timezone.now()
    ev.resolved_by = request.user
    ev.resolution_notes = notes
    ev.save(update_fields=["is_resolved", "resolved_at", "resolved_by", "resolution_notes"])

    audit(
        request=request,
        action=AuditAction.OTHER,
        verb="resolve_error_event",
        reason=notes,
        target=ev,
        before_json=before,
        after_json={
            "is_resolved": ev.is_resolved,
            "resolved_at": ev.resolved_at.isoformat() if ev.resolved_at else None,
            "resolved_by": ev.resolved_by_id,
            "resolution_notes": ev.resolution_notes,
        },
    )

    messages.success(request, "Error marked as resolved.")
    return redirect("ops:error_event_detail", pk=pk)

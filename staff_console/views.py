from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.db.models import Count
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from orders.models import Order
from refunds.models import RefundRequest
from qa.models import ProductQuestionReport
from products.models import Product
from catalog.models import Category
from core.models import ContactMessage, SupportResponseTemplate, SupportOutboundEmailLog
from core.config import get_site_config

from .forms import ListingPolicyForm, ContactMessageTriageForm, SupportReplyForm
from ops.services import audit
from ops.models import AuditAction

from .decorators import staff_required


@staff_required
def dashboard(request):
    orders = Order.objects.all()
    refund_q = RefundRequest.objects.filter(status=RefundRequest.Status.REQUESTED)
    qa_q = ProductQuestionReport.objects.filter(status=ProductQuestionReport.Status.OPEN)
    support_q = ContactMessage.objects.filter(is_resolved=False)

    ctx = {
        "orders_total": orders.count(),
        "orders_paid": orders.filter(status=Order.Status.PAID).count(),
        "orders_pending": orders.filter(status__in=[Order.Status.PENDING, Order.Status.AWAITING_PAYMENT]).count(),
        "refunds_open": refund_q.count(),
        "qa_reports_open": qa_q.count(),
        "support_open": support_q.count(),
        "recent_orders": orders.order_by("-created_at")[:10],
        "recent_refunds": refund_q.order_by("-created_at")[:10],
        "recent_reports": qa_q.order_by("-created_at")[:10],
        "recent_support": ContactMessage.objects.select_related("user", "resolved_by").order_by("-created_at")[:10],
    }
    return render(request, "staff_console/dashboard.html", ctx)


@staff_required
def orders_list(request):
    qs = Order.objects.all().order_by("-created_at")
    return render(request, "staff_console/orders_list.html", {"orders": qs[:200]})


@staff_required
def order_detail(request, order_id: int):
    order = get_object_or_404(Order, pk=order_id)
    return render(request, "staff_console/order_detail.html", {"order": order})


@staff_required
def refund_requests_queue(request):
    qs = RefundRequest.objects.all().order_by("-created_at")
    return render(request, "staff_console/refund_requests_queue.html", {"refunds": qs[:200]})


@staff_required
def qa_reports_queue(request):
    qs = ProductQuestionReport.objects.select_related(
        "message",
        "reporter",
        "message__thread",
        "message__thread__product",
    ).order_by("-created_at")

    status = (request.GET.get("status") or ProductQuestionReport.Status.OPEN).strip()
    if status:
        qs = qs.filter(status=status)

    from django.core.paginator import Paginator  # local import keeps module lightweight
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(request, "staff_console/qa_reports_queue.html", {"page_obj": page, "status": status})


@staff_required
def resolve_qa_report(request, report_id: int):
    report = get_object_or_404(ProductQuestionReport, pk=report_id)

    if request.method != "POST":
        return redirect("staff_console:qa_reports_queue")

    if report.status == ProductQuestionReport.Status.RESOLVED:
        messages.info(request, "Report already resolved.")
        return redirect("staff_console:qa_reports_queue")

    before = {"status": report.status}
    report.status = ProductQuestionReport.Status.RESOLVED
    from django.utils import timezone
    report.resolved_at = timezone.now()
    report.resolved_by = request.user
    report.save(update_fields=["status", "resolved_at", "resolved_by"])

    audit(
        request=request,
        action=AuditAction.MODERATION,
        verb="qa_report_resolved_admin_console",
        reason=(request.POST.get("reason") or "").strip(),
        target=report,
        before=before,
        after={"status": report.status},
    )

    messages.success(request, "Report resolved.")
    return redirect("staff_console:qa_reports_queue")



@staff_required
def listings_list(request):
    qs = Product.objects.select_related("seller", "category", "subcategory").order_by("-created_at")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(title__icontains=q)

    flagged = (request.GET.get("flagged") or "").strip()
    if flagged == "1":
        qs = qs.filter(category__is_prohibited=True) | qs.filter(subcategory__is_prohibited=True)

    ctx = {
        "q": q,
        "flagged": flagged,
        "listings": qs[:200],
    }
    return render(request, "staff_console/listings_list.html", ctx)


@staff_required
def listing_edit(request, product_id: int):
    product = get_object_or_404(Product.objects.select_related("category", "subcategory", "seller"), pk=product_id)

    if request.method == "POST":
        form = ListingPolicyForm(request.POST, instance=product)
        if form.is_valid():
            before = {
                "is_active": product.is_active,
                "category_id": product.category_id,
                "subcategory_id": product.subcategory_id,
            }
            reason = (form.cleaned_data.get("reason") or "").strip()
            if not reason:
                messages.error(request, "Reason is required for staff listing changes.")
                return render(request, "staff_console/listing_edit.html", {"product": product, "form": form})
            updated = form.save(commit=False)
            updated.save()
            form.save_m2m()

            after = {
                "is_active": updated.is_active,
                "category_id": updated.category_id,
                "subcategory_id": updated.subcategory_id,
            }
            audit(
                request=request,
                action=AuditAction.MODERATION,
                verb="listing_policy_update",
                reason=(reason or "").strip(),
                target=updated,
                before=before,
                after=after,
            )
            messages.success(request, "Listing updated.")
            return redirect("staff_console:listings_list")
    else:
        form = ListingPolicyForm(instance=product)

    ctx = {"product": product, "form": form}
    return render(request, "staff_console/listing_edit.html", ctx)


@staff_required
def contact_messages_list(request):
    qs = ContactMessage.objects.select_related("user", "resolved_by", "last_responded_by").order_by("-created_at")

    status = (request.GET.get("status") or "open").strip().lower()
    if status == "open":
        qs = qs.filter(is_resolved=False)
    elif status == "resolved":
        qs = qs.filter(is_resolved=True)

    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(email__icontains=q)
            | Q(name__icontains=q)
            | Q(subject__icontains=q)
            | Q(message__icontains=q)
        )

    sla = (request.GET.get("sla") or "").strip().lower()
    if sla:
        qs = qs.filter(sla_tag=sla)

    from django.core.paginator import Paginator

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)
    ctx = {
        "page_obj": page,
        "status": status,
        "q": q,
        "sla": sla,
        "open_count": ContactMessage.objects.filter(is_resolved=False).count(),
        "resolved_count": ContactMessage.objects.filter(is_resolved=True).count(),
    }
    return render(request, "staff_console/contact_messages_list.html", ctx)


@staff_required
def contact_message_detail(request, message_id: int):
    msg = get_object_or_404(ContactMessage.objects.select_related("user", "resolved_by", "last_responded_by"), pk=message_id)

    triage_form = ContactMessageTriageForm(instance=msg)

    # Reply form defaults
    template_id = (request.GET.get("template") or "").strip()
    tpl = None
    if template_id.isdigit():
        tpl = SupportResponseTemplate.objects.filter(is_active=True, pk=int(template_id)).first()

    default_subject = "Re: Your message to Local Market NE"
    if msg.subject:
        default_subject = f"Re: {msg.subject}"[:200]

    initial = {
        "subject": (tpl.subject or default_subject) if tpl else default_subject,
        "body": (tpl.body or "") if tpl else "",
        "mark_resolved": True,
    }
    reply_form = SupportReplyForm(initial=initial)

    templates = SupportResponseTemplate.objects.filter(is_active=True).order_by("title")
    outbound_emails = (
        SupportOutboundEmailLog.objects.filter(contact_message=msg)
        .select_related("sent_by")
        .order_by("-sent_at")[:10]
    )
    return render(
        request,
        "staff_console/contact_message_detail.html",
        {
            "msg": msg,
            "triage_form": triage_form,
            "reply_form": reply_form,
            "templates": templates,
            "selected_template": tpl,
            "outbound_emails": outbound_emails,
        },
    )


@staff_required
def contact_message_update(request, message_id: int):
    if request.method != "POST":
        return redirect("staff_console:contact_message_detail", message_id=message_id)

    msg = get_object_or_404(ContactMessage, pk=message_id)
    form = ContactMessageTriageForm(request.POST, instance=msg)
    if not form.is_valid():
        messages.error(request, "Please correct the errors and try again.")
        return redirect("staff_console:contact_message_detail", message_id=message_id)

    before = {"sla_tag": msg.sla_tag, "internal_notes": msg.internal_notes}
    updated = form.save(commit=False)
    updated.save(update_fields=["sla_tag", "internal_notes"])

    audit(
        request=request,
        action=AuditAction.MODERATION,
        verb="contact_message_triage_updated",
        reason=(request.POST.get("reason") or "").strip(),
        target=updated,
        before=before,
        after={"sla_tag": updated.sla_tag, "internal_notes": updated.internal_notes},
    )

    messages.success(request, "Triage updated.")
    return redirect("staff_console:contact_message_detail", message_id=message_id)


@staff_required
def contact_message_reply(request, message_id: int):
    if request.method != "POST":
        return redirect("staff_console:contact_message_detail", message_id=message_id)

    msg = get_object_or_404(ContactMessage, pk=message_id)
    form = SupportReplyForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please correct the reply form and try again.")
        return redirect("staff_console:contact_message_detail", message_id=message_id)

    site_config = get_site_config()
    from_email = settings.DEFAULT_FROM_EMAIL
    support_email = (getattr(site_config, "support_email", "") or "").strip() or from_email

    subject = (form.cleaned_data.get("subject") or "").strip()[:200]
    body = (form.cleaned_data.get("body") or "").strip()
    mark_resolved = bool(form.cleaned_data.get("mark_resolved"))
    reason = (form.cleaned_data.get("reason") or "").strip()

    if not subject or not body:
        messages.error(request, "Subject and body are required.")
        return redirect("staff_console:contact_message_detail", message_id=message_id)

    # Best-effort send (do not crash staff console) + write an outbound log.
    email_status = SupportOutboundEmailLog.Status.SENT
    error_text = ""
    try:
        sent_count = send_mail(
            subject,
            body,
            support_email,
            [msg.email],
            fail_silently=False,
        )
        if int(sent_count or 0) < 1:
            email_status = SupportOutboundEmailLog.Status.FAILED
            error_text = "Email backend reported 0 messages sent."
    except Exception as e:
        email_status = SupportOutboundEmailLog.Status.FAILED
        error_text = (str(e) or "").strip()[:2000]

    SupportOutboundEmailLog.objects.create(
        contact_message=msg,
        to_email=msg.email,
        from_email=support_email,
        subject=subject,
        body=body,
        status=email_status,
        error_text=error_text,
        sent_by=request.user,
    )

    before = {
        "response_count": msg.response_count,
        "last_responded_at": msg.last_responded_at.isoformat() if msg.last_responded_at else None,
        "is_resolved": msg.is_resolved,
    }

    msg.response_count = int(msg.response_count or 0) + 1
    msg.last_responded_at = timezone.now()
    msg.last_responded_by = request.user
    update_fields = ["response_count", "last_responded_at", "last_responded_by"]

    if mark_resolved and not msg.is_resolved:
        msg.is_resolved = True
        msg.resolved_at = timezone.now()
        msg.resolved_by = request.user
        update_fields += ["is_resolved", "resolved_at", "resolved_by"]

    msg.save(update_fields=update_fields)

    audit(
        request=request,
        action=AuditAction.MODERATION,
        verb="contact_message_reply_sent",
        reason=reason,
        target=msg,
        before=before,
        after={
            "response_count": msg.response_count,
            "last_responded_at": msg.last_responded_at.isoformat() if msg.last_responded_at else None,
            "is_resolved": msg.is_resolved,
        },
    )

    messages.success(request, "Reply sent.")
    return redirect("staff_console:contact_message_detail", message_id=message_id)


@staff_required
def contact_message_toggle_resolved(request, message_id: int):
    if request.method != "POST":
        return redirect("staff_console:contact_messages_list")

    msg = get_object_or_404(ContactMessage, pk=message_id)
    from django.utils import timezone

    before = {"is_resolved": msg.is_resolved}
    make_resolved = (request.POST.get("resolved") or "").strip() in {"1", "true", "yes", "on"}

    if make_resolved and not msg.is_resolved:
        msg.is_resolved = True
        msg.resolved_at = timezone.now()
        msg.resolved_by = request.user
        msg.save(update_fields=["is_resolved", "resolved_at", "resolved_by"])
        audit(
            request=request,
            action=AuditAction.MODERATION,
            verb="contact_message_resolved",
            reason=(request.POST.get("reason") or "").strip(),
            target=msg,
            before=before,
            after={"is_resolved": True},
        )
        messages.success(request, "Marked resolved.")
    elif (not make_resolved) and msg.is_resolved:
        msg.is_resolved = False
        msg.resolved_at = None
        msg.resolved_by = None
        msg.save(update_fields=["is_resolved", "resolved_at", "resolved_by"])
        audit(
            request=request,
            action=AuditAction.MODERATION,
            verb="contact_message_reopened",
            reason=(request.POST.get("reason") or "").strip(),
            target=msg,
            before=before,
            after={"is_resolved": False},
        )
        messages.success(request, "Reopened.")

    return redirect("staff_console:contact_message_detail", message_id=msg.id)

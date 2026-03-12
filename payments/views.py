# payments/views.py
from __future__ import annotations

import stripe

from django.contrib import messages
from django.conf import settings

from django.utils import timezone
from core.config import get_site_config

from accounts.decorators import email_verified_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from legal.models import LegalDocument
from legal.services import has_accepted_doc_type, record_acceptance_for_doc_types

from products.permissions import seller_required

from .models import SellerBalanceEntry, SellerFeeInvoice, SellerStripeAccount
from .services import get_seller_balance_cents
from .stripe_connect import create_account_link, create_express_account, retrieve_account


def _seller_email_for_connect(user) -> str:
    """Pick a stable email for Stripe Connect.

    Preference order:
      1) user.email (if you have a custom user model with email)
      2) user.profile.email (your Profile model stores contact email)
    """
    email = (getattr(user, "email", "") or "").strip()
    if email:
        return email

    profile = getattr(user, "profile", None)
    if profile is not None:
        email = (getattr(profile, "email", "") or "").strip()
        if email:
            return email

    return ""


def _refresh_connect_status(obj: SellerStripeAccount) -> None:
    """Refresh Stripe Connect status fields from Stripe (best-effort)."""
    if not obj.stripe_account_id:
        return

    acct = retrieve_account(obj.stripe_account_id)
    obj.details_submitted = bool(acct.get("details_submitted"))
    obj.charges_enabled = bool(acct.get("charges_enabled"))
    obj.payouts_enabled = bool(acct.get("payouts_enabled"))
    obj.save(
        update_fields=[
            "details_submitted",
            "charges_enabled",
            "payouts_enabled",
            "updated_at",
        ]
    )

    # This will also sync Profile legacy fields now.
    obj.mark_onboarding_completed_if_ready()


@seller_required
def connect_status(request):
    """Seller-facing status page + CTA to start/continue Stripe onboarding."""
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)

    # Optional: light refresh on GET if linked but not ready yet.
    if obj.stripe_account_id and not obj.is_ready:
        try:
            _refresh_connect_status(obj)
        except Exception:
            pass

    seller_agreement_doc = None
    seller_agreement_accepted = False
    try:
        seller_agreement_doc = (
            LegalDocument.objects.filter(
                doc_type=LegalDocument.DocType.SELLER_AGREEMENT,
                is_published=True,
            )
            .order_by("-version")
            .first()
        )
        if seller_agreement_doc is not None:
            seller_agreement_accepted = has_accepted_doc_type(
                doc_type=LegalDocument.DocType.SELLER_AGREEMENT,
                request=request,
                user=request.user,
            )
    except Exception:
        seller_agreement_doc = None

    cfg = get_site_config()

    prof = getattr(request.user, "profile", None)
    seller_age_confirmed = bool(getattr(prof, "is_age_18_confirmed", False)) if prof else False
    seller_prohibited_ack = bool(getattr(prof, "seller_prohibited_items_ack", False)) if prof else False

    context = {
        "stripe": obj,
        "ready": obj.is_ready,
        "seller_agreement_doc": seller_agreement_doc,
        "seller_agreement_accepted": seller_agreement_accepted,
        "seller_requires_age_18": bool(getattr(cfg, "seller_requires_age_18", True)),
        "seller_prohibited_notice": (getattr(cfg, "seller_prohibited_items_notice", "") or "").strip(),
        "seller_age_confirmed": seller_age_confirmed,
        "seller_prohibited_ack": seller_prohibited_ack,
    }
    return render(request, "payments/connect_status.html", context)


@seller_required
@email_verified_required
@require_POST
def connect_start(request):
    """Create Stripe Express account if needed, then redirect to onboarding link."""
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)

    # Pack V: Require Seller Agreement acceptance only when a published Seller Agreement exists.
    seller_agreement_doc = (
        LegalDocument.objects.filter(
            doc_type=LegalDocument.DocType.SELLER_AGREEMENT,
            is_published=True,
        )
        .order_by("-version")
        .first()
    )
    if seller_agreement_doc is not None:
        try:
            accepted = has_accepted_doc_type(
                doc_type=LegalDocument.DocType.SELLER_AGREEMENT,
                request=request,
                user=request.user,
            )
        except Exception:
            accepted = False

        if not accepted:
            checked = (request.POST.get("accept_seller_agreement") or "").strip() == "1"
            if not checked:
                messages.error(request, "Please accept the Seller Agreement to continue.")
                return redirect("payments:connect_status")
            try:
                record_acceptance_for_doc_types(
                    request=request,
                    user=request.user,
                    doc_types=[LegalDocument.DocType.SELLER_AGREEMENT],
                )
            except ValidationError:
                messages.error(request, "Seller Agreement is not published yet. Please try again later.")
                return redirect("payments:connect_status")
            except Exception:
                messages.error(request, "We couldn't record your acceptance. Please try again.")
                return redirect("payments:connect_status")

    # Pack BK: Seller onboarding policy acknowledgements
    cfg = get_site_config()
    prof = getattr(request.user, "profile", None)
    if prof is not None:
        # 18+ is required for sellers (buyers are not gated)
        if bool(getattr(cfg, "seller_requires_age_18", True)) and not bool(getattr(prof, "is_age_18_confirmed", False)):
            checked = (request.POST.get("confirm_seller_age_18") or "").strip() == "1"
            if not checked:
                messages.error(request, "Please confirm you are 18+ to continue seller onboarding.")
                return redirect("payments:connect_status")
            prof.is_age_18_confirmed = True
            prof.age_18_confirmed_at = timezone.now()

        # Prohibited items acknowledgement for sellers
        if not bool(getattr(prof, "seller_prohibited_items_ack", False)):
            checked = (request.POST.get("ack_prohibited_items") or "").strip() == "1"
            if not checked:
                messages.error(request, "Please acknowledge the prohibited items policy to continue.")
                return redirect("payments:connect_status")
            prof.seller_prohibited_items_ack = True
            prof.seller_prohibited_items_ack_at = timezone.now()

        try:
            prof.save(update_fields=[
                "is_age_18_confirmed",
                "age_18_confirmed_at",
                "seller_prohibited_items_ack",
                "seller_prohibited_items_ack_at",
                "updated_at",
            ])
        except Exception:
            messages.error(request, "We couldn't save your onboarding confirmations. Please try again.")
            return redirect("payments:connect_status")


    if not obj.stripe_account_id:
        email = _seller_email_for_connect(request.user)
        if not email:
            messages.error(
                request,
                "Your account is missing an email. Add one in your profile, then try again.",
            )
            return redirect("payments:connect_status")

        acct = create_express_account(email=email, country="US")
        obj.stripe_account_id = acct["id"]
        obj.details_submitted = bool(acct.get("details_submitted"))
        obj.charges_enabled = bool(acct.get("charges_enabled"))
        obj.payouts_enabled = bool(acct.get("payouts_enabled"))
        obj.save(
            update_fields=[
                "stripe_account_id",
                "details_submitted",
                "charges_enabled",
                "payouts_enabled",
                "updated_at",
            ]
        )

        # Immediately mirror legacy Profile fields.
        obj.mark_onboarding_completed_if_ready()

    obj.mark_onboarding_started()

    link = create_account_link(stripe_account_id=obj.stripe_account_id)
    return redirect(link["url"])


@seller_required
@email_verified_required
@require_POST
def connect_sync(request):
    """Manual refresh button for sellers (handy if webhook delivery is delayed)."""
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)
    if not obj.stripe_account_id:
        messages.info(request, "You haven’t started Stripe onboarding yet.")
        return redirect("payments:connect_status")

    try:
        _refresh_connect_status(obj)
    except Exception:
        messages.info(
            request, "Couldn’t refresh Stripe status right now. Try again in a moment."
        )
        return redirect("payments:connect_status")

    if obj.is_ready:
        messages.success(request, "Stripe payouts are enabled. You’re ready to sell!")
    else:
        messages.info(
            request,
            "Stripe status refreshed. If anything is missing, click Continue to finish onboarding.",
        )

    return redirect("payments:connect_status")


@seller_required
def connect_refresh(request):
    """Stripe sends user here if they abandon or the session expires."""
    messages.info(
        request, "Your Stripe onboarding link expired. Click Continue to generate a new one."
    )
    return redirect("payments:connect_status")


@seller_required
def connect_return(request):
    """Stripe sends user here after onboarding. We refresh the account status."""
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)

    if obj.stripe_account_id:
        try:
            _refresh_connect_status(obj)
        except Exception:
            pass

    if obj.is_ready:
        messages.success(request, "Stripe payouts are enabled. You’re ready to sell!")
        return redirect("products:seller_list")
    else:
        messages.info(
            request,
            "Stripe setup saved. If anything is missing, click Continue to finish onboarding.",
        )

    return redirect("payments:connect_status")


@seller_required
def payouts_dashboard(request):
    """
    Seller payouts / ledger page.

    Shows:
      - current signed balance (platform owes seller if positive; seller owes platform if negative)
      - ledger entries (append-only)
      - optional filters: reason, q (note/order id)
    """
    seller = request.user

    balance_cents = int(get_seller_balance_cents(seller=seller) or 0)

    reason = (request.GET.get("reason") or "").strip()
    q = (request.GET.get("q") or "").strip()

    entries = SellerBalanceEntry.objects.filter(seller=seller).select_related(
        "order", "order_item"
    )

    if reason:
        entries = entries.filter(reason=reason)

    if q:
        entries = entries.filter(Q(note__icontains=q) | Q(order__id__icontains=q))

    entries = entries.order_by("-created_at")

    paginator = Paginator(entries, 50)
    page = paginator.get_page(request.GET.get("page") or 1)

    stripe_obj, _ = SellerStripeAccount.objects.get_or_create(user=seller)

    context = {
        "balance_cents": balance_cents,
        "page_obj": page,
        "entries": page.object_list,
        "reason": reason,
        "q": q,
        "reasons": SellerBalanceEntry.Reason.choices,
        "stripe": stripe_obj,
        "stripe_ready": stripe_obj.is_ready,
    }
    return render(request, "payments/payouts_dashboard.html", context)


def _verify_and_parse_connect_webhook(payload: bytes, sig_header: str):
    """Verify Stripe webhook for Connect events."""
    import stripe
    from django.conf import settings

    stripe.api_key = settings.STRIPE_SECRET_KEY

    secret = getattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", "")
    if not secret:
        raise RuntimeError("STRIPE_CONNECT_WEBHOOK_SECRET is not configured")

    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=secret,
    )


def _stripe():
    stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    return stripe


def _stripe_configured() -> bool:
    return bool((getattr(settings, "STRIPE_SECRET_KEY", "") or "").strip())


@csrf_exempt
@require_POST
def stripe_connect_webhook(request):
    """Stripe webhook endpoint to keep Connect statuses updated."""
    payload = request.body
    sig_header = request.headers.get("Stripe-Signature", "")

    if not sig_header:
        return HttpResponseBadRequest("Missing signature")

    try:
        event = _verify_and_parse_connect_webhook(payload, sig_header)
    except Exception:
        return HttpResponseBadRequest("Invalid signature")

    event_type = event.get("type", "")
    data_object = (event.get("data") or {}).get("object") or {}

    if event_type == "account.updated":
        acct_id = data_object.get("id", "")
        if acct_id:
            obj = SellerStripeAccount.objects.filter(stripe_account_id=acct_id).first()
            if obj:
                obj.details_submitted = bool(data_object.get("details_submitted"))
                obj.charges_enabled = bool(data_object.get("charges_enabled"))
                obj.payouts_enabled = bool(data_object.get("payouts_enabled"))
                obj.save(
                    update_fields=[
                        "details_submitted",
                        "charges_enabled",
                        "payouts_enabled",
                        "updated_at",
                    ]
                )
                # This now also syncs Profile legacy fields.
                obj.mark_onboarding_completed_if_ready()

    return HttpResponse(status=200)


@seller_required
def fees_dashboard(request):
    seller = request.user
    qs = (
        SellerFeeInvoice.objects.filter(seller=seller)
        .select_related("order", "order__buyer")
        .order_by("-created_at")
    )
    status = (request.GET.get("status") or "").strip().lower()
    if status in {SellerFeeInvoice.Status.OPEN, SellerFeeInvoice.Status.PAID, SellerFeeInvoice.Status.VOID}:
        qs = qs.filter(status=status)

    open_agg = SellerFeeInvoice.objects.filter(seller=seller, status=SellerFeeInvoice.Status.OPEN).aggregate(
        total=Sum("amount_cents"),
    )
    open_total_cents = int(open_agg.get("total") or 0)
    open_count = SellerFeeInvoice.objects.filter(seller=seller, status=SellerFeeInvoice.Status.OPEN).count()

    rows = []
    for inv in qs[:200]:
        order = inv.order
        buyer = getattr(order, "buyer", None)
        buyer_name = ""
        if buyer:
            buyer_name = (getattr(buyer, "username", "") or "").strip()
        if not buyer_name:
            buyer_name = (getattr(order, "guest_email", "") or "").strip() or "Guest buyer"
        buyer_email = (getattr(order, "buyer_email", "") or "").strip() if order else ""
        rows.append(
            {
                "invoice": inv,
                "buyer_name": buyer_name,
                "buyer_email": buyer_email,
                "contact_link": f"mailto:{buyer_email}" if buyer_email else "",
            }
        )

    return render(
        request,
        "payments/fees_dashboard.html",
        {
            "rows": rows,
            "open_total_cents": open_total_cents,
            "open_count": open_count,
            "status": status,
        },
    )


@seller_required
@require_POST
def fees_pay_now(request):
    seller = request.user
    if not _stripe_configured():
        messages.error(request, "Fee payment is unavailable right now. Stripe is not configured.")
        return redirect("payments:fees_dashboard")

    open_invoices = list(
        SellerFeeInvoice.objects.filter(seller=seller, status=SellerFeeInvoice.Status.OPEN).order_by("created_at")
    )
    if not open_invoices:
        messages.info(request, "No owed fees to pay right now.")
        return redirect("payments:fees_dashboard")

    total_cents = sum(int(inv.amount_cents or 0) for inv in open_invoices)
    if total_cents <= 0:
        messages.info(request, "No owed fees to pay right now.")
        return redirect("payments:fees_dashboard")

    success_url = request.build_absolute_uri(reverse("payments:fees_success")) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = request.build_absolute_uri(reverse("payments:fees_dashboard"))

    try:
        s = _stripe()
        session = s.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": int(total_cents),
                        "product_data": {"name": "Local Market NE marketplace fees owed"},
                    },
                    "quantity": 1,
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "seller_id": str(seller.id),
                "kind": "seller_fee_settlement",
            },
        )
    except Exception:
        messages.error(request, "Could not start fee payment right now. Please try again.")
        return redirect("payments:fees_dashboard")

    SellerFeeInvoice.objects.filter(id__in=[inv.id for inv in open_invoices]).update(
        stripe_session_id=session.id,
        updated_at=timezone.now(),
    )
    return redirect(session.url)


@seller_required
def fees_success(request):
    seller = request.user
    if not _stripe_configured():
        messages.info(request, "Payment status is pending sync. Please refresh shortly.")
        return redirect("payments:fees_dashboard")

    session_id = (request.GET.get("session_id") or "").strip()
    if not session_id:
        messages.info(request, "Payment completed. If balances do not update immediately, refresh in a moment.")
        return redirect("payments:fees_dashboard")

    invoices_qs = SellerFeeInvoice.objects.filter(
        seller=seller,
        status=SellerFeeInvoice.Status.OPEN,
        stripe_session_id=session_id,
    )
    if not invoices_qs.exists():
        messages.info(request, "No open fee invoices matched this session.")
        return redirect("payments:fees_dashboard")

    try:
        s = _stripe()
        session = s.checkout.Session.retrieve(session_id)
    except Exception:
        messages.info(request, "We could not verify payment status yet. Please refresh in a moment.")
        return redirect("payments:fees_dashboard")

    payment_status = str(getattr(session, "payment_status", "") or "")
    payment_intent = str(getattr(session, "payment_intent", "") or "")
    if payment_status == "paid":
        invoices_qs.update(
            status=SellerFeeInvoice.Status.PAID,
            paid_at=timezone.now(),
            stripe_payment_intent_id=payment_intent,
            updated_at=timezone.now(),
        )
        messages.success(request, "Fee payment received. Thank you.")
    else:
        messages.info(request, "Payment is not marked paid yet. Please refresh shortly.")
    return redirect("payments:fees_dashboard")

# legal/views.py
from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import LegalDocument
from .services import get_latest_published_docs, record_acceptance


@dataclass(frozen=True)
class LegalDocFallback:
    """Fallback doc object for rendering when no published doc exists."""
    title: str
    summary: str
    body: str
    version: int = 0


def _get_latest_or_fallback(doc_type: LegalDocument.DocType):
    """Get published doc or return fallback with titles for unpublished docs."""
    if doc := (
        LegalDocument.objects.filter(doc_type=doc_type, is_published=True)
        .order_by("-version")
        .first()
    ):
        return doc

    title_map = {
        LegalDocument.DocType.TERMS: "Terms of Service",
        LegalDocument.DocType.PRIVACY: "Privacy Policy",
        LegalDocument.DocType.REFUND: "Refund Policy",
        LegalDocument.DocType.CONTENT: "Content & Safety Policy",
        LegalDocument.DocType.SELLER_AGREEMENT: "Seller Agreement",
        LegalDocument.DocType.SELLER_FEES: "Seller Fees",
        LegalDocument.DocType.FULFILLMENT_POLICY: "Fulfillment Policy",
        LegalDocument.DocType.SERVICES_POLICY: "Services & Appointments Policy",
    }

    title = title_map.get(doc_type, "Legal Policy")
    return LegalDocFallback(title=title, summary="", body="", version=0)


def _ctx_for(doc: LegalDocument | LegalDocFallback) -> dict:
    """Provide context for legal page templates."""
    docs = get_latest_published_docs()
    return {"doc": doc, "docs": docs}


# ----------------------------
# Public pages
# ----------------------------

def legal_index(request: HttpRequest) -> HttpResponse:
    """Landing page listing all legal documents."""
    docs = {
        "terms": _get_latest_or_fallback(LegalDocument.DocType.TERMS),
        "privacy": _get_latest_or_fallback(LegalDocument.DocType.PRIVACY),
        "refund": _get_latest_or_fallback(LegalDocument.DocType.REFUND),
        "content": _get_latest_or_fallback(LegalDocument.DocType.CONTENT),
        "seller_agreement": _get_latest_or_fallback(LegalDocument.DocType.SELLER_AGREEMENT),
        "seller_fees": _get_latest_or_fallback(LegalDocument.DocType.SELLER_FEES),
        "fulfillment_policy": _get_latest_or_fallback(LegalDocument.DocType.FULFILLMENT_POLICY),
        "services_policy": _get_latest_or_fallback(LegalDocument.DocType.SERVICES_POLICY),
    }
    return render(request, "legal/index.html", {"docs": docs})


def terms(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.TERMS)
    return render(request, "legal/terms.html", _ctx_for(doc))


def privacy(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.PRIVACY)
    return render(request, "legal/privacy.html", _ctx_for(doc))


def refund_policy(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.REFUND)
    return render(request, "legal/refund.html", _ctx_for(doc))


def content_policy(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.CONTENT)
    return render(request, "legal/content.html", _ctx_for(doc))


def seller_agreement(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.SELLER_AGREEMENT)
    return render(request, "legal/seller_agreement.html", _ctx_for(doc))


def seller_fees(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.SELLER_FEES)
    return render(request, "legal/seller_fees.html", _ctx_for(doc))


def fulfillment_policy(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.FULFILLMENT_POLICY)
    return render(request, "legal/fulfillment_policy.html", _ctx_for(doc))


def services_policy(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.SERVICES_POLICY)
    return render(request, "legal/services_policy.html", _ctx_for(doc))


# ----------------------------
# Acceptance (if used elsewhere)
# ----------------------------

@require_POST
def accept(request: HttpRequest) -> HttpResponse:
    """
    Records acceptance of all REQUIRED_DOC_TYPES in one action,
    for either logged-in user or guest_email (if provided).
    """
    next_url = (request.POST.get("next") or request.GET.get("next") or "/").strip()
    guest_email = (request.POST.get("guest_email") or "").strip().lower()

    try:
        record_acceptance(request=request, user=request.user, guest_email=guest_email)
        messages.success(request, "Thanks - your acceptance has been recorded.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to record acceptance. Please try again.")
        return redirect(reverse("legal:terms") + f"?next={next_url}")

    return redirect(next_url)


# ----------------------------
# Backwards-compatible aliases
# ----------------------------
index = legal_index
refund = refund_policy
content = content_policy

# legal/services.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest

from .models import LegalAcceptance, LegalDocument


# Base documents required for any checkout / marketplace use.
REQUIRED_DOC_TYPES: tuple[LegalDocument.DocType, ...] = (
    LegalDocument.DocType.TERMS,
    LegalDocument.DocType.PRIVACY,
    LegalDocument.DocType.REFUND,
    LegalDocument.DocType.CONTENT,
)


@dataclass(frozen=True)
class LegalStatus:
    ok: bool
    missing: list[LegalDocument.DocType]
    latest_docs: dict[LegalDocument.DocType, Optional[LegalDocument]]


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _get_client_ip(request: HttpRequest) -> str | None:
    trust_proxy = bool(getattr(settings, "THROTTLE_TRUST_PROXY_HEADERS", False))
    if trust_proxy:
        xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
        if xff:
            return xff.split(",")[0].strip() or None
    ip = (request.META.get("REMOTE_ADDR") or "").strip()
    return ip or None


def get_latest_published_doc(doc_type: LegalDocument.DocType) -> Optional[LegalDocument]:
    return (
        LegalDocument.objects.filter(doc_type=doc_type, is_published=True)
        .order_by("-version")
        .first()
    )


def get_latest_published_docs(
    doc_types: Sequence[LegalDocument.DocType] = REQUIRED_DOC_TYPES,
) -> dict[LegalDocument.DocType, Optional[LegalDocument]]:
    out: dict[LegalDocument.DocType, Optional[LegalDocument]] = {}
    for dt in doc_types:
        out[dt] = get_latest_published_doc(dt)
    return out


def _acceptance_exists_for(*, doc: LegalDocument, user, guest_email: str) -> bool:
    qs = LegalAcceptance.objects.filter(document_id=doc.id, document_hash=doc.content_hash)
    if user and getattr(user, "is_authenticated", False):
        return qs.filter(user_id=user.id).exists()
    if guest_email:
        return qs.filter(guest_email=_norm_email(guest_email)).exists()
    return False


def has_accepted_doc_type(
    *,
    doc_type: LegalDocument.DocType,
    request: HttpRequest,
    user,
    guest_email: str = "",
) -> bool:
    doc = get_latest_published_doc(doc_type)
    if doc is None:
        return False
    return _acceptance_exists_for(doc=doc, user=user, guest_email=guest_email)


def check_legal_acceptance_for_doc_types(
    *,
    request: HttpRequest,
    user,
    guest_email: str = "",
    doc_types: Sequence[LegalDocument.DocType] = REQUIRED_DOC_TYPES,
) -> LegalStatus:
    docs = get_latest_published_docs(doc_types)
    missing: list[LegalDocument.DocType] = []
    for dt, doc in docs.items():
        if doc is None:
            missing.append(dt)
            continue
        if not _acceptance_exists_for(doc=doc, user=user, guest_email=guest_email):
            missing.append(dt)

    return LegalStatus(ok=(len(missing) == 0), missing=missing, latest_docs=docs)


def check_legal_acceptance(*, request: HttpRequest, user, guest_email: str = "") -> LegalStatus:
    """Back-compat wrapper: checks REQUIRED_DOC_TYPES."""
    return check_legal_acceptance_for_doc_types(
        request=request,
        user=user,
        guest_email=guest_email,
        doc_types=REQUIRED_DOC_TYPES,
    )


@transaction.atomic
def record_acceptance_for_doc_types(
    *,
    request: HttpRequest,
    user,
    guest_email: str = "",
    doc_types: Sequence[LegalDocument.DocType] = REQUIRED_DOC_TYPES,
) -> None:
    docs = get_latest_published_docs(doc_types)
    if any(d is None for d in docs.values()):
        raise ValidationError("Legal documents are not published yet.")

    ip = _get_client_ip(request)
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:300]
    guest_email_norm = _norm_email(guest_email)

    for _, doc in docs.items():
        assert doc is not None
        if _acceptance_exists_for(doc=doc, user=user, guest_email=guest_email_norm):
            continue

        LegalAcceptance.objects.create(
            document=doc,
            user=user if (user and getattr(user, "is_authenticated", False)) else None,
            guest_email=guest_email_norm,
            ip_address=ip,
            user_agent=ua,
            document_hash=doc.content_hash,
        )


@transaction.atomic
def record_acceptance(*, request: HttpRequest, user, guest_email: str = "") -> None:
    """Back-compat wrapper: records acceptance for REQUIRED_DOC_TYPES."""
    record_acceptance_for_doc_types(
        request=request,
        user=user,
        guest_email=guest_email,
        doc_types=REQUIRED_DOC_TYPES,
    )

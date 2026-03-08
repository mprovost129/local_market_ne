from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import AuditAction, AuditLog
from .utils import request_meta


@transaction.atomic
def audit(
    *,
    request,
    action: str = AuditAction.OTHER,
    verb: str,
    reason: str = "",
    target=None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    meta = request_meta(request)
    ct = None
    obj_id = None
    if target is not None:
        ct = ContentType.objects.get_for_model(target.__class__)
        obj_id = str(target.pk)

    return AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        ip_address=meta.get("ip_address"),
        user_agent=meta.get("user_agent", ""),
        action=action,
        verb=verb,
        reason=reason or "",
        target_content_type=ct,
        target_object_id=obj_id,
        before_json=before or {},
        after_json=after or {},
    )

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import Group
from django.http import HttpRequest

STAFF_GROUP_NAME = "staff_admin"


def user_is_staff_admin(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name=STAFF_GROUP_NAME).exists()


def request_meta(request: HttpRequest) -> dict[str, Any]:
    return {
        "ip_address": request.META.get("REMOTE_ADDR"),
        "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:1000],
    }

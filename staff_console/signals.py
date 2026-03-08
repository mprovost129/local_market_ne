from __future__ import annotations

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

STAFF_GROUP_NAME = "staff_admin"

# Apps that day-to-day admins should manage.
STAFF_DEFAULT_APPS = {
    "orders",
    "refunds",
    "products",
    "appointments",
    "qa",
    "reviews",
    "accounts",
    "notifications",
}

def ensure_staff_admin_group(sender, **kwargs) -> None:
    """Ensure the staff_admin group exists with appropriate day-to-day permissions."""
    group, _ = Group.objects.get_or_create(name=STAFF_GROUP_NAME)

    perms: list[Permission] = []
    for model in apps.get_models():
        if model._meta.app_label in STAFF_DEFAULT_APPS:
            ct = ContentType.objects.get_for_model(model)
            perms.extend(list(Permission.objects.filter(content_type=ct)))

    if perms:
        group.permissions.set(perms)

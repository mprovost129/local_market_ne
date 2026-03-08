from __future__ import annotations

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


OPS_GROUP_NAME = "ops"

# Apps whose permissions Ops should have by default.
OPS_DEFAULT_APPS = {
    "orders",
    "payments",
    "refunds",
    "products",
    "appointments",
    "qa",
    "reviews",
    "accounts",
    "notifications",
    "analytics",
    "core",
    "legal",
    "catalog",
    "favorites",
}


def ensure_ops_group(sender, **kwargs) -> None:
    """Ensure the OPS group exists and has broad operational permissions.

    Notes:
    - Superusers are always treated as OPS by the app layer.
    - This group exists to support non-superuser operational staff later.
    """
    group, _ = Group.objects.get_or_create(name=OPS_GROUP_NAME)

    # Grant all permissions for models in our allowlist apps.
    perms: list[Permission] = []
    for model in apps.get_models():
        if model._meta.app_label in OPS_DEFAULT_APPS:
            ct = ContentType.objects.get_for_model(model)
            perms.extend(list(Permission.objects.filter(content_type=ct)))

    if perms:
        group.permissions.set(perms)

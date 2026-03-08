from __future__ import annotations

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class OpsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ops"

    def ready(self) -> None:
        from .signals import ensure_ops_group  # noqa: F401

        post_migrate.connect(ensure_ops_group, sender=self)

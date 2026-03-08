from __future__ import annotations

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class StaffConsoleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "staff_console"
    verbose_name = "Admin Console"

    def ready(self) -> None:
        from .signals import ensure_staff_admin_group  # noqa: F401

        post_migrate.connect(ensure_staff_admin_group, sender=self)

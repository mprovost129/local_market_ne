from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from ops.utils import OPS_GROUP_NAME
from staff_console.utils import STAFF_GROUP_NAME


class Command(BaseCommand):
    help = "Bootstrap day-to-day Admin Console account and Ops Console account (optional env-driven)."

    def handle(self, *args, **options):
        User = get_user_model()

        Group.objects.get_or_create(name=STAFF_GROUP_NAME)
        ops_group, _ = Group.objects.get_or_create(name=OPS_GROUP_NAME)

        # Grant explicit high-risk perms to ops group (least-privilege alternative to full owner/staff).
        high_risk_perms = Permission.objects.filter(
            codename__in=[
                "can_reprocess_webhooks",
                "can_retry_payouts",
                "can_trigger_refunds",
            ]
        )
        if high_risk_perms.exists():
            ops_group.permissions.add(*list(high_risk_perms))

        admin_username = os.getenv("LMNE_ADMIN_USERNAME", "").strip()
        admin_password = os.getenv("LMNE_ADMIN_PASSWORD", "").strip()
        ops_username = os.getenv("LMNE_OPS_USERNAME", "").strip()
        ops_password = os.getenv("LMNE_OPS_PASSWORD", "").strip()

        if not admin_username or not admin_password:
            self.stdout.write(self.style.WARNING(
                "LMNE_ADMIN_USERNAME/LMNE_ADMIN_PASSWORD not set; skipping Admin account creation."
            ))
        else:
            admin_user, created = User.objects.get_or_create(username=admin_username)
            if created:
                admin_user.set_password(admin_password)
            admin_user.is_staff = True
            admin_user.is_superuser = False
            admin_user.save()
            admin_user.groups.add(Group.objects.get(name=STAFF_GROUP_NAME))
            self.stdout.write(self.style.SUCCESS(f"Admin account ready: {admin_username} (staff_admin group)"))

        if not ops_username or not ops_password:
            self.stdout.write(self.style.WARNING(
                "LMNE_OPS_USERNAME/LMNE_OPS_PASSWORD not set; skipping Ops account creation."
            ))
        else:
            ops_user, created = User.objects.get_or_create(username=ops_username)
            if created:
                ops_user.set_password(ops_password)
            ops_user.is_staff = True
            ops_user.is_superuser = False
            ops_user.save()
            ops_user.groups.add(Group.objects.get(name=OPS_GROUP_NAME))
            self.stdout.write(self.style.SUCCESS(f"Ops account ready: {ops_username} (ops group)"))

        self.stdout.write(self.style.NOTICE("Done. You can now use /staff/ for Admin Console and /ops/ for Ops Console."))

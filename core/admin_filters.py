from __future__ import annotations

from django.contrib import admin
from django.db import models


def _company_label_for_user(user) -> str:
    profile = getattr(user, "profile", None)
    shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
    return shop_name or getattr(user, "username", "") or str(getattr(user, "id", ""))


class SellerCompanyFilter(admin.SimpleListFilter):
    title = "seller company"
    parameter_name = "seller_company"
    seller_field_name = "seller"

    def lookups(self, request, model_admin):
        from accounts.models import Profile

        rows = (
            Profile.objects.filter(is_seller=True)
            .select_related("user")
            .order_by("shop_name", "user__username")
            .only("user_id", "shop_name", "user__username")
        )
        return [(str(p.user_id), (p.shop_name or "").strip() or p.user.username) for p in rows[:300]]

    def queryset(self, request, queryset):
        val = (self.value() or "").strip()
        if not val:
            return queryset
        if val.isdigit():
            return queryset.filter(**{f"{self.seller_field_name}_id": int(val)})
        return queryset.filter(
            models.Q(**{f"{self.seller_field_name}__profile__shop_name__icontains": val})
            | models.Q(**{f"{self.seller_field_name}__username__icontains": val})
        ).distinct()


class UserCompanyFilter(admin.SimpleListFilter):
    title = "user company"
    parameter_name = "user_company"
    user_field_name = "user"

    def lookups(self, request, model_admin):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        rows = User.objects.select_related("profile").order_by("profile__shop_name", "username")
        out = []
        for u in rows[:300]:
            out.append((str(u.id), _company_label_for_user(u)))
        return out

    def queryset(self, request, queryset):
        val = (self.value() or "").strip()
        if not val:
            return queryset
        if val.isdigit():
            return queryset.filter(**{f"{self.user_field_name}_id": int(val)})
        return queryset.filter(
            models.Q(**{f"{self.user_field_name}__profile__shop_name__icontains": val})
            | models.Q(**{f"{self.user_field_name}__username__icontains": val})
        ).distinct()

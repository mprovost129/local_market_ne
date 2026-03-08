# refunds/admin.py

from __future__ import annotations

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from core.admin_filters import SellerCompanyFilter
from products.permissions import can_run_high_risk_action

from .models import RefundRequest, RefundAttempt


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    list_select_related = ("seller", "seller__profile", "buyer", "order", "order_item")
    list_display = (
        "id",
        "status",
        "reason",
        "order_link",
        "order_item_link",
        "seller_company",
        "seller",
        "buyer_or_guest",
        "total_refund_display",
        "created_at",
    )
    list_filter = ("status", "reason", "created_at", SellerCompanyFilter, "seller")
    search_fields = (
        "id",
        "order__id",
        "order_item__id",
        "seller__username",
        "seller__profile__shop_name",
        "buyer__username",
        "buyer__email",
        "order__guest_email",
        "requester_email",
        "stripe_refund_id",
    )
    ordering = ("-created_at",)
    actions = ("admin_trigger_refund",)

    readonly_fields = (
        "id",
        "order",
        "order_item",
        "seller",
        "buyer",
        "requester_email",
        "reason",
        "notes",
        "status",
        "line_subtotal_cents_snapshot",
        "tax_cents_allocated_snapshot",
        "shipping_cents_allocated_snapshot",
        "total_refund_cents_snapshot",
        "stripe_refund_id",
        "refunded_at",
        "transfer_reversal_id",
        "transfer_reversal_amount_cents",
        "transfer_reversed_at",
        "seller_decided_at",
        "seller_decision_note",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Identity", {"fields": ("id", "status", "reason", "created_at", "updated_at")}),
        ("Parties", {"fields": ("order", "order_item", "seller", "buyer", "requester_email")}),
        ("Buyer request", {"fields": ("notes",)}),
        (
            "Snapshots (source of truth)",
            {
                "fields": (
                    "line_subtotal_cents_snapshot",
                    "tax_cents_allocated_snapshot",
                    "shipping_cents_allocated_snapshot",
                    "total_refund_cents_snapshot",
                )
            },
        ),
        ("Seller decision", {"fields": ("seller_decided_at", "seller_decision_note")}),
        (
            "Stripe",
            {
                "fields": (
                    "stripe_refund_id",
                    "refunded_at",
                    "transfer_reversal_id",
                    "transfer_reversal_amount_cents",
                    "transfer_reversed_at",
                )
            },
        ),
    )

    def order_link(self, obj: RefundRequest) -> str:
        url = reverse("admin:orders_order_change", args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order_id)

    order_link.short_description = "Order"

    def order_item_link(self, obj: RefundRequest) -> str:
        url = reverse("admin:orders_orderitem_change", args=[obj.order_item_id])
        return format_html('<a href="{}">{}</a>', url, obj.order_item_id)

    order_item_link.short_description = "Order item"

    def buyer_or_guest(self, obj: RefundRequest) -> str:
        if obj.buyer_id:
            email = (getattr(obj.buyer, "email", "") or "").strip()
            username = getattr(obj.buyer, "username", str(obj.buyer_id))
            return f"{username} ({email})" if email else username
        return f"Guest ({(obj.requester_email or '').strip()})"

    buyer_or_guest.short_description = "Buyer"

    def seller_company(self, obj: RefundRequest) -> str:
        profile = getattr(obj.seller, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.seller, "username", str(obj.seller_id))

    seller_company.short_description = "Seller company"

    def total_refund_display(self, obj: RefundRequest) -> str:
        cents = int(obj.total_refund_cents_snapshot or 0)
        return f"${cents / 100:.2f}"

    total_refund_display.short_description = "Refund total"

    @admin.action(description="Trigger Stripe refund (DANGEROUS) for APPROVED requests")
    def admin_trigger_refund(self, request, queryset):
        """
        Safety valve:
        - Only APPROVED, not already refunded
        - Uses service layer so invariants stay centralized
        """
        if not can_run_high_risk_action(getattr(request, "user", None), "refunds.can_trigger_refunds"):
            self.message_user(
                request,
                "You do not have permission to trigger refunds from admin.",
                level=messages.ERROR,
            )
            return

        from .services import trigger_refund  # local import

        count_ok = 0
        count_skip = 0

        for rr in queryset.select_related("order", "seller"):
            if rr.status != RefundRequest.Status.APPROVED or rr.stripe_refund_id or rr.refunded_at:
                count_skip += 1
                continue

            try:
                trigger_refund(rr=rr, actor_user=request.user, allow_staff_safety_valve=True, request_id=getattr(request, 'request_id', '') )
                count_ok += 1
            except Exception as e:
                count_skip += 1
                messages.error(request, f"Refund {rr.pk}: {e}")

        if count_ok:
            messages.success(request, f"Processed {count_ok} refund(s).")
        if count_skip:
            messages.info(request, f"Skipped {count_skip} refund(s).")


@admin.register(RefundAttempt)
class RefundAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "refund_request",
        "success",
        "stripe_refund_id",
        "created_at",
    )
    list_filter = ("success",)
    search_fields = ("stripe_refund_id",)

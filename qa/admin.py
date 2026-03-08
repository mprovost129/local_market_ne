# qa/admin.py
from django.contrib import admin

from core.admin_filters import SellerCompanyFilter

from .models import ProductQuestionMessage, ProductQuestionReport, ProductQuestionThread


class QASellerCompanyFilter(SellerCompanyFilter):
    seller_field_name = "product__seller"
    parameter_name = "seller_company"


class QAThreadSellerCompanyFilter(SellerCompanyFilter):
    seller_field_name = "thread__product__seller"
    parameter_name = "seller_company"


class QAReportSellerCompanyFilter(SellerCompanyFilter):
    seller_field_name = "message__thread__product__seller"
    parameter_name = "seller_company"


@admin.register(ProductQuestionThread)
class ProductQuestionThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "seller_company", "buyer", "created_at", "updated_at", "deleted_at")
    search_fields = ("product__title", "product__seller__username", "product__seller__profile__shop_name", "buyer__username", "subject")
    list_filter = ("created_at", "deleted_at", QASellerCompanyFilter)
    raw_id_fields = ("product", "buyer")
    list_select_related = ("product", "product__seller", "product__seller__profile", "buyer")

    @admin.display(description="seller company")
    def seller_company(self, obj: ProductQuestionThread) -> str:
        seller = getattr(obj.product, "seller", None)
        profile = getattr(seller, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(seller, "username", str(getattr(obj.product, "seller_id", "")))


@admin.register(ProductQuestionMessage)
class ProductQuestionMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "thread", "seller_company", "author", "created_at", "deleted_at")
    search_fields = ("thread__product__title", "thread__product__seller__username", "thread__product__seller__profile__shop_name", "author__username", "body")
    list_filter = ("created_at", "deleted_at", QAThreadSellerCompanyFilter)
    raw_id_fields = ("thread", "author", "deleted_by")
    list_select_related = ("thread", "thread__product", "thread__product__seller", "thread__product__seller__profile", "author")

    @admin.display(description="seller company")
    def seller_company(self, obj: ProductQuestionMessage) -> str:
        seller = getattr(getattr(obj.thread, "product", None), "seller", None)
        profile = getattr(seller, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(seller, "username", str(getattr(getattr(obj.thread, "product", None), "seller_id", "")))


@admin.register(ProductQuestionReport)
class ProductQuestionReportAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "reason", "message", "seller_company", "reporter", "created_at")
    search_fields = ("message__body", "message__thread__product__seller__username", "message__thread__product__seller__profile__shop_name", "reporter__username", "details")
    list_filter = ("status", "reason", "created_at", QAReportSellerCompanyFilter)
    raw_id_fields = ("message", "reporter", "resolved_by")
    list_select_related = (
        "message",
        "message__thread",
        "message__thread__product",
        "message__thread__product__seller",
        "message__thread__product__seller__profile",
        "reporter",
    )

    @admin.display(description="seller company")
    def seller_company(self, obj: ProductQuestionReport) -> str:
        seller = getattr(getattr(getattr(obj.message, "thread", None), "product", None), "seller", None)
        profile = getattr(seller, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(seller, "username", str(getattr(getattr(getattr(obj.message, "thread", None), "product", None), "seller_id", "")))

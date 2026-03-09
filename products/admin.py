# products/admin.py
from __future__ import annotations

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from catalog.models import Category
from core.admin_filters import SellerCompanyFilter
from .models import Product, ProductImage, ProductEngagementEvent, SavedSearchAlert


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "slug",
        "slug_is_manual",
        "kind",
        "seller_company",
        "seller",
        "category",
        "subcategory",
        "price",
        "is_free",
        "is_active",
        "is_featured",
        "is_trending",
        "created_at",
    )
    list_filter = ("kind", "is_active", "is_featured", "is_trending", "category", "slug_is_manual", SellerCompanyFilter, "seller")
    search_fields = ("title", "slug", "seller__username", "seller__profile__shop_name", "short_description", "description")
    inlines = [ProductImageInline]
    prepopulated_fields = {}

    class Media:
        js = ("products/admin/product_category_subcategory.js",)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "subcategories-for-category/",
                self.admin_site.admin_view(self.subcategories_for_category),
                name="products_product_subcategories_for_category",
            ),
        ]
        return custom + urls

    def subcategories_for_category(self, request):
        raw_id = (request.GET.get("category_id") or "").strip()
        try:
            category_id = int(raw_id)
        except Exception:
            return JsonResponse({"results": []})

        parent = Category.objects.filter(pk=category_id).only("id").first()
        if not parent:
            return JsonResponse({"results": []})

        qs = (
            Category.objects.filter(parent_id=parent.id, is_active=True)
            .only("id", "name")
            .order_by("sort_order", "name")
        )
        return JsonResponse({"results": [{"id": c.id, "text": c.name} for c in qs]})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "subcategory":
            kwargs["queryset"] = Category.objects.none()
            obj_id = request.resolver_match.kwargs.get("object_id") if request.resolver_match else None
            if obj_id:
                try:
                    obj = Product.objects.select_related("category").only("id", "category_id").get(pk=obj_id)
                    if obj.category_id:
                        kwargs["queryset"] = Category.objects.filter(
                            parent_id=obj.category_id,
                            is_active=True,
                        ).order_by("sort_order", "name")
                except Exception:
                    pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        raw_slug = (request.POST.get("slug") or "").strip()
        if raw_slug:
            obj.slug_is_manual = True
            obj.slug = raw_slug
        else:
            obj.slug_is_manual = False
            if not obj.slug:
                obj.slug = ""
        super().save_model(request, obj, form, change)

    @admin.display(description="seller company")
    def seller_company(self, obj: Product) -> str:
        profile = getattr(obj.seller, "profile", None)
        shop_name = (getattr(profile, "shop_name", "") or "").strip() if profile else ""
        return shop_name or getattr(obj.seller, "username", str(obj.seller_id))


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "is_primary", "sort_order", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("product__title", "alt_text")


@admin.register(ProductEngagementEvent)
class ProductEngagementEventAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "kind", "user", "session_key", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("product__title", "user__username", "session_key")


@admin.register(SavedSearchAlert)
class SavedSearchAlertAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "kind",
        "query",
        "zip_prefix",
        "category_id_filter",
        "radius_miles",
        "sort",
        "email_enabled",
        "is_active",
        "last_notified_at",
        "created_at",
    )
    list_filter = ("kind", "is_active", "email_enabled", "sort")
    search_fields = ("user__username", "query", "zip_prefix")

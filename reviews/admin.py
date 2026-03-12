# reviews/admin.py
from django.contrib import admin

from .models import BuyerReview, Review, ReviewReply, SellerReview


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "buyer", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("product__title", "buyer__username", "title", "body")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SellerReview)
class SellerReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "seller", "buyer", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("seller__username", "buyer__username", "title", "body")


@admin.register(ReviewReply)
class ReviewReplyAdmin(admin.ModelAdmin):
    list_display = ("id", "review", "seller", "created_at")
    list_filter = ("created_at",)
    search_fields = ("review__product__title", "seller__username", "body")
    readonly_fields = ("created_at", "updated_at")


@admin.register(BuyerReview)
class BuyerReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "buyer", "seller", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("buyer__username", "seller__username", "title", "body")

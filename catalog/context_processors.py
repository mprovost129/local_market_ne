# catalog/context_processors.py
from __future__ import annotations

from django.core.cache import cache
from django.db.models import Prefetch

from .models import Category


def sidebar_categories(request):
    """Category trees for navbar/sidebar.

    LocalMarketNE v1:
    - Goods categories (type=GOOD)
    - Service categories (type=SERVICE)
    """
    cache_key = "lmne_sidebar_categories_v1"
    cached = cache.get(cache_key)
    if cached:
        return cached

    active_children = Prefetch(
        "children",
        queryset=Category.objects.filter(is_active=True).order_by("sort_order", "name"),
    )

    goods = (
        Category.objects.filter(type=Category.CategoryType.GOOD, parent__isnull=True, is_active=True)
        .prefetch_related(active_children)
        .order_by("sort_order", "name")
    )

    services = (
        Category.objects.filter(type=Category.CategoryType.SERVICE, parent__isnull=True, is_active=True)
        .prefetch_related(active_children)
        .order_by("sort_order", "name")
    )

    payload = {
        # backwards-compatible keys if templates still reference them
        "sidebar_model_categories": goods,
        "sidebar_file_categories": services,

        # preferred names for LocalMarketNE templates
        "store_goods_categories": goods,
        "store_service_categories": services,
    }
    cache.set(cache_key, payload, 3600)
    return payload

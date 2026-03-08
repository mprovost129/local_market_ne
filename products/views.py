# products/views.py
from __future__ import annotations

import base64
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg, Count, Prefetch, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from catalog.models import Category
from core.qr import qr_data_uri
from core.throttle import ThrottleRule, throttle
from payments.models import SellerStripeAccount
from products.permissions import is_owner_user
from products.services.trending import get_trending_badge_ids
from .models import Product, ProductEngagementEvent


VIEW_THROTTLE_MINUTES = 10
CLICK_THROTTLE_MINUTES = 5

CLICK_THROTTLE_RULE = ThrottleRule(
    key_prefix="products:click",
    limit=CLICK_THROTTLE_MINUTES,
    window_seconds=CLICK_THROTTLE_MINUTES * 60,
)
VIEW_THROTTLE_RULE = ThrottleRule(
    key_prefix="products:view",
    limit=VIEW_THROTTLE_MINUTES,
    window_seconds=VIEW_THROTTLE_MINUTES * 60,
)

# Browse hardening
DEFAULT_PER_PAGE = 24
MAX_PER_PAGE = 60
MAX_QUERY_LEN = 200

# Service browse filters
NE_STATE_CHOICES = [
    ("CT", "Connecticut"),
    ("ME", "Maine"),
    ("MA", "Massachusetts"),
    ("NH", "New Hampshire"),
    ("RI", "Rhode Island"),
    ("VT", "Vermont"),
]
SERVICE_RADIUS_CHOICES = [5, 10, 25, 50, 100]

# Short cache for anonymous browse/storefront pages
ANON_CACHE_SECONDS = 60


def _base_qs():
    return (
        Product.objects.filter(is_active=True)
        .select_related("category", "category__parent", "seller", "seller__profile")
        .prefetch_related("images")
    )


def _safe_int(raw: str, default: int) -> int:
    try:
        return int(str(raw).strip())
    except Exception:
        return default


def _get_per_page(request: HttpRequest) -> int:
    per_page = _safe_int(request.GET.get("per_page", ""), DEFAULT_PER_PAGE)
    if per_page <= 0:
        return DEFAULT_PER_PAGE
    return min(per_page, MAX_PER_PAGE)


def _get_page_num(request: HttpRequest) -> int:
    page = _safe_int(request.GET.get("page", ""), 1)
    return 1 if page <= 0 else page


def _paginate(request: HttpRequest, qs, *, per_page: int | None = None):
    per_page = per_page or _get_per_page(request)
    page_num = _get_page_num(request)

    paginator = Paginator(qs, per_page)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return page_obj


def _anon_cache_key(request: HttpRequest) -> str:
    # Include full querystring to safely cache filtered views.
    qs = (request.META.get("QUERY_STRING") or "")[:800]
    return f"anon:{request.path}?{qs}"


def _maybe_cached_render(request: HttpRequest, template_name: str, context: dict) -> HttpResponse:
    """Cache rendered HTML for anonymous GET pages (short TTL)."""
    if request.method != "GET" or request.user.is_authenticated:
        return render(request, template_name, context)

    key = _anon_cache_key(request)
    cached = cache.get(key)
    if cached:
        return HttpResponse(cached)

    resp = render(request, template_name, context)
    try:
        cache.set(key, resp.content, timeout=ANON_CACHE_SECONDS)
    except Exception:
        pass
    return resp


def _selected_category_name(raw_category: str) -> str:
    category = (raw_category or "").strip()
    if not category.isdigit():
        return ""
    return (
        Category.objects.filter(pk=int(category), is_active=True)
        .values_list("name", flat=True)
        .first()
        or ""
    )


def product_list(request: HttpRequest) -> HttpResponse:
    """Default public browse: Products (Goods)."""
    qs = _base_qs().filter(kind=Product.Kind.GOOD).order_by("-created_at")

    q = (request.GET.get("q") or "").strip()[:MAX_QUERY_LEN]
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q))

    category = (request.GET.get("category") or "").strip()
    if category.isdigit():
        cid = int(category)
        qs = qs.filter(Q(category_id=cid) | Q(subcategory_id=cid))

    page_obj = _paginate(request, qs)
    selected_category_name = _selected_category_name(category)
    trending_badge_ids = sorted(get_trending_badge_ids())

    return _maybe_cached_render(
        request,
        "products/product_list.html",
        {
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": page_obj.paginator,
            "active_tab": "products",
            "q": q,
            "category": category,
            "selected_category_name": selected_category_name,
            "trending_badge_ids": trending_badge_ids,
        },
    )


def services_list(request: HttpRequest) -> HttpResponse:
    qs = _base_qs().filter(kind=Product.Kind.SERVICE).order_by("-created_at")

    q = (request.GET.get("q") or "").strip()[:MAX_QUERY_LEN]
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q))

    category = (request.GET.get("category") or "").strip()
    if category.isdigit():
        cid = int(category)
        qs = qs.filter(Q(category_id=cid) | Q(subcategory_id=cid))

    state = (request.GET.get("state") or "").strip().upper()
    if state and len(state) <= 4:
        qs = qs.filter(seller__profile__public_state__iexact=state)

    radius_raw = (request.GET.get("radius") or "").strip()
    radius = _safe_int(radius_raw, 0)
    if radius > 0:
        qs = qs.filter(seller__profile__service_radius_miles__gte=radius)

    page_obj = _paginate(request, qs)
    selected_category_name = _selected_category_name(category)
    trending_badge_ids = sorted(get_trending_badge_ids())

    return _maybe_cached_render(
        request,
        "products/services_list.html",
        {
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": page_obj.paginator,
            "active_tab": "services",
            "q": q,
            "category": category,
            "selected_category_name": selected_category_name,
            "state": state,
            "radius": radius if radius > 0 else "",
            "state_choices": NE_STATE_CHOICES,
            "radius_choices": SERVICE_RADIUS_CHOICES,
            "trending_badge_ids": trending_badge_ids,
        },
    )


def product_go(request: HttpRequest, pk: int, slug: str) -> HttpResponse:
    product = get_object_or_404(Product, pk=pk, slug=slug, is_active=True)

    @throttle(CLICK_THROTTLE_RULE, methods=("GET",))
    def _log_click(req: HttpRequest):
        ProductEngagementEvent.objects.create(
            product=product,
            kind=ProductEngagementEvent.Kind.CLICK,
            user=req.user if req.user.is_authenticated else None,
            session_key=getattr(req.session, "session_key", "") or "",
        )

    _log_click(request)
    return redirect(product.get_absolute_url())


def product_detail(request: HttpRequest, pk: int, slug: str) -> HttpResponse:
    product = get_object_or_404(Product, pk=pk, slug=slug, is_active=True)

    @throttle(VIEW_THROTTLE_RULE, methods=("GET",))
    def _log_view(req: HttpRequest):
        ProductEngagementEvent.objects.create(
            product=product,
            kind=ProductEngagementEvent.Kind.VIEW,
            user=req.user if req.user.is_authenticated else None,
            session_key=getattr(req.session, "session_key", "") or "",
        )

    _log_view(request)

    can_buy = True
    if product.seller and not is_owner_user(request.user):
        acct = SellerStripeAccount.objects.filter(user_id=product.seller.id).first()
        if (not acct) or (not acct.is_ready):
            can_buy = False

    # Reviews summary + recent list
    from reviews.models import Review

    reviews_qs = (
        Review.objects.select_related("buyer", "reply", "reply__seller")
        .filter(product_id=product.id)
        .order_by("-created_at")
    )
    review_summary = reviews_qs.aggregate(avg=Avg("rating"), count=Count("id"))
    review_count = int(review_summary.get("count") or 0)
    avg_rating = review_summary.get("avg") or 0
    recent_reviews = reviews_qs[:5]

    # Product Q&A threads/messages
    from qa.models import ProductQuestionMessage, ProductQuestionReport, ProductQuestionThread

    qa_messages_qs = (
        ProductQuestionMessage.objects.select_related("author")
        .annotate(open_report_count=Count("reports", filter=Q(reports__status=ProductQuestionReport.Status.OPEN)))
        .order_by("created_at")
    )
    qa_threads = (
        ProductQuestionThread.objects.filter(product_id=product.id, deleted_at__isnull=True)
        .select_related("buyer")
        .prefetch_related(Prefetch("messages", queryset=qa_messages_qs))
        .order_by("-created_at")[:10]
    )
    qa_thread_count = qa_threads.count()

    seller_id = getattr(product, "seller_id", None) or getattr(getattr(product, "seller", None), "id", None)
    category_id = getattr(product, "category_id", None) or getattr(getattr(product, "category", None), "id", None)
    subcategory_id = getattr(product, "subcategory_id", None) or getattr(getattr(product, "subcategory", None), "id", None)

    more_from_seller = (
        _base_qs()
        .filter(seller_id=seller_id, kind=product.kind)
        .exclude(id=product.id)
        .order_by("-created_at")[:4]
    )

    related_filter = Q(category_id=category_id)
    if subcategory_id:
        related_filter |= Q(subcategory_id=subcategory_id)

    more_from_others = (
        _base_qs()
        .filter(kind=product.kind)
        .filter(related_filter)
        .exclude(id=product.id)
        .exclude(seller_id=seller_id)
        .order_by("-created_at")[:4]
    )

    return _maybe_cached_render(
        request,
        "products/product_detail.html",
        {
            "product": product,
            "can_buy": can_buy,
            "active_tab": "services" if product.kind == Product.Kind.SERVICE else "products",
            "review_count": review_count,
            "avg_rating": avg_rating,
            "recent_reviews": recent_reviews,
            "qa_threads": qa_threads,
            "qa_thread_count": qa_thread_count,
            "more_from_seller": more_from_seller,
            "more_from_others": more_from_others,
        },
    )


def seller_shop(request: HttpRequest, seller_id: int) -> HttpResponse:
    User = get_user_model()
    seller = get_object_or_404(User, pk=seller_id)

    qs = _base_qs().filter(seller=seller).order_by("-created_at")

    # Storefront scoped filter
    kind = (request.GET.get("kind") or "").strip().lower()
    if kind in {"products", "goods"}:
        qs = qs.filter(kind=Product.Kind.GOOD)
    elif kind in {"services", "service"}:
        qs = qs.filter(kind=Product.Kind.SERVICE)

    category = (request.GET.get("category") or "").strip()
    if category.isdigit():
        cid = int(category)
        qs = qs.filter(Q(category_id=cid) | Q(subcategory_id=cid))

    q = (request.GET.get("q") or "").strip()[:MAX_QUERY_LEN]
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q))

    page_obj = _paginate(request, qs)
    trending_badge_ids = sorted(get_trending_badge_ids())

    profile = getattr(seller, "profile", None)

    venmo = (getattr(profile, "venmo_handle", "") or "").strip() if profile else ""
    paypal = (getattr(profile, "paypal_me_url", "") or "").strip() if profile else ""
    zelle = (getattr(profile, "zelle_contact", "") or "").strip() if profile else ""
    cashapp = (getattr(profile, "cashapp_handle", "") or "").strip() if profile else ""

    # Only generate QR codes if seller has explicitly enabled them for storefront display
    show_venmo = bool(getattr(profile, "show_venmo_qr_storefront", False)) if profile else False
    show_paypal = bool(getattr(profile, "show_paypal_qr_storefront", False)) if profile else False
    show_zelle = bool(getattr(profile, "show_zelle_qr_storefront", False)) if profile else False
    show_cashapp = bool(getattr(profile, "show_cashapp_qr_storefront", False)) if profile else False

    # Only show the method on storefront when the seller has enabled it (reduces clutter)
    venmo_display = venmo if (show_venmo and venmo) else ""
    paypal_display = paypal if (show_paypal and paypal) else ""
    zelle_display = zelle if (show_zelle and zelle) else ""
    cashapp_display = cashapp if (show_cashapp and cashapp) else ""

    qr_venmo = qr_data_uri(f"https://venmo.com/{venmo.lstrip('@')}" if venmo_display else "")
    qr_paypal = qr_data_uri(paypal_display if paypal_display else "")
    qr_zelle = qr_data_uri(zelle_display if zelle_display else "")
    qr_cashapp = qr_data_uri(f"https://cash.app/${cashapp.lstrip('$')}" if (cashapp_display) else "")

    return _maybe_cached_render(
        request,
        "products/seller_shop.html",
        {
            "seller": seller,
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": page_obj.paginator,
            "trending_badge_ids": trending_badge_ids,
            "profile": profile,
            "venmo": venmo_display,
            "paypal": paypal_display,
            "zelle": zelle_display,
            "qr_venmo": qr_venmo,
            "qr_paypal": qr_paypal,
            "qr_zelle": qr_zelle,
            "cashapp": cashapp_display,
            "qr_cashapp": qr_cashapp,
            "kind": kind,
            "q": q,
            "category": category,
        },
    )


def top_sellers(request: HttpRequest) -> HttpResponse:
    User = get_user_model()

    qs = (
        User.objects.filter(profile__is_seller=True)
        .select_related("profile")
        .annotate(active_listings_count=Count("products", filter=Q(products__is_active=True)))
        .order_by("-active_listings_count", "username")
    )

    page_obj = _paginate(request, qs, per_page=50)

    return _maybe_cached_render(
        request,
        "products/top_sellers.html",
        {"sellers": page_obj.object_list, "page_obj": page_obj, "paginator": page_obj.paginator},
    )

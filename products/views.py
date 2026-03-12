# products/views.py
from __future__ import annotations

import base64
import io
import math
from datetime import timedelta
import re
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg, Case, Count, IntegerField, Prefetch, Q, Value, When
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalog.models import Category
from core.qr import qr_data_uri
from accounts.geo import lookup_zip_centroid
from core.throttle import ThrottleRule, throttle
from payments.models import SellerStripeAccount
from products.permissions import is_owner_user
from products.services.trending import get_trending_badge_ids
from .models import Product, ProductEngagementEvent, SavedSearchAlert


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
SERVICE_RADIUS_CHOICES = [5, 10, 25, 50, 100]
SORT_CHOICES = [
    ("local", "Local first"),
    ("new", "Newest"),
    ("price_low", "Price: low to high"),
    ("price_high", "Price: high to low"),
    ("trending", "Trending"),
]

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


def _normalized_zip_prefix(raw: str) -> str:
    """
    Normalize a ZIP-like input to a numeric prefix for startswith filtering.
    Supports inputs like:
    - 02860
    - 02860-1234
    - 02860 1234
    """
    txt = (raw or "").strip()
    if not txt:
        return ""
    digits = re.sub(r"[^0-9]", "", txt)
    if not digits:
        return ""
    # ZIP5 + optional ZIP4: we only need ZIP5 prefix for location filtering.
    return digits[:5]


def _zip_distance_case(zip_code: str):
    """
    Approximate ZIP distance buckets for local matching.
    This is intentionally coarse for v1 and used only for sorting/filter gating.
    """
    zip5 = _normalized_zip_prefix(zip_code)
    if len(zip5) < 5:
        return Value(999, output_field=IntegerField())
    zip3 = zip5[:3]
    zip2 = zip5[:2]
    return Case(
        When(seller__profile__zip_code__istartswith=zip5, then=Value(0)),
        When(seller__profile__zip_code__istartswith=zip3, then=Value(10)),
        When(seller__profile__zip_code__istartswith=zip2, then=Value(50)),
        default=Value(999),
        output_field=IntegerField(),
    )


def _zip_distance_bucket(zip_code: str, seller_zip: str) -> int:
    buyer_zip = _normalized_zip_prefix(zip_code)
    seller_zip = _normalized_zip_prefix(seller_zip)
    if len(buyer_zip) < 5 or len(seller_zip) < 5:
        return 999
    if seller_zip.startswith(buyer_zip):
        return 0
    if seller_zip.startswith(buyer_zip[:3]):
        return 10
    if seller_zip.startswith(buyer_zip[:2]):
        return 50
    return 999


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.7613  # earth radius miles
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return float(r * c)


def _distance_from_buyer_zip(zip_code: str, seller_profile) -> float:
    """
    Return approximate miles from buyer ZIP to seller.
    Uses private lat/lng when available, otherwise ZIP-prefix buckets.
    """
    buyer_centroid = lookup_zip_centroid(zip_code)
    seller_lat = getattr(seller_profile, "private_latitude", None)
    seller_lng = getattr(seller_profile, "private_longitude", None)
    if buyer_centroid and seller_lat is not None and seller_lng is not None:
        try:
            bl_lat, bl_lng = buyer_centroid
            return _haversine_miles(float(bl_lat), float(bl_lng), float(seller_lat), float(seller_lng))
        except Exception:
            pass
    return float(_zip_distance_bucket(zip_code, getattr(seller_profile, "zip_code", "")))


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


def _sort_key(raw: str, *, has_zip: bool) -> str:
    key = (raw or "").strip().lower()
    allowed = {k for k, _ in SORT_CHOICES}
    if key not in allowed:
        return "local" if has_zip else "new"
    if key == "local" and not has_zip:
        return "new"
    return key


def _apply_listing_sort(qs, *, sort: str, zip_code: str):
    if sort == "price_low":
        return qs.order_by("price", "-created_at")
    if sort == "price_high":
        return qs.order_by("-price", "-created_at")
    if sort == "trending":
        return qs.order_by("-is_trending", "-created_at")
    if sort == "local" and zip_code:
        return (
            qs.annotate(local_distance_miles=_zip_distance_case(zip_code))
            .order_by("local_distance_miles", "-created_at")
        )
    return qs.order_by("-created_at")


def _saved_search_existing(*, user, kind: str, q: str, category: str, zip_code: str, radius: int, sort: str):
    category_id_filter = int(category) if str(category or "").isdigit() else None
    return (
        SavedSearchAlert.objects.filter(
            user=user,
            kind=kind,
            query=(q or "").strip(),
            category_id_filter=category_id_filter,
            zip_prefix=(zip_code or "").strip(),
            radius_miles=max(0, int(radius or 0)),
            sort=(sort or "new").strip(),
            is_active=True,
        )
        .only("id")
        .first()
    )


def _saved_search_browse_url(*, kind: str, q: str, category: str, zip_code: str, radius: int, sort: str) -> str:
    route = "products:services" if kind == SavedSearchAlert.Kind.SERVICE else "products:list"
    params: dict[str, str] = {}
    if q:
        params["q"] = q
    if category and str(category).isdigit():
        params["category"] = str(category)
    if zip_code:
        params["zip"] = zip_code
    if kind == SavedSearchAlert.Kind.SERVICE and radius and int(radius) > 0:
        params["radius"] = str(int(radius))
    if sort:
        params["sort"] = sort
    qs = urlencode(params)
    return f"{reverse(route)}?{qs}" if qs else reverse(route)


def product_list(request: HttpRequest) -> HttpResponse:
    """Default public browse: Products (Goods)."""
    qs = _base_qs().filter(kind=Product.Kind.GOOD)

    q = (request.GET.get("q") or "").strip()[:MAX_QUERY_LEN]
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q))

    category = (request.GET.get("category") or "").strip()
    if category.isdigit():
        cid = int(category)
        qs = qs.filter(Q(category_id=cid) | Q(subcategory_id=cid))

    zip_code = _normalized_zip_prefix(request.GET.get("zip"))
    sort = _sort_key(request.GET.get("sort"), has_zip=bool(zip_code))
    if zip_code:
        if sort != "local":
            qs = _apply_listing_sort(qs, sort=sort, zip_code="")
        rows = list(qs)
        seller_distance_cache: dict[int, float] = {}
        out = []
        for p in rows:
            sid = int(getattr(p, "seller_id", 0) or 0)
            dist = seller_distance_cache.get(sid)
            if dist is None:
                dist = _distance_from_buyer_zip(zip_code, p.seller.profile)
                seller_distance_cache[sid] = dist
            p.local_distance_miles = dist
            # Keep product browsing meaningfully local when ZIP is set.
            if dist <= 10:
                out.append(p)
        if sort == "local":
            out.sort(key=lambda p: (float(getattr(p, "local_distance_miles", 999.0)), -int(p.created_at.timestamp())))
        page_obj = _paginate(request, out)
    else:
        qs = _apply_listing_sort(qs, sort=sort, zip_code=zip_code)
        page_obj = _paginate(request, qs)
    selected_category_name = _selected_category_name(category)
    trending_badge_ids = sorted(get_trending_badge_ids())
    saved_search = None
    if request.user.is_authenticated:
        saved_search = _saved_search_existing(
            user=request.user,
            kind=SavedSearchAlert.Kind.GOOD,
            q=q,
            category=category,
            zip_code=zip_code,
            radius=0,
            sort=sort,
        )

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
            "zip": zip_code,
            "sort": sort,
            "sort_choices": SORT_CHOICES,
            "saved_search": saved_search,
            "selected_category_name": selected_category_name,
            "trending_badge_ids": trending_badge_ids,
        },
    )


def services_list(request: HttpRequest) -> HttpResponse:
    qs = _base_qs().filter(kind=Product.Kind.SERVICE)

    q = (request.GET.get("q") or "").strip()[:MAX_QUERY_LEN]
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q))

    category = (request.GET.get("category") or "").strip()
    if category.isdigit():
        cid = int(category)
        qs = qs.filter(Q(category_id=cid) | Q(subcategory_id=cid))

    zip_code = _normalized_zip_prefix(request.GET.get("zip"))
    radius_raw = (request.GET.get("radius") or "").strip()
    radius = _safe_int(radius_raw, 0)
    sort = _sort_key(request.GET.get("sort"), has_zip=bool(zip_code))
    if zip_code:
        if sort != "local":
            qs = _apply_listing_sort(qs, sort=sort, zip_code="")
        rows = list(qs)
        seller_distance_cache: dict[int, float] = {}
        out = []
        for p in rows:
            sid = int(getattr(p, "seller_id", 0) or 0)
            dist = seller_distance_cache.get(sid)
            if dist is None:
                dist = _distance_from_buyer_zip(zip_code, p.seller.profile)
                seller_distance_cache[sid] = dist
            p.local_distance_miles = dist
            if dist > 10:
                continue
            seller_radius = int(getattr(p.seller.profile, "service_radius_miles", 0) or 0)
            # If seller set a radius, enforce it against buyer distance.
            if seller_radius > 0 and dist > float(seller_radius):
                continue
            if radius > 0 and dist > float(radius):
                continue
            out.append(p)
        if sort == "local":
            out.sort(key=lambda p: (float(getattr(p, "local_distance_miles", 999.0)), -int(p.created_at.timestamp())))
        page_obj = _paginate(request, out)
    else:
        if radius > 0:
            qs = qs.filter(seller__profile__service_radius_miles__gte=radius)
        qs = _apply_listing_sort(qs, sort=sort, zip_code=zip_code)
        page_obj = _paginate(request, qs)
    selected_category_name = _selected_category_name(category)
    trending_badge_ids = sorted(get_trending_badge_ids())
    saved_search = None
    if request.user.is_authenticated:
        saved_search = _saved_search_existing(
            user=request.user,
            kind=SavedSearchAlert.Kind.SERVICE,
            q=q,
            category=category,
            zip_code=zip_code,
            radius=radius,
            sort=sort,
        )

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
            "zip": zip_code,
            "sort": sort,
            "sort_choices": SORT_CHOICES,
            "saved_search": saved_search,
            "selected_category_name": selected_category_name,
            "radius": radius if radius > 0 else "",
            "radius_choices": SERVICE_RADIUS_CHOICES,
            "trending_badge_ids": trending_badge_ids,
        },
    )


@login_required
@require_POST
def saved_search_create(request: HttpRequest) -> HttpResponse:
    kind = (request.POST.get("kind") or "").strip().upper()
    if kind not in {SavedSearchAlert.Kind.GOOD, SavedSearchAlert.Kind.SERVICE}:
        kind = SavedSearchAlert.Kind.GOOD

    q = (request.POST.get("q") or "").strip()[:MAX_QUERY_LEN]
    category = (request.POST.get("category") or "").strip()
    zip_code = _normalized_zip_prefix(request.POST.get("zip"))
    radius = _safe_int(request.POST.get("radius"), 0) if kind == SavedSearchAlert.Kind.SERVICE else 0
    sort = _sort_key(request.POST.get("sort"), has_zip=bool(zip_code))
    email_enabled = bool(request.POST.get("email_enabled"))

    category_id_filter = int(category) if category.isdigit() else None
    existing = _saved_search_existing(
        user=request.user,
        kind=kind,
        q=q,
        category=category,
        zip_code=zip_code,
        radius=radius,
        sort=sort,
    )
    if existing:
        messages.info(request, "This local search is already saved.")
        return redirect(_saved_search_browse_url(kind=kind, q=q, category=category, zip_code=zip_code, radius=radius, sort=sort))

    SavedSearchAlert.objects.create(
        user=request.user,
        kind=kind,
        query=q,
        category_id_filter=category_id_filter,
        zip_prefix=zip_code,
        radius_miles=max(0, int(radius)),
        sort=sort,
        email_enabled=email_enabled,
        is_active=True,
    )
    messages.success(request, "Saved search created. We'll alert you when new matching listings appear.")
    return redirect(_saved_search_browse_url(kind=kind, q=q, category=category, zip_code=zip_code, radius=radius, sort=sort))


@login_required
@require_POST
def saved_search_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(SavedSearchAlert, pk=pk, user=request.user)
    kind = obj.kind
    q = obj.query
    category = str(obj.category_id_filter or "")
    zip_code = obj.zip_prefix
    radius = int(obj.radius_miles or 0)
    sort = obj.sort or "new"
    obj.delete()
    messages.success(request, "Saved search removed.")
    return redirect(_saved_search_browse_url(kind=kind, q=q, category=category, zip_code=zip_code, radius=radius, sort=sort))


@login_required
@require_POST
def saved_search_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(SavedSearchAlert, pk=pk, user=request.user)
    obj.is_active = bool(request.POST.get("is_active"))
    obj.email_enabled = bool(request.POST.get("email_enabled"))
    obj.save(update_fields=["is_active", "email_enabled", "updated_at"])
    messages.success(request, "Saved search settings updated.")
    return redirect("products:saved_search_list")


@login_required
def saved_search_list(request: HttpRequest) -> HttpResponse:
    rows = SavedSearchAlert.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "products/saved_search_list.html", {"saved_searches": rows})


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
    storefront_theme_enabled = bool(getattr(profile, "storefront_theme_enabled", False)) if profile else False
    storefront_layout = (getattr(profile, "storefront_layout", "") or "").strip()
    if storefront_layout not in {"balanced", "catalog", "minimal"}:
        storefront_layout = "balanced"
    storefront_primary_color = (getattr(profile, "storefront_primary_color", "") or "").strip() if profile else ""
    if not re.fullmatch(r"^#[0-9A-Fa-f]{6}$", storefront_primary_color):
        storefront_primary_color = ""
    storefront_primary_color = storefront_primary_color or "#2F4F2F"
    storefront_logo = getattr(profile, "storefront_logo", None) if profile else None
    storefront_banner = getattr(profile, "storefront_banner", None) if profile else None
    seller_rating_avg = None
    seller_rating_count = 0
    try:
        from reviews.models import SellerReview

        agg = SellerReview.objects.filter(seller_id=seller.id).aggregate(
            avg=Avg("rating"),
            count=Count("id"),
        )
        seller_rating_avg = agg.get("avg")
        seller_rating_count = int(agg.get("count") or 0)
    except Exception:
        seller_rating_avg = None
        seller_rating_count = 0

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
            "storefront_theme_enabled": storefront_theme_enabled,
            "storefront_layout": storefront_layout,
            "storefront_primary_color": storefront_primary_color,
            "storefront_logo": storefront_logo,
            "storefront_banner": storefront_banner,
            "seller_rating_avg": seller_rating_avg,
            "seller_rating_count": seller_rating_count,
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
        .annotate(
            active_listings_count=Count("products", filter=Q(products__is_active=True), distinct=True),
            seller_rating_avg=Avg("seller_reviews_received__rating"),
            seller_rating_count=Count("seller_reviews_received", distinct=True),
        )
        .order_by("-active_listings_count", "username")
    )
    q = (request.GET.get("q") or "").strip()[:MAX_QUERY_LEN]
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(profile__shop_name__icontains=q)
            | Q(profile__public_city__icontains=q)
            | Q(profile__public_state__icontains=q)
            | Q(profile__show_business_address_public=True, profile__city__icontains=q)
            | Q(profile__show_business_address_public=True, profile__state__icontains=q)
        )

    zip_code = _normalized_zip_prefix(request.GET.get("zip"))
    if zip_code:
        rows = list(qs)
        out = []
        for u in rows:
            prof = getattr(u, "profile", None)
            if prof is None:
                continue
            dist = _distance_from_buyer_zip(zip_code, prof)
            u.local_distance_miles = dist
            if dist <= 10:
                out.append(u)
        out.sort(key=lambda u: (float(getattr(u, "local_distance_miles", 999.0)), -int(getattr(u, "active_listings_count", 0))))
        page_obj = _paginate(request, out, per_page=50)
    else:
        page_obj = _paginate(request, qs, per_page=50)

    return _maybe_cached_render(
        request,
        "products/top_sellers.html",
        {
            "sellers": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": page_obj.paginator,
            "q": q,
            "zip": zip_code,
        },
    )

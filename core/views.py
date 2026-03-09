# core/views.py
from __future__ import annotations

from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db.models import Avg, Count, F, FloatField, Q, Value
from django.db.models.functions import Coalesce
import os

from django.http import HttpResponse, JsonResponse, HttpResponsePermanentRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category
from orders.models import Order
from payments.models import SellerStripeAccount
from products.models import Product, ProductEngagementEvent
from products.permissions import is_owner_user
from products.services.trending import annotate_trending, get_trending_badge_ids
from .recaptcha import require_recaptcha_v3
from .config import get_site_config
from .models import WaitlistEntry, ContactMessage
from .throttle import throttle
from .throttle_rules import WAITLIST_SIGNUP, CONTACT_SUBMIT


HOME_BUCKET_SIZE = 8
TRENDING_WINDOW_DAYS = 30

# Cache only the fully-rendered anonymous home HTML
HOME_ANON_CACHE_SECONDS = 60 * 15
HOME_ANON_CACHE_KEY = "home_html_anon_v2"


def healthz(request):
    """Public health endpoint for hosting providers (Render, uptime checks).

    Intentionally lightweight: no external calls and no DB query by default.
    """

    payload = {
        "status": "ok",
        "service": "localmarketne",
        "ts": timezone.now().isoformat(),
        "environment": getattr(settings, "ENVIRONMENT", ""),
        "version": os.getenv("GIT_SHA", ""),
    }
    return JsonResponse(payload)

def version(request):
    """Return a lightweight version string for deployments."""
    v = os.getenv("APP_VERSION") or os.getenv("GIT_SHA") or "dev"
    return JsonResponse({"version": v})



def _base_home_qs():
    return (
        Product.objects.filter(is_active=True)
        .select_related("seller", "category")
        .prefetch_related("images")
    )


def _annotate_rating(qs):
    qs = qs.annotate(
        avg_rating=Coalesce(Avg("reviews__rating"), Value(0.0), output_field=FloatField()),
        review_count=Coalesce(Count("reviews", distinct=True), Value(0)),
    )

    # Seller reputation (purchased-only seller reviews)
    qs = qs.annotate(
        seller_avg_rating=Coalesce(
            Avg("seller__seller_reviews_received__rating"),
            Value(0.0),
            output_field=FloatField(),
        ),
        seller_review_count=Coalesce(
            Count("seller__seller_reviews_received", distinct=True),
            Value(0),
        ),
    )

    return qs


def _annotate_trending(qs, *, since_days: int = TRENDING_WINDOW_DAYS):
    since = timezone.now() - timedelta(days=since_days)

    recent_purchases = Count(
        "order_items",
        filter=Q(
            order_items__order__status=Order.Status.PAID,
            order_items__order__paid_at__isnull=False,
            order_items__order__paid_at__gte=since,
        ),
        distinct=True,
    )

    recent_reviews = Count(
        "reviews",
        filter=Q(reviews__created_at__gte=since),
        distinct=True,
    )

    recent_views = Count(
        "engagement_events",
        filter=Q(
            engagement_events__kind=ProductEngagementEvent.Kind.VIEW,
            engagement_events__created_at__gte=since,
        ),
        distinct=True,
    )

    recent_clicks = Count(
        "engagement_events",
        filter=Q(
            engagement_events__kind=ProductEngagementEvent.Kind.CLICK,
            engagement_events__created_at__gte=since,
        ),
        distinct=True,
    )

    recent_add_to_cart = Count(
        "engagement_events",
        filter=Q(
            engagement_events__kind=ProductEngagementEvent.Kind.ADD_TO_CART,
            engagement_events__created_at__gte=since,
        ),
        distinct=True,
    )

    qs = qs.annotate(
        recent_purchases=Coalesce(recent_purchases, Value(0)),
        recent_reviews=Coalesce(recent_reviews, Value(0)),
        recent_views=Coalesce(recent_views, Value(0)),
        recent_clicks=Coalesce(recent_clicks, Value(0)),
        recent_add_to_cart=Coalesce(recent_add_to_cart, Value(0)),
    )

    qs = qs.annotate(
        trending_score=(
            Coalesce(F("recent_purchases"), Value(0)) * Value(6.0)
            + Coalesce(F("recent_add_to_cart"), Value(0)) * Value(3.0)
            + Coalesce(F("recent_clicks"), Value(0)) * Value(1.25)
            + Coalesce(F("recent_reviews"), Value(0)) * Value(2.0)
            + Coalesce(F("recent_views"), Value(0)) * Value(0.25)
            + Coalesce(F("avg_rating"), Value(0.0)) * Value(1.0)
        )
    )

    return qs


def _seller_can_sell(product: Product) -> bool:
    """Single source of truth for buy-gating on the home page."""
    try:
        if product.seller and is_owner_user(product.seller):
            return True
    except Exception:
        pass

    try:
        acct = getattr(product.seller, "stripe_connect", None)
        if acct is not None:
            return bool(acct.is_ready)
    except Exception:
        pass

    try:
        if not product.seller_id:
            return False
        return SellerStripeAccount.objects.filter(
            user_id=product.seller_id,
            stripe_account_id__gt="",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
        ).exists()
    except Exception:
        return False


def _apply_can_buy_flag(products: list[Product]) -> None:
    for p in products:
        p.can_buy = _seller_can_sell(p)


def _apply_trending_badge_flag(products: list[Product], *, computed_ids: set[int] | None = None) -> None:
    computed_ids = computed_ids or set()
    for p in products:
        p.trending_badge = bool(getattr(p, "is_trending", False) or (p.id in computed_ids))


def _build_home_context(request):
    qs = _base_home_qs()
    qs = _annotate_rating(qs)

    featured = list(qs.filter(is_featured=True).order_by("-created_at")[:HOME_BUCKET_SIZE])
    new_items = list(qs.order_by("-created_at")[:HOME_BUCKET_SIZE])

    manual_trending = list(qs.filter(is_trending=True).order_by("-created_at")[:HOME_BUCKET_SIZE])
    manual_ids = {p.id for p in manual_trending}

    trending_needed = max(0, HOME_BUCKET_SIZE - len(manual_trending))
    computed_trending: list[Product] = []
    computed_ids: set[int] = get_trending_badge_ids(since_days=TRENDING_WINDOW_DAYS)

    if trending_needed > 0:
        trending_qs = annotate_trending(qs, since_days=TRENDING_WINDOW_DAYS).exclude(id__in=manual_ids)
        computed_trending = list(
            trending_qs.order_by("-trending_score", "-avg_rating", "-created_at")[:trending_needed]
        )

    trending = manual_trending + computed_trending

    exclude_ids = {p.id for p in featured} | {p.id for p in new_items} | {p.id for p in trending}
    misc = list(qs.exclude(id__in=exclude_ids).order_by("-created_at")[:HOME_BUCKET_SIZE])

    # Recently purchased (by paid order date)
    since = timezone.now() - timedelta(days=30)
    recently_purchased = (
        _base_home_qs()
        .annotate(
            recent_purchase_count=Count(
                "order_items",
                filter=Q(
                    order_items__order__status=Order.Status.PAID,
                    order_items__order__paid_at__gte=since,
                ),
                distinct=True,
            )
        )
        .filter(recent_purchase_count__gt=0)
        .order_by("-recent_purchase_count", "-created_at")[:HOME_BUCKET_SIZE]
    )
    recently_purchased = _annotate_rating(recently_purchased)
    recently_purchased_list = list(recently_purchased)
    _apply_can_buy_flag(recently_purchased_list)

    # Most popular (using order counts)
    most_popular = (
        _base_home_qs()
        .annotate(
            total_purchase_count=Count(
                "order_items",
                filter=Q(order_items__order__status=Order.Status.PAID),
                distinct=True,
            )
        )
        .filter(total_purchase_count__gt=0, kind=Product.Kind.SERVICE)
        .order_by("-total_purchase_count", "-created_at")[:HOME_BUCKET_SIZE]
    )
    most_popular = _annotate_rating(most_popular)
    most_popular_list = list(most_popular)
    _apply_can_buy_flag(most_popular_list)

    all_cards = featured + new_items + trending + misc + recently_purchased_list + most_popular_list
    _apply_can_buy_flag(all_cards)
    _apply_trending_badge_flag(all_cards, computed_ids=computed_ids)

    # Advertisement banner (show first currently active)
    from core.models_advert import AdvertisementBanner
    ad_banner = AdvertisementBanner.objects.filter(is_active=True).order_by("-created_at").first()

    user_is_seller = False
    user_is_owner = False
    if request.user.is_authenticated:
        user_is_owner = bool(request.user.is_superuser)
        user_is_seller = bool(hasattr(request.user, "profile") and getattr(request.user.profile, "is_seller", False))
    site_config = get_site_config()

    return {
        "featured": featured,
        "trending": trending,
        "new_items": new_items,
        "misc": misc,
        "recently_purchased_list": recently_purchased_list,
        "most_popular_list": most_popular_list,
        "ad_banner": ad_banner,
        "user_is_seller": user_is_seller,
        "user_is_owner": user_is_owner,
        "site_config": site_config,
    }


def home(request):
    """
    IMPORTANT:
    Do NOT cache the full page for authenticated users.
    Otherwise an anonymous cached navbar gets served to logged-in users.
    """
    if not request.user.is_authenticated:
        cached_html = cache.get(HOME_ANON_CACHE_KEY)
        if cached_html:
            return HttpResponse(cached_html)

        context = _build_home_context(request)
        response = render(request, "core/home.html", context)
        try:
            cache.set(HOME_ANON_CACHE_KEY, response.content.decode("utf-8"), HOME_ANON_CACHE_SECONDS)
        except Exception:
            pass
        return response

    # Authenticated: always render fresh
    context = _build_home_context(request)
    return render(request, "core/home.html", context)


def error_400(request, exception=None):
    return render(request, "errors/400.html", status=400)


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)


def robots_txt(request):
    cache_key = "robots_txt_v1"
    cached = cache.get(cache_key)
    if cached:
        return HttpResponse(cached, content_type="text/plain")

    base_url = (getattr(settings, "SITE_BASE_URL", "") or "").rstrip("/")
    if not base_url:
        base_url = request.build_absolute_uri("/").rstrip("/")

    content = "\n".join(
        [
            "User-agent: *",
            "Disallow: /admin/",
            "Disallow: /ops/",
            "Disallow: /staff/",
            "Disallow: /dashboard/",
            "Disallow: /accounts/",
            f"Sitemap: {base_url}/sitemap.xml",
        ]
    )
    cache.set(cache_key, content, getattr(settings, "SITEMAP_CACHE_SECONDS", 3600))
    return HttpResponse(content, content_type="text/plain")


def sitemap_xml(request):
    cache_key = "sitemap_xml_v1"
    cached = cache.get(cache_key)
    if cached:
        return HttpResponse(cached, content_type="application/xml")

    base_url = (getattr(settings, "SITE_BASE_URL", "") or "").rstrip("/")
    if not base_url:
        base_url = request.build_absolute_uri("/").rstrip("/")

    urls: list[str] = [
        urljoin(base_url + "/", ""),
        urljoin(base_url + "/", "products/"),
        urljoin(base_url + "/", "catalog/"),
    ]

    # Reference pages (static v1)
    urls.extend([
        urljoin(base_url + "/", "about/"),
        urljoin(base_url + "/", "help/"),
        urljoin(base_url + "/", "faqs/"),
        urljoin(base_url + "/", "tips/"),
    ])

    # Categories
    for cat_id in Category.objects.filter(is_active=True).values_list("id", flat=True):
        urls.append(urljoin(base_url + "/", f"catalog/{cat_id}/"))

    # Products (active only)
    for product_id, slug in Product.objects.filter(is_active=True).values_list("id", "slug"):
        urls.append(urljoin(base_url + "/", f"products/{product_id}/{slug}/"))

    xml_lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">",
    ]
    xml_lines.extend([f"  <url><loc>{url}</loc></url>" for url in urls])
    xml_lines.append("</urlset>")

    content = "\n".join(xml_lines)
    cache.set(cache_key, content, getattr(settings, "SITEMAP_CACHE_SECONDS", 3600))
    return HttpResponse(content, content_type="application/xml")


@throttle(WAITLIST_SIGNUP)
@require_recaptcha_v3("waitlist_signup")
def waitlist_signup(request):
    """Email waitlist capture used by Coming Soon pages."""

    cfg = get_site_config()
    if not bool(getattr(cfg, "waitlist_enabled", True)):
        # Keep this friendly and non-leaky.
        return render(request, "core/waitlist.html", {"waitlist_disabled": True})

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        if not email:
            messages.error(request, "Please enter your email.")
            return redirect("core:waitlist")
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Please enter a valid email address.")
            return redirect("core:waitlist")

        ua = (request.META.get("HTTP_USER_AGENT") or "")[:240]
        ip = request.META.get("HTTP_X_FORWARDED_FOR")
        if ip:
            ip = ip.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")

        obj, created = WaitlistEntry.objects.get_or_create(
            email=email,
            defaults={
                "source_path": (request.POST.get("source_path") or request.path)[:200],
                "user_agent": ua,
                "ip_address": ip,
            },
        )

        if created:
            messages.success(request, "Thanks! You're on the list.")

            # Optional confirmation email (controlled via SiteConfig).
            if bool(getattr(cfg, "waitlist_send_confirmation", False)):
                try:
                    subject = (getattr(cfg, "waitlist_confirmation_subject", "") or "").strip() or "You’re on the Local Market NE waitlist"
                    body = (getattr(cfg, "waitlist_confirmation_body", "") or "").strip() or "Thanks for joining the Local Market NE waitlist!"
                    send_mail(
                        subject=subject,
                        message=body,
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                        recipient_list=[email],
                        fail_silently=True,
                    )
                except Exception:
                    pass

            # Optional admin notification.
            if bool(getattr(cfg, "waitlist_admin_notify_enabled", False)):
                admin_email = (getattr(cfg, "waitlist_admin_email", "") or "").strip()
                if admin_email:
                    try:
                        send_mail(
                            subject=f"New waitlist signup: {email}",
                            message=f"New waitlist signup:\n\nEmail: {email}\nSource: {obj.source_path}\nIP: {obj.ip_address}\n",
                            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                            recipient_list=[admin_email],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
        else:
            messages.info(request, "You're already on the list — thanks!")

        return redirect("core:waitlist")

    source = request.GET.get("source") or request.META.get("HTTP_REFERER") or ""
    return render(request, "core/waitlist.html", {"source": source})


def coming_soon(request):
    feature = request.GET.get("feature", "")
    context = {}
    if feature == "blog":
        context["feature_title"] = "Blog"
        context["feature_desc"] = "Our blog will inspire, inform, and connect the Local Market NE community!"
    elif feature == "community":
        context["feature_title"] = "Community Chat Board"
        context["feature_desc"] = "Our chat board will be the go-to place for collaboration, support, and fun challenges."
    else:
        context["feature_title"] = None
        context["feature_desc"] = None
    return render(request, "coming_soon.html", context)


def reference_redirect(request, to: str):
    """301 redirect legacy reference routes to the canonical short routes."""
    return HttpResponsePermanentRedirect(reverse(to))




def about_page(request):
    """Static About page (v1)."""
    return render(request, "core/about.html", {})


def help_page(request):
    """Static help landing (placeholder; can evolve into full help center)."""
    return render(request, "core/help.html", {})


def faqs_page(request):
    """Static FAQs page (placeholder; can evolve later)."""
    return render(request, "core/faqs.html", {})


def tips_page(request):
    """Static Tips & Tricks page (locked to be static now; blog later)."""
    return render(request, "core/tips.html", {})

@throttle(CONTACT_SUBMIT, methods=["POST"])
@require_recaptcha_v3("contact_submit")
def contact_page(request):
    """Public Contact page (v1)."""
    site_config = get_site_config()

    support_email = (getattr(site_config, "support_email", "") or "").strip()
    # Fallback: reuse waitlist admin email if set, so Contact isn't a dead end in v1.
    if not support_email:
        support_email = (getattr(site_config, "waitlist_admin_email", "") or "").strip()

    support_form_enabled = bool(getattr(site_config, "support_form_enabled", True))
    support_store_messages = bool(getattr(site_config, "support_store_messages", True))
    support_send_email = bool(getattr(site_config, "support_send_email", True))
    support_admin_notify_enabled = bool(getattr(site_config, "support_admin_notify_enabled", False))
    support_admin_email = (getattr(site_config, "support_admin_email", "") or "").strip()
    support_auto_reply_enabled = bool(getattr(site_config, "support_auto_reply_enabled", False))
    support_auto_reply_subject = (
        (getattr(site_config, "support_auto_reply_subject", "") or "").strip() or "We received your message"
    )
    support_auto_reply_body = (getattr(site_config, "support_auto_reply_body", "") or "").strip()

    if request.method == "POST":
        if not support_form_enabled:
            messages.error(request, "The contact form is currently disabled. Please try again later.")
            return redirect("core:contact")

        name = (request.POST.get("name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        subject_line = (request.POST.get("subject") or "").strip()
        message_text = (request.POST.get("message") or "").strip()

        errors: list[str] = []
        if not message_text:
            errors.append("Please enter a message.")

        if email:
            try:
                validate_email(email)
            except ValidationError:
                errors.append("Please enter a valid email address.")
        else:
            errors.append("Please enter your email address.")

        if not support_email and support_send_email:
            errors.append("Support email is not configured yet. Please try again later.")

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            # Always store (if enabled) so staff has an inbox even when email isn't configured.
            if support_store_messages:
                try:
                    ContactMessage.objects.create(
                        name=name,
                        email=email,
                        subject=subject_line,
                        message=message_text,
                        user=request.user if getattr(request.user, "is_authenticated", False) else None,
                        source_path=(request.path or "")[:200],
                        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:240],
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )
                except Exception:
                    # Never block the user on DB storage failures.
                    pass

            # Best-effort email send to support
            if support_send_email and support_email:
                subj = "Local Market NE — Contact form submission"
                if subject_line:
                    subj = f"{subj} — {subject_line}"

                body = (
                    f"Name: {name or '(not provided)'}\n"
                    f"Email: {email}\n"
                    f"Subject: {subject_line or '(not provided)'}\n\n"
                    f"Message:\n{message_text}\n"
                )
                try:
                    send_mail(
                        subj,
                        body,
                        settings.DEFAULT_FROM_EMAIL,
                        [support_email],
                        fail_silently=True,
                    )
                except Exception:
                    pass

            # Optional admin notify (separate from support_email)
            admin_target = support_admin_email or (getattr(site_config, "waitlist_admin_email", "") or "").strip()
            if support_admin_notify_enabled and admin_target:
                try:
                    send_mail(
                        "Local Market NE — New contact message",
                        f"From: {email}\nSubject: {subject_line or '(not provided)'}\n\n{message_text}",
                        settings.DEFAULT_FROM_EMAIL,
                        [admin_target],
                        fail_silently=True,
                    )
                except Exception:
                    pass

            # Optional auto-reply to sender
            if support_auto_reply_enabled and email and support_auto_reply_body:
                try:
                    send_mail(
                        support_auto_reply_subject,
                        support_auto_reply_body,
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=True,
                    )
                except Exception:
                    pass

            messages.success(request, "Thanks! Your message has been received.")
            return redirect("core:contact")

    return render(
        request,
        "core/contact.html",
        {
            "support_email": support_email,
            "support_form_enabled": support_form_enabled,
            "support_send_email": support_send_email,
            "support_store_messages": support_store_messages,
        },
    )

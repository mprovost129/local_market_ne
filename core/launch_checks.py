# core/launch_checks.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.cache import caches
from django.db import connection
from django.urls import NoReverseMatch, reverse

from core.models import SiteConfig


@dataclass(frozen=True)
class CheckResult:
    key: str
    ok: bool
    message: str
    detail: Optional[Dict[str, Any]] = None


def run_launch_checks() -> List[CheckResult]:
    """Return a list of launch-readiness checks.

    Conservative: failures suggest you should NOT go live yet.
    """
    results: List[CheckResult] = []

    debug = bool(getattr(settings, "DEBUG", False))
    results.append(
        CheckResult(
            key="debug_off",
            ok=not debug,
            message="DEBUG is disabled." if not debug else "DEBUG must be False in production.",
            detail={"DEBUG": debug},
        )
    )

    allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
    results.append(
        CheckResult(
            key="allowed_hosts",
            ok=bool(allowed_hosts) and "*" not in allowed_hosts,
            message="ALLOWED_HOSTS configured." if (allowed_hosts and "*" not in allowed_hosts) else "ALLOWED_HOSTS must be set (no '*').",
            detail={"ALLOWED_HOSTS": allowed_hosts},
        )
    )

    csrf_origins = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
    results.append(
        CheckResult(
            key="csrf_trusted_origins",
            ok=bool(csrf_origins),
            message="CSRF_TRUSTED_ORIGINS configured." if csrf_origins else "CSRF_TRUSTED_ORIGINS should be set in production.",
            detail={"CSRF_TRUSTED_ORIGINS": csrf_origins},
        )
    )

    # Database
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        results.append(CheckResult("db", True, "Database reachable."))
    except Exception as e:
        results.append(CheckResult("db", False, f"Database error: {e!s}"))

    # Cache (rate limiting depends on it)
    try:
        alias = getattr(settings, "RATE_LIMIT_CACHE_ALIAS", "default")
        cache = caches[alias]
        cache.set("__lmne_check__", "1", 5)
        ok = cache.get("__lmne_check__") == "1"
        results.append(
            CheckResult(
                "cache",
                ok,
                "Cache reachable." if ok else "Cache set/get failed.",
                detail={"alias": alias},
            )
        )
    except Exception as e:
        results.append(CheckResult("cache", False, f"Cache error: {e!s}"))

    # Email
    email_backend = getattr(settings, "EMAIL_BACKEND", "")
    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    results.append(
        CheckResult(
            key="email_backend",
            ok=bool(email_backend),
            message="EMAIL_BACKEND is configured." if email_backend else "EMAIL_BACKEND is missing.",
            detail={"EMAIL_BACKEND": email_backend},
        )
    )
    results.append(
        CheckResult(
            key="default_from_email",
            ok=bool(default_from),
            message="DEFAULT_FROM_EMAIL is configured." if default_from else "DEFAULT_FROM_EMAIL is missing.",
            detail={"DEFAULT_FROM_EMAIL": default_from},
        )
    )

    # Stripe
    stripe_pub = getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")
    stripe_secret = getattr(settings, "STRIPE_SECRET_KEY", "")
    results.append(
        CheckResult(
            key="stripe_keys",
            ok=bool(stripe_pub) and bool(stripe_secret),
            message="Stripe keys configured." if (stripe_pub and stripe_secret) else "Stripe keys missing.",
        )
    )

    # reCAPTCHA
    recaptcha_enabled = bool(getattr(settings, "RECAPTCHA_ENABLED", False))
    if recaptcha_enabled:
        site_key = getattr(settings, "RECAPTCHA_V3_SITE_KEY", "")
        secret_key = getattr(settings, "RECAPTCHA_V3_SECRET_KEY", "")
        ok = bool(site_key) and bool(secret_key)
        results.append(
            CheckResult(
                key="recaptcha",
                ok=ok,
                message="reCAPTCHA configured." if ok else "reCAPTCHA enabled but keys missing.",
            )
        )
    else:
        results.append(
            CheckResult(
                key="recaptcha",
                ok=True,
                message="reCAPTCHA disabled (OK for dev; recommended for prod).",
            )
        )

    # Storage
    use_s3 = bool(getattr(settings, "USE_S3", False))
    if use_s3:
        bucket = getattr(settings, "AWS_S3_MEDIA_BUCKET", "")
        ok = bool(bucket)
        results.append(
            CheckResult(
                key="storage_s3",
                ok=ok,
                message="S3 storage enabled and configured." if ok else "USE_S3 is True but AWS_S3_MEDIA_BUCKET missing.",
                detail={"AWS_S3_MEDIA_BUCKET": bucket},
            )
        )
    else:
        results.append(
            CheckResult(
                key="storage_s3",
                ok=True,
                message="Local media storage in use (OK for dev; consider S3 for prod).",
            )
        )

    # SiteConfig exists
    try:
        sc = SiteConfig.objects.first()
        ok = sc is not None
        results.append(
            CheckResult(
                key="siteconfig",
                ok=ok,
                message="SiteConfig exists." if ok else "SiteConfig missing (create one in admin).",
            )
        )
    except Exception as e:
        results.append(CheckResult("siteconfig", False, f"SiteConfig lookup failed: {e!s}"))

    # HSTS posture
    hsts = int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0)
    results.append(
        CheckResult(
            key="hsts",
            ok=hsts > 0,
            message="HSTS enabled." if hsts > 0 else "HSTS not enabled (recommended for production HTTPS).",
            detail={"SECURE_HSTS_SECONDS": hsts},
        )
    )



    # Security posture (production only)
    # Django should enforce HTTPS and secure cookies in production.
    if not debug:
        ssl_redirect = bool(getattr(settings, "SECURE_SSL_REDIRECT", False))
        session_secure = bool(getattr(settings, "SESSION_COOKIE_SECURE", False))
        csrf_secure = bool(getattr(settings, "CSRF_COOKIE_SECURE", False))
        proxy_hdr = getattr(settings, "SECURE_PROXY_SSL_HEADER", None)

        results.append(
            CheckResult(
                key="secure_ssl_redirect",
                ok=ssl_redirect,
                message="SECURE_SSL_REDIRECT enabled." if ssl_redirect else "SECURE_SSL_REDIRECT should be True in production.",
                detail={"SECURE_SSL_REDIRECT": ssl_redirect},
            )
        )
        results.append(
            CheckResult(
                key="secure_cookies",
                ok=session_secure and csrf_secure,
                message="Secure cookies enabled." if (session_secure and csrf_secure) else "SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE should be True in production.",
                detail={"SESSION_COOKIE_SECURE": session_secure, "CSRF_COOKIE_SECURE": csrf_secure},
            )
        )
        results.append(
            CheckResult(
                key="proxy_header",
                ok=bool(proxy_hdr),
                message="SECURE_PROXY_SSL_HEADER configured." if proxy_hdr else "SECURE_PROXY_SSL_HEADER should be set behind a proxy/load balancer.",
                detail={"SECURE_PROXY_SSL_HEADER": proxy_hdr},
            )
        )

        # Avoid dev-only email backends in production.
        backend_lower = str(email_backend).lower()
        bad_backends = ("console", "locmem", "filebased")
        results.append(
            CheckResult(
                key="email_backend_prod",
                ok=not any(b in backend_lower for b in bad_backends),
                message="Email backend looks production-ready." if not any(b in backend_lower for b in bad_backends) else "Email backend appears to be a dev backend (console/locmem/filebased).",
                detail={"EMAIL_BACKEND": email_backend},
            )
        )
    else:
        # In dev, cookie domains frequently break localhost sessions.
        sess_domain = getattr(settings, "SESSION_COOKIE_DOMAIN", "")
        csrf_domain = getattr(settings, "CSRF_COOKIE_DOMAIN", "")
        ok = not sess_domain and not csrf_domain
        results.append(
            CheckResult(
                key="cookie_domains_dev",
                ok=ok,
                message="Cookie domains not set (recommended for local dev)." if ok else "SESSION_COOKIE_DOMAIN/CSRF_COOKIE_DOMAIN are set; this may break localhost sessions.",
                detail={"SESSION_COOKIE_DOMAIN": sess_domain, "CSRF_COOKIE_DOMAIN": csrf_domain},
            )
        )
    # URL wiring / dead-end guardrail
    # These are the core operator surfaces that should always be routable.
    url_names = [
        "dashboards:consumer",
        "dashboards:seller",
        "dashboards:admin_ops",
        "ops:dashboard",
        "ops:ops_health",
        "ops:launch_check",
        "ops:runbook",
        "ops:error_events",
        "ops:webhooks_list",
        "ops:failed_emails",
        "ops:funnel_dashboard",
        "products:list",
        "products:services",
        "products:top_sellers",
        "cart:view",
    ]
    missing: List[str] = []
    for name in url_names:
        try:
            reverse(name)
        except NoReverseMatch:
            missing.append(name)
    results.append(
        CheckResult(
            key="url_wiring",
            ok=len(missing) == 0,
            message="Core URLs are routable." if not missing else "One or more critical URLs are not routable (dead-end risk).",
            detail={"missing": missing} if missing else {"checked": url_names},
        )
    )

    # ------------------------------------------------------------------
    # Money loop invariants (Pack BY)
    # ------------------------------------------------------------------
    # Keep this fast: check a bounded sample of recent paid orders.
    try:
        from orders.models import Order, OrderItem

        sample_qs = (
            Order.objects.filter(status=Order.Status.PAID)
            .order_by("-paid_at")
            .only("id", "subtotal_cents", "tax_cents", "shipping_cents", "platform_fee_cents_snapshot", "total_cents")
        )
        sample = list(sample_qs[:100])
        if not sample:
            results.append(CheckResult("money_loop", True, "No paid orders yet (nothing to verify)."))
        else:
            bad_orders: list[str] = []
            bad_items: int = 0

            for o in sample:
                items = list(
                    OrderItem.objects.filter(order=o)
                    .only(
                        "line_total_cents",
                        "tax_cents",
                        "shipping_fee_cents_snapshot",
                        "delivery_fee_cents_snapshot",
                        "marketplace_fee_cents",
                        "seller_net_cents",
                    )
                )

                # Order totals must match recompute logic.
                subtotal = sum(int(i.line_total_cents or 0) for i in items)
                shipping = sum(
                    int(i.shipping_fee_cents_snapshot or 0) + int(i.delivery_fee_cents_snapshot or 0)
                    for i in items
                )
                tax = sum(int(i.tax_cents or 0) for i in items)
                platform_fee = int(o.platform_fee_cents_snapshot or 0)
                total = max(0, int(subtotal) + int(shipping) + int(tax) + int(platform_fee))

                if (
                    int(o.subtotal_cents or 0) != subtotal
                    or int(o.shipping_cents or 0) != shipping
                    or int(o.tax_cents or 0) != tax
                    or int(o.total_cents or 0) != total
                ):
                    bad_orders.append(str(o.id))

                # Per-line ledger invariant: marketplace_fee + seller_net == line_total.
                for i in items:
                    gross = int(i.line_total_cents or 0)
                    fee = int(i.marketplace_fee_cents or 0)
                    net = int(i.seller_net_cents or 0)
                    if fee + net != gross:
                        bad_items += 1

            ok = (len(bad_orders) == 0) and (bad_items == 0)
            msg = "Money loop invariants OK (sampled recent paid orders)." if ok else "Money loop invariants FAILED (fix before going live)."
            detail = {
                "sampled_paid_orders": len(sample),
                "bad_orders": bad_orders[:10],
                "bad_orders_count": len(bad_orders),
                "bad_items_count": bad_items,
            }
            results.append(CheckResult("money_loop", ok, msg, detail=detail))
    except Exception as e:
        results.append(CheckResult("money_loop", False, f"Money loop check errored: {e!s}"))

    return results


def as_dict(results: List[CheckResult]) -> Dict[str, Any]:
    return {
        "ok": all(r.ok for r in results),
        "results": [
            {"key": r.key, "ok": r.ok, "message": r.message, "detail": r.detail}
            for r in results
        ],
    }

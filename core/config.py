# core/config.py
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.cache import cache

from .models import SiteConfig

CACHE_KEY = "core:site_config:v1"
CACHE_TTL_SECONDS = 30  # short TTL so admin changes take effect quickly


def get_site_config(*, use_cache: bool = True) -> SiteConfig:
    """
    Returns the singleton SiteConfig.

    Fresh DB case: auto-creates one row with model defaults.
    This avoids boot errors on a brand-new DB.
    """
    if use_cache:
        cached = cache.get(CACHE_KEY)
        if isinstance(cached, SiteConfig):
            return cached

    obj, _ = SiteConfig.objects.get_or_create(pk=1)

    cache.set(CACHE_KEY, obj, CACHE_TTL_SECONDS)
    return obj


def invalidate_site_config_cache() -> None:
    cache.delete(CACHE_KEY)


def get_marketplace_sales_percent() -> Decimal:
    cfg = get_site_config()
    return Decimal(cfg.marketplace_sales_percent or Decimal("0"))


def get_marketplace_sales_rate() -> Decimal:
    # 10.00 -> 0.10
    pct = get_marketplace_sales_percent()
    try:
        return pct / Decimal("100")
    except Exception:
        return Decimal("0")


def get_platform_fee_cents() -> int:
    cfg = get_site_config()
    try:
        return int(cfg.platform_fee_cents or 0)
    except Exception:
        return 0


def get_allowed_shipping_countries() -> list[str]:
    cfg = get_site_config()
    return cfg.allowed_shipping_countries


def get_affiliate_sidebar_links() -> dict[str, Any]:
    """
    Convenience accessor for templates.
    Returns: {enabled, title, disclosure, links:[{label,url,note}]}
    """
    cfg = get_site_config()
    return {
        "enabled": bool(getattr(cfg, "affiliate_links_enabled", False)),
        "title": str(getattr(cfg, "affiliate_links_title", "") or "").strip() or "Recommended Products",
        "disclosure": str(getattr(cfg, "affiliate_disclosure_text", "") or "").strip(),
        "links": list(getattr(cfg, "affiliate_links", []) or []),
    }


def get_site_announcement() -> dict[str, str | bool]:
    cfg = get_site_config()
    return {
        "enabled": bool(getattr(cfg, "site_announcement_enabled", False)),
        "text": str(getattr(cfg, "site_announcement_text", "") or "").strip(),
    }


def is_maintenance_mode_enabled() -> bool:
    cfg = get_site_config()
    return bool(getattr(cfg, "maintenance_mode_enabled", False))


def get_maintenance_message() -> str:
    cfg = get_site_config()
    return str(getattr(cfg, "maintenance_mode_message", "") or "").strip() or "We’re performing maintenance. Please check back soon."


def is_checkout_enabled() -> bool:
    cfg = get_site_config()
    return bool(getattr(cfg, "checkout_enabled", True))


def get_checkout_disabled_message() -> str:
    cfg = get_site_config()
    return (
        str(getattr(cfg, "checkout_disabled_message", "") or "").strip()
        or "Checkout is temporarily unavailable. Please try again soon."
    )


def get_featured_seller_usernames() -> list[str]:
    cfg = get_site_config()
    try:
        raw = getattr(cfg, "featured_seller_usernames", []) or []
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
    except Exception:
        pass
    return []


def get_featured_category_ids() -> list[int]:
    cfg = get_site_config()
    try:
        raw = getattr(cfg, "featured_category_ids", []) or []
        if isinstance(raw, list):
            out: list[int] = []
            for x in raw:
                try:
                    out.append(int(x))
                except Exception:
                    continue
            return out
    except Exception:
        pass
    return []

from __future__ import annotations

from typing import Any

from django.conf import settings


def _normalize_host(host: str) -> str:
    host = (host or "").strip().lower()
    if not host:
        return ""
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _env_label() -> str:
    env = (getattr(settings, "ENVIRONMENT", "") or "").strip()
    if env:
        return env[:32]
    return "development" if settings.DEBUG else "production"


def log_event_from_request(
    request,
    *,
    event_type: str,
    path: str | None = None,
    status_code: int = 200,
    meta: dict[str, Any] | None = None,
) -> None:
    """Best-effort analytics logging for conversion events.

    This is intentionally non-blocking and shares the same cookie-based identity
    approach as RequestAnalyticsMiddleware (hc_vid / hc_sid).
    """
    try:
        from core.config import get_site_config

        cfg = get_site_config()
        if cfg and hasattr(cfg, "analytics_enabled") and not bool(getattr(cfg, "analytics_enabled")):
            return
    except Exception:
        pass

    try:
        from analytics.models import AnalyticsEvent

        user = request.user if getattr(request.user, "is_authenticated", False) else None
        is_staff = bool(getattr(user, "is_staff", False)) if user else False

        # Respect staff exclusion (when configured).
        try:
            from core.config import get_site_config

            cfg = get_site_config()
            if cfg and bool(getattr(cfg, "analytics_exclude_staff", True)) and is_staff:
                return
        except Exception:
            pass

        vid = (request.COOKIES.get("hc_vid") or "").strip()[:36]
        sid = (request.COOKIES.get("hc_sid") or "").strip()[:36]

        session_key = getattr(getattr(request, "session", None), "session_key", "") or ""
        ua = (request.META.get("HTTP_USER_AGENT") or "")[:400]
        ref = (request.META.get("HTTP_REFERER") or "")[:512]

        host = _normalize_host(request.get_host() or "")[:255]
        env = _env_label()

        AnalyticsEvent.objects.create(
            event_type=event_type,
            path=(path or request.path or "/")[:512],
            method=(request.method or "GET")[:8],
            status_code=int(status_code or 200),
            visitor_id=vid,
            session_id=sid,
            user=user,
            session_key=(session_key or "")[:64],
            ip_hash="",  # conversion events are higher-signal; avoid IP collection here
            host=host,
            environment=env,
            is_staff=is_staff,
            is_bot=False,
            user_agent=ua,
            referrer=ref,
            meta=meta or {},
        )
    except Exception:
        return


def log_system_event(
    *,
    event_type: str,
    path: str,
    status_code: int = 200,
    meta: dict[str, Any] | None = None,
    host: str = "",
    environment: str = "",
) -> None:
    """Log an event without a request context (e.g., Stripe webhook)."""
    try:
        from core.config import get_site_config

        cfg = get_site_config()
        if cfg and hasattr(cfg, "analytics_enabled") and not bool(getattr(cfg, "analytics_enabled")):
            return
    except Exception:
        pass

    try:
        from analytics.models import AnalyticsEvent

        AnalyticsEvent.objects.create(
            event_type=event_type,
            path=(path or "")[:512],
            method="SYSTEM",
            status_code=int(status_code or 200),
            visitor_id="",
            session_id="",
            user=None,
            session_key="",
            ip_hash="",
            host=_normalize_host(host)[:255],
            environment=(environment or _env_label())[:32],
            is_staff=True,
            is_bot=False,
            user_agent="",
            referrer="",
            meta=meta or {},
        )
    except Exception:
        return

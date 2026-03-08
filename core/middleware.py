# core/middleware.py
from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

from .logging_context import clear_context, new_request_id, set_context


class RequestIDMiddleware(MiddlewareMixin):
    """
    Adds a stable request id for observability.

    - request.request_id
    - response header: X-Request-ID
    - threadlocal context for logging filters
    """

    header_name = "HTTP_X_REQUEST_ID"
    response_header = "X-Request-ID"

    def process_request(self, request):
        rid = (request.META.get(self.header_name) or "").strip() or new_request_id()
        request.request_id = rid
        user_id = getattr(getattr(request, "user", None), "id", None) if getattr(request, "user", None) and request.user.is_authenticated else None
        set_context(request_id=rid, user_id=user_id, path=(request.path or ""))

    def process_response(self, request, response):
        rid = getattr(request, "request_id", None)
        if rid:
            try:
                response[self.response_header] = rid
            except Exception:
                pass
        clear_context()
        return response

    def process_exception(self, request, exception):
        clear_context()
        return None


class MaintenanceModeMiddleware(MiddlewareMixin):
    """Serves a maintenance page to the public when SiteConfig.maintenance_mode_enabled is on.

    - OPS and Staff Admin can still access the site.
    - Allowlisted paths always pass through (admin, ops, staff, auth, health, static).
    """

    ALLOWLIST_PREFIXES = (
        "/admin/",
        "/ops/",
        "/staff/",
        "/accounts/",
        "/healthz/",
        "/health/",
        "/version/",
        "/static/",
        "/media/",
    )

    def process_request(self, request):
        path = (getattr(request, "path", "") or "").strip() or "/"
        for prefix in self.ALLOWLIST_PREFIXES:
            if path.startswith(prefix):
                return None

        try:
            from .config import get_site_config
            from ops.utils import user_is_ops
            from staff_console.utils import user_is_staff_admin
            from django.shortcuts import render

            cfg = get_site_config()
            if not getattr(cfg, "maintenance_mode_enabled", False):
                return None

            user = getattr(request, "user", None)
            if user and getattr(user, "is_authenticated", False):
                if user_is_ops(user) or user_is_staff_admin(user):
                    return None

            context = {
                "maintenance_message": str(getattr(cfg, "maintenance_mode_message", "") or "").strip() or "We’re performing maintenance. Please check back soon.",
            }
            return render(request, "maintenance.html", context=context, status=503)
        except Exception:
            return None


class ExceptionCaptureMiddleware(MiddlewareMixin):
    """Capture unhandled exceptions into the DB for Ops triage.

    This is a pragmatic "real store" observability layer when you don't want to
    depend on external services.

    - Stores a compact ErrorEvent row (request id, path, user, traceback)
    - Never blocks the exception from propagating
    """

    TRACEBACK_MAX_CHARS = 12000
    MESSAGE_MAX_CHARS = 2000

    def process_exception(self, request, exception):
        try:
            import traceback as _tb

            from ops.models import ErrorEvent

            rid = getattr(request, "request_id", "") or ""
            path = (getattr(request, "path", "") or "")[:500]
            method = (getattr(request, "method", "") or "")[:16]
            user = getattr(request, "user", None)
            user_obj = user if (user and getattr(user, "is_authenticated", False)) else None

            ua = (request.META.get("HTTP_USER_AGENT") or "")
            ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip() or (request.META.get("REMOTE_ADDR") or "")

            exc_type = exception.__class__.__name__
            msg = (str(exception) or "")[: self.MESSAGE_MAX_CHARS]
            tb = _tb.format_exc()[: self.TRACEBACK_MAX_CHARS]

            ErrorEvent.objects.create(
                request_id=rid,
                path=path,
                method=method,
                status_code=500,
                user=user_obj,
                ip_address=ip or None,
                user_agent=ua,
                exception_type=exc_type,
                message=msg,
                traceback=tb,
            )
        except Exception:
            # Never allow observability to crash the request.
            return None
        return None


class RobotsNoIndexMiddleware(MiddlewareMixin):
    """Add X-Robots-Tag: noindex for non-public areas.

    This helps ensure private dashboards and ops tooling are not indexed even
    if links leak or robots.txt is ignored.

    Applies to HTML responses for:
    - /admin/
    - /ops/
    - /staff/
    - /dashboard/
    """

    PREFIXES = ("/admin/", "/ops/", "/staff/", "/dashboard/")

    def process_response(self, request, response):
        try:
            path = (getattr(request, "path", "") or "").strip() or "/"
            if not any(path.startswith(p) for p in self.PREFIXES):
                return response

            ctype = (response.get("Content-Type") or "").lower()
            if "text/html" not in ctype:
                return response

            # Don't clobber an existing value.
            if "X-Robots-Tag" not in response:
                response["X-Robots-Tag"] = "noindex, nofollow"
        except Exception:
            return response
        return response

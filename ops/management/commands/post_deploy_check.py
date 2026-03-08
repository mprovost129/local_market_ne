from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management import BaseCommand, call_command
from django.db import connection


class Command(BaseCommand):
    help = (
        "Post-deploy validation checks for production environments. "
        "Focuses on config sanity + basic runtime invariants."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            default=os.getenv("POST_DEPLOY_BASE_URL", "").strip(),
            help=(
                "Optional base URL to run a couple of public HTTP checks against (e.g. https://localmarketne.com). "
                "If omitted, HTTP checks are skipped. Can also be set via POST_DEPLOY_BASE_URL."
            ),
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit JSON output only (suitable for CI logs).",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Reduce output noise.",
        )

    def handle(self, *args, **opts):
        base_url = (opts.get("base_url") or "").strip().rstrip("/")
        as_json = bool(opts.get("json"))
        quiet = bool(opts.get("quiet"))

        results: dict[str, object] = {
            "ok": True,
            "fatal": [],
            "warnings": [],
            "info": {},
            "http": {},
        }

        def fatal(msg: str):
            results["ok"] = False
            results["fatal"].append(msg)

        def warn(msg: str):
            results["warnings"].append(msg)

        # ------------------------------------------------------------------------------
        # SETTINGS / ENV SANITY
        # ------------------------------------------------------------------------------
        results["info"].update(
            {
                "debug": bool(getattr(settings, "DEBUG", False)),
                "allowed_hosts": list(getattr(settings, "ALLOWED_HOSTS", [])),
                "csrf_trusted_origins": list(getattr(settings, "CSRF_TRUSTED_ORIGINS", [])),
                "use_s3": bool(getattr(settings, "USE_S3", False)),
            }
        )

        if getattr(settings, "DEBUG", False):
            fatal("DEBUG is True in the current settings module.")

        secret_key = str(getattr(settings, "SECRET_KEY", "") or "")
        if not secret_key or "changeme" in secret_key.lower():
            fatal("SECRET_KEY is missing or looks like a placeholder.")

        if not getattr(settings, "ALLOWED_HOSTS", None):
            fatal("ALLOWED_HOSTS is empty.")

        # ------------------------------------------------------------------------------
        # DB CONNECTIVITY
        # ------------------------------------------------------------------------------
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as e:
            fatal(f"Database connectivity failed: {e}")

        # ------------------------------------------------------------------------------
        # STATICFILES
        # ------------------------------------------------------------------------------
        static_root = getattr(settings, "STATIC_ROOT", "") or ""
        if static_root:
            try:
                admin_css = os.path.join(static_root, "admin", "css", "base.css")
                if not os.path.exists(admin_css):
                    warn(
                        "STATIC_ROOT is set but admin static was not found at "
                        f"{admin_css}. Did collectstatic run on deploy?"
                    )
            except Exception as e:
                warn(f"Staticfiles check failed: {e}")
        else:
            warn("STATIC_ROOT is not set.")

        # ------------------------------------------------------------------------------
        # S3 SANITY (if enabled)
        # ------------------------------------------------------------------------------
        if bool(getattr(settings, "USE_S3", False)):
            bucket = getattr(settings, "AWS_S3_MEDIA_BUCKET", "")
            if not bucket:
                fatal("USE_S3 is enabled but AWS_S3_MEDIA_BUCKET is missing.")
            if not getattr(settings, "AWS_ACCESS_KEY_ID", ""):
                warn(
                    "USE_S3 is enabled but AWS_ACCESS_KEY_ID is not set (might be using an IAM role)."
                )

        # ------------------------------------------------------------------------------
        # EXISTING RC CHECKS (non-fatal unless they hard fail)
        # ------------------------------------------------------------------------------
        try:
            call_command("stripe_config_check", verbosity=0)
            results["info"].update({"stripe_config_check": "ok"})
        except SystemExit as e:
            warn(f"stripe_config_check exited early: {e}")
        except Exception as e:
            warn(f"stripe_config_check failed: {e}")

        # ------------------------------------------------------------------------------
        # OPTIONAL PUBLIC HTTP CHECKS
        # ------------------------------------------------------------------------------
        def http_get_json(url: str) -> tuple[int, dict | None, str | None]:
            req = urllib.request.Request(
                url, headers={"User-Agent": "LMNE-post-deploy-check"}
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = int(getattr(resp, "status", 200))
                    body = resp.read().decode("utf-8", errors="replace")
                    try:
                        return status, json.loads(body), None
                    except Exception:
                        return status, None, body
            except urllib.error.HTTPError as e:
                return int(getattr(e, "code", 0) or 0), None, str(e)
            except Exception as e:
                return 0, None, str(e)

        if base_url:
            status, data, raw = http_get_json(f"{base_url}/healthz/")
            results["http"].update(
                {
                    "healthz": {
                        "url": f"{base_url}/healthz/",
                        "status": status,
                        "json": data,
                        "raw": raw if data is None else None,
                    }
                }
            )
            if status < 200 or status >= 300:
                fatal(f"HTTP check failed for {base_url}/healthz/ (status={status}).")
            else:
                if isinstance(data, dict):
                    okish = (data.get("ok") is True) or (data.get("status") == "ok")
                    if not okish:
                        warn(f"/healthz/ returned JSON but did not indicate ok: {data}")

            v_status, v_data, v_raw = http_get_json(f"{base_url}/version/")
            results["http"].update(
                {
                    "version": {
                        "url": f"{base_url}/version/",
                        "status": v_status,
                        "json": v_data,
                        "raw": v_raw if v_data is None else None,
                    }
                }
            )
            if v_status < 200 or v_status >= 300:
                warn(f"HTTP check failed for {base_url}/version/ (status={v_status}).")
            else:
                if isinstance(v_data, dict) and not v_data.get("version"):
                    warn(f"/version/ returned JSON but version was empty: {v_data}")

        # ------------------------------------------------------------------------------
        # OUTPUT + EXIT
        # ------------------------------------------------------------------------------
        if as_json:
            self.stdout.write(json.dumps(results, indent=2, sort_keys=True))
        else:
            if not quiet:
                self.stdout.write("Post-deploy check results:\n")
            if results["fatal"]:
                self.stdout.write(self.style.ERROR("FATAL:"))
                for m in results["fatal"]:
                    self.stdout.write(f"- {m}")
            if results["warnings"] and not quiet:
                self.stdout.write(self.style.WARNING("WARNINGS:"))
                for m in results["warnings"]:
                    self.stdout.write(f"- {m}")
            if not quiet:
                self.stdout.write(self.style.SUCCESS("OK" if results["ok"] else "NOT OK"))

        if not results["ok"]:
            sys.exit(2)

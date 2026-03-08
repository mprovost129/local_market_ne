from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from django.core.management import BaseCommand, call_command


@dataclass
class HttpCheckResult:
    name: str
    url: str
    ok: bool
    status: int | None = None
    detail: str | None = None


def _http_get(url: str, timeout: int = 10) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "LocalMarketNE/first_live_validate"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(getattr(resp, "status", 200)), resp.read()


class Command(BaseCommand):
    help = (
        "First-live validation helper. Runs server-side post_deploy_check and, if --base-url is provided, "
        "performs a small set of public HTTP checks (healthz + key pages)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            dest="base_url",
            default="",
            help="Optional public base URL, e.g. https://localmarketne.com (no trailing slash).",
        )
        parser.add_argument(
            "--timeout",
            dest="timeout",
            type=int,
            default=10,
            help="HTTP timeout (seconds) for public checks (default: 10).",
        )

    def handle(self, *args, **opts):
        base_url = (opts.get("base_url") or "").strip().rstrip("/")
        timeout = int(opts.get("timeout") or 10)

        self.stdout.write(self.style.MIGRATE_HEADING("== First-live validation =="))

        # Always run server-side validations first.
        self.stdout.write(self.style.HTTP_INFO("Running: post_deploy_check"))
        try:
            call_command("post_deploy_check")
        except SystemExit:
            raise
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"post_deploy_check raised: {e}"))
            sys.exit(1)

        if not base_url:
            self.stdout.write(self.style.WARNING("No --base-url provided; skipping public HTTP checks."))
            return

        checks: list[tuple[str, str, str]] = [
            ("Public healthz", "/healthz/", "json_ok"),
            ("Public version", "/version/", "json_version"),
            ("Catalog browse", "/catalog/", "status_only"),
            ("Login page", "/accounts/login/", "status_only"),
        ]

        results: list[HttpCheckResult] = []
        for name, path, kind in checks:
            url = f"{base_url}{path}"
            try:
                status, body = _http_get(url, timeout=timeout)
                ok = True
                detail: str | None = None

                if kind == "json_ok":
                    try:
                        payload: dict[str, Any] = json.loads(body.decode("utf-8"))
                        ok = bool((payload.get("ok") is True) or (payload.get("status") == "ok"))
                        if not ok:
                            detail = f"Expected ok:true or status:'ok', got: {payload!r}"
                    except Exception:
                        ok = False
                        detail = "Response was not valid JSON"

                if kind == "json_version":
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        v = (payload or {}).get("version") if isinstance(payload, dict) else None
                        ok = bool(v)
                        if not ok:
                            detail = f"Expected JSON with non-empty version, got: {payload!r}"
                    except Exception:
                        ok = False
                        detail = "Response was not valid JSON"

                results.append(HttpCheckResult(name=name, url=url, ok=ok and (status == 200), status=status, detail=detail))
            except urllib.error.HTTPError as e:
                results.append(HttpCheckResult(name=name, url=url, ok=False, status=int(getattr(e, "code", 0)), detail=str(e)))
            except Exception as e:
                results.append(HttpCheckResult(name=name, url=url, ok=False, status=None, detail=str(e)))

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("== Public HTTP checks =="))
        failed = 0
        for r in results:
            if r.ok:
                self.stdout.write(self.style.SUCCESS(f"OK   {r.name}: {r.status} {r.url}"))
            else:
                failed += 1
                detail = f" — {r.detail}" if r.detail else ""
                status = r.status if r.status is not None else "ERR"
                self.stderr.write(self.style.ERROR(f"FAIL {r.name}: {status} {r.url}{detail}"))

        if failed:
            self.stderr.write(self.style.ERROR(f"{failed} public check(s) failed."))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS("All first-live checks passed."))

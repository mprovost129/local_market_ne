from __future__ import annotations

import re
from pathlib import Path

import json

from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse


URL_TAG_RE = re.compile(r"{%\s*url\s+['\"]([^'\"]+)['\"]", re.MULTILINE)


class Command(BaseCommand):
    """Audit templates for stale `{% url 'route_name' %}` references.

    This intentionally only audits *literal* route names (quoted strings) because
    variable/argument-based url tags require runtime context.

    Output is a list of template paths and the route names that failed to reverse.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--root",
            default="templates",
            help="Template root directory to scan (default: templates).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Max findings to print / include.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output JSON payload.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with non-zero status if any stale routes are found.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Reduce output (only summary).",
        )

    def handle(self, *args, **options):
        quiet = bool(options.get("quiet"))
        limit = int(options.get("limit") or 200)
        emit_json = bool(options.get("json"))
        template_root = Path(options["root"])
        if not template_root.is_absolute():
            template_root = Path.cwd() / template_root

        if not template_root.exists():
            self.stdout.write(self.style.WARNING(f"Template root not found: {template_root}"))
            return

        findings: list[dict] = []

        for path in sorted(template_root.rglob("*.html")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue

            for match in URL_TAG_RE.finditer(text):
                route_name = match.group(1).strip()
                # Skip obvious non-route placeholders (rare but safe)
                if not route_name or " " in route_name:
                    continue
                try:
                    reverse(route_name)
                except NoReverseMatch as e:
                    findings.append(
                        {
                            "template": str(path.relative_to(template_root.parent)),
                            "route": route_name,
                            "error": str(e),
                        }
                    )

        if not findings:
            payload = {"ok": True, "count": 0, "findings": [], "truncated": False}
            if emit_json:
                self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
                return
            if not quiet:
                self.stdout.write(self.style.SUCCESS("url_reverse_audit: OK (no stale literal route names found)"))
            return

        payload = {
            "ok": False,
            "count": len(findings),
            "findings": findings[:limit],
            "truncated": len(findings) > limit,
        }

        if emit_json:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(self.style.ERROR(f"url_reverse_audit: found {len(findings)} stale route reference(s)"))
            if not quiet:
                for f in findings[:limit]:
                    self.stdout.write(f" - {f['template']}: {f['route']}")
                if payload["truncated"]:
                    self.stdout.write(self.style.WARNING("(truncated output; increase --limit to see more)"))

        if options["strict"]:
            raise SystemExit(2)

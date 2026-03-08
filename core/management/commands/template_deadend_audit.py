from __future__ import annotations

import os
import re
from dataclasses import dataclass

from django.conf import settings
from django.core.management.base import BaseCommand


@dataclass
class Finding:
    relpath: str
    lineno: int
    line: str
    kind: str


HREF_DEADEND_RE = re.compile(r"href\s*=\s*['\"]#['\"]")
ACTION_DEADEND_RE = re.compile(r"action\s*=\s*['\"]#['\"]")
JS_VOID_RE = re.compile(r"javascript:void\(0\)", re.IGNORECASE)


def _should_ignore(line: str) -> bool:
    # Common legit patterns: Bootstrap toggles, collapse triggers, offcanvas openers.
    if "data-bs-toggle" in line or "data-bs-target" in line:
        return True
    # Allow explicit opt-out marker.
    if "data-lm-ignore-deadend" in line:
        return True
    return False


class Command(BaseCommand):
    help = "Scan templates for common dead-end link patterns (href='#', action='#', javascript:void(0))."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="Exit non-zero if any dead ends are found.")
        parser.add_argument("--limit", type=int, default=200, help="Max findings to print.")
        parser.add_argument("--json", action="store_true", help="Output JSON payload.")
        parser.add_argument("--quiet", action="store_true", help="Reduce human output.")

    def handle(self, *args, **options):
        strict = bool(options.get("strict"))
        limit = int(options.get("limit") or 200)
        emit_json = bool(options.get("json"))
        quiet = bool(options.get("quiet"))

        templates_dirs: list[str] = []
        # Prefer project-level templates dir.
        for d in getattr(settings, "TEMPLATES", []):
            for p in d.get("DIRS", []):
                templates_dirs.append(str(p))

        # Add app templates dirs (best effort)
        # We intentionally keep this lightweight; we just scan under BASE_DIR / 'templates' too.
        base_templates = os.path.join(getattr(settings, "BASE_DIR", "."), "templates")
        templates_dirs.append(base_templates)

        seen: set[str] = set()
        findings: list[Finding] = []

        for root in templates_dirs:
            if not root or root in seen:
                continue
            seen.add(root)
            if not os.path.isdir(root):
                continue
            for dirpath, _dirnames, filenames in os.walk(root):
                for fn in filenames:
                    if not fn.endswith((".html", ".txt")):
                        continue
                    abspath = os.path.join(dirpath, fn)
                    rel = os.path.relpath(abspath, getattr(settings, "BASE_DIR", os.getcwd()))
                    try:
                        with open(abspath, "r", encoding="utf-8") as f:
                            for idx, line in enumerate(f, start=1):
                                if _should_ignore(line):
                                    continue
                                if HREF_DEADEND_RE.search(line):
                                    findings.append(Finding(rel, idx, line.strip(), "href_hash"))
                                if ACTION_DEADEND_RE.search(line):
                                    findings.append(Finding(rel, idx, line.strip(), "action_hash"))
                                if JS_VOID_RE.search(line):
                                    findings.append(Finding(rel, idx, line.strip(), "js_void"))
                    except Exception:
                        # Ignore unreadable files.
                        continue

        payload = {
            "ok": len(findings) == 0,
            "count": len(findings),
            "findings": [
                {
                    "file": f.relpath,
                    "line": f.lineno,
                    "kind": f.kind,
                    "text": f.line,
                }
                for f in findings[:limit]
            ],
            "truncated": len(findings) > limit,
        }

        if emit_json:
            import json

            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            if not quiet:
                if payload["ok"]:
                    self.stdout.write(self.style.SUCCESS("Template dead-end audit: OK (no obvious dead ends found)"))
                else:
                    self.stdout.write(self.style.WARNING(f"Template dead-end audit: {payload['count']} potential dead ends found"))
                    for f in payload["findings"]:
                        self.stdout.write(f"- {f['file']}:{f['line']} [{f['kind']}] {f['text']}")
                    if payload["truncated"]:
                        self.stdout.write(self.style.WARNING("(truncated output; increase --limit to see more)"))

        if strict and not payload["ok"]:
            raise SystemExit(2)

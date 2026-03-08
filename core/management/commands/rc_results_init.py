from __future__ import annotations

import datetime as dt
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Create a timestamped RC results log from docs/RC_RESULTS_TEMPLATE.md. "
        "This supports the manual RC run in docs/RC_CHECKLIST.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--env",
            default="local",
            choices=["local", "staging", "prod"],
            help="Environment label to embed in the output filename.",
        )
        parser.add_argument(
            "--outdir",
            default="docs/rc_runs",
            help="Output directory (relative to BASE_DIR).",
        )
        parser.add_argument(
            "--name",
            default="",
            help="Optional custom filename (without path). If omitted, uses a timestamped name.",
        )

    def handle(self, *args, **opts):
        env = str(opts.get("env") or "local")
        outdir_rel = str(opts.get("outdir") or "docs/rc_runs")
        custom_name = str(opts.get("name") or "").strip()

        base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
        template_path = base_dir / "docs" / "RC_RESULTS_TEMPLATE.md"
        if not template_path.exists():
            self.stderr.write(self.style.ERROR(f"Missing template: {template_path}"))
            raise SystemExit(2)

        outdir = base_dir / outdir_rel
        outdir.mkdir(parents=True, exist_ok=True)

        if custom_name:
            filename = custom_name
            if not filename.lower().endswith(".md"):
                filename += ".md"
        else:
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"rc_results_{env}_{stamp}.md"

        out_path = outdir / filename
        if out_path.exists():
            self.stderr.write(self.style.ERROR(f"Refusing to overwrite existing file: {out_path}"))
            raise SystemExit(2)

        out_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Created RC results log: {out_path}"))

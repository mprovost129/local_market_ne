#!/usr/bin/env bash
set -euo pipefail

# Render start script
# - Ensures DB schema is up-to-date before serving traffic
# - Keeps the actual web command in one place for easier ops changes

echo "[render_start] Python runtime: $(python -V 2>&1)"

# Django 5.1 is not compatible with Python 3.14 in admin template rendering.
# Fail fast with a clear message instead of serving a partially broken app.
python - <<'PY'
import sys
if sys.version_info >= (3, 14):
    raise SystemExit(
        "[render_start] Unsupported Python runtime for this deployment. "
        "Use Python 3.12.x or 3.13.x with current requirements."
    )
PY

if [[ "${RUN_MIGRATIONS_ON_START:-0}" == "1" ]]; then
  echo "[render_start] Running migrations..."
  python manage.py migrate --noinput
else
  echo "[render_start] Skipping migrations (RUN_MIGRATIONS_ON_START != 1)."
fi

if [[ "${RUN_LAUNCH_GATE_ON_START:-0}" == "1" ]]; then
  echo "[render_start] Running launch gate..."
  LG_ARGS=(launch_gate --json)
  if [[ "${LAUNCH_GATE_FAIL_ON_WARNING:-0}" == "1" ]]; then
    LG_ARGS+=(--fail-on-warning)
  fi
  python manage.py "${LG_ARGS[@]}"
  echo "[render_start] Launch gate passed."
else
  echo "[render_start] Skipping launch gate (RUN_LAUNCH_GATE_ON_START != 1)."
fi

exec gunicorn config.wsgi:application --log-file -

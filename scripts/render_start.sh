#!/usr/bin/env bash
set -euo pipefail

# Render start script
# - Ensures DB schema is up-to-date before serving traffic
# - Keeps the actual web command in one place for easier ops changes

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

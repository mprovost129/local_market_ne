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

exec gunicorn config.wsgi:application --log-file -

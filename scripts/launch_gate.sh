#!/usr/bin/env bash
set -euo pipefail

# Run the deployment gate locally/CI with consistent defaults.
# Usage:
#   bash scripts/launch_gate.sh
#   FAIL_ON_WARNING=1 bash scripts/launch_gate.sh

ARGS=(launch_gate --json)
if [[ "${FAIL_ON_WARNING:-0}" == "1" ]]; then
  ARGS+=(--fail-on-warning)
fi

python manage.py "${ARGS[@]}"

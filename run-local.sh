#!/bin/sh
# V5 local application only; no automatic broker connection or model download.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$ROOT/src:$ROOT/adapters/databento/src:$ROOT/adapters/databento_planner/src"
export PYTHONDONTWRITEBYTECODE=1
PY="$ROOT/adapters/databento_planner/.venv/bin/python"
if [ "${1:-}" = "--tests" ]; then exec "$PY" -m pytest "$ROOT/tests_local" -q; fi
if [ "$#" -eq 0 ]; then set -- app; fi
exec "$PY" -m mnq_local "$@"

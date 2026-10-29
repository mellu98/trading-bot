#!/bin/sh
# Offline strategy comparison only. No downloads, accounts or order routing.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$ROOT/src:$ROOT/adapters/databento/src:$ROOT/adapters/databento_planner/src"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONWARNINGS=ignore
PY="$ROOT/adapters/databento_planner/.venv/bin/python"
if [ "${1:-}" = "--tests" ]; then
    exec "$PY" -m pytest "$ROOT/tests_sim" -q
fi
exec "$PY" -m mnq_sim.research_v2 "$@"

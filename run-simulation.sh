#!/bin/sh
# Offline only: no data acquisition and no broker connectivity.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$ROOT/src:$ROOT/adapters/databento/src:$ROOT/adapters/databento_planner/src"
export PYTHONDONTWRITEBYTECODE=1
exec "$ROOT/adapters/databento_planner/.venv/bin/python" -m mnq_sim "$@"

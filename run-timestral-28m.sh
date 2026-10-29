#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
export PYTHONPATH="$ROOT/src:$ROOT/adapters/databento/src:$ROOT/adapters/databento_planner/src"
export PYTHONDONTWRITEBYTECODE=1
case "${1:-}" in
    infer) PY="$ROOT/.venv/bin/python" ;;
    *) PY="$ROOT/adapters/databento_planner/.venv/bin/python" ;;
esac
exec "$PY" -m mnq_local.timestral_experiment "$@"

#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
export PYTHONPATH="$ROOT/src:$ROOT/adapters/databento/src:$ROOT/adapters/databento_planner/src"
export PYTHONDONTWRITEBYTECODE=1
if [ "$#" -eq 0 ]; then set -- app; fi
exec "$ROOT/.venv/bin/python" -m mnq_local.capital_app "$@"

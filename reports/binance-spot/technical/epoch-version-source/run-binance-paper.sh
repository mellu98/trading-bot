#!/bin/sh
# Public live data, one finite local technical paper BUY/SELL, then observe only.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$ROOT/src:$ROOT/adapters/databento/src:$ROOT/adapters/databento_planner/src"
export PYTHONDONTWRITEBYTECODE=1
exec "$ROOT/.venv/bin/python" -m mnq_local.binance_app "$@"

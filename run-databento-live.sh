#!/bin/sh
# Live market input only after a scoped license/cost grant. No broker order API.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
export PYTHONPATH="$ROOT/src:$ROOT/adapters/databento/src:$ROOT/adapters/databento_planner/src"
export PYTHONDONTWRITEBYTECODE=1
if [ "$#" -eq 0 ]; then set -- preflight; fi
exec "$ROOT/.venv/bin/python" -m mnq_local.databento_app "$@"

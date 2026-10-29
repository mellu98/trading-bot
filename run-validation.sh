#!/bin/sh
# Offline quantitative evaluation only. No acquisition or broker endpoints.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$ROOT/src:$ROOT/adapters/databento/src:$ROOT/adapters/databento_planner/src"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONWARNINGS=ignore
"$ROOT/adapters/databento_planner/.venv/bin/python" -m mnq_sim.quant "$@"
"$ROOT/adapters/databento_planner/.venv/bin/python" "$ROOT/reports/quant-validation/build-report.py"

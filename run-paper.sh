#!/bin/sh
# No live mode. Default preflight performs no broker/data connection.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$ROOT/src"
export PYTHONDONTWRITEBYTECODE=1
PY="$ROOT/adapters/ib_paper/.venv/bin/python"
if [ "${1:-}" = "--tests" ]; then exec "$PY" -m pytest "$ROOT/tests_paper" -q; fi
if [ "$#" -eq 0 ]; then set -- preflight; fi
exec "$PY" -m mnq_paper "$@"

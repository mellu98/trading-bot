#!/bin/sh
# Default is offline status. No live endpoint/mode or automatic order activation.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$ROOT/src"
export PYTHONDONTWRITEBYTECODE=1
exec "$ROOT/adapters/ib_paper/.venv/bin/python" -m mnq_paper.v4 "$@"

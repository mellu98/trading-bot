#!/bin/sh
# ICT research engines (A1 + v2). Simulation only: no command here can place an order.
# Usage: ./run-ict.sh full-test | calibrate | run | summary | download-capital | download-binance | quickstart | profiles | selftest
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
export PYTHONDONTWRITEBYTECODE=1
if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY=python3; fi
if ! "$PY" -c "import numpy" 2>/dev/null; then
    echo "numpy mancante: esegui 'uv sync' nella cartella del bot (oppure: $PY -m pip install numpy)" >&2
    exit 1
fi
if [ "$#" -eq 0 ]; then set -- --help; fi
exec "$PY" -m ict_engine "$@"

#!/bin/sh
# Installs software only in the isolated paper environment; no broker/data calls.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
if [ ! -x adapters/ib_paper/.venv/bin/python ]; then uv venv adapters/ib_paper/.venv --python 3.12; fi
uv pip install --python adapters/ib_paper/.venv/bin/python -r adapters/ib_paper/requirements.lock

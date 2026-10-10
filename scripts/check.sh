#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${PYTHON:-"$ROOT_DIR/venv/bin/python"}

if [ ! -x "$PYTHON" ]; then
	PYTHON=python
fi

cd "$ROOT_DIR"
"$PYTHON" -m pytest
"$PYTHON" -m ruff check .
"$PYTHON" -m pyrefly check

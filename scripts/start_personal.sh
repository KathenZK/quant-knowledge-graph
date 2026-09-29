#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then uv sync --frozen --extra test; fi
exec .venv/bin/python scripts/start_personal.py "$@"

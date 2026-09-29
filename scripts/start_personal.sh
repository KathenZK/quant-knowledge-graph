#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
runtime="${1:-.artifacts/personal}"
port="${QUANTGRAPH_PERSONAL_PORT:-8791}"
if [ ! -x .venv/bin/python ]; then uv sync --frozen --extra test; fi
if [ ! -f web/dist/index.html ]; then
  npm --prefix web ci
  npm --prefix web run build
fi
exec .venv/bin/python -m quantgraph.api.personal_app --runtime "$runtime" --port "$port"

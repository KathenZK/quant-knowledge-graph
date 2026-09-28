#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
export QUANTGRAPH_ROOT="$PWD"
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) { console.error("QuantGraph web requires Node.js 22+"); process.exit(1); }'
uv sync --frozen --extra test
npm --prefix web ci --no-audit --no-fund
npm --prefix web run build
exec uv run python -m quantgraph.api.web --port "${QUANTGRAPH_WEB_PORT:-8765}"

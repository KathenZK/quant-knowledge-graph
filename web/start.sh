#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
export QUANTGRAPH_ROOT="$PWD"
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) { console.error("QuantGraph web requires Node.js 22+"); process.exit(1); }'
uv sync --frozen --extra test
npm --prefix web ci --no-audit --no-fund
npm --prefix web run build
if [ -n "${QUANTGRAPH_PLATFORM_CONFIG:-}" ]; then
  exec bash scripts/start_platform.sh "$QUANTGRAPH_PLATFORM_CONFIG"
fi
runtime="${QUANTGRAPH_CATALOG_RUNTIME:-$PWD/.artifacts/platform}"
if [ "${QUANTGRAPH_QLIB_ONLY:-0}" != "1" ] && [ -f "$runtime/catalog.sqlite" ]; then
  exec uv run python -m quantgraph.api.web --catalog "$runtime/catalog.sqlite" --ingestion-journal "$runtime/ingestion.sqlite" --port "${QUANTGRAPH_WEB_PORT:-8765}"
fi
echo "No runtime Catalog selected: starting the Qlib-only distribution. Import authorized sources for the full strategy product."
exec uv run python -m quantgraph.api.web --port "${QUANTGRAPH_WEB_PORT:-8765}"

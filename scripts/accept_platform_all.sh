#!/usr/bin/env bash
# Run against an already started, explicitly isolated real-data runtime.
set -euo pipefail
if [ "$#" -ne 1 ]; then echo "Usage: bash scripts/accept_platform_all.sh CONFIG" >&2; exit 2; fi
graph_root=$(cd "$(dirname "$0")/.." && pwd)
config_path=$("$graph_root/.venv/bin/python" -c 'import pathlib,sys;print(pathlib.Path(sys.argv[1]).resolve())' "$1")
cd "$graph_root"
if [ -n "${QUANTGRAPH_NODE_BIN:-}" ]; then export PATH="$QUANTGRAPH_NODE_BIN:$PATH"; fi
node -e 'if(Number(process.versions.node.split(".")[0])<22)throw new Error("Node 22+ required; set QUANTGRAPH_NODE_BIN")'
api_port=$(.venv/bin/python -c 'import json,sys;print(json.load(open(sys.argv[1])).get("port",8761))' "$config_path")
output_dir=$(dirname "$config_path")
.venv/bin/python scripts/accept_platform.py --config "$config_path" --url "http://127.0.0.1:$api_port" --output "$output_dir/acceptance-final.json"
cd web
QUANTGRAPH_PRODUCT_CONFIG="$config_path" QUANTGRAPH_PRODUCT_URL="http://127.0.0.1:$api_port" npx playwright test -c product.playwright.config.ts

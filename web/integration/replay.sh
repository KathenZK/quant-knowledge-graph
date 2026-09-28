#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ "$(node -p 'Number(process.versions.node.split(".")[0])')" -lt 22 ]; then
  echo 'Node 22 or newer is required.' >&2; exit 1
fi
export PLAYWRIGHT_BROWSERS_PATH="$PWD/web/.artifacts/browsers"
node web/integration/replay.mjs "$@"

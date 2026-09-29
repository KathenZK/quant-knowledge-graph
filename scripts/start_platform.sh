#!/usr/bin/env bash
# One supervised command. Stopping it stops both services; no background-work claim.
set -euo pipefail
if [ "$#" -ne 1 ]; then
  echo "Usage: bash scripts/start_platform.sh /absolute/path/to/operator-config.json" >&2
  exit 2
fi
graph_root=$(cd "$(dirname "$0")/.." && pwd)
config_path=$("$graph_root/.venv/bin/python" -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$1")
lab_python=$("$graph_root/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["lab_python"])' "$config_path")
api_port=$("$graph_root/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("port",8761))' "$config_path")
test -x "$lab_python"
test -f "$graph_root/web/dist/index.html"
children=()
cleanup() {
  trap - EXIT INT TERM
  for pid in "${children[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait || true
}
trap cleanup EXIT INT TERM
"$lab_python" -m strategy_lab.platform_worker --config "$config_path" &
children+=("$!")
"$graph_root/.venv/bin/python" -m quantgraph.api.platform --config "$config_path" --port "$api_port" &
children+=("$!")
echo "Local platform: http://127.0.0.1:$api_port (API + worker supervised by this command)"
worker_pid_file=$("$graph_root/.venv/bin/python" -c 'import json,sys,pathlib; print(pathlib.Path(json.load(open(sys.argv[1]))["job_db"]).parent/"worker.pid")' "$config_path")
printf '%s\n' "${children[0]}" > "$worker_pid_file"
restarts=0
while kill -0 "${children[1]}" 2>/dev/null; do
  if ! kill -0 "${children[0]}" 2>/dev/null; then
    wait "${children[0]}" 2>/dev/null || true
    if [ "$restarts" -ge 3 ]; then break; fi
    restarts=$((restarts+1))
    "$lab_python" -m strategy_lab.platform_worker --config "$config_path" &
    children[0]=$!
    printf '%s\n' "${children[0]}" > "$worker_pid_file"
    echo "Worker restarted ($restarts/3); expired leases retain their original run IDs."
  fi
  sleep 1
done
echo "A platform process exited; stopping the remaining process." >&2
exit 1

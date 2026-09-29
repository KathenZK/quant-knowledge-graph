"""Browser acceptance: actual snapshot copy, fresh test notes, owned process restart."""
from pathlib import Path
import json
import os
import signal
import sqlite3
import subprocess
import time

root = Path(__file__).resolve().parents[2]
source = Path(os.environ.get('QUANTGRAPH_PERSONAL_TEST_SOURCE', root / '.artifacts/personal')).resolve()
target = root / '.artifacts/polish-v1/browser-runtime'
target.mkdir(parents=True, exist_ok=True)
if not (source / 'catalog.sqlite').is_file():
    raise SystemExit('Real personal catalog missing; set QUANTGRAPH_PERSONAL_TEST_SOURCE. No mock fallback.')
# Reset only disposable test notes. Formal personal.sqlite is never opened.
for suffix in ['', '-wal', '-shm']:
    (target / ('personal.sqlite' + suffix)).unlink(missing_ok=True)
for name in ['catalog.sqlite', 'ingestion.sqlite', 'factor-studies.sqlite', 'jobs.sqlite']:
    if (source / name).is_file():
        with sqlite3.connect(f'file:{source / name}?mode=ro', uri=True) as src, sqlite3.connect(target / name) as dst:
            src.backup(dst)
for name in ['snapshot.json']:
    if (source / name).is_file():
        (target / name).write_bytes((source / name).read_bytes())
request = target / 'restart-request'
status = target / 'server-generation.json'
request.unlink(missing_ok=True)
child = None

def stop(*_args):
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=12)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def exit_owned(*_args):
    stop()
    raise SystemExit(0)

signal.signal(signal.SIGTERM, exit_owned)
signal.signal(signal.SIGINT, exit_owned)
generation = 0
try:
    while True:
        child = subprocess.Popen(['bash', str(root / 'scripts/start_personal.sh'), '--port', '8792', str(target)], cwd=root)
        generation += 1
        status.write_text(json.dumps({'generation': generation, 'pid': child.pid}))
        while child.poll() is None and not request.exists():
            time.sleep(.25)
        if not request.exists():
            raise SystemExit(child.returncode)
        request.unlink()
        stop()
finally:
    stop()

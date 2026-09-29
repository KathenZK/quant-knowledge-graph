"""Browser acceptance uses an isolated copy of the actual personal snapshot."""
from pathlib import Path
import os
import sqlite3
import sys
root = Path(__file__).resolve().parents[2]
source = Path(os.environ.get('QUANTGRAPH_PERSONAL_TEST_SOURCE', root / '.artifacts/personal')).resolve()
target = root / '.artifacts/personal-browser-runtime'
target.mkdir(parents=True, exist_ok=True)
if not (source / 'catalog.sqlite').is_file():
    raise SystemExit('Real personal catalog missing; set QUANTGRAPH_PERSONAL_TEST_SOURCE. No mock fallback.')
for name in ['catalog.sqlite', 'ingestion.sqlite', 'factor-studies.sqlite', 'jobs.sqlite']:
    if (source / name).is_file():
        with sqlite3.connect(f'file:{source / name}?mode=ro', uri=True) as src, sqlite3.connect(target / name) as dst:
            src.backup(dst)
for name in ['snapshot.json', 'config.json']:
    if (source / name).is_file():
        (target / name).write_bytes((source / name).read_bytes())
os.chdir(root)
os.execv(sys.executable, [sys.executable, '-m', 'quantgraph.api.personal_app', '--runtime', str(target), '--port', '8792'])

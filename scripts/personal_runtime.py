"""Copy explicitly selected Graph inputs; never discover or open other projects."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def backup_database(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if not source.is_file() or target.exists():
        raise ValueError('Source must exist and destination must be new')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Database integrity check failed')
        target.chmod(0o600)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return dict(source=str(source), copy=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest())


def initialize(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if not (source / 'catalog.sqlite').is_file():
        raise ValueError('The selected Graph runtime has no complete Catalog; no Qlib fallback')
    if target.exists():
        raise ValueError('Choose a new isolated destination; existing personal data is never overwritten')
    target.mkdir(parents=True, mode=0o700)
    manifest = dict(mode='personal_local', created_at=datetime.now(timezone.utc).isoformat(), inputs=[])
    for name in ['catalog.sqlite', 'ingestion.sqlite', 'jobs.sqlite', 'factor-studies.sqlite', 'personal.sqlite']:
        if (source / name).is_file():
            manifest['inputs'].append(backup_database(source / name, target / name))
    (target / 'snapshot.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-runtime', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    args = p.parse_args()
    result = initialize(args.source_runtime, args.destination)
    print(json.dumps({'status': 'COPIED', 'databases': len(result['inputs']),
                      'created_at': result['created_at']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

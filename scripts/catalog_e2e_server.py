"""Actual-input browser acceptance uses fresh SQLite backups, not shared writes."""
from pathlib import Path
import os
import sqlite3
import secrets

from quantgraph.api.web import create_web_app
from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
import uvicorn

source=Path(os.environ['QUANTGRAPH_ACCEPTANCE_RUNTIME']).resolve()
target=Path(os.environ['QUANTGRAPH_ACCEPTANCE_OUTPUT']).resolve()
if source==target:
    raise ValueError('Acceptance requires an isolated output directory')
target.mkdir(parents=True,exist_ok=True)
for name in ['catalog.sqlite','ingestion.sqlite']:
    path=target/name
    if path.exists():
        raise ValueError('Use a fresh acceptance output directory')
    with sqlite3.connect((source/name).as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(path) as dst:
        src.backup(dst)
    path.chmod(0o600)
secret=target/'admin-secret'
secret.write_text(secrets.token_urlsafe(32));secret.chmod(0o600)
catalog=CatalogRepository(target/'catalog.sqlite',ingestion=SQLiteIngestionRepository(target/'ingestion.sqlite'))
uvicorn.run(create_web_app(catalog=catalog,admin_password=secret.read_text()),host='127.0.0.1',port=8787,access_log=False)

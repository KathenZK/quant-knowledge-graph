"""Build/rebuild a runtime catalog using explicit authorized inputs, never home scanning."""
import argparse
from pathlib import Path
import sqlite3
import json

from quantgraph.api.app import create_app
from quantgraph.api.web_read_model import WebReadModel
from quantgraph.db import FactorDB
from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--source-journal',type=Path)
    p.add_argument('--factor-database',type=Path)
    p.add_argument('--normalized-records',type=Path)
    p.add_argument('--archive',type=Path)
    args=p.parse_args()
    args.runtime.mkdir(parents=True,exist_ok=True)
    journal=args.runtime/'ingestion.sqlite'
    if args.source_journal and not journal.exists():
        with sqlite3.connect(args.source_journal.resolve().as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(journal) as dst:
            src.backup(dst)
    ingestion=SQLiteIngestionRepository(journal)
    if args.archive:
        from quantgraph.collectors.grokbot.collector import read_bundle
        from quantgraph.models.ingestion import IngestBatch
        from scripts.replay_grokbot_api import batches
        bundle=read_bundle(args.archive)
        for batch in batches(bundle,'2026-09-28T00:00:00Z'):
            ingestion.ingest(IngestBatch.model_validate(batch),json.dumps(batch,ensure_ascii=False).encode(),'catalog-bootstrap')
    ingestion.reproject()
    catalog=CatalogRepository(args.runtime/'catalog.sqlite',ingestion=ingestion)
    model=WebReadModel(create_app(args.root,public_only=True).state.db)
    catalog.import_factors(model,FactorDB(database=args.factor_database) if args.factor_database else None,args.normalized_records)
    sync=catalog.sync_ingestion()
    print(json.dumps({'sync':sync,'counts':catalog.metadata()['counts'],'reconciliation':catalog.reconcile()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()

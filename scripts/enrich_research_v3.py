"""Apply reviewed, hash-bound source evidence; never create automatic grants.

Inputs are a private, explicitly reviewed manifest and append-only journal.
Source bytes stay in ignored datasets/raw. This tool validates hashes and models;
it cannot download sources, infer licenses, or silently accept research choices.
"""
import argparse
import hashlib
import json
from pathlib import Path

from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.models.evidence import EvidenceEnrichment
from quantgraph.models.ingestion import IngestBatch


def verify_files(manifest):
    for entry in manifest['pinned_files']:
        path = Path(entry['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Pinned review artifact changed: '+str(path))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--journal',type=Path,required=True)
    p.add_argument('--review-manifest',type=Path,required=True)
    a=p.parse_args()
    manifest=json.loads(a.review_manifest.read_text())
    verify_files(manifest)
    repo=SQLiteIngestionRepository(a.journal)
    if manifest.get('derived_records'):
        value=IngestBatch.model_validate(manifest['derived_records'])
        repo.ingest(value,json.dumps(manifest['derived_records'],ensure_ascii=False).encode(),'local-evidence-review-v3')
    receipts=[]
    for raw in manifest['reviews']:
        value=EvidenceEnrichment.model_validate(raw)
        receipts.append(repo.review_record(value.model_dump(mode='json')))
    print(json.dumps({'review_count':len(receipts),'receipts':receipts,'promotion_allowed':False},indent=2))


if __name__=='__main__':main()

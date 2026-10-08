import hashlib
import json

from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.graph.private_intake import import_cards
from quantgraph.models.ingestion import IngestBatch


def ingest(store, number, threshold):
    batch={'batch_id':f'synthetic-batch-{number}','collector_version':'synthetic-v1','records':[{
        'record_id':f'synthetic-{number}','name':f'Synthetic rule {number}',
        'source_url':f'https://example.com/source-{number}', 'raw_market':'美股 ETF',
        'raw_rule':f'日频：若 RSI(14)>{threshold} → 满仓 SPY，否则 BIL。',
        'collected_at':'2026-01-01T00:00:00Z'}]}
    return store.ingest(IngestBatch.model_validate(batch),json.dumps(batch).encode(),'synthetic-test')


def test_increment_does_not_reclassify_candidate_or_replace_reviewed_reference(tmp_path):
    source=SQLiteIngestionRepository(tmp_path/'ingestion.sqlite')
    cat=CatalogRepository(tmp_path/'catalog.sqlite',ingestion=source)
    ingest(source,1,50);assert cat.sync_ingestion()['errors']==0
    with cat.connect() as con:
        references={r['entity_id']:dict(r) for r in con.execute("SELECT entity_id,definition_revision,payload,private_payload FROM catalog_items WHERE kind='variant'")}
    assert references
    card={'record_id':'synthetic-candidate','name_zh':'合成待补规则','original_rule_text':'候选定义，尚未结构化',
          'entity_type':'research_model','admission_status':'QUARANTINE'}
    path=tmp_path/'card.json';path.write_text(json.dumps([card]))
    receipt=import_cards(cat,path,hashlib.sha256(path.read_bytes()).hexdigest(),'strategy')
    candidate=receipt['entity_ids'][0]
    with cat.connect() as con:
        before=tuple(con.execute('SELECT payload,private_payload,definition_revision FROM catalog_items WHERE entity_id=?',(candidate,)).fetchone())
    ingest(source,2,60)
    assert cat.sync_ingestion()=={'processed':1,'errors':0}
    with cat.connect() as con:
        assert tuple(con.execute('SELECT payload,private_payload,definition_revision FROM catalog_items WHERE entity_id=?',(candidate,)).fetchone())==before
        for eid,row in references.items():
            assert dict(con.execute('SELECT entity_id,definition_revision,payload,private_payload FROM catalog_items WHERE entity_id=?',(eid,)).fetchone())==row
            assert con.execute("SELECT COUNT(*) FROM catalog_origins WHERE entity_id=? AND active=1",(eid,)).fetchone()[0]==2

"""Synthetic adversarial tests; actual-corpus acceptance is a separate opt-in run."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from quantgraph.api.app import create_app
from quantgraph.api.web import create_web_app
from quantgraph.api.web_read_model import WebReadModel
from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.models.ingestion import IngestBatch
from quantgraph.models.factor_study import ResearchRequest

PASSWORD='only-for-synthetic-test-password'
HEADERS={'X-QuantGraph-Request':'1'}


def batch(name='SYNTHETIC RSI 规则',rule='日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。',rid='TEST-ONLY-1',batch_id='TEST-BATCH-1'):
    return {'batch_id':batch_id,'collector_version':'explicit-test-fixture', 'records':[
        {'record_id':rid,'name':name,'source_url':'https://example.org/synthetic?token=SECRET',
         'raw_market':'美股 ETF','raw_rule':rule,'collected_at':'2026-09-28T00:00:00Z','metadata':{'fixture':True}}]}


@pytest.fixture
def runtime(tmp_path):
    ingestion=SQLiteIngestionRepository(tmp_path/'ingest.sqlite')
    cat=CatalogRepository(tmp_path/'catalog.sqlite',ingestion=ingestion)
    cat.import_factors(WebReadModel(create_app(public_only=True).state.db))
    b=batch(); ingestion.ingest(IngestBatch.model_validate(b),json.dumps(b).encode(),'test')
    cat.sync_ingestion()
    app=create_web_app(catalog=cat,admin_password=PASSWORD)
    return cat,TestClient(app)


def login(client):
    r=client.post('/v1/admin/session',json={'password':PASSWORD},headers=HEADERS)
    assert r.status_code==200
    assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']


def test_real_qlib_and_ingestion_visible_unresearched(runtime):
    cat,client=runtime
    assert cat.metadata()['counts']['strategy']==1
    row=client.get('/v1/web/search?kind=strategy&q=RSI').json()['items'][0]
    assert row['test_record'] is True
    assert row['entity_type']=='StrategyVariant'
    assert row['statuses']['catalog']=='已收录'
    assert row['strategy']['original_rule'] is None
    assert row['strategy']['structured_rule']['condition']['left']['name']=='RSI'
    assert 'SECRET' not in json.dumps(row)
    detail=client.get('/v1/web/entities/strategy/'+row['entity_id']).json()
    assert detail['results']['total']==0
    assert any(r['relation']=='USES_FACTOR' and r['attribution_status']=='RULE_LINK_ONLY' for r in detail['relations'])
    ref={k:row[k] for k in ['entity_type','entity_id','definition_revision']}
    request=client.post('/v1/web/research-requests',json={'entity_refs':[ref],'study_type':'STRATEGY_REPLICATION','requested_settings':{}})
    assert request.status_code==200
    assert ResearchRequest.model_validate(request.json()).status=='DRAFT'


def test_server_visibility_all_surfaces_and_restore(runtime):
    cat,client=runtime
    row=cat.search()['items'][0];eid=row['entity_id']
    ref={k:row[k] for k in ['entity_type','entity_id','definition_revision']}
    original=cat.metadata()['counts']['strategy']
    assert client.patch('/v1/admin/catalog',json={'ids':[eid],'patch':{'visibility':'HIDDEN'}},headers=HEADERS).status_code==401
    login(client)
    assert client.patch('/v1/admin/catalog',json={'ids':[eid],'patch':{'visibility':'HIDDEN'}},headers=HEADERS).status_code==200
    assert cat.metadata()['counts']['strategy']==original-1
    assert not cat.visible(eid)
    with pytest.raises(KeyError):cat.resolve_ref(**ref)
    for path in [f'/v1/web/entities/strategy/{eid}',f'/v1/web/relations/{eid}',f'/v1/web/export/strategy/{eid}',f'/v1/web/results?kind=strategy&eid={eid}']:
        assert client.get(path).status_code==404
    for path in ['/v1/stats','/v1/strategies','/v1/factors','/v1/entities/FactorVariant/'+eid]:
        assert client.get(path).status_code==404
    assert client.get('/v1/web/search?kind=strategy&q=SYNTHETIC').json()['total']==0
    assert client.post('/v1/web/references/resolve',json={'refs':[ref]}).status_code==409
    assert client.post('/v1/web/research-requests',json={'entity_refs':[ref],'study_type':'STRATEGY_REPLICATION','requested_settings':{}}).status_code==409
    factor=next(i for i in cat.all_items() if i.get('source_type')=='RULE_LINK_ONLY')
    assert eid not in json.dumps(cat.relations(factor['entity_id'],hops=2))
    assert client.patch('/v1/admin/catalog',json={'ids':[eid],'patch':{'visibility':'PUBLIC'}},headers=HEADERS).status_code==200
    assert client.get('/v1/web/entities/strategy/'+eid).status_code==200
    assert len(cat.audit())==2


def test_incremental_idempotent_revision_and_raw_review(runtime):
    cat,client=runtime
    original=cat.search()['items'][0]
    login(client)
    b=batch()
    r=client.post('/v1/admin/imports/grokbot',json=b,headers=HEADERS)
    assert r.json()['replayed'] and cat.search()['total']==1
    b=batch(rule='未知规则 SECRET_RAW_ONLY',batch_id='TEST-BATCH-2')
    assert client.post('/v1/admin/imports/grokbot',json=b,headers=HEADERS).status_code==200
    row=cat.search()['items'][0]
    assert row['entity_id']!=original['entity_id']
    assert not cat.visible(original['entity_id'])
    assert cat.search()['total']==1 and row['record_level']=='source_record'
    assert cat.search(q='SECRET_RAW_ONLY')['total']==0
    assert 'SECRET_RAW_ONLY' not in json.dumps(cat.detail('strategy',row['entity_id']))
    assert cat.sync_ingestion()=={'processed':0,'errors':0}
    with cat.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM catalog_versions WHERE entity_id=?',(original['entity_id'],)).fetchone()[0]==1


def test_csrf_auth_edit_and_relations(runtime):
    cat,client=runtime
    assert client.post('/v1/admin/session',json={'password':PASSWORD}).status_code==403
    assert client.post('/v1/admin/session',json={'password':PASSWORD},headers=HEADERS|{'Origin':'https://evil.example'}).status_code==403
    login(client)
    row=cat.search()['items'][0]
    changed=client.patch('/v1/admin/catalog',json={'ids':[row['entity_id']], 'patch':{'aliases':['测试 alias'], 'description':'<img src=x onerror=alert(1)>', 'source_url':'javascript:alert(1)'}},headers=HEADERS)
    assert changed.status_code==200
    assert cat.search(q='测试 alias')['total']==1
    assert cat.get(row['entity_id'])['source_url'] is None
    edges=cat.relations(row['entity_id'],hops=2,limit=2)
    assert len(edges['items'])==2 and edges['total']>2
    assert all(e['from_name'] and e['to_name'] and e['version'] for e in edges['items'])
    assert cat.relations(row['entity_id'],relation='DOES_NOT_EXIST')['total']==0
    e=edges['items'][0]
    assert client.patch('/v1/admin/relations/'+e['relationship_id'],json={'visibility':'HIDDEN'},headers=HEADERS).status_code==200
    assert e['relationship_id'] not in json.dumps(cat.relations(row['entity_id'],hops=2))
    assert client.delete('/v1/admin/session',headers=HEADERS).status_code==200
    assert client.get('/v1/admin/audit').status_code==401


def test_missing_invalid_pagination_and_safe_failure(runtime,monkeypatch):
    cat,client=runtime
    assert client.get('/v1/web/search?page=0').status_code==422
    assert client.get('/v1/web/relations/missing').status_code==404
    assert client.get('/v1/web/search?q=not-a-record').json()['total']==0
    first=cat.search(kind='variant',page_size=2);second=cat.search(kind='variant',page=2,page_size=2)
    assert {v['entity_id'] for v in first['items']}.isdisjoint(v['entity_id'] for v in second['items'])
    monkeypatch.setattr(cat,'search',lambda **kw: (_ for _ in ()).throw(RuntimeError('PRIVATE_DB_PATH_AND_TEXT')))
    r=client.get('/v1/web/search')
    assert r.status_code==500 and 'PRIVATE' not in r.text

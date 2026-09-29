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
    assert cat.metadata()['visible_counts'].get('strategy',0)==1
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
    original=cat.metadata()['visible_counts'].get('strategy',0)
    assert client.patch('/v1/admin/catalog',json={'ids':[eid],'patch':{'visibility':'HIDDEN'}},headers=HEADERS).status_code==401
    login(client)
    assert client.patch('/v1/admin/catalog',json={'ids':[eid],'patch':{'visibility':'HIDDEN'}},headers=HEADERS).status_code==200
    assert cat.metadata()['visible_counts'].get('strategy',0)==original-1
    assert not cat.visible(eid)
    with pytest.raises(KeyError):cat.resolve_ref(**ref)
    for path in [f'/v1/web/entities/strategy/{eid}',f'/v1/web/relations/{eid}',f'/v1/web/export/strategy/{eid}',f'/v1/web/results?kind=strategy&eid={eid}']:
        assert client.get(path).status_code==404
    for path in ['/v1/stats','/v1/strategies','/v1/factors','/v1/entities/FactorVariant/'+eid]:
        assert client.get(path).status_code==404
    assert client.get('/v1/web/search?kind=strategy&q=SYNTHETIC').json()['total']==0
    assert client.post('/v1/web/references/resolve',json={'refs':[ref]}).status_code==409
    assert client.post('/v1/web/research-requests',json={'entity_refs':[ref],'study_type':'STRATEGY_REPLICATION','requested_settings':{}}).status_code==409
    # This fixture owns its rule-factor reference exclusively, so hiding the
    # fixture must also remove that reference from the public projection.
    assert not any(i.get('source_type')=='RULE_LINK_ONLY' for i in cat.all_items())
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


def test_existing_ingestion_api_updates_catalog_and_permissions(runtime,monkeypatch):
    cat,_=runtime
    token='synthetic-api-key-with-more-than-thirty-two-characters'
    monkeypatch.setenv('QUANTGRAPH_API_KEYS',json.dumps({'test':{'token':token,'scopes':['ingest:write'],'requests_per_minute':60}}))
    client=TestClient(create_web_app(catalog=cat,admin_password=PASSWORD))
    body=batch(rid='TEST-INGEST-2',batch_id='TEST-INGEST-2')
    assert client.post('/v1/ingest/grokbot/batches',json=body).status_code==401
    result=client.post('/v1/ingest/grokbot/batches',json=body,headers={'Authorization':'Bearer '+token})
    assert result.status_code==200 and result.json()['accepted']==1
    assert cat.search()['total']==2
    assert cat.metadata()['knowledge_counts']['collected_strategy_records']==0
    row=cat.search()['items'][0]
    source=next(e['from_id'] for e in cat.relations(row['entity_id'])['items'] if e['relation']=='DESCRIBES')
    cat.edit([row['entity_id']],{'visibility':'HIDDEN'},'test')
    assert not cat.visible(source)
    assert client.get('/v1/web/entities/source/'+source).status_code==404
    cat.edit([row['entity_id']],{'visibility':'PUBLIC'},'test')
    assert cat.visible(source)


def test_bad_admin_edits_fail_without_mutation(runtime):
    cat,client=runtime;login(client);eid=cat.search()['items'][0]['entity_id']
    for patch in [{'aliases':'not-a-list'},{'aliases':[{}]},{'markets':42},{'name':['bad']}]:
        assert client.patch('/v1/admin/catalog',json={'ids':[eid],'patch':patch},headers=HEADERS).status_code==422
    assert cat.audit()==[]


def test_fixture_children_do_not_inflate_real_counts_and_shared_nodes_survive(runtime):
    cat,_=runtime
    row=cat.search()['items'][0]
    factor=next(r['to_id'] for r in cat.relations(row['entity_id'])['items'] if r['relation']=='USES_FACTOR')
    assert cat.get(factor)['test_record']
    assert cat.metadata()['counts']['variant']==508
    assert cat.metadata()['test_counts']['variant']==1
    cat.edit([row['entity_id']],{'visibility':'HIDDEN'},'test')
    assert not cat.visible(factor)
    body=batch(rid='BUSINESS-SOURCE',batch_id='BUSINESS-SOURCE');body['records'][0]['metadata']={}
    cat.ingestion.ingest(IngestBatch.model_validate(body),json.dumps(body).encode(),'test');cat.sync_ingestion()
    assert cat.visible(factor) and not cat.get(factor)['test_record']
    assert cat.metadata()['counts']['variant']==509


def test_admin_operational_views_are_authenticated_and_audited(runtime):
    cat,client=runtime
    for route in ['/v1/admin/research-jobs','/v1/admin/merge-suggestions']:
        assert client.get(route).status_code==401
    login(client)
    assert client.get('/v1/admin/research-jobs').json()=={'items':[],'total':0}
    items=cat.search(kind='variant',page_size=2)['items']
    body={'left':items[0]['entity_id'],'right':items[1]['entity_id'],'reason':'SYNTHETIC review only; no equivalence claim'}
    proposed=client.post('/v1/admin/merge-suggestions',json=body,headers=HEADERS).json()
    values=client.get('/v1/admin/merge-suggestions').json()['items']
    assert values[0]['left']['name']==items[0]['name']
    assert client.patch('/v1/admin/merge-suggestions/'+proposed['suggestion_id'],json={'status':'REJECTED'},headers=HEADERS).status_code==200
    assert cat.audit()[0]['action']=='REVIEW_MERGE'
    eid=cat.search()['items'][0]['entity_id']; edge=cat.relations(eid)['items'][0]
    for patch in [{'confidence':'bad'},{'review_status':'SAME_AS'},{'evidence':[]}]:
        assert client.patch('/v1/admin/relations/'+edge['relationship_id'],json=patch,headers=HEADERS).status_code==422


def test_projection_rebuild_preserves_administrator_search_overlay(runtime):
    cat,_=runtime
    value=cat.search(kind='variant')['items'][0]
    cat.edit([value['entity_id']],{'aliases':['SYNTHETIC-REBUILD-ALIAS']},'test')
    cat.import_factors(WebReadModel(create_app(public_only=True).state.db))
    assert cat.search(kind='variant',q='SYNTHETIC-REBUILD-ALIAS')['total']==1
    cat.edit([value['entity_id']],{'visibility':'HIDDEN'},'test')
    cat.import_factors(WebReadModel(create_app(public_only=True).state.db))
    assert not cat.visible(value['entity_id'])

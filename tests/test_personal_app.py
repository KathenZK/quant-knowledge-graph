"""Local personal data must never relax the independently created public app."""
import json

from fastapi.testclient import TestClient
import pytest

from quantgraph.api.personal_app import create_personal_app
from quantgraph.api.web import create_web_app
from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.graph.personal_catalog import PersonalCatalogRepository
from quantgraph.graph.personal_store import PersonalStore
from quantgraph.models.ingestion import IngestBatch


@pytest.fixture
def personal(tmp_path):
    journal = SQLiteIngestionRepository(tmp_path / 'ingestion.sqlite')
    batch = IngestBatch.model_validate(dict(batch_id='personal-security', collector_version='test-only', records=[
        dict(record_id='local-only-rule', name='隔离验证资料', raw_rule='未解析的完整规则。观察 SYNTHETIC_ORIGINAL_ONLY 后再核对。',
             raw_market='未确认', source_url='https://example.org/article?id=42#section-2', collected_at='2026-09-29T00:00:00Z')]))
    journal.ingest(batch, batch.model_dump_json().encode(), 'test')
    catalog = PersonalCatalogRepository(tmp_path / 'catalog.sqlite', ingestion=journal)
    catalog.sync_ingestion()
    item = catalog.search(kind='strategy')['items'][0]
    catalog.edit([item['entity_id']], {'visibility': 'HIDDEN'}, 'test')
    store = PersonalStore(tmp_path / 'personal.sqlite')
    app = create_personal_app(runtime=tmp_path, catalog=catalog, store=store)
    return TestClient(app), catalog, item, tmp_path


def test_missing_catalog_is_explicit_and_never_qlib(tmp_path):
    client = TestClient(create_personal_app(runtime=tmp_path))
    meta = client.get('/v1/web/meta').json()
    assert meta['mode'] == 'personal_local' and meta['initialized'] is False
    assert meta['initialization']['status'] == 'MISSING'
    assert client.get('/v1/web/search').status_code == 503


def test_private_reading_hidden_flags_and_public_isolation(personal):
    client, catalog, item, path = personal
    route = '/v1/web/entities/strategy/' + item['entity_id']
    response = client.get(route)
    assert response.status_code == 200
    assert 'SYNTHETIC_ORIGINAL_ONLY' in response.text
    assert 'id=42' in response.json()['source_url'] and '#section-2' in response.json()['source_url']
    with catalog.connect() as con:
        assert con.execute('SELECT visibility FROM catalog_items WHERE entity_id=?', (item['entity_id'],)).fetchone()[0] == 'HIDDEN'
    public = TestClient(create_web_app(catalog=CatalogRepository(path / 'catalog.sqlite')))
    assert public.get(route).status_code == 404
    assert 'SYNTHETIC_ORIGINAL_ONLY' not in public.get('/v1/web/search?kind=strategy').text
    for route in ['/v1/admin/session', '/v1/research/jobs', '/v1/ingest/grokbot/batches']:
        assert client.post(route, json={}).status_code == 404


def test_same_origin_host_and_remote_restrictions(personal):
    client, catalog, item, path = personal
    for headers in [{'Origin':'https://outside.example'}, {'Origin':'null'}, {'Sec-Fetch-Site':'cross-site'}]:
        assert client.get('/v1/web/meta', headers=headers).status_code == 403
        assert client.post('/v1/personal/restore', json={}, headers=headers).status_code == 403
    assert client.get('/v1/web/meta', headers={'Host':'outside.example'}).status_code == 400
    remote = TestClient(create_personal_app(runtime=path, catalog=catalog), client=('192.0.2.4', 9999))
    assert remote.get('/v1/web/meta').status_code == 403
    assert client.get('/v1/web/meta', headers={'Origin':'http://testserver'}).status_code == 200
    assert "frame-ancestors 'none'" in client.get('/v1/web/meta').headers['content-security-policy']


def test_notes_survive_service_recreation_and_filter_before_pagination(personal):
    client, catalog, item, path = personal
    route = '/v1/personal/items/strategy/' + item['entity_id']
    saved = client.put(route, json={'definition_revision': item['definition_revision'], 'starred': True,
        'status': '值得研究', 'note': '我自己的判断', 'group': '规则核对', 'questions': '样本外是否稳定？'})
    assert saved.status_code == 200
    other = TestClient(create_personal_app(runtime=path))
    assert other.get(route).json()['note'] == '我自己的判断'
    result = other.get('/v1/web/search?kind=strategy&personal_status=值得研究&page_size=1').json()
    assert result['total'] == 1 and result['items'][0]['entity_id'] == item['entity_id']
    assert other.get('/v1/web/search?kind=strategy&personal_status=待读').json()['total'] == 0
    exported = other.get('/v1/personal/export?format=json').json()
    assert exported['items'][0]['rule'] and exported['research_requests'][0]['status'] == 'DRAFT'
    assert 'SYNTHETIC_ORIGINAL_ONLY' in json.dumps(exported)


def test_long_formula_queries_are_accepted_with_bounded_length(personal):
    client, _, _, _ = personal
    formula = 'Mean($close, 5)/$close + ' * 25 + '$volume'
    response = client.get('/v1/web/search', params={'kind':'variant', 'q':formula})
    assert response.status_code == 200 and response.json()['total'] == 0
    assert response.json()['query']['units'][0]['kind'] == 'formula'
    assert client.get('/v1/web/search', params={'q':'x'*2001}).status_code == 422

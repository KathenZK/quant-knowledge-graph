import copy
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from quantgraph.api.app import create_app
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.models.ingestion import IngestBatch
from quantgraph.client import load_batch

TOKEN = 'synthetic-test-token-with-no-real-authority'


def batch():
    return {'batch_id': 'test-001', 'collector_version': 'test-v1', 'records': [{
        'record_id': 'example-1', 'source_url': 'https://example.org/rule', 'name': 'Synthetic rule',
        'raw_market': '美股 ETF', 'raw_rule': '日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。',
        'collected_at': '2026-01-01T00:00:00Z'}]}


@pytest.fixture
def setup(tmp_path):
    repo = SQLiteIngestionRepository(tmp_path / 'private.sqlite')
    keys = {'collector': {'token': TOKEN, 'scopes': ['ingest:read', 'ingest:write', 'research:read', 'research:write'], 'requests_per_minute': 500}}
    app = create_app(ingestion_repository=repo, ingestion_keys=keys)
    return repo, TestClient(app), {'Authorization': 'Bearer ' + TOKEN}


def test_auth_scope_rotation_and_logs(setup):
    repo, client, headers = setup
    assert client.post('/v1/ingest/grokbot/batches', json=batch()).status_code == 401
    client.app.state.ingestion_keys['collector']['scopes'] = ['ingest:read']
    assert client.post('/v1/ingest/grokbot/batches', json=batch(), headers=headers).status_code == 403
    client.app.state.ingestion_keys['new'] = {'token': TOKEN + '-rotated', 'scopes': ['ingest:read']}
    assert client.get('/v1/usage', headers={'Authorization': 'Bearer ' + TOKEN + '-rotated'}).status_code == 200
    del client.app.state.ingestion_keys['new']
    assert client.get('/v1/usage', headers={'Authorization': 'Bearer ' + TOKEN + '-rotated'}).status_code == 401
    with repo.connect() as con:
        logs = str([tuple(r) for r in con.execute('SELECT * FROM request_logs')])
    assert TOKEN not in logs and 'raw_rule' not in logs


def test_replay_revisions_unknown_fields_and_rights(setup):
    repo, client, headers = setup
    value = batch()
    value['new_batch_field'] = {'unfamiliar': True}
    value['records'][0].update(new_field=[1, 2], live_ready=True, rights='ALLOWED')
    first = client.post('/v1/ingest/grokbot/batches', json=value, headers=headers).json()
    assert first['accepted'] == first['curated'] == first['review_required'] == 1
    assert first['errors'] == first['revision'] == first['duplicate'] == 0
    again = client.post('/v1/ingest/grokbot/batches', json=value, headers=headers).json()
    assert again['job_id'] == first['job_id'] and again['duplicate'] == 1 and again['accepted'] == 0
    value['records'][0]['raw_rule'] = '日频：若 RSI(7)>58 → 满仓 QQQ，否则 SHV。'
    revised = client.post('/v1/ingest/grokbot/batches', json=value, headers=headers).json()
    assert revised['revision'] == 1
    value['batch_id'] = 'test-002'
    assert client.post('/v1/ingest/grokbot/batches', json=value, headers=headers).json()['duplicate'] == 1
    row = repo.variants()[0]
    v = row['variant']
    assert not v['executable'] and not row['research_allowed']
    assert v['rights_status'] == 'REVIEW_REQUIRED'
    assert v['auditable_metadata']['auditable_unknown_fields']['new_field'] == [1, 2]
    assert v['ingestion_lineage']['revision'] == 2
    assert len(repo.lineage(v['strategy_variant_id'])) == 2
    assert client.get('/v1/ingest/jobs/' + first['job_id'], headers=headers).json()['accepted'] == 1
    assert len(client.get('/v1/ingest/batches/test-001', headers=headers).json()['submissions']) == 2
    assert client.get('/v1/ingest/jobs/missing', headers=headers).status_code == 404
    with repo.connect() as con:
        assert con.execute('SELECT count(*) FROM revisions').fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            con.execute("UPDATE revisions SET raw_payload='{}'")


def test_unknown_rule_and_invalid_payload(setup):
    repo, client, headers = setup
    value = batch()
    value['records'][0]['raw_rule'] = 'Some clever undisclosed model'
    result = client.post('/v1/ingest/grokbot/batches', json=value, headers=headers).json()
    assert result['curated'] == 0 and result['review_required'] == 1
    assert repo.variants()[0]['variant']['rule_ast'] is None
    for bad in [{}, {**value, 'records': value['records'] * 2}, {**value, 'records': value['records'] * 1001}]:
        assert client.post('/v1/ingest/grokbot/batches', json=bad, headers=headers).status_code == 422
    bad = copy.deepcopy(value)
    bad['records'][0]['source_url'] = 'file:///etc/passwd'
    assert client.post('/v1/ingest/grokbot/batches', json=bad, headers=headers).status_code == 422
    bad['records'][0]['source_url'] = 'https://example.org'
    bad['records'][0]['external_id'] = 'conflicting-id'
    assert client.post('/v1/ingest/grokbot/batches', json=bad, headers=headers).status_code == 422


def test_gzip_payload_rate_limit_and_restart(setup):
    repo, client, headers = setup
    raw = json.dumps(batch()).encode()
    response = client.post('/v1/ingest/grokbot/batches', content=gzip.compress(raw), headers={**headers, 'Content-Encoding': 'gzip', 'Content-Type': 'application/json'})
    assert response.status_code == 200
    for encoding, content, expected in [('identity', b'X' * (2 * 1024 * 1024 + 1), 413),
                                         ('gzip', gzip.compress(b'X' * (3 * 1024 * 1024)), 413),
                                         ('gzip', b'bad-gzip', 400), ('br', raw, 415)]:
        assert client.post('/v1/ingest/grokbot/batches', content=content, headers={**headers, 'Content-Encoding': encoding}).status_code == expected
    client.app.state.ingestion_keys['collector']['requests_per_minute'] = 1
    assert client.get('/v1/usage', headers=headers).status_code == 429
    restarted = SQLiteIngestionRepository(repo.path)
    assert restarted.get_job(response.json()['job_id'])['accepted'] == 1


def test_concurrent_requests_and_atomic_rollback(setup, monkeypatch):
    repo, _, _ = setup
    value = IngestBatch.model_validate(batch())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: repo.ingest(value, b'raw', 'test'), range(8)))
    assert sum(r['accepted'] for r in results) == 1
    import quantgraph.graph.ingestion as projection
    def fail(*args):
        raise RuntimeError('injected projection failure')
    monkeypatch.setattr(projection, 'project_record', fail)
    next_value = batch()
    next_value['records'][0]['raw_rule'] = 'changed'
    with pytest.raises(RuntimeError):
        repo.ingest(IngestBatch.model_validate(next_value), b'changed', 'test')
    with repo.connect() as con:
        assert con.execute('SELECT count(*) FROM revisions').fetchone()[0] == 1


def test_private_routes_and_evidence_cannot_promote(setup):
    repo, client, headers = setup
    client.post('/v1/ingest/grokbot/batches', json=batch(), headers=headers)
    row = repo.variants()[0]
    for kind in ('concepts', 'templates', 'variants'):
        assert len(client.get('/v1/research/strategies/' + kind, headers=headers).json()['items']) == 1
    factor_id = row['factor_links'][0]['factor_id']
    assert len(client.get(f'/v1/research/factors/{factor_id}/strategies', headers=headers).json()['items']) == 1
    assert client.get('/v1/research/candidates', headers=headers).json()['scope'] == 'TRIAGE_ONLY'
    evidence = dict(research_run_id='synthetic-run', experiment_family_id='synthetic-family',
                    source_strategy_ids=[row['variant']['strategy_variant_id']], artifact_uri='file:synthetic',
                    artifact_sha256='a' * 64, contract_sha256='b' * 64, trial_count=1,
                    results={'oos': None}, evidence_kind='PIPELINE_DIAGNOSTIC')
    result = client.post('/v1/research/evidence', json=evidence, headers=headers)
    assert result.status_code == 200 and not result.json()['promotion_triggered']
    assert client.post('/v1/research/evidence', json=evidence, headers=headers).json()['duplicate']
    evidence['results']['oos'] = {'return': 1}
    assert client.post('/v1/research/evidence', json=evidence, headers=headers).status_code == 409
    evidence['promotion_status'] = 'APPROVED_FOR_LIVE'
    assert client.post('/v1/research/evidence', json=evidence, headers=headers).status_code == 422
    assert client.get('/v1/strategies').json()['items'] == []


def test_jsonl_and_aliases(tmp_path):
    value = batch()['records'][0]
    value['external_id'] = value.pop('record_id')
    value['title'] = value.pop('name')
    path = tmp_path / 'records.ndjson.gz'
    path.write_bytes(gzip.compress((json.dumps(value) + '\n').encode()))
    result = load_batch(path, batch_id='jsonl', collector_version='test')
    assert IngestBatch.model_validate(result).records[0].record_id == 'example-1'


def test_reprojection_and_stable_ids(setup):
    repo, _, _ = setup
    value = IngestBatch.model_validate(batch())
    repo.ingest(value, b'raw', 'test')
    before = repo.variants()[0]['variant']
    assert repo.reproject()['projections_added'] == 0
    other = batch()
    other['records'][0]['record_id'] = 'unrelated-new-record'
    other['batch_id'] = 'unrelated-new-batch'
    repo.ingest(IngestBatch.model_validate(other), b'other', 'test')
    after = next(r['variant'] for r in repo.variants() if r['variant']['source_native_id'] == before['source_native_id'])
    assert after == before
    from quantgraph.models.entities import StrategyVariant
    StrategyVariant.model_validate(after)

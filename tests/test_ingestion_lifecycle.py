import copy
import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from quantgraph.api.app import create_app
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository, ProjectionUnavailable
from quantgraph.models.ingestion import IngestBatch


def payload():
    return {'batch_id': 'observation-one', 'collector_version': 'fixture', 'records': [{
        'record_id': 'fixture-one', 'source_url': 'https://example.org/own-rule',
        'name': 'Synthetic fixture', 'raw_market': '美股 ETF',
        'raw_rule': '日频：若RSI(14)>55→满仓SPY，否则满仓BIL。',
        'collected_at': '2026-01-01T00:00:00Z'}]}


def ingest(repo, value):
    raw = json.dumps(value).encode()
    return repo.ingest(IngestBatch.model_validate(value), raw, 'fixture'), raw


def test_new_observation_does_not_create_revision_and_retains_both_hashes(tmp_path):
    repo = SQLiteIngestionRepository(tmp_path / 'journal.sqlite')
    value = payload()
    first, wire1 = ingest(repo, value)
    before = repo.variants()
    value['records'][0]['collected_at'] = '2026-01-02T00:00:00Z'
    value['records'][0]['metadata'] = {'request_timestamp': '2026-01-02', 'observation_metadata': {'batch': 2}}
    value['metadata'] = {'runtime': 2}
    second, wire2 = ingest(repo, value)
    assert second['duplicate'] == 1 and second['revision'] == second['accepted'] == 0
    assert first['job_id'] != second['job_id']
    assert repo.variants() == before
    with repo.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM revisions').fetchone()[0] == 1
        rows = con.execute('SELECT * FROM observation_payloads').fetchall()
        assert len(rows) == 2 and rows[0]['raw_payload_hash'] != rows[1]['raw_payload_hash']
        assert rows[0]['semantic_record_hash'] == rows[1]['semantic_record_hash']
        assert {r[0] for r in con.execute('SELECT raw_payload_hash FROM submission_bytes')} == {
            hashlib.sha256(wire1).hexdigest(), hashlib.sha256(wire2).hexdigest()}
        for r in rows:
            data = json.loads(r['raw_payload'])
            encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
            assert hashlib.sha256(encoded).hexdigest() == r['raw_payload_hash']
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            con.execute("UPDATE observation_payloads SET raw_payload='{}'")


@pytest.mark.parametrize('change', [
    {'raw_rule': '日频：若RSI(14)>60→满仓SPY，否则满仓BIL。'},
    {'author': 'Changed source author'}, {'source_publication_date': '2025-02-02'},
    {'metadata': {'source_revision': 'v2'}}, {'source_metadata': {'document_hash': 'changed'}},
    {'strategy_parameters': {'window': 20}}, {'raw_market': '全球 ETF'},
])
def test_material_source_changes_create_revision(tmp_path, change):
    repo = SQLiteIngestionRepository(tmp_path / 'journal.sqlite')
    value = payload()
    ingest(repo, value)
    value['records'][0].update(change)
    result, _ = ingest(repo, value)
    assert result['revision'] == 1
    assert repo.ingest_stats()['revisions'] == 1


def test_additive_migration_keeps_historical_rows_and_original_wire_bytes(tmp_path):
    path = tmp_path / 'legacy.sqlite'
    repo = SQLiteIngestionRepository(path)
    ingest(repo, payload())
    with repo.connect() as con:
        before = {t: [tuple(r) for r in con.execute('SELECT * FROM ' + t)]
                  for t in ('submissions', 'observations', 'revisions', 'projections')}
        for t in ('observation_hash_versions', 'observation_payloads', 'revision_semantics_v2', 'revision_semantics', 'submission_bytes', 'projection_runs'):
            con.execute('DROP TABLE ' + t)
        con.execute('PRAGMA user_version=1')
    migrated = SQLiteIngestionRepository(path)
    with migrated.connect() as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 4
        for table, expected in before.items():
            assert [tuple(r) for r in con.execute('SELECT * FROM ' + table)] == expected
    value = payload()
    value['records'][0]['collected_at'] = '2026-02-02T00:00:00Z'
    assert ingest(migrated, value)[0]['duplicate'] == 1
    assert SQLiteIngestionRepository(path).ingest_stats()['total_observations'] == 2


def test_upgrade_blocks_partial_universe_and_retry_recovers_atomically(tmp_path, monkeypatch):
    import quantgraph.graph.ingestion_store as store
    import quantgraph.graph.ingestion as projection
    repo = SQLiteIngestionRepository(tmp_path / 'journal.sqlite')
    one = payload()
    two = copy.deepcopy(one)
    two['records'][0]['record_id'] = 'fixture-two'
    ingest(repo, one)
    ingest(repo, two)
    ids = [r['variant']['strategy_variant_id'] for r in repo.variants()]
    monkeypatch.setattr(store, 'VERSION', 'fixture-next-parser')
    assert repo.projection_status()['stale_projection_count'] == 2
    with pytest.raises(ProjectionUnavailable):
        repo.variants()
    key = {'test': {'token': 't' * 40, 'scopes': ['research:read']}}
    client = TestClient(create_app(ingestion_repository=repo, ingestion_keys=key))
    headers = {'Authorization': 'Bearer ' + 't' * 40}
    response = client.get('/v1/research/candidates', headers=headers)
    assert response.status_code == 503 and response.json()['projection_status'] == 'STALE'
    original = projection.project_record
    def fail(*args):
        assert repo.projection_status()['projection_status'] == 'REPROJECTING'
        raise RuntimeError('fixture failure')
    monkeypatch.setattr(projection, 'project_record', fail)
    with pytest.raises(RuntimeError):
        repo.reproject()
    assert repo.projection_status()['projection_status'] == 'FAILED'
    assert repo.projection_status()['current_projection_count'] == 0
    monkeypatch.setattr(projection, 'project_record', original)
    assert repo.reproject()['projections_added'] == 2
    assert repo.projection_status()['projection_status'] == 'READY'
    assert [r['variant']['strategy_variant_id'] for r in repo.variants()] == ids
    assert repo.reproject()['projections_added'] == 0
    assert client.get('/v1/research/candidates', headers=headers).status_code == 200


def test_duplicate_after_upgrade_uses_first_observation_for_projection(tmp_path, monkeypatch):
    import quantgraph.graph.ingestion_store as store
    repo = SQLiteIngestionRepository(tmp_path / 'journal.sqlite')
    value = payload()
    ingest(repo, value)
    monkeypatch.setattr(store, 'VERSION', 'fixture-next-parser')
    value['records'][0]['collected_at'] = '2026-01-02T00:00:00Z'
    value['batch_id'] = 'second'
    assert ingest(repo, value)[0]['duplicate'] == 1
    assert repo.reproject()['projections_added'] == 0


def test_future_schema_is_never_downgraded(tmp_path):
    path = tmp_path / 'future.sqlite'
    repo = SQLiteIngestionRepository(path)
    with repo.connect() as con:
        con.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError, match='newer'):
        SQLiteIngestionRepository(path)
    with repo.connect() as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 99


@pytest.mark.parametrize('assessment', ['backtestability', 'bot_assessment', 'parser_output',
    'candidate_score', 'research_readiness', 'rights_enrichment_result'])
def test_assessment_updates_only_add_observations(tmp_path, assessment):
    repo = SQLiteIngestionRepository(tmp_path / 'journal.sqlite')
    value = payload()
    ingest(repo, value)
    record = value['records'][0]
    record[assessment] = 'HIGH'
    record['metadata'] = {assessment: 'HIGH'}
    record['source_metadata'] = {assessment: 'HIGH'}
    result, _ = ingest(repo, value)
    assert result['duplicate'] == 1 and result['revision'] == 0
    with repo.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM revisions').fetchone()[0] == 1
        rows = con.execute('SELECT * FROM observation_payloads').fetchall()
        assert len(rows) == 2
        assert rows[0]['raw_payload_hash'] != rows[1]['raw_payload_hash']
        assert rows[0]['semantic_record_hash'] == rows[1]['semantic_record_hash']
        assert assessment in json.loads(rows[1]['raw_payload'])


def test_v3_migration_preserves_old_hashes_and_observation_payloads(tmp_path):
    path = tmp_path / 'v3.sqlite'
    repo = SQLiteIngestionRepository(path)
    value = payload()
    value['records'][0]['backtestability'] = 'MEDIUM'
    ingest(repo, value)
    with repo.connect() as con:
        before = {t: [tuple(r) for r in con.execute('SELECT * FROM ' + t)]
                  for t in ('revisions', 'revision_semantics', 'observation_payloads', 'submissions')}
        con.execute('DROP TABLE observation_hash_versions')
        con.execute('DROP TABLE revision_semantics_v2')
        con.execute('PRAGMA user_version=3')
    repo = SQLiteIngestionRepository(path)
    with repo.connect() as con:
        for table, rows in before.items():
            assert [tuple(r) for r in con.execute('SELECT * FROM ' + table)] == rows
    value['records'][0]['backtestability'] = 'HIGH'
    assert ingest(repo, value)[0]['duplicate'] == 1

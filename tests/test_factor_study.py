"""Public source lineage with synthetic, de-identified evidence only."""
import copy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from quantgraph import FactorDB
from quantgraph.db import project_root
from quantgraph.api.app import create_app
from quantgraph.factor_study import definition_identity, draft_request
from quantgraph.graph.factor_study_store import FactorStudyRepository
from quantgraph.models.factor_study import FactorStudyResult, ResearchRequest

ROOT = project_root()
CONTRACTS = ROOT / 'contracts/factor-study/v1'


@pytest.fixture
def evidence():
    return json.loads((CONTRACTS / 'fixtures/factor-study-result.json').read_text())


@pytest.fixture
def repo(tmp_path):
    return FactorStudyRepository(tmp_path / 'private.sqlite', FactorDB(ROOT, profile='commercial'))


def test_schema_is_generated_from_authoritative_models_and_fixtures_validate():
    for name, model in [('research-request', ResearchRequest), ('factor-study-result', FactorStudyResult)]:
        schema = json.loads((CONTRACTS / (name + '.schema.json')).read_text())
        value = json.loads((CONTRACTS / 'fixtures' / (name + '.json')).read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)
        assert model.model_validate(value).model_dump(mode='json') == value
        assert {k: v for k, v in schema.items() if k not in {'$id', '$schema'}} == model.model_json_schema()


def test_draft_is_not_an_approval():
    request = json.loads((CONTRACTS / 'fixtures/research-request.json').read_text())
    for value in ['APPROVED', 'ELIGIBLE', 'RUNNING']:
        with pytest.raises(ValueError):
            ResearchRequest.model_validate({**request, 'status': value})
    result = draft_request(FactorDB(ROOT), ['KMID', 'STD5', 'RANK5'], 'test', {})
    assert len(result['request']['entity_refs']) == 3
    assert result['request']['status'] == 'DRAFT'
    with pytest.raises(ValueError):
        draft_request(FactorDB(ROOT), ['RSI_FAKE'], 'test', {})


def test_idempotent_failed_writeback_and_variant_concept_reads(repo, evidence):
    identity = evidence['mapping']['identity']
    assert repo.put(evidence)['duplicate'] is False
    assert repo.put(evidence)['duplicate'] is True
    assert repo.query(identity['factor_variant_id'], profile='research') == [evidence]
    assert repo.query(identity['factor_concept_id'], profile='research') == [evidence]
    assert repo.query(identity['factor_variant_id']) == []
    bad = copy.deepcopy(evidence)
    bad['results']['reason'] = 'different evidence'
    with pytest.raises(ValueError, match='Immutable'):
        repo.put(bad)
    with repo.connect() as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []
        assert con.execute('SELECT count(*) FROM studies').fetchone()[0] == 1


@pytest.mark.parametrize('field,value', [('factor_concept_id', 'wrong-concept'), ('formula', 'same name wrong formula'),
                                     ('source_revision', 'wrong-source'), ('definition_revision', 'a' * 64)])
def test_same_name_cannot_override_source_or_definition(repo, evidence, field, value):
    evidence['mapping']['identity'][field] = value
    with pytest.raises(ValueError, match='revision mismatch'):
        repo.put(evidence)


def test_no_synthetic_diagnostic_or_unverified_success(evidence):
    evidence['status'] = 'SUCCESS'
    with pytest.raises(ValueError, match='verified computation'):
        FactorStudyResult.model_validate(evidence)
    evidence['mapping']['mapping_status'] = 'VERIFIED'
    with pytest.raises(ValueError, match='both semantic layers'):
        FactorStudyResult.model_validate(evidence)
    evidence['mapping']['semantic_tests'] = [dict(name=k, status='PASS', evidence=evidence['code'])
        for k in ('hand_calculated', 'reference_parity', 'real_market_boundaries')]
    evidence['study_type'] = 'FACTOR_DIAGNOSTIC'
    with pytest.raises(ValueError, match='real data'):
        FactorStudyResult.model_validate(evidence)
    evidence['research_status'] = 'RESEARCH_PASSED'
    with pytest.raises(ValueError):
        FactorStudyResult.model_validate(evidence)


def test_no_producer_can_publish_market_or_derived_results(repo, evidence):
    for name in ('market_data', 'derived_result'):
        bad = copy.deepcopy(evidence)
        bad['permissions'][name]['public_display'] = 'ALLOWED'
        with pytest.raises(ValueError, match='separate rights review'):
            repo.put(bad)
    with pytest.raises(ValueError, match='outside graph releases'):
        FactorStudyRepository(FactorDB(ROOT).path, FactorDB(ROOT))


def test_private_api_auth_and_public_isolation(repo, evidence):
    keys = {'test': {'token': 'synthetic-test-token-' * 3, 'scopes': ['research:read', 'research:write']}}
    client = TestClient(create_app(ROOT, factor_study_repository=repo, ingestion_keys=keys))
    endpoint = '/v1/research/factor-studies'
    vid = evidence['mapping']['identity']['factor_variant_id']
    assert client.post(endpoint, json=evidence).status_code == 401
    assert client.get(endpoint + '/' + vid).status_code == 401
    headers = {'Authorization': 'Bearer ' + keys['test']['token']}
    assert client.post(endpoint, json=evidence, headers=headers).status_code == 200
    assert client.post(endpoint, json=evidence, headers=headers).json()['duplicate'] is True
    assert client.get(endpoint + '/' + vid, headers=headers).json()['items'] == [evidence]
    assert client.get('/v1/factors/' + vid + '/studies').json()['items'] == []
    assert 'results' not in client.get('/v1/factors/' + vid).json()
    keys['test']['scopes'] = ['research:read']
    assert client.post(endpoint, json=evidence, headers=headers).status_code == 403


def test_unknown_study_type_does_not_weaken_strategy_gate(evidence):
    for kind in ('PORTFOLIO_BACKTEST', 'CONFIRMATORY_VALIDATION'):
        evidence['study_type'] = kind
        with pytest.raises(ValueError, match='existing strategy'):
            FactorStudyResult.model_validate(evidence)


def test_definition_revision_is_stable_and_parameters_matter():
    v = FactorDB(ROOT).search_factors('Alpha158:STD5', limit=1000)[0]
    before = definition_identity(v)
    v['parameters'] = {'window': 99}
    assert definition_identity(v)['definition_revision'] != before['definition_revision']


def test_ingestion_and_factor_studies_share_one_body_limiter(repo, tmp_path, evidence):
    import gzip
    from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
    from quantgraph.api.ingestion import BoundedBodyMiddleware
    keys = {'test': {'token': 'coexistence-fixture-token-' * 3, 'scopes': ['research:write']}}
    app = create_app(ROOT, ingestion_repository=SQLiteIngestionRepository(tmp_path / 'ingest.sqlite'),
                     factor_study_repository=repo, ingestion_keys=keys)
    assert sum(m.cls is BoundedBodyMiddleware for m in app.user_middleware) == 1
    c = TestClient(app)
    response = c.post('/v1/research/factor-studies', content=gzip.compress(json.dumps(evidence).encode()),
                      headers={'Authorization': 'Bearer ' + keys['test']['token'],
                               'Content-Type': 'application/json', 'Content-Encoding': 'gzip'})
    assert response.status_code == 200

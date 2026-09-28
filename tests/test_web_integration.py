"""Real public definitions plus explicitly synthetic restricted result fixture."""
import json
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from quantgraph.api.web import create_web_app
from quantgraph.db import project_root
from quantgraph.factor_study import definition_identity
from quantgraph.graph.factor_study_store import FactorStudyRepository


def test_draft_uses_authoritative_schema_and_revision():
    app = create_web_app()
    c = TestClient(app)
    row = c.get('/v1/web/search?q=MA5').json()['items'][0]
    ref = {k: row[k] for k in ('entity_id', 'entity_type', 'definition_revision')}
    assert ref['definition_revision'] == definition_identity(app.state.db.get_variant(ref['entity_id']))['definition_revision']
    body = dict(entity_refs=[ref], study_type='FACTOR_DIAGNOSTIC', requested_settings={'market': 'crypto'})
    response = c.post('/v1/web/research-requests', json=body)
    assert response.status_code == 200
    schema = json.loads((project_root()/'contracts/factor-study/v1/research-request.schema.json').read_text())
    Draft202012Validator(schema).validate(response.json())
    assert response.json()['status'] == 'DRAFT'
    assert c.post('/v1/web/research-requests', json={**body, 'profile':'research'}).status_code == 422
    assert c.post('/v1/web/research-requests', json={**body, 'entity_refs':[ref, ref]}).status_code == 422
    assert c.post('/v1/web/research-requests', json={**body, 'entity_refs':[{**ref, 'definition_revision':'stale'}]}).status_code == 409


def test_private_journal_never_changes_public_payloads(tmp_path, monkeypatch):
    baseline = TestClient(create_web_app())
    journal = tmp_path/'private.sqlite'
    repo = FactorStudyRepository(journal, baseline.app.state.db)
    evidence = json.loads((project_root()/'contracts/factor-study/v1/fixtures/factor-study-result.json').read_text())
    evidence['run_id'] = 'SYNTHETIC_PRIVATE_SENTINEL'
    repo.put(evidence)
    vid = evidence['mapping']['identity']['factor_variant_id']
    monkeypatch.setenv('QUANTGRAPH_FACTOR_STUDY_DB', str(journal))
    public = TestClient(create_web_app())
    for url in ['/v1/web/meta', '/v1/web/search', '/v1/web/results', '/v1/stats',
                '/v1/web/entities/variant/'+vid, '/v1/relationships/'+vid, '/v1/factors/'+vid+'/studies']:
        assert public.get(url+'?profile=research').json() == baseline.get(url).json()
        assert 'SYNTHETIC_PRIVATE_SENTINEL' not in public.get(url).text
    assert public.get('/v1/research/factor-studies/'+vid).status_code == 404
    private = TestClient(create_web_app(private_journal=journal))
    assert private.get('/v1/web/meta').json()['mode'] == 'PRIVATE'
    assert private.get('/v1/web/entities/variant/'+vid).json()['results']['items'][0]['run_id'] == evidence['run_id']
    assert public.app.state.web_model.studies is None

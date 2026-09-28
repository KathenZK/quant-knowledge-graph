"""Transport tests use explicit test evidence; real-market acceptance is separate."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from quantgraph.api.research_jobs import install_research_jobs, public_results
from quantgraph.graph.research_jobs import ResearchJobRepository, LeaseLost, CapacityExceeded

REF = {'entity_type':'FactorVariant','entity_id':'test-factor','definition_revision':'a'*64}
PROFILES = {'test':dict(study_type='FACTOR_DIAGNOSTIC',entity_types=['FactorVariant'],
                        max_trials=2,max_seconds=60,capability='discovery-v1',
                        display_policy='test-rights-review',public_display=True)}


def request(key='one'):
    return dict(request_id=key,entity_refs=[REF],study_type='FACTOR_DIAGNOSTIC',
                requested_settings={'profile_id':'test'})


@pytest.fixture
def repo(tmp_path):
    return ResearchJobRepository(tmp_path/'jobs.sqlite',PROFILES)


def submit(repo, key='one'):
    return repo.submit(request(key),owner='admin',resolve_ref=lambda **ref: {'ref':ref})[0]


def test_concurrent_idempotency_and_changed_request_are_distinct(repo):
    with ThreadPoolExecutor(max_workers=12) as pool:
        values=list(pool.map(lambda _: submit(repo), range(36)))
    assert len({v['job_id'] for v in values}) == 1
    changed=request();changed['hypothesis']='different'
    with pytest.raises(ValueError,match='another request'):
        repo.submit(changed,owner='admin',resolve_ref=lambda **r:r)
    assert submit(repo,'two')['job_id'] != values[0]['job_id']


def test_concurrency_limit_and_recovery_fencing_preserve_run(repo):
    now=[100.0];repo.clock=lambda:now[0]
    original=submit(repo);submit(repo,'two')
    first=repo.claim('first',['test'],lease_seconds=5)
    assert first['job_id']==original['job_id']
    assert repo.claim('second',['test']) is None
    now[0]=106
    recovered=repo.claim('second',['test'])
    assert recovered['run_id']==first['run_id'] and recovered['attempts']==2
    with pytest.raises(LeaseLost):
        repo.finish(first['job_id'],first['lease_token'],status='FAILED')
    with pytest.raises(LeaseLost):
        repo.heartbeat(first['job_id'],first['lease_token'],stage='stale',progress=.5)
    repo.finish(recovered['job_id'],recovered['lease_token'],status='BLOCKED',error={'code':'TEST'})
    assert repo.get(recovered['job_id'])['status']=='BLOCKED'


def test_cancel_queued_and_running_jobs(repo):
    one=submit(repo);two=submit(repo,'two')
    assert repo.cancel(two['job_id'])['status']=='CANCELLED'
    active=repo.claim('worker',['test'])
    assert active['job_id']==one['job_id']
    assert repo.cancel(one['job_id'])['cancel_requested']==1
    assert repo.heartbeat(one['job_id'],active['lease_token'],stage='stop',progress=.1)
    repo.finish(one['job_id'],active['lease_token'],status='FAILED')
    assert repo.get(one['job_id'])['status']=='CANCELLED'


def test_budget_and_untrusted_execution_settings(tmp_path):
    repo=ResearchJobRepository(tmp_path/'jobs.sqlite',PROFILES,daily_trial_budget=2)
    submit(repo)
    with pytest.raises(CapacityExceeded):submit(repo,'two')
    for field in ('shell','python','manifest','path','live_ready'):
        bad=request();bad['requested_settings'][field]='untrusted'
        with pytest.raises(ValueError,match='server controlled'):
            repo.submit(bad,owner='admin',resolve_ref=lambda **r:r)


def test_definition_snapshot_and_profile_are_pinned(repo):
    def stale(**ref):raise ValueError('revision mismatch')
    with pytest.raises(ValueError,match='revision'):
        repo.submit(request(),owner='admin',resolve_ref=stale)
    job=submit(repo)
    repo.profiles=deepcopy(PROFILES);repo.profiles['test']['max_trials']=3
    assert repo.claim('worker',['test']) is None
    assert repo.get(job['job_id'])['status']=='BLOCKED'


def result(ref):
    value=json.loads((Path(__file__).parents[1]/'contracts/factor-study/v1/fixtures/factor-study-result.json').read_text())
    value['mapping']['identity']['factor_variant_id']=ref['entity_id']
    value['mapping']['identity']['definition_revision']=ref['definition_revision']
    value['study_metadata']=dict(entity_refs=[ref],study_type='FACTOR_DIAGNOSTIC',
        study_kind='EXPLORATORY_ANALYSIS',provenance={},limitations=['Explicit test data; not market acceptance'],
        conclusion_level='INCONCLUSIVE',lineage=[],display_policy='test-rights-review',
        public_summary={'metrics':{'ic':None,'forbidden_path':'/secret/path'},
                        'sample':{'real_market_data':False},'artifact_uri':'/secret/file'})
    return value


def test_public_results_revision_visibility_and_server_rights(repo):
    job=submit(repo);active=repo.claim('worker',['test'])
    evidence=result(REF)
    repo.finish(job['job_id'],active['lease_token'],status='PARTIAL',results=[evidence])
    items=public_results(repo,REF,lambda _:True)
    assert len(items)==1 and items[0]['promotion_allowed'] is False
    assert '/secret' not in json.dumps(items)
    with pytest.raises(KeyError):public_results(repo,REF,lambda _:False)
    assert public_results(repo,{**REF,'definition_revision':'b'*64},lambda _:True)==[]
    repo.profiles=deepcopy(PROFILES);repo.profiles['test']['public_display']=False
    assert public_results(repo,REF,lambda _:True)==[]


def test_result_wrong_definition_and_missing_metadata_rejected(repo):
    job=submit(repo);active=repo.claim('worker',['test'])
    for bad in (result({**REF,'definition_revision':'b'*64}), {**result(REF),'study_metadata':None}):
        with pytest.raises(ValueError):repo.finish(job['job_id'],active['lease_token'],status='PARTIAL',results=[bad])


def test_api_auth_idempotency_worker_state_and_cancel(repo):
    app=FastAPI();keys={'admin':dict(token='test-token',scopes=['research:submit'])}
    install_research_jobs(app,repo,resolve_ref=lambda **r:r,can_view=lambda _:True,keys=keys)
    client=TestClient(app);headers={'Authorization':'Bearer test-token'}
    assert client.post('/v1/research/jobs',json=request()).status_code==401
    response=client.post('/v1/research/jobs',json=request(),headers=headers)
    assert response.status_code==202,response.text
    job=response.json();assert job['status']=='QUEUED' and not job['worker_available']
    assert client.post('/v1/research/jobs',json=request(),headers=headers).json()['duplicate']
    endpoint='/v1/research/jobs/'+job['job_id']
    assert client.get(endpoint).status_code==401
    repo.announce('live',['test'])
    assert client.get(endpoint,headers=headers).json()['worker_available']
    assert client.post(endpoint+'/cancel',headers=headers).json()['status']=='CANCELLED'


def test_cookie_auth_injection(repo):
    def principal():return {'id':'cookie-session-admin'}
    app=FastAPI();install_research_jobs(app,repo,resolve_ref=lambda **r:r,
                                      can_view=lambda _:True,auth_dependency=principal)
    assert TestClient(app).post('/v1/research/jobs',json=request()).status_code==202

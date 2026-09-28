"""Synthetic isolated trust contracts: no production evidence is written."""
import copy
import hashlib
import json
import pytest
from test_evidence_v4 import current_sample
from quantgraph.graph.research_gate import evaluate
from quantgraph.models.market import MarketDatasetTrustAssessment, canonical_sha256


def core_sample(tmp_path):
    repo,row,d=current_sample(tmp_path)
    b=d['dataset_binding'];c=json.loads(b['contract_json'])
    c['data_requirements']['dataset_profile']='TRUSTED_OHLCV_CORE_V1'
    d['derived_data_requirement']=copy.deepcopy(c['data_requirements'])
    b['contract_json']=json.dumps(c);b['contract_sha256']=hashlib.sha256(b['contract_json'].encode()).hexdigest()
    return repo,row,d


def assessment(d):
    b=d['dataset_binding']
    return dict(schema_version='market-dataset-trust-v1',dataset_profile='TRUSTED_OHLCV_CORE_V1',
        contract_sha256=b['contract_sha256'],dataset_sha256=d['data_requirement']['dataset_hash'],
        rights_sha256=b['rights_sha256'],raw_dataset_sha256='a'*64,
        **{k:'PASS' for k in ('source_identity','rights','coverage','schema_status','calendar','integrity','hashes','finality','provenance')},
        page_count=2,assessment_code_sha256='b'*64,assessed_at='2026-01-01T00:00:00Z',status='TRUSTED',limitations=['Unit fixture only'])


def test_core_profile_requires_independent_trust_not_just_coverage(tmp_path):
    _,row,d=core_sample(tmp_path)
    result=evaluate(row,d)
    assert not result['eligible'] and 'DATASET_TRUST_UNVERIFIED' in result['blocking_reasons']
    t=MarketDatasetTrustAssessment.model_validate(assessment(d)).model_dump(mode='json')
    d['dataset_binding'].update(trust_assessment=t,trust_assessment_sha256=canonical_sha256(t))
    assert evaluate(row,d)['eligible']
    d['dataset_binding']['trust_assessment']['finality']='UNKNOWN'
    with pytest.raises(ValueError,match='Trust status'):evaluate(row,d)


@pytest.mark.parametrize('check',['source_identity','rights','coverage','schema_status','calendar','integrity','hashes','finality','provenance'])
def test_each_trust_dimension_can_independently_block(tmp_path,check):
    _,row,d=core_sample(tmp_path);t=assessment(d)
    t[check]='UNKNOWN';t['status']='DIAGNOSTIC_ONLY'
    t=MarketDatasetTrustAssessment.model_validate(t).model_dump(mode='json')
    d['dataset_binding'].update(acceptance_status='raw_unaccepted',trust_assessment=t,trust_assessment_sha256=canonical_sha256(t))
    assert not evaluate(row,d)['eligible']


@pytest.mark.parametrize('field',['dataset_sha256','contract_sha256','rights_sha256'])
def test_trust_hash_cannot_bind_another_dataset_or_contract(tmp_path,field):
    _,row,d=core_sample(tmp_path);t=assessment(d);t[field]='f'*64
    t=MarketDatasetTrustAssessment.model_validate(t).model_dump(mode='json')
    d['dataset_binding'].update(trust_assessment=t,trust_assessment_sha256=canonical_sha256(t))
    with pytest.raises(ValueError,match='mismatch'):evaluate(row,d)


def test_core_trust_survives_append_only_review_and_gate_reload(tmp_path):
    repo,row,d=core_sample(tmp_path)
    t=MarketDatasetTrustAssessment.model_validate(assessment(d)).model_dump(mode='json')
    d['dataset_binding'].update(trust_assessment=t,trust_assessment_sha256=canonical_sha256(t))
    receipt=repo.review_record(d)
    current=repo.variants()[0]
    assert receipt['promotion_allowed'] is False
    assert current['candidate_gate']['eligible']
    assert current['reviewed_evidence']['dataset_binding']['trust_assessment']==t
    bad=copy.deepcopy(d);bad['dataset_binding']['trust_assessment_sha256']='0'*64
    with pytest.raises(ValueError,match='digest mismatch'):repo.review_record(bad)

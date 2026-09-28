import copy
import pytest
from quantgraph.models.evidence import EvidenceEnrichment
from quantgraph.graph.research_gate_v3 import evaluate  # historical gate compatibility
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from test_ingestion_lifecycle import ingest, payload


def decision(row, semantic_hash='a'*64):
    ref={'uri':'fixture:pinned','sha256':'a'*64}
    fact={'value':'fixture explicit value','basis':'RESEARCH_ASSUMPTION','rationale':'Test contract; never real research','evidence':ref}
    execution={k:copy.deepcopy(fact) for k in ('signal_timing','execution_timing','execution_price','rebalance_frequency',
      'holding_period','position_rule','cash_rule','fallback_rule','long_short','leverage','slippage_model',
      'price_adjustment','missing_data_policy','indicator_semantics')}
    execution.update(transaction_cost_model={'fee_bps':10,'slippage_bps':4,'basis':'RESEARCH_ASSUMPTION','description':'fixture'},
      closed_bar_only=True,accepted_research_assumptions=True,artifact=ref)
    rights=[{'scope':scope,'research_use_allowed':True,'research_use_scope':'PRIVATE_INTERNAL_RESEARCH',
      'commercial_use_allowed':None,'redistribution_allowed':False,'derivative_allowed':True,'attribution_required':False,
      'attribution':None,'license_source':'fixture:license','license_checked_at':'2026-01-01T00:00:00Z',
      'license_confidence':'HIGH','artifact':ref,'rationale':'Test only'} for scope in ('SOURCE_TEXT','IMPLEMENTATION_CODE','MARKET_DATA')]
    return {'schema_version':'evidence-enrichment-v3','record_id':row['variant']['source_native_id'],
      'semantic_record_hash':semantic_hash,'reviewed_by':'fixture','source':{'source_type':'OPEN_SOURCE_IMPLEMENTATION',
      'source_evidence_level':'PRIMARY','source_support_type':'IMPLEMENTATION_EXAMPLE','url':row['variant']['source_url'],
      'version':'fixture1','artifact':ref,'supported_rule_components':dict(indicator='fixture',entry='fixture',exit='fixture'),
      'unsupported_rule_components':{},'attributed_author':'fixture','checked_at':'2026-01-01T00:00:00Z'},
      'provenance_type':'SOURCE_IMPLEMENTATION','parent_record_ids':[],'rights':rights,'use_context':'PRIVATE_INTERNAL_RESEARCH',
      'execution':execution,'data_requirement':{'data_types':['OHLCV'],'symbols':['SPY','BIL'],'required_fields':['open','close'],
       'frequency':'1d','data_availability_status':'VERIFIED_AVAILABLE','data_source':'fixture','exchange':'fixture',
       'dataset_version':'fixture','downloaded_at':'2026-01-01T00:00:00Z','adjustment_method':'fixture','timezone':'UTC',
       'calendar':'fixture','start_date':'2020-01-01','end_date':'2026-01-01','dataset_hash':'b'*64,'raw_data_hashes':['c'*64],
       'real_market_data':True,'quality_status':'PASS','evidence':ref},'rule_review_status':'VERIFIED','rule_evidence':ref,
      'dedup_status':'INDEPENDENT_TEMPLATE','warnings':[]}


def sample(tmp_path):
    repo=SQLiteIngestionRepository(tmp_path/'q.sqlite');ingest(repo,payload());row=repo.variants()[0]
    with repo.connect() as con:h=con.execute('SELECT semantic_record_hash FROM revision_semantics_v2').fetchone()[0]
    return repo,row,decision(row,h)


def test_v3_review_is_bound_and_explicit_assumptions_do_not_grant_commercial_rights(tmp_path):
    repo,row,d=sample(tmp_path);repo.review_record(d)
    got=repo.variants()[0]
    assert got['candidate_gate']['status']=='REVIEW_REQUIRED'
    assert 'V4_REVIEW_REQUIRED' in got['candidate_gate']['blockers']
    assert got['variant']['commercial_use']=='REVIEW_REQUIRED'
    assert got['reviewed_evidence']['source']['indicator_author_is_strategy_author'] is False
    changed=payload();changed['records'][0]['raw_rule']+=' 未明确规则';ingest(repo,changed)
    assert repo.variants()[0]['candidate_gate']['status']=='REVIEW_REQUIRED'
    with pytest.raises(ValueError,match='current semantic'):repo.review_record(d)


@pytest.mark.parametrize(('key','value','expected'),[
 ('source_support_type','INDICATOR_DEFINITION','REVIEW_REQUIRED'),
 ('source_evidence_level','UNKNOWN','REVIEW_REQUIRED'),
])
def test_indicator_page_cannot_support_a_complete_strategy(tmp_path,key,value,expected):
    _,row,d=sample(tmp_path);d['source'][key]=value
    assert evaluate(row,d)['status']==expected


def test_independent_rights_data_and_assumption_gates(tmp_path):
    _,row,d=sample(tmp_path)
    for i in range(3):
        bad=copy.deepcopy(d);bad['rights'][i]['research_use_allowed']=None
        assert not evaluate(row,bad)['eligible']
    bad=copy.deepcopy(d);bad['rights'][2]['research_use_allowed']=False
    assert evaluate(row,bad)['status']=='BLOCKED'
    bad=copy.deepcopy(d);bad['rights'][2]['research_use_scope']='PERSONAL_NONCOMMERCIAL'
    assert not evaluate(row,bad)['eligible']
    bad=copy.deepcopy(d);bad['execution']['accepted_research_assumptions']=False
    assert evaluate(row,bad)['status']=='CONDITIONALLY_ELIGIBLE'
    bad=copy.deepcopy(d);bad['data_requirement']['real_market_data']=False
    assert not evaluate(row,bad)['eligible']
    bad=copy.deepcopy(d);bad['data_requirement']['quality_status']='FAIL'
    assert evaluate(row,bad)['status']=='BLOCKED'


def test_schema_rejects_source_facts_without_bytes_and_unknown_grants(tmp_path):
    _,_,d=sample(tmp_path)
    d['execution']['signal_timing'].update(basis='SOURCE_DEFINED',evidence=None)
    with pytest.raises(ValueError):EvidenceEnrichment.model_validate(d)


def formal_payload(row,d):
    """In-memory validation fixture, never written to the production journal."""
    window={k:0.0 for k in ('total_return','cagr','sharpe','sortino','calmar','max_drawdown','volatility','turnover','win_rate','exposure')}
    window['observations']=40
    results={'in_sample':window,'oos':copy.deepcopy(window),'costs':{},'turnover':0.,'robustness':{},
             'deflated_sharpe':{'value':None,'reason':'unit test'},'pbo':{'value':None,'reason':'unit test'}}
    return dict(schema_version='2.0',research_run_id='in-memory-contract-check',experiment_family_id='qg-unit',
      source_strategy_ids=[row['variant']['strategy_variant_id']],strategy_concept_id=row['variant']['strategy_concept_id'],
      strategy_template_id=row['variant']['strategy_template_id'],artifact_uri='local:validation',artifact_sha256='1'*64,
      contract_sha256='2'*64,code_sha256='3'*64,config_sha256='4'*64,candidate_snapshot_sha256='5'*64,
      real_market_data=True,data_provenance=d['data_requirement'],trial_count=2,parameter_grid=[{'n':7},{'n':8}],
      results=results,evidence_kind='REAL_MARKET_BACKTEST',research_status='INCONCLUSIVE',limitations=['contract unit test'])


def nonfixture_labels(d):
    # Model guard against obvious test labels is tested separately. This bypass
    # exists only within an isolated pytest tmp_path, never a market-data claim.
    d=copy.deepcopy(d)
    d['data_requirement'].update(data_source='unit-provider',exchange='unit-venue',dataset_version='unit-version',
                                evidence={'uri':'local:unit-audit','sha256':'9'*64})
    return d


def test_real_evidence_rechecks_admission_lineage_data_and_idempotency(tmp_path):
    from fastapi.testclient import TestClient
    from quantgraph.api.app import create_app
    repo,row,d=sample(tmp_path);d=nonfixture_labels(d)
    body=formal_payload(row,d)
    keys={'unit':{'token':'unit-token-for-isolated-tests-000000','scopes':['research:write','research:read'],'requests_per_minute':500}}
    client=TestClient(create_app(ingestion_repository=repo,ingestion_keys=keys))
    headers={'Authorization':'Bearer '+keys['unit']['token']}
    assert client.post('/v1/research/evidence',json=body).status_code==401
    assert client.post('/v1/research/evidence',json=body,headers=headers).status_code==409
    repo.review_record(d)
    for field in ('strategy_template_id','strategy_concept_id'):
        bad=copy.deepcopy(body);bad[field]='wrong'
        assert client.post('/v1/research/evidence',json=bad,headers=headers).status_code==409
    bad=copy.deepcopy(body);bad['data_provenance']['exchange']='wrong'
    assert client.post('/v1/research/evidence',json=bad,headers=headers).status_code==409
    reply=client.post('/v1/research/evidence',json=body,headers=headers)
    assert reply.status_code==409  # V3 lacks mandatory V4 dataset/rights bindings
    assert client.get('/v1/research/evidence/'+row['variant']['strategy_variant_id'],headers=headers).json()['items']==[]
    bad=copy.deepcopy(body);bad['results']['oos']['sharpe']=1
    assert client.post('/v1/research/evidence',json=bad,headers=headers).status_code==409
    assert client.get('/v1/research/assessments',headers=headers).status_code==200


def test_market_model_rejects_synthetic_partial_or_unpinned_results(tmp_path):
    from quantgraph.models.evidence import MarketResearchEvidence
    _,row,d=sample(tmp_path);body=formal_payload(row,d)
    with pytest.raises(ValueError,match='Synthetic/fixture'):MarketResearchEvidence.model_validate(body)
    body=formal_payload(row,nonfixture_labels(d))
    for path,value in [('real_market_data',False),('trial_count',3)]:
        bad=copy.deepcopy(body);bad[path]=value
        with pytest.raises(ValueError):MarketResearchEvidence.model_validate(bad)
    for metric in [float('nan'),float('inf')]:
        bad=copy.deepcopy(body);bad['results']['oos']['sharpe']=metric
        with pytest.raises(ValueError):MarketResearchEvidence.model_validate(bad)
    bad=copy.deepcopy(body);bad['results']['in_sample']={}
    with pytest.raises(ValueError,match='Completed IS/OOS'):MarketResearchEvidence.model_validate(bad)


def test_generated_evidence_schemas_match_models():
    import json
    from pathlib import Path
    from quantgraph.models import evidence
    for name in ('SourceEvidence','RightsEvidence','ExecutionContract','DataRequirement','EvidenceEnrichment','ResearchCandidateAssessment','MarketResearchEvidence'):
        path=Path(__file__).resolve().parents[1]/'models/schemas'/(name+'.schema.json')
        assert json.loads(path.read_text())==getattr(evidence,name).model_json_schema()


def test_cross_asset_condition_requires_signal_asset_data(tmp_path):
    repo=SQLiteIngestionRepository(tmp_path/'cross.sqlite');raw=payload()
    raw['records'][0]['raw_rule']='日频：若 QQQ21日实现波动×√252<0.12 → 满仓 SPY，否则 BIL。'
    ingest(repo,raw);row=repo.variants()[0];d=decision(row)
    assert 'DATA_AVAILABILITY_UNCONFIRMED' in evaluate(row,d)['blocking_reasons']
    d['data_requirement']['symbols'].append('QQQ')
    assert evaluate(row,d)['status']=='ELIGIBLE'

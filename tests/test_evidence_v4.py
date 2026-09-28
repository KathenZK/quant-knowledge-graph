"""All data here are synthetic isolation fixtures, never production evidence."""
import copy
import json
import pytest
from quantgraph.graph.research_gate import evaluate
from quantgraph.graph.data_requirements import derive
from quantgraph.models.market import canonical_sha256, ReviewedRightsEvidence
from quantgraph.models.evidence_v4 import EvidenceEnrichmentV4
from test_evidence_v3 import sample, formal_payload, nonfixture_labels


def current_sample(tmp_path):
    repo,row,d=sample(tmp_path)
    # Source test fixture is explicitly replaced by one supported DSL record.
    from test_ingestion_lifecycle import payload,ingest
    raw=payload();record=raw['records'][0]
    ast=dict(type='long_only_signal',signal='PRICE_SMA',asset='BTC/EUR',schedule='daily_eod',parameters=[50],
      comparison='gt_else_cash',allocation='all_equity_net_of_costs',cash='EUR_ZERO_INTEREST',initial_position='cash',
      indicator_semantics='SMA including latest closed close',entry='close>SMA',exit='close<=SMA',rebalance='signal_change_only',
      stop_loss_fraction=None,take_profit_fraction=None,parent_record_id='unit-parent',derivation='unit only')
    record['raw_rule']='QG-DSL/1\n'+json.dumps(ast)
    ingest(repo,raw);row=repo.variants()[0]
    with repo.connect() as c:d['semantic_record_hash']=c.execute('select semantic_record_hash from revision_semantics_v2 order by revision desc limit 1').fetchone()[0]
    d=nonfixture_labels(d);d['schema_version']='evidence-enrichment-v4'
    for f in d['execution'].values():
        if isinstance(f,dict) and f.get('basis')=='RESEARCH_ASSUMPTION':
            f.update(assumption_reason='Isolated test fixture',assumption_version='unit-v4')
    d['execution']['execution_price']['value']='OPEN'
    d['execution']['price_adjustment']['value']='UNADJUSTED'
    r=derive(row['variant']['rule_ast'],d['execution'],calendar='CRYPTO_24_7')
    # Model dump expands nullable annotations; freeze derivation after expansion.
    from quantgraph.models.evidence import ExecutionContract
    d['execution']=ExecutionContract.model_validate(d['execution']).model_dump(mode='json')
    r=derive(row['variant']['rule_ast'],d['execution'],calendar='CRYPTO_24_7')
    d['derived_data_requirement']=r
    d['data_requirement'].update(symbols=r['symbols'],required_fields=r['required_fields'],frequency=r['frequency'],
      adjustment_method=r['adjustment'],calendar=r['calendar'])
    rights=dict(schema_version='reviewed-rights-v4',rights_id='unit-rights',provider='unit-venue',source='unit-provider',scope='MARKET_DATA',
      research_use_allowed=True,research_use_scope='PRIVATE_INTERNAL_RESEARCH',commercial_use_allowed=None,redistribution_allowed=False,
      derivative_allowed=True,attribution_required=False,attribution=None,license_source='unit-only',license_url='https://example.org/unit',
      reviewed_at='2026-01-01T00:00:00Z',reviewed_by='unit',confidence='HIGH',status='VERIFIED',evidence_path='unit',evidence_sha256='a'*64,rationale='unit')
    rights=ReviewedRightsEvidence.model_validate(rights).model_dump(mode='json')
    coverage=dict(requested_start='2020-01-01T00:00:00+00:00',requested_end='2026-01-01T00:00:00+00:00',actual_start='2020-01-01T00:00:00+00:00',
      actual_end='2025-12-31T00:00:00+00:00',expected_count=2192,actual_count=2192,gap_count=0,duplicate_count=0,unexpected_count=0,ordered=True,
      calendar='CRYPTO_24_7',calendar_version='crypto-utc-grid-v1',coverage_status='VERIFIED',coverage_reason='unit exact match')
    contract=dict(schema_version='research-contract-v4',frozen_at='2026-01-01T00:00:00Z',
      strategy_concept_id=row['variant']['strategy_concept_id'],strategy_template_id=row['variant']['strategy_template_id'],strategy_variant_id=row['variant']['strategy_variant_id'],experiment_family_id='qg-unit',
      parameters=[50],parameter_grid=[[40],[50]],trial_count=2,symbols=['BTC/EUR'],universe='FIXED_SINGLE_ASSET',provider='unit-venue',source='unit-provider',market_type='spot',frequency='1d',
      requested_start='2020-01-01T00:00:00Z',requested_end='2026-01-01T00:00:00Z',is_start='2020-02-01T00:00:00Z',is_end='2024-01-01T00:00:00Z',oos_start='2024-01-01T00:00:00Z',oos_end='2026-01-01T00:00:00Z',
      signal_timing='CLOSED_BAR',execution_timing='NEXT_BAR_OPEN',execution_price='OPEN',rebalance='SIGNAL_CHANGE_ONLY',holding_period='UNTIL_EXIT',fees_bps=10,slippage_bps=4,cost_model='unit',
      execution_contract=d['execution'],rule_ast=row['variant']['rule_ast'],data_requirements=r,use_context='PRIVATE_INTERNAL_RESEARCH',engine_config={},prior_trial_count=0,holdout_status='UNOBSERVED_AT_FREEZE',limitations=['unit'])
    contract_json=json.dumps(contract)
    import hashlib
    d['dataset_binding']=dict(contract_json=contract_json,contract_sha256=hashlib.sha256(contract_json.encode()).hexdigest(),dataset_manifest_sha256='6'*64,rights_id=rights['rights_id'],rights_sha256=canonical_sha256(rights),
      rights_evidence=rights,coverage=coverage,acceptance_status='TRUSTED',missing_native_fields=[])
    return repo,row,EvidenceEnrichmentV4.model_validate(d).model_dump(mode='json')


def test_current_gate_requires_independent_coverage_rights_and_assumption_version(tmp_path):
    _,row,d=current_sample(tmp_path)
    assert evaluate(row,d)['status']=='ELIGIBLE'
    assert evaluate(row,d)['source_support_status']=='VERIFIED'
    for mutate in ('coverage','schema','rights','derived'):
        bad=copy.deepcopy(d)
        if mutate=='coverage':bad['dataset_binding']['coverage']['coverage_status']='PARTIAL'
        if mutate=='schema':bad['dataset_binding']['missing_native_fields']=['trade_count']
        if mutate=='rights':
            r=bad['dataset_binding']['rights_evidence'];r['research_use_allowed']=None
            bad['dataset_binding']['rights_sha256']=canonical_sha256(r)
        if mutate=='derived':
            bad['derived_data_requirement']['derivation_sha256']='f'*64
            with pytest.raises(ValueError,match='frozen research contract'):evaluate(row,bad)
            continue
        assert not evaluate(row,bad)['eligible']
    d['execution']['holding_period']['assumption_version']=None
    with pytest.raises(ValueError,match='Version and reason'):EvidenceEnrichmentV4.model_validate(d)


def test_ast_and_execution_requirements_are_not_open_close_constant(tmp_path):
    _,row,d=current_sample(tmp_path)
    ast=row['variant']['rule_ast'];exec=d['execution']
    assert derive(ast,exec,calendar='CRYPTO_24_7')['required_fields']==['close','open']
    exec['execution_price']['value']='CLOSE'
    assert derive(ast,exec,calendar='CRYPTO_24_7')['required_fields']==['close']
    ast=copy.deepcopy(ast);ast.update(signal='EMA_CROSSOVER',parameters=[8,21],stop_loss_fraction=.2,take_profit_fraction=.5)
    assert derive(ast,exec,calendar='CRYPTO_24_7')['required_fields']==['close','high','low','open','volume']
    with pytest.raises(ValueError,match='Unresolved'):derive({'type':'indicator','name':'UNSUPPORTED'},exec,calendar='CRYPTO_24_7')


def test_v4_api_writeback_checks_all_pins_and_reads_full_chain(tmp_path):
    from fastapi.testclient import TestClient
    from quantgraph.api.app import create_app
    repo,row,d=current_sample(tmp_path);repo.review_record(d)
    body=formal_payload(row,d)
    b=d['dataset_binding']
    body.update(contract_sha256=b['contract_sha256'],config_sha256=canonical_sha256({}),parameter_grid=[[40],[50]],schema_version='3.0',strategy_variant_id=row['variant']['strategy_variant_id'],dataset_sha256=d['data_requirement']['dataset_hash'],
      dataset_manifest_sha256=b['dataset_manifest_sha256'],rights_id=b['rights_id'],rights_sha256=b['rights_sha256'],
      exposure_definition='POST_OPEN_POSITION_PROXY_WITH_INTRABAR_BOUNDS')
    keys={'unit':{'token':'unit-token-for-isolated-tests-000000','scopes':['research:write','research:read'],'requests_per_minute':500}}
    client=TestClient(create_app(ingestion_repository=repo,ingestion_keys=keys));headers={'Authorization':'Bearer '+keys['unit']['token']}
    for field in ('contract_sha256','dataset_manifest_sha256','rights_sha256','rights_id','strategy_template_id','strategy_concept_id'):
        bad=copy.deepcopy(body);bad[field]='9'*64
        assert client.post('/v1/research/evidence',json=bad,headers=headers).status_code==409
    bad=copy.deepcopy(body);bad['parameter_grid']=[[49],[50]]
    assert client.post('/v1/research/evidence',json=bad,headers=headers).status_code==409
    reply=client.post('/v1/research/evidence',json=body,headers=headers)
    assert reply.status_code==200,reply.text
    assert reply.json()['promotion_triggered'] is False
    assert client.post('/v1/research/evidence',json=body,headers=headers).json()['duplicate']
    changed=copy.deepcopy(body);changed['results']['oos']['sharpe']=1
    assert client.post('/v1/research/evidence',json=changed,headers=headers).status_code==409
    got=client.get('/v1/research/evidence/'+row['variant']['strategy_variant_id'],headers=headers).json()['items'][0]
    assert got['dataset_manifest_sha256']==body['dataset_manifest_sha256']
    chain=client.get('/v1/research/chain/'+row['variant']['strategy_variant_id'],headers=headers).json()
    assert chain['strategy']['reviewed_evidence']['dataset_binding']['rights_id']==body['rights_id']
    assert chain['backtest_results'][0]['research_run_id']==body['research_run_id']
    assert len(chain['provenance'])>=1
    assert repo.ingest_stats()['real_market_backtest_count']==1  # isolated test journal only


def test_current_schema_exports_match_models():
    from pathlib import Path
    import importlib.util
    path=Path(__file__).resolve().parents[1]/'scripts/generate_v4_schemas.py'
    s=importlib.util.spec_from_file_location('schemas_v4',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    for name,_,module in m.CONTRACTS:
        assert json.loads((path.parents[1]/'models/schemas'/(name+'.schema.json')).read_text())==getattr(module,name).model_json_schema()


def test_contract_binding_preserves_exact_json_whitespace(tmp_path):
    import hashlib
    _,_,d=current_sample(tmp_path)
    b=d['dataset_binding'];b['contract_json']+='\n'
    b['contract_sha256']=hashlib.sha256(b['contract_json'].encode()).hexdigest()
    parsed=EvidenceEnrichmentV4.model_validate(d)
    assert parsed.dataset_binding.contract_json.endswith('\n')
    b['contract_json']+=' '
    with pytest.raises(ValueError,match='bytes digest mismatch'):EvidenceEnrichmentV4.model_validate(d)


def test_legacy_fetcher_rights_never_become_current_permissions(tmp_path):
    _,row,d=sample(tmp_path)
    result=evaluate(row,d)
    assert not result['eligible'] and result['rights_status']=='REVIEW_REQUIRED'


def test_false_verified_coverage_and_parameter_writeback_are_rejected(tmp_path):
    _,_,d=current_sample(tmp_path)
    d['dataset_binding']['coverage']['gap_count']=1
    with pytest.raises(ValueError,match='Inconsistent VERIFIED'):EvidenceEnrichmentV4.model_validate(d)

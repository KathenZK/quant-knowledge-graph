"""Synthetic nine-role M1266 display/acceptance tests; no Lab or historical data."""
import calendar
from copy import deepcopy
import gzip
import json

import pytest

from quantgraph.graph import lab_display_m1266 as mod
from quantgraph.graph.lab_display_projection import digest, encoded, encode_asset, project, verified_source, prepare, merge_snapshot
from test_lab_display_projection import active


def seal(root,e,b,monkeypatch,relink=True):
    """Allow intentional synthetic source changes so semantic gates can be tested."""
    pub=json.loads(b['public_scope_review'])
    selected=['original_record','original_detail','metrics','operational_rules','approved_report']
    pub['files']=[dict(path=e['artifacts'][k]['path'],bytes=len(b[k]),sha256=digest(b[k])) for k in selected]+[
        dict(path=f'research/public-strategies/M1266/extra-public-{n}.md',bytes=1,sha256=str(n)*64) for n in range(7)]
    b['public_scope_review']=encoded(pub)
    if relink:
        a=json.loads(b['coordinator_acceptance'])
        a['public_delivery']['public_review_sha256']=digest(b['public_scope_review'])
        a['receipt_cross_review']['sha256']=digest(b['receipt_evidence_review'])
        b['coordinator_acceptance']=encoded(a)
    refs=deepcopy(e['artifacts'])
    for k,body in b.items():
        refs[k].update(bytes=len(body),sha256=digest(body))
        p=root/refs[k]['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
    monkeypatch.setattr(mod,'SOURCE_LOCK',deepcopy(refs));e['artifacts']=refs


def fixture(tmp_path,monkeypatch):
    root=tmp_path/'source';root.mkdir()
    entry=dict(id=mod.ID,group='synthetic',lab_commit=mod.PIN,run_id=mod.RUN,variant_id=mod.VARIANT,
        source_contract=mod.CONTRACT,projection_profile=mod.PROFILE,manifest_kind=mod.KIND,source_inventory_kind=mod.LOCK_KIND,
        fidelity_class='ADAPTED',artifacts=deepcopy(mod.SOURCE_LOCK))
    audit=dict(accepted=False,trusted=False,OOS=False,window_OOS=False,original_runtime_equivalence=False,
        strict_reproductions=0,PIT='UNKNOWN',publication_review_status='PENDING_EXACT_ALLOWLIST_REVIEW')
    attribution=dict(derived_data_license='CC BY-NC-SA 4.0',coverage='Synthetic derived metrics only')
    metric=dict(total_return=.24,cagr=.1,max_drawdown=-.1,exposure=.3,fees_paid=8.0,initial_equity=100000.0,final_equity=124000.0,
        sharpe=None,sharpe_zero_cash=None,observations=731,annualization=365,closed_roundtrips=2,fill_count=4,monthly_count=24,
        rejected_order_count=0,start='2023-01-01',end='2024-12-31',end_exclusive='2025-01-01',status=mod.PENDING)
    fee0=dict(metric,fees_paid=0.0)
    limitation='Synthetic only: no fee0/20 or delay2 matched control.'
    metrics=dict(periods={'full':deepcopy(metric)},same_instrument_benchmark={'full':deepcopy(metric)},
        additional_native_bar_lag={'full':deepcopy(metric)},cost_sensitivity={'0':{'full':fee0},'20':{'full':deepcopy(metric)}},
        execution_class=mod.EXECUTION,implementation_fidelity=mod.FIDELITY,fee_control_limitation=limitation)
    record=dict(id=mod.ID,name='Synthetic M1266',audit=deepcopy(audit),related_results=[dict(run_id=mod.RUN,status=mod.PENDING)],
        selected_source_sha256='a'*64,source_url='https://example.org/corrected-source',coverage_history=[dict(accepted=False)])
    dates=['2023-01-01']+[f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}' for y in [2023,2024] for m in range(1,13)]
    curve=[dict(date=d,equity=1.0+n*.01,drawdown=0.0) for n,d in enumerate(dates)]
    detail=dict(id=mod.ID,run_id=mod.RUN,origin_run_id=mod.RUN,variant_id=mod.VARIANT,name='Synthetic only',family='synthetic-family',
        fidelity_class=mod.FIDELITY,execution_class=mod.EXECUTION,audit=deepcopy(audit),metrics=metrics,
        spec=dict(rule_summary='合成自撰规则摘要',selected_source_sha256='a'*64,source_url=record['source_url']),
        curve=curve,benchmark_curve=deepcopy(curve),data_attribution=attribution,
        curve_meta=dict(point_count=25,benchmark_point_count=25,source_observations=731,normalized_to_initial=100000,
            initial_anchor_date='2023-01-01',initial_anchor_phase='before first evaluation open, not Jan1 close',resolution='initial pre-open anchor plus24monthends'),
        lineage={'synthetic':'original frozen pending lineage'},limitations=['协调者验收和公开范围审查仍待完成','Synthetic only'])
    rules=dict(schema='M1266-self-authored-operational-rules/v1',id=mod.ID,run_id=mod.RUN,audit=deepcopy(audit),
        classification=mod.FIDELITY,execution_class=mod.EXECUTION,strict_reproductions=0,trusted=False,OOS=False,PIT='UNKNOWN',
        identity=dict(evaluation_rows=731,warmup_rows=100,initial_equity='100000',symbol='BTCUSDT',timeframe='UTC 1d'),
        indicators={'periods':[20,50,100]},entry={k:'Synthetic '+k for k in ['when','quantity','frozen']},
        exit={k:'Synthetic '+k for k in ['predicate','high','reset']},execution={k:'Synthetic '+k for k in ['pending','rejection']},
        benchmark=dict(new_controls=1,name='buyhold-base',sizing='q=0.9*100000/close',holding='fixed quantity; no rebalance',fee_control_limitation=limitation),
        cases=deepcopy(mod.COSTS),statistics={'basis':'Synthetic only'},
        source=dict(full_text_or_attachment_redistribution=False,selected_source_sha256='a'*64,url=record['source_url'],author_selection_warning='Exposed window'))
    summary=dict(schema='M1266-lightweight-metrics/v1',id=mod.ID,run_id=mod.RUN,audit=deepcopy(audit),classification=mod.FIDELITY,
        execution_class=mod.EXECUTION,strategy_configurations=4,new_controls=1,cases=deepcopy(mod.COSTS),metrics=deepcopy(metrics),
        fee_control_limitation=limitation,data_attribution=deepcopy(attribution))
    acc=dict(schema='coordinator-research-acceptance/v1',id=mod.ID,accepted_at_utc='2026-10-03T00:00:00Z',status=mod.ACCEPTED,
        new_strategy_configurations=4,new_original_controls=1,strict_reproductions=0,trusted=False,OOS=False,PIT='UNKNOWN',
        classification=mod.FIDELITY,execution_class=mod.EXECUTION,C0_sha256=mod.C0_SHA,root_release_sha256=mod.RELEASE_SHA,
        public_delivery={},receipt_cross_review={},recovery=dict(parent_actual_Library_saved_and_restored=True,archive_entries=292,
            root_full_archive_materialized_or_historical_replayed=False,later432entry_addendum_in_this_receipt_scope=False,new_trials_from_recovery=0),
        quality=dict(base={k:v for k,v in metric.items() if k!='status'},declared_control={k:v for k,v in metric.items() if k!='status'},interpretation='Synthetic comparison; no superiority'))
    pub=dict(C0_sha256=mod.C0_SHA,release_sha256=mod.RELEASE_SHA,reviewed_commit=mod.ORIGINAL_PIN,file_count=12,file_bytes=77633)
    evidence=dict(C0_sha256=mod.C0_SHA,root_release_sha256=mod.RELEASE_SHA,local_review_scope={k:False for k in [
        'historical_result_bytes_received','local_Library_materialization','local_original_runner_replay','market_input_bytes_read']})
    blobs={k:encoded(v) for k,v in dict(original_record=record,original_detail=detail,metrics=summary,operational_rules=rules,
        coordinator_acceptance=acc,public_scope_review=pub,receipt_evidence_review=evidence).items()}
    blobs.update(approved_report=b'Synthetic self-authored report',acceptance_note=b'Synthetic current acceptance note')
    seal(root,entry,blobs,monkeypatch)
    return root,entry,blobs


def test_typed_public_projection_preserves_original_pending_and_control(tmp_path,monkeypatch):
    root,e,b=fixture(tmp_path,monkeypatch);before=deepcopy(b);r,d=project(e,verified_source(root,e))
    assert b==before and r['audit']['accepted'] is False and d['original_publication_audit']['accepted'] is False
    assert r['coordinator_acceptance']['accepted'] is True and r['coordinator_acceptance']['trusted'] is False
    assert r['coordinator_acceptance']['root_full_archive_materialized_or_historical_replayed'] is False
    assert r['fidelity_class']=='ADAPTED' and r['research_fidelity']==mod.FIDELITY and d['execution_class']==mod.EXECUTION
    assert r['new_control_runs']==1 and r['benchmark_reference']['id']=='M1266' and not r['benchmark_reference']['matched_cost_or_delay_controls_available']
    assert d['projection_activity']==dict(new_strategy_trials=0,new_controls=0)
    assert r['original_related_results']==json.loads(b['original_record'])['related_results']
    assert '自撰操作规则摘要' in d['spec']['rule_excerpt'] and all(type(x) is str for x in d['spec']['assumptions'])
    assert d['curve_meta']['observations']==731 and d['curve_meta']['returned_points']==25
    assert d['curve']==json.loads(b['original_detail'])['curve'] and d['benchmark_curve']==json.loads(b['original_detail'])['benchmark_curve']
    assert d['curve_meta']['initial_anchor_phase']=='before first evaluation open, not Jan1 close'
    assert 'M1266自身控制' in d['metrics']['risk_match_note'] and 'no fee0/20' in d['metrics']['risk_match_note']
    assert 'current' not in d['metrics']['periods'] and d['metrics']['periods']['full']['status']==mod.PENDING
    assert d['metrics']['periods']['full']['sharpe'] is None and d['metrics']['cost_sensitivity']['0']['full']['fees_paid']==0.0
    assert 'annual_turnover' not in d['metrics']['periods']['full'] and 'catalog_fields' not in r
    manifest=r['public_display_manifest'];assert manifest==d['public_display_manifest']
    assert manifest['manifest_kind']==mod.KIND and not manifest['historical_publication_manifest'] and not manifest['self_or_output_hashes_included']
    assert digest(encoded(manifest))==d['lineage']['manifest_sha256'] and manifest['source_artifacts']==e['artifacts']
    assert 'entity_id' not in r and 'definition_revision' not in d and r['definition_revision_bound'] is False
    mod.check_output(r,d)


@pytest.mark.parametrize('field,value',[('id','M1258'),('source_contract','CATALOG_RSI5_FULLCASH_V1'),
    ('source_contract','M1347_OTHER'),('source_contract','UNKNOWN'),('projection_profile','DAILY_SAMPLED_APPROVED_DETAIL_V1'),
    ('manifest_kind','LAB_ORIGIN_RESULT_MANIFEST_NOT_GRAPH_COLLECTION'),('source_inventory_kind','C0'),('lab_commit','a'*40),
    ('fidelity_class','HYPOTHESIS'),('run_id','wrong'),('variant_id','wrong')])
def test_identity_before_source_read(tmp_path,monkeypatch,field,value):
    root,e,b=fixture(tmp_path,monkeypatch);e[field]=value
    with pytest.raises(ValueError):verified_source(root,e)


@pytest.mark.parametrize('change',['extra','missing','private_C0','traversal','cross_id','hash','bytes','url','symlink'])
def test_exact_nine_role_boundary(tmp_path,monkeypatch,change):
    root,e,b=fixture(tmp_path,monkeypatch)
    if change=='extra':e['artifacts']['unapproved']=dict(e['artifacts']['original_record'])
    elif change=='missing':del e['artifacts']['coordinator_acceptance']
    elif change=='private_C0':e['artifacts']['C0']=dict(e['artifacts']['operational_rules'])
    elif change=='symlink':
        p=root/e['artifacts']['original_record']['path'];p.unlink();target=tmp_path/'elsewhere';target.write_bytes(b['original_record']);p.symlink_to(target)
    else:
        ref=e['artifacts']['original_detail']
        if change=='traversal':ref['path']='research/public-strategies/M1266/../../private.json'
        elif change=='cross_id':ref['path']=ref['path'].replace('M1266','M1258')
        elif change=='hash':ref['sha256']='0'*64
        elif change=='bytes':ref['bytes']=float(ref['bytes'])
        else:ref['url']=ref['url'].replace(mod.PIN,'a'*40)
    with pytest.raises(ValueError):verified_source(root,e)


@pytest.mark.parametrize('role,path,value',[
 ('coordinator_acceptance',['status'],'PENDING'),('coordinator_acceptance',['C0_sha256'],'a'*64),
 ('coordinator_acceptance',['new_strategy_configurations'],4.0),('coordinator_acceptance',['new_original_controls'],True),
 ('coordinator_acceptance',['strict_reproductions'],False),('coordinator_acceptance',['trusted'],True),
 ('coordinator_acceptance',['OOS'],True),('coordinator_acceptance',['PIT'],'PASS'),
 ('coordinator_acceptance',['recovery','archive_entries'],432),
 ('coordinator_acceptance',['recovery','root_full_archive_materialized_or_historical_replayed'],True),
 ('coordinator_acceptance',['recovery','later432entry_addendum_in_this_receipt_scope'],True),
 ('receipt_evidence_review',['local_review_scope','historical_result_bytes_received'],True),
 ('public_scope_review',['reviewed_commit'],'a'*40),('public_scope_review',['file_count'],12.0),
 ('operational_rules',['benchmark','new_controls'],True),('operational_rules',['benchmark','sizing'],'M1258 100% fee-inclusive cash'),
 ('operational_rules',['indicators','periods'],[20,50,200]),('operational_rules',['identity','warmup_rows'],731),
 ('operational_rules',['source','full_text_or_attachment_redistribution'],True),
 ('original_record',['definition_revision'],'invented'),('original_detail',['entity_id'],'invented'),
 ('original_detail',['curve_meta','initial_anchor_phase'],'Jan1 close'),('original_detail',['curve_meta','source_observations'],25),
 ('original_detail',['curve_meta','point_count'],25.0),('original_detail',['curve',0,'equity'],True),
 ('original_detail',['benchmark_curve',0,'equity'],100000.0),('original_detail',['curve',1,'date'],'2023-01-30'),
 ('original_detail',['spec','rule_summary'],'libfile_privatefake'),('original_detail',['spec','rule_summary'],'api_key=synthetic-secret'),
 ('original_detail',['spec','rule_summary'],'/workspace/private/notes'),
 ('original_record',['audit','accepted'],True),('original_record',['audit','strict_reproductions'],False),
])
def test_full_synthetic_repin_does_not_bypass_semantic_boundary(tmp_path,monkeypatch,role,path,value):
    root,e,b=fixture(tmp_path,monkeypatch);v=json.loads(b[role]);node=v
    for key in path[:-1]:node=node[key]
    node[path[-1]]=value;b[role]=encoded(v);seal(root,e,b,monkeypatch)
    with pytest.raises(ValueError):project(e,verified_source(root,e))


@pytest.mark.parametrize('role,key',[('public_delivery','public_review_sha256'),('receipt_cross_review','sha256')])
def test_acceptance_cannot_detach_from_received_reviews(tmp_path,monkeypatch,role,key):
    root,e,b=fixture(tmp_path,monkeypatch);a=json.loads(b['coordinator_acceptance']);a[role][key]='a'*64;b['coordinator_acceptance']=encoded(a)
    seal(root,e,b,monkeypatch,relink=False)
    with pytest.raises(ValueError,match='both exact'):project(e,verified_source(root,e))


@pytest.mark.parametrize('route',['periods','same_instrument_benchmark','additional_native_bar_lag','0','20'])
@pytest.mark.parametrize('field',['cagr','max_drawdown','sharpe','final_equity','fees_paid','observations'])
@pytest.mark.parametrize('bad',['0.1',True])
def test_numeric_types_after_consistent_repin(tmp_path,monkeypatch,route,field,bad):
    root,e,b=fixture(tmp_path,monkeypatch);d,m,a=(json.loads(b[k]) for k in ['original_detail','metrics','coordinator_acceptance'])
    group=d['metrics']['cost_sensitivity'][route] if route in ['0','20'] else d['metrics'][route]
    group['full'][field]=bad
    if field=='sharpe':group['full']['sharpe_zero_cash']=bad
    m['metrics']=deepcopy(d['metrics'])
    for role,key in [('base','periods'),('declared_control','same_instrument_benchmark')]:a['quality'][role]={k:v for k,v in d['metrics'][key]['full'].items() if k!='status'}
    b.update(original_detail=encoded(d),metrics=encoded(m),coordinator_acceptance=encoded(a));seal(root,e,b,monkeypatch)
    with pytest.raises(ValueError):project(e,verified_source(root,e))


def test_offline_manifest_determinism_and_no_native_activation(tmp_path,monkeypatch):
    root,e,b=fixture(tmp_path,monkeypatch);registry=dict(schema_version='quantgraph-approved-lab-display-sources/v1',records=[e])
    paths=[tmp_path/'a',tmp_path/'b']
    for p in paths:
        status=prepare({'synthetic':root},p,registry=registry)
        assert status['new_execution_trials']==0 and not status['native_corpus_imported'] and not status['deployed']
        assert status['active_merge_status']=='BLOCKED_CURRENT_ACTIVE_ROOT_ENTITY_REVISION_REQUIRED'
        assert not (p/'site-sync-candidate.json').exists()
    assert {p.relative_to(paths[0]):p.read_bytes() for p in paths[0].rglob('*') if p.is_file()}=={
        p.relative_to(paths[1]):p.read_bytes() for p in paths[1].rglob('*') if p.is_file()}
    with pytest.raises(ValueError):prepare({'synthetic':root},paths[0],registry=registry)


def test_existing_record_notes_and_old_results_preserved(tmp_path,monkeypatch):
    root,e,b=fixture(tmp_path,monkeypatch);r,d=project(e,verified_source(root,e));snap,receipt,shard=active(tmp_path,r,d)
    assets,envelope=merge_snapshot([r],[d],snap,digest(encoded(receipt)),receipt['active_batch'])
    row=json.loads(gzip.decompress(assets[shard]))[mod.ID]
    assert row['audit']=={'retained':'original'} and row['note_marker']=='unchanged' and len(row['related_results'])==3
    assert set(envelope['results'][0])=={'origin_run_id','variant_id','manifest_sha256','record_id','detail_path','detail_sha256'}
    for path,body in assets.items():
        p=snap/'assets'/path[1:];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body);receipt['files'][path]=dict(bytes=len(body),sha256=digest(body))
    (snap/'active-snapshot.json').write_bytes(encoded(receipt))
    assert merge_snapshot([r],[d],snap,digest(encoded(receipt)),receipt['active_batch'])[0]=={}
    d['name']='changed same identity'
    with pytest.raises(ValueError,match='different bytes'):merge_snapshot([r],[d],snap,digest(encoded(receipt)),receipt['active_batch'])


@pytest.mark.parametrize('change',['manifest_cycle','protocol_kind','wrong_contract','run_kind_conflict','revision','orphan'])
def test_output_type_immutability_and_active_binding(tmp_path,monkeypatch,change):
    root,e,b=fixture(tmp_path,monkeypatch);r,d=project(e,verified_source(root,e));snap,receipt,shard=active(tmp_path,r,d)
    if change=='manifest_cycle':d['public_display_manifest']['output_hash']='a'*64
    elif change=='protocol_kind':r['related_results'][0]['protocol_kind']='ORIGINAL_C0'
    elif change=='wrong_contract':d['source_contract']='M1258'
    elif change=='revision':receipt['bindings'][mod.ID]['definition_revision']='wrong'
    elif change=='run_kind_conflict':
        p=snap/'assets/data/manifest.json';m=json.loads(p.read_bytes());m['runs'].append(dict(run_id=mod.RUN,manifest_kind='OLD',source_manifest_sha256='a'*64))
        raw=encoded(m);p.write_bytes(raw);receipt['files']['/data/manifest.json']=dict(bytes=len(raw),sha256=digest(raw))
    else:
        path='/data/implementations/'+digest((mod.RUN+'\n'+mod.VARIANT).encode())[:24]+'.json.gz';raw=encode_asset({'old':'orphan'})
        p=snap/'assets'/path[1:];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);receipt['files'][path]=dict(bytes=len(raw),sha256=digest(raw))
    (snap/'active-snapshot.json').write_bytes(encoded(receipt))
    with pytest.raises(ValueError):merge_snapshot([r],[d],snap,digest(encoded(receipt)),receipt['active_batch'])

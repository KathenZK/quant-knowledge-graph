"""Synthetic M1258 display contract; no Lab checkout or market data required."""
import calendar
from copy import deepcopy
import gzip
import json

import pytest

from quantgraph.graph.lab_display_catalog_daily import CONTRACT, FIDELITY
from quantgraph.graph.lab_display_projection import digest, encoded, merge_snapshot, prepare, project, verified_source
from quantgraph.graph.lab_display_v2 import DAILY, KIND, SCHEMA
from test_lab_display_projection import active


def fixture(tmp_path):
    rid='M1258'
    entry=dict(id=rid,group='synthetic',lab_commit='b'*40,origin_lab_commit='a'*40,
        run_id='synthetic-'+rid,variant_id=rid+'-base',fidelity_class='HYPOTHESIS',
        manifest_kind=KIND,projection_profile=DAILY,source_contract=CONTRACT)
    capital=dict(fraction='1',entry_fee_inclusive=True,initial_cash='100000',Decimal_precision=50,rounding='ROUND_HALF_EVEN')
    costs=[dict(name=c,fee_bps_each_side=f,slippage_bps_each_side=2,delay_bars=l)
           for c,f,l in [('base',8,1),('fee0',0,1),('fee20',20,1),('delay2',8,2)]]
    rules=dict(id=rid,capital=capital,cost_cases=costs,execution={'raw_M1258':'synthetic raw cross cancellation'},
        benchmark=dict(allocation=capital,fee_bps=8,slippage_bps=2,new_control_configurations=1),
        **{k:'synthetic '+k for k in ['RSI5','entry','exit','cold_start','stop_or_roi','known_halt']})
    protocol=dict(schema='M1258-catalog-hypothesis-protocol/v1',id=rid,classification=FIDELITY,
        execution='ADAPTED_EXECUTION_PROXY',strict_reproductions=0,initial_cash='100000',
        cases=costs,benchmark=dict(name='buyhold',fee_bps_each_side=8,slippage_bps_each_side=2,delay_bars=0,new_controls=1),
        statistics={'basis':'synthetic frozen daily convention'},input={'sha256':'c'*64})
    metric=dict(total_return=.024,cagr=.01,max_drawdown=-.1,sharpe_zero_cash=.2,observations=731,final_equity=102400)
    cases={cfg['name']:dict(metric,kind='STRATEGY',fee_bps=cfg['fee_bps_each_side'],slippage_bps=2,delay_bars=cfg['delay_bars']) for cfg in costs}
    cases['buyhold']=dict(metric,kind='CONTROL',fee_bps=8,slippage_bps=2,delay_bars=0,fills=1,closed_roundtrips=0,win_rate=None)
    summary=dict(id=rid,classification=FIDELITY,execution='ADAPTED_EXECUTION_PROXY',strict_reproductions=0,
        strategy_configurations=4,new_controls=1,input_sha256='c'*64,source_commit='d'*40,cases=cases,
        monthly={'synthetic':'original monthly values'})
    card=dict(id=rid,fidelity=FIDELITY,source_verified=False,original_framework_verified=False)
    catalog=dict(fields={'id':rid,**{f'field{n}':f'synthetic {n}' for n in range(10)}})
    view=dict(metric,sharpe=metric['sharpe_zero_cash'],annualization=365,start='2023-01-01',end='2024-12-31')
    periods={'2023-2024':view}
    original_metrics=dict(periods=periods,same_instrument_benchmark=periods,
        additional_native_bar_lag=periods,cost_sensitivity={'fee0':periods,'fee20':periods},capital_state={'initial_cash_usdt':100000})
    dates=['2023-01-01']+[f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}' for y in [2023,2024] for m in range(1,13)]
    curve=[dict(date=d,equity=1+n*.001,drawdown=0) for n,d in enumerate(dates)]
    original=dict(id=rid,run_id=entry['run_id'],origin_run_id=entry['run_id'],variant_id=entry['variant_id'],
        fidelity_class='HYPOTHESIS',curve=curve,metrics=original_metrics,
        lineage=dict(input_sha256='c'*64,source_commit='d'*40))
    expected_rules={k:rules[k] for k in ['RSI5','entry','exit','capital','cold_start','stop_or_roi','known_halt']}
    expected_rules.update(raw_cross_cancellation=rules['execution']['raw_M1258'],
        same_side_pending='Retain original earliest due; no postponement. Opposite raw cross cancels before holding-eligible scheduling.',cost_cases=costs)
    record=dict(id=rid,name='Synthetic only',status='tested_hypothesis_only',reason='Synthetic only',audit={},families=['synthetic'],
        fidelity_class='HYPOTHESIS',research_fidelity=FIDELITY,execution_class='ADAPTED_EXECUTION_PROXY',
        projection_profile=DAILY,manifest_kind=KIND,projection_status='STAGED_NOT_IMPORTED',definition_revision_bound=False,
        configuration_runs=4,new_control_runs=1,strategy_configurations=4,control_configurations=1,reused_control_configurations=0,
        tested_variants=1,results=deepcopy(cases),monthly=deepcopy(summary['monthly']),catalog_fields=catalog['fields'],source=card,
        rules=expected_rules,metric_conventions=protocol['statistics'],limitations=[],economic_basis={'paper':None},
        benchmark_reference=dict(kind='ACTUAL_ORIGINAL_NEW_CONTROL',name='buyhold',new_controls_at_original_run=1,
            allocation=capital,configuration=protocol['benchmark'],result=cases['buyhold'],evidence_role='summary'))
    detail=dict(id=rid,name='Synthetic only',family='synthetic',run_id=entry['run_id'],origin_run_id=entry['run_id'],
        variant_id=entry['variant_id'],fidelity_class='HYPOTHESIS',execution_class='ADAPTED_EXECUTION_PROXY',
        research_fidelity=FIDELITY,implementation_fidelity='ADAPTED_EXECUTION_PROXY',manifest_kind=KIND,
        projection_profile=DAILY,projection_status='STAGED_NOT_IMPORTED',curve=curve,
        curve_meta=dict(returned_points=25,observations=731,total_observations=731,equity_unit='initial_capital_multiple',
            drawdown_unit='fraction',denominator=100000,first_point_rebased=False,full_daily_curve_published=False,
            interpolation_claim=False,private_daily_nav_used=False),
        metrics={**deepcopy(original_metrics),'cost_sensitivity':{'0':periods,'20':periods},'source_cost_key_aliases':{'fee0':'0','fee20':'20'}},
        lab_counts=dict(strategy_ids=1,strategy_configurations=4,new_control_configurations=1,reused_control_configurations=0,strict_reproductions=0),
        projection_activity=dict(new_strategy_trials=0,new_controls=0),audit={},limitations=[],
        spec=dict(params={**{k:rules[k] for k in ['capital','RSI5','entry','exit']},'metric_conventions':protocol['statistics']},assumptions=[]))
    c0=dict(id=rid,strict_reproductions=0,planned_strategy_configurations=4,planned_new_controls=1,canonical_sha256='c'*64)
    blobs={k:encoded(v) for k,v in dict(protocol=protocol,summary=summary,C0=c0,rules=rules,source_card=card,
        catalog_fields=catalog,original_detail=original,original_record={'id':rid},curve=curve,record=record,detail=detail).items()}
    root=tmp_path/'source';root.mkdir();seal(root,entry,blobs)
    return root,entry,blobs


def seal(root,e,b):
    """Re-pin synthetic mutations so semantic guards run beyond hash validation."""
    prefix='research/public-strategies/M1258/'
    def ref(role,body,pin,path=None):
        path=path or prefix+role+'.json'
        return dict(path=path,sha256=digest(body),bytes=len(body),url=f'https://github.com/KathenZK/quant-research-lab/blob/{pin}/{path}')
    p=json.loads(b['protocol']);p['source_rules']={'sha256':digest(b['rules'])};b['protocol']=encoded(p)
    c=json.loads(b['C0']);c['files']=[dict(path=k+'.json',bytes=len(b[k]),sha256=digest(b[k])) for k in ['protocol','rules','source_card','catalog_fields']];b['C0']=encoded(c)
    s=json.loads(b['summary']);s['C0_sha256']=digest(b['C0']);b['summary']=encoded(s)
    old=json.loads(b['original_detail']);old['lineage']['C0_sha256']=digest(b['C0']);b['original_detail']=encoded(old)
    roles=['summary','protocol','C0','rules','source_card','catalog_fields','original_record','original_detail']
    refs={k:ref(k,b[k],'a'*40) for k in roles}
    b['origin_publication_manifest']=encoded(dict(id='M1258',files=list(refs.values())))
    refs['publication_manifest']=ref('publication_manifest',b['origin_publication_manifest'],'a'*40,prefix+'publication-manifest.json')
    r,d=(json.loads(b[k]) for k in ['record','detail'])
    manifest=dict(schema_version=SCHEMA,manifest_kind=KIND,projection_profile=DAILY,id='M1258',origin_run_id=e['run_id'],
        variant_id=e['variant_id'],origin_lab_commit='a'*40,original_private_result_manifest=False,original_results_modified=False,
        source_artifacts=refs,files={**refs,'base-nav-sampled.json':dict(bytes=len(b['curve']),sha256=digest(b['curve']))},
        curve_contract=d['curve_meta'],excluded_from_self_hash=['public-display-manifest.json','graph-record.json','graph-detail.json'])
    b['result_manifest']=encoded(manifest)
    binding=dict(origin_run_id=e['run_id'],variant_id=e['variant_id'],fidelity_class='HYPOTHESIS',execution_class='ADAPTED_EXECUTION_PROXY',
        protocol_sha256=digest(b['protocol']),manifest_sha256=digest(b['result_manifest']))
    rr=dict(binding,manifest_kind=KIND)
    r.update(source_artifacts=refs,related_results=[rr],implementations=[dict(rr,family='synthetic')])
    d.update(transport_binding=binding,lineage=dict(manifest_kind=KIND,manifest_sha256=digest(b['result_manifest']),
        source_display_manifest_sha256=digest(b['result_manifest']),protocol_sha256=digest(b['protocol']),C0_sha256=digest(b['C0']),
        lab_commit='a'*40,definition_revision_bound=False,source_artifacts=refs))
    b.update(record=encoded(r),detail=encoded(d))
    artifacts={k:ref(k,v,'b'*40) for k,v in b.items() if k!='publication_manifest'}
    b['publication_manifest']=encoded(dict(id='M1258',files=list(artifacts.values())))
    artifacts['publication_manifest']=ref('publication_manifest',b['publication_manifest'],'b'*40,prefix+'publication-manifest.json')
    e['artifacts']=artifacts
    for k,raw in b.items():
        path=root/artifacts[k]['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)


def test_catalog_projection_preserves_counts_units_aliases_and_fidelity(tmp_path):
    root,e,b=fixture(tmp_path);r,d=project(e,verified_source(root,e))
    assert r['research_fidelity']==d['research_fidelity']==FIDELITY and d['fidelity_class']=='HYPOTHESIS'
    assert r['source_contract']==d['lineage']['source_contract']==CONTRACT
    assert d['lab_counts']['new_control_configurations']==1 and d['projection_activity']['new_controls']==0
    assert r['benchmark_reference']['result']['win_rate'] is None
    assert r['rules']['capital']['fraction']=='1' and r['rules']['capital']['entry_fee_inclusive'] is True
    assert d['curve']==json.loads(b['original_detail'])['curve'] and len(d['curve'])==25
    assert d['curve_meta']['total_observations']==d['metrics']['periods']['full']['observations']==731
    assert d['metrics']['additional_lag_unit']=='day'
    assert d['metrics']['periods']['full']==d['metrics']['periods']['2023-2024']
    registry=dict(schema_version='quantgraph-approved-lab-display-sources/v1',records=[e])
    a,z=tmp_path/'first',tmp_path/'rebuild';status=prepare({'synthetic':root},a,registry=registry)
    prepare({'synthetic':root},z,registry=registry)
    assert status['active_merge_status'].startswith('BLOCKED_') and status['new_execution_trials']==0
    assert {f.relative_to(a):f.read_bytes() for f in a.rglob('*') if f.is_file()}=={f.relative_to(z):f.read_bytes() for f in z.rglob('*') if f.is_file()}
    with pytest.raises(ValueError):prepare({'synthetic':root},a,registry=registry)


@pytest.mark.parametrize('change',['contract','missing_contract','kind','cycle','ref_kind','hash','path','private','identity'])
def test_catalog_source_and_manifest_guards(tmp_path,change):
    root,e,b=fixture(tmp_path)
    if change=='contract':e['source_contract']='AUTO'
    elif change=='missing_contract':e.pop('source_contract')
    elif change=='kind':e['manifest_kind']='LAB_ORIGIN_RESULT_MANIFEST_NOT_GRAPH_COLLECTION'
    elif change=='hash':
        (root/e['artifacts']['summary']['path']).write_bytes(b['summary']+b' ')
        with pytest.raises(ValueError):verified_source(root,e)
        return
    elif change=='path':
        e['artifacts']['summary']['path']+='/../../escape'
        with pytest.raises(ValueError):verified_source(root,e)
        return
    elif change=='cycle':
        m=json.loads(b['result_manifest']);m['files']['graph-record.json']={};b['result_manifest']=encoded(m)
    else:
        r=json.loads(b['record'])
        if change=='ref_kind':r['related_results'][0]['manifest_kind']='NATIVE'
        elif change=='identity':r['id']='M9999'
        else:r['economic_basis']={'paper':'libfile_privateexample'}
        b['record']=encoded(r)
    with pytest.raises(ValueError):project(e,b)


@pytest.mark.parametrize('change',['fraction95','fee_exclusive','promoted','verified_author','wrong_control','reuse_control',
                                  'new_projection_control','null_to_zero','wrong_fee','wrong_day_lag','metric_changed',
                                  'double_scale','extra_point','731_points','absolute_units','rules','monthly'])
def test_catalog_semantic_guards_after_repinning(tmp_path,change):
    root,e,b=fixture(tmp_path)
    r,d,s,rules,card,old=(json.loads(b[k]) for k in ['record','detail','summary','rules','source_card','original_detail'])
    if change=='fraction95':rules['capital']['fraction']='0.95'
    elif change=='fee_exclusive':rules['capital']['entry_fee_inclusive']=False
    elif change=='promoted':r['research_fidelity']='ADAPTED'
    elif change=='verified_author':card['source_verified']=True;r['source']=card
    elif change=='wrong_control':s['new_controls']=0
    elif change=='reuse_control':r['reused_control_configurations']=1
    elif change=='new_projection_control':d['projection_activity']['new_controls']=1
    elif change=='null_to_zero':s['cases']['buyhold']['win_rate']=0;r['results']=s['cases'];r['benchmark_reference']['result']=s['cases']['buyhold']
    elif change=='wrong_fee':s['cases']['fee0']['fee_bps']=8;r['results']=s['cases']
    elif change=='wrong_day_lag':s['cases']['delay2']['delay_bars']=1;r['results']=s['cases']
    elif change=='metric_changed':d['metrics']['periods']['2023-2024']['total_return']=.99
    elif change=='double_scale':
        for p in old['curve']:p['equity']/=100000
        d['curve']=old['curve'];b['curve']=encoded(old['curve'])
    elif change=='extra_point':d['curve'].append(deepcopy(d['curve'][-1]))
    elif change=='731_points':d['curve_meta']['returned_points']=731
    elif change=='absolute_units':d['curve_meta']['equity_unit']='USDT'
    elif change=='rules':r['rules']['RSI5']='invented smoothing'
    elif change=='monthly':r['monthly']={'invented':True}
    b.update({k:encoded(v) for k,v in dict(record=r,detail=d,summary=s,rules=rules,source_card=card,original_detail=old).items()})
    seal(root,e,b)
    with pytest.raises(ValueError):project(e,b)


def test_catalog_existing_merge_preserves_notes_and_transport(tmp_path):
    root,e,b=fixture(tmp_path);r,d=project(e,verified_source(root,e));snapshot,receipt,shard=active(tmp_path,r,d)
    assets,envelope=merge_snapshot([r],[d],snapshot,digest(encoded(receipt)),receipt['active_batch'])
    assert set(envelope['results'][0])=={'origin_run_id','variant_id','manifest_sha256','record_id','detail_path','detail_sha256'}
    row=json.loads(gzip.decompress(assets[shard]))[r['id']]
    assert row['note_marker']=='unchanged' and len(row['related_results'])==3
    assert row['audit']=={'retained':'original'}
    for path,raw in assets.items():
        target=snapshot/'assets'/path[1:];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        receipt['files'][path]=dict(sha256=digest(raw),bytes=len(raw))
    (snapshot/'active-snapshot.json').write_bytes(encoded(receipt))
    assert merge_snapshot([r],[d],snapshot,digest(encoded(receipt)),receipt['active_batch'])[0]=={}
    changed=deepcopy(d);changed['name']='different bytes for same frozen run'
    with pytest.raises(ValueError,match='different bytes'):
        merge_snapshot([r],[changed],snapshot,digest(encoded(receipt)),receipt['active_batch'])

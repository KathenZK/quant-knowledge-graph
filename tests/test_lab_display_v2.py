"""Synthetic public-only v2 profiles: hash, identity, units and staging guards."""
import calendar
from copy import deepcopy
import csv
from datetime import date, timedelta
import gzip
import io
import json

import pytest

from quantgraph.graph.lab_display_projection import (
    digest, encoded, merge_snapshot, prepare, project, verified_source,
)
from quantgraph.graph.lab_display_v2 import DAILY, KIND, NATIVE, SCHEMA, native_period
from test_lab_display_projection import active


def fixture(tmp_path, profile=NATIVE, *, zero=False):
    rid = 'M1358' if profile == DAILY else 'M0289' if zero else 'M0287'
    e = dict(id=rid, group='synthetic', lab_commit='b'*40, origin_lab_commit='a'*40,
             run_id='synthetic-'+rid, variant_id=rid+'-base',
             fidelity_class='HYPOTHESIS' if profile == DAILY else 'ADAPTED',
             manifest_kind=KIND, projection_profile=profile)
    counts = dict(strategy_ids=1, strategy_configurations=4, new_control_configurations=0,
                  reused_control_configurations=1, strict_reproductions=0)
    record = dict(id=rid, name='Synthetic only', families=['synthetic'], audit={},
        status='tested_hypothesis_only' if profile == DAILY else 'tested_adapted_only', reason='Synthetic only',
        fidelity_class=e['fidelity_class'], execution_class='ADAPTED_EXECUTION_PROXY',
        strategy_configurations=4, control_configurations=0, reused_control_configurations=1,
        tested_variants=1, limitations=[], economic_basis={'paper':None},
        definition_revision_bound=False, projection_status='STAGED_NOT_IMPORTED', manifest_kind=KIND)
    detail = dict(id=rid, name='Synthetic only', family='synthetic', run_id=e['run_id'],
        origin_run_id=e['run_id'], variant_id=e['variant_id'], fidelity_class=e['fidelity_class'],
        lab_counts=counts, spec={'params':{}, 'assumptions':[]}, audit={}, limitations=[],
        projection_status='STAGED_NOT_IMPORTED', manifest_kind=KIND)
    blobs = {'readme':b'Synthetic original README'}
    if profile == NATIVE:
        execution = dict(initial_cash=100000)
        cases = [dict(name=c, fee_bps=f, delay_bars=l) for c,f,l in
                 [('base',8,1),('fee0',0,1),('fee20',20,1),('delay2',8,2)]]
        p = dict(record_id=rid, run_id=e['run_id'], variant_id=e['variant_id'],
            fidelity_class='ADAPTED', execution=execution, risk={}, parameters={},
            source_specific_requirements={}, source={'sha256':'c'*64}, cases=cases)
        card = dict(id=rid, rules='synthetic signal', catalog_omissions=[], source={'sha256':'c'*64})
        m = dict(start='2024-01-01', daily_observations=366, observations=105408,
                 total_return=0 if zero else .1, annualized_return=0 if zero else .2,
                 sharpe=None if zero else .3, max_drawdown=0 if zero else .04,
                 trades=0 if zero else 1, final_equity=100000 if zero else 110000)
        p['benchmark_reference'] = dict(metrics=m)
        summary = dict(id=rid, origin_run_id=e['run_id'], variant_id=e['variant_id'], fidelity_class='ADAPTED',
            strategy_configurations=4, new_control_configurations=0, reused_control_configurations=1,
            benchmark_reference=p['benchmark_reference'], signals={},
            results={c['name']:dict(configuration=c, metrics=deepcopy(m)) for c in cases})
        c0 = dict(record_id=rid, source_sha256='c'*64, strategy_configurations_frozen=4, new_controls=0)
        rules = dict(source_signal_rules=card['rules'], source_specific_requirements=p['source_specific_requirements'],
            execution=execution, risk={}, parameters={}, catalog_omissions=[])
        record.update(rules=rules, results=deepcopy(summary['results']), signals={},
                      benchmark_reference=deepcopy(p['benchmark_reference']))
        points, curve, peak = [], [], 1.0
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=['date','valuation_time_utc','equity','nav','source_native_drawdown'], lineterminator='\n')
        writer.writeheader()
        for n in range(366):
            stamp=(date(2024,1,1)+timedelta(days=n)).isoformat()
            time=(date(2024,1,2)+timedelta(days=n)).isoformat()+'T00:00:00Z'
            equity=100000 if zero else 99000 if n==0 else 110000
            nav=equity/100000;dd=0 if zero else -.04;peak=max(peak,nav)
            points.append(dict(date=stamp,timestamp_utc=time,equity=equity,drawdown=dd))
            curve.append(dict(date=stamp,valuation_time_utc=time,equity=nav,drawdown=nav/peak-1,source_native_drawdown=dd))
            writer.writerow(dict(date=stamp,valuation_time_utc=time,equity=equity,nav=nav,source_native_drawdown=dd))
        blobs['curve']=stream.getvalue().encode()
        for case in ['base','fee0','fee20','delay2']:
            blobs[case+'_daily']=encoded(dict(initial_equity=100000,observations=105408,points=points))
        blobs.update(attribution=b'Synthetic', validation_summary=b'{}')
        detail.update(curve=curve, curve_meta=dict(total_observations=366,returned_points=366,
            native_observations=105408,equity_unit='initial_capital_multiple',denominator=100000,first_point_rebased=False),
            metrics=dict(periods={'full':native_period(m)},same_instrument_benchmark={'full':native_period(m)},
                cost_sensitivity={k:{'full':native_period(m)} for k in ['0','20']},
                additional_native_bar_lag={'full':native_period(m)}))
        detail['spec']['params']['rules']=rules
    else:
        execution=dict(initial_cash=100000,buy_fee_additional_in_USDT=True)
        metric=dict(observations=731,final_equity=102400,total_return=.024,cagr=.01,sharpe_zero_cash=.2,max_drawdown=-.1)
        years={y:dict(metric,observations=n) for y,n in [('2023',365),('2024',366)]}
        result=dict(metrics=metric,periods=years)
        cases=[dict(name=c,fee_bps=f,lag_days=l) for c,f,l in [('base',8,1),('fee0',0,1),('fee20',20,1),('lag2',8,2)]]
        p=dict(exclusive_ids=[rid],fidelity='ADAPTED',strategy_configurations_expected=4,
               new_control_configurations_expected=0,execution=execution,source_signal_rules='synthetic daily state',
               cases=cases,benchmark_reference={'result':result})
        c0=dict(record_id=rid,fidelity='ADAPTED')
        card=dict(record_id=rid)
        summary=dict(record_id=rid,fidelity='ADAPTED',configurations=4,new_controls=0,
            summary={c['name']:{**c,**deepcopy(result)} for c in cases},existing_buyhold_reference=result)
        record.update(rules=dict(source_signal_rules=p['source_signal_rules'],execution=execution),
            results=deepcopy(summary['summary']),benchmark_reference=deepcopy(p['benchmark_reference']),research_fidelity='ADAPTED')
        dates=['2023-01-01']+[f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}' for y in [2023,2024] for m in range(1,13)]
        curve=[dict(date=d,equity=1+n*.001,drawdown=0) for n,d in enumerate(dates)]
        periods={'2023-2024':dict(metric,sharpe=metric['sharpe_zero_cash']),
                 **{y:dict(m,sharpe=m['sharpe_zero_cash']) for y,m in years.items()}}
        original_metrics=dict(periods=periods,same_instrument_benchmark=periods,
            cost_sensitivity={'fee0':periods,'fee20':periods},additional_native_bar_lag=periods)
        original=dict(id=rid,run_id=e['run_id'],variant_id=e['variant_id'],fidelity_class='HYPOTHESIS',
                      curve=curve,metrics=original_metrics)
        blobs.update(original_detail=encoded(original),original_record=b'{}',numerics=b'{}',report=b'Synthetic report',curve=encoded(curve))
        detail.update(curve=curve,curve_meta=dict(returned_points=25,observations=731,total_observations=731,
            equity_unit='initial_capital_multiple',full_daily_curve_published=False,interpolation_claim=False,
            private_daily_nav_used=False,first_point_rebased=False),
            metrics={**deepcopy(original_metrics),'cost_sensitivity':{'0':periods,'20':periods},'source_cost_key_aliases':{'fee0':'0','fee20':'20'}},
            implementation_fidelity='ADAPTED_EXECUTION_PROXY',research_fidelity='ADAPTED')
        detail['spec']['params'].update(source_signal_rules=p['source_signal_rules'],execution=execution)
    blobs.update(protocol=encoded(p),C0=encoded(c0),summary=encoded(summary),source_rule_card=encoded(card),
                 record=encoded(record),detail=encoded(detail))
    root=tmp_path/rid;root.mkdir()
    seal(root,e,blobs)
    return root,e,blobs


def seal(root, e, b):
    """Rebind synthetic approved evidence, so value guards are tested after hashes."""
    prefix=f"research/public-strategies/{e['id']}/"
    def ref(path,body,pin):
        return dict(path=path,bytes=len(body),sha256=digest(body),url=f'https://github.com/KathenZK/quant-research-lab/blob/{pin}/{path}')
    p,c,s,r,d=(_loads(b[k]) for k in ['protocol','C0','summary','record','detail'])
    if e['projection_profile']==NATIVE:
        c['protocol_sha256']=s['protocol_sha256']=digest(b['protocol'])
    else:
        c['root_contract_sha256']=digest(b['protocol'])
    b['C0']=encoded(c)
    if e['projection_profile']==DAILY:s['C0_sha256']=digest(b['C0'])
    b['summary']=encoded(s)
    source_roles=set(b)-{'record','detail','curve','result_manifest','publication_manifest','origin_publication_manifest'}
    refs={k:ref(prefix+k+'.json',b[k],'a'*40) for k in source_roles}
    oldfiles=list(refs.values())
    if e['projection_profile']==DAILY:
        private=ref(prefix+'private-output-manifest.json',b'not read','a'*40)
        oldfiles.append(private)
        refs['private_output_inventory_reference_only']=private
    b['origin_publication_manifest']=encoded(dict(record_id=e['id'],files=oldfiles))
    refs['publication_manifest']=ref(prefix+'publication-manifest.json',b['origin_publication_manifest'],'a'*40)
    curve_name='base-nav-light.csv' if e['projection_profile']==NATIVE else 'base-nav-sampled.json'
    manifest=dict(schema_version=SCHEMA,manifest_kind=KIND,projection_profile=e['projection_profile'],id=e['id'],
        origin_run_id=e['run_id'],variant_id=e['variant_id'],origin_lab_commit='a'*40,
        original_private_result_manifest=False,original_results_modified=False,source_artifacts=refs,
        files={**{k:v for k,v in refs.items() if k!='private_output_inventory_reference_only'},
               curve_name:dict(bytes=len(b['curve']),sha256=digest(b['curve']))},
        excluded_from_self_hash=['public-display-manifest.json','graph-record.json','graph-detail.json'],curve_contract=d['curve_meta'])
    b['result_manifest']=encoded(manifest)
    result_ref=dict(origin_run_id=e['run_id'],variant_id=e['variant_id'],fidelity_class=e['fidelity_class'],
        execution_class='ADAPTED_EXECUTION_PROXY',manifest_kind=KIND,manifest_sha256=digest(b['result_manifest']),protocol_sha256=digest(b['protocol']))
    r.update(source_artifacts=refs,related_results=[result_ref],implementations=[dict(result_ref,family='synthetic')])
    d['lineage']=dict(manifest_kind=KIND,manifest_sha256=digest(b['result_manifest']),
        source_display_manifest_sha256=digest(b['result_manifest']),protocol_sha256=digest(b['protocol']),
        C0_sha256=digest(b['C0']),lab_commit='a'*40,definition_revision_bound=False,source_artifacts=refs)
    b.update(record=encoded(r),detail=encoded(d))
    artifacts={k:ref(prefix+(f'history/{k}' if k in {'origin_publication_manifest','readme'} else k)+'.json',v,'b'*40)
               for k,v in b.items() if k!='publication_manifest'}
    b['publication_manifest']=encoded(dict(record_id=e['id'],files=list(artifacts.values())))
    artifacts['publication_manifest']=ref(prefix+'publication-manifest.json',b['publication_manifest'],'b'*40)
    e['artifacts']=artifacts
    for role,body in b.items():
        target=root/artifacts[role]['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)


def _loads(raw):
    return json.loads(raw)


@pytest.mark.parametrize('profile',[NATIVE,DAILY])
def test_v2_profiles_source_fidelity_units_and_deterministic_stage(tmp_path,profile):
    root,e,b=fixture(tmp_path,profile)
    r,d=project(e,verified_source(root,e))
    assert r['manifest_kind']==d['lineage']['manifest_kind']==KIND
    assert d['spec']['params']['rules']==r['rules']
    assert 'source_run_manifest_sha256' not in d['lineage']
    if profile==DAILY:
        assert d['fidelity_class']=='HYPOTHESIS' and d['research_fidelity']=='ADAPTED'
        assert len(d['curve'])==25 and d['curve_meta']['total_observations']==731
        assert d['curve']==_loads(b['original_detail'])['curve']
        assert d['metrics']['periods']['full']==d['metrics']['periods']['2023-2024']
        assert d['metrics']['periods']['full']['observations']==731
        assert d['metrics']['additional_lag_unit']=='day'
    else:
        assert d['curve'][0]['equity']==.99 and d['curve'][0]['drawdown']==pytest.approx(-.01)
        assert d['curve'][0]['source_native_drawdown']==-.04
        assert d['metrics']['additional_lag_unit']=='native_5m_bar'
    registry=dict(schema_version='quantgraph-approved-lab-display-sources/v1',records=[e])
    a,z=tmp_path/'a',tmp_path/'z'
    status=prepare({'synthetic':root},a,registry=registry)
    prepare({'synthetic':root},z,registry=registry)
    assert status['active_merge_status'].startswith('BLOCKED_')
    assert {f.relative_to(a):f.read_bytes() for f in a.rglob('*') if f.is_file()}=={f.relative_to(z):f.read_bytes() for f in z.rglob('*') if f.is_file()}
    with pytest.raises(ValueError,match='immutable'):prepare({'synthetic':root},a,registry=registry)


def test_zero_trade_null_survives(tmp_path):
    root,e,b=fixture(tmp_path,zero=True)
    r,d=project(e,verified_source(root,e))
    assert d['metrics']['periods']['full']['sharpe'] is None
    assert all(p['equity']==1 for p in d['curve'])
    s=_loads(b['summary']);s['results']['base']['metrics']['sharpe']=0;b['summary']=encoded(s)
    r=_loads(b['record']);r['results']=s['results'];b['record']=encoded(r)
    seal(root,e,b)
    with pytest.raises(ValueError,match='null'):project(e,b)


@pytest.mark.parametrize('change',['hash','path','publication','wrong_profile','hidden_profile','wrong_type','ref_type','cycle','private','rules','curve','native_boundary','counts','native_fee'])
def test_native_v2_guards(tmp_path,change):
    root,e,b=fixture(tmp_path)
    if change in {'hash','path','publication'}:
        ref=e['artifacts']['summary']
        if change=='path':ref['path']+='/../../escape'
        elif change=='hash':(root/ref['path']).write_bytes(b['summary']+b' ')
        else:e['artifacts']['summary']['sha256']='0'*64
        with pytest.raises(ValueError):verified_source(root,e)
        return
    r,d,m=(_loads(b[k]) for k in ['record','detail','result_manifest'])
    if change=='wrong_profile':e['projection_profile']='AUTO'
    elif change=='hidden_profile':e.pop('projection_profile')
    elif change=='wrong_type':e['manifest_kind']='LAB_ORIGIN_RESULT_MANIFEST_NOT_GRAPH_COLLECTION'
    elif change=='ref_type':r['related_results'][0]['manifest_kind']='NATIVE'
    elif change=='cycle':m['files']['graph-record.json']={}
    elif change=='private':r['economic_basis']={'paper':'api_key=secret'}
    elif change=='rules':r['rules']['source_signal_rules']='invented'
    elif change=='curve':d['curve'][0]['equity']=1
    elif change=='native_boundary':d['curve'][0]['valuation_time_utc']='2024-01-01T00:00:00Z'
    elif change=='counts':d['lab_counts']['strategy_configurations']=99
    elif change=='native_fee':
        s=_loads(b['summary']);s['results']['fee0']['configuration']['fee_bps']=8;b['summary']=encoded(s)
        r['results']=s['results'];b['record']=encoded(r);seal(root,e,b)
        with pytest.raises(ValueError,match='cost/lag'):project(e,b)
        return
    b.update(record=encoded(r),detail=encoded(d),result_manifest=encoded(m))
    with pytest.raises(ValueError):project(e,b)


@pytest.mark.parametrize('change',['double_scale','extra_sample','731_curve_claim','lag_bars','wrong_fee','enum','research_fidelity','full_alias','C0','private_inventory_body'])
def test_daily_v2_guards(tmp_path,change):
    root,e,b=fixture(tmp_path,DAILY)
    r,d=(_loads(b[k]) for k in ['record','detail'])
    if change=='double_scale':
        old=_loads(b['original_detail'])
        for p in old['curve']:p['equity']/=100000
        d['curve']=old['curve'];b['original_detail']=encoded(old);b['curve']=encoded(old['curve'])
    elif change=='extra_sample':d['curve'].append(deepcopy(d['curve'][-1]))
    elif change=='731_curve_claim':d['curve_meta']['returned_points']=731
    elif change in {'lag_bars','wrong_fee'}:
        s=_loads(b['summary'])
        if change=='wrong_fee':s['summary']['fee0']['fee_bps']=8
        else:s['summary']['lag2']['lag_days']=1
        b['summary']=encoded(s);r['results']=s['summary']
    elif change=='enum':d['fidelity_class']='ADAPTED'
    elif change=='research_fidelity':r['research_fidelity']='STRICT'
    elif change=='full_alias':d['metrics']['periods']['full']={}
    elif change=='C0':
        c=_loads(b['C0']);c['record_id']='M9999';b['C0']=encoded(c)
    elif change=='private_inventory_body':b['private_output_inventory_reference_only']=b'{}'
    b.update(record=encoded(r),detail=encoded(d))
    if change!='private_inventory_body':seal(root,e,b)
    with pytest.raises(ValueError):project(e,b)


def test_v2_merge_keeps_six_field_transport_old_notes_and_rejects_conflicting_run(tmp_path):
    root,e,b=fixture(tmp_path,DAILY);r,d=project(e,verified_source(root,e))
    snapshot,receipt,shard=active(tmp_path,r,d)
    assets,envelope=merge_snapshot([r],[d],snapshot,digest(encoded(receipt)),receipt['active_batch'])
    assert set(envelope['results'][0])=={'origin_run_id','variant_id','manifest_sha256','record_id','detail_path','detail_sha256'}
    row=_loads(gzip.decompress(assets[shard]))[r['id']]
    assert row['note_marker']=='unchanged' and len(row['related_results'])==3
    m=_loads(assets['/data/manifest.json'])
    assert m['runs'][-1]['manifest_kind']==KIND
    path=snapshot/'assets/data/manifest.json';old=_loads(path.read_bytes())
    old['runs'].append(dict(run_id=d['run_id'],manifest_kind='WRONG',source_manifest_sha256=d['lineage']['manifest_sha256']))
    body=encoded(old);path.write_bytes(body);receipt['files']['/data/manifest.json']=dict(bytes=len(body),sha256=digest(body))
    (snapshot/'active-snapshot.json').write_bytes(encoded(receipt))
    with pytest.raises(ValueError,match='conflicts'):merge_snapshot([r],[d],snapshot,digest(encoded(receipt)),receipt['active_batch'])

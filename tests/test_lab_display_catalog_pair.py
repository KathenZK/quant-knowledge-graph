"""Synthetic pair fixtures; no Lab checkout, private NAV or real market input."""
from copy import deepcopy
import gzip
import json

import pytest

from quantgraph.graph.lab_display_catalog_daily import FIDELITY
from quantgraph.graph.lab_display_catalog_pair import CONTRACTS, CONTROL_PIN, RULE_KEYS, SPECIFIC
from quantgraph.graph.lab_display_projection import digest, encoded, merge_snapshot, prepare, project, verified_source
from quantgraph.graph.lab_display_v2 import DAILY, KIND, SCHEMA
from test_lab_display_catalog_daily import fixture as rsi_fixture
from test_lab_display_projection import active


def fixture(tmp_path, rid='M1396'):
    root, entry, old = rsi_fixture(tmp_path)
    blobs = {k: encoded(json.loads(v.decode().replace('M1258', rid))) for k, v in old.items()
             if k not in ['source_card', 'publication_manifest', 'origin_publication_manifest', 'result_manifest']}
    entry.update(id=rid, run_id='synthetic-'+rid, variant_id=rid+'-base', source_contract=CONTRACTS[rid])
    r, d, summary, original = (json.loads(blobs[k]) for k in ['record', 'detail', 'summary', 'original_detail'])
    capital = r['rules']['capital']
    costs = r['rules']['cost_cases']
    classification = FIDELITY + ' / ADAPTED_EXECUTION_PROXY; strict0'
    rules = dict(id=rid, classification=classification, capital=capital, cost_cases=costs,
        input={'sha256': 'c'*64}, economic_hypothesis='Synthetic inferred rationale',
        benchmark={'new_control_configurations': 0}, **{k:'Synthetic '+k for k in RULE_KEYS if k not in ['capital', 'cost_cases']},
        **{k:'Synthetic '+k for k in SPECIFIC[rid]})
    protocol = dict(deepcopy(rules), cases=costs, statistics={'basis':'synthetic frozen daily convention'},
                    evaluation_start_ms=1672531200000, evaluation_end_ms=1735689600000)
    c0 = dict(id=rid, strict_reproductions=0, planned_strategy_configurations=4, planned_new_controls=0, canonical_sha256='c'*64)
    cases = [dict(value, case=name, monthly_observations=24, terminal_pending=None)
             for name, value in summary['cases'].items() if name != 'buyhold']
    summary = dict(id=rid, classification=FIDELITY, execution_class='ADAPTED_EXECUTION_PROXY',
        strict_reproductions=0, strategy_configurations=4, new_controls=0, cases=cases, control_remote_commit=CONTROL_PIN)
    metrics = {k:cases[0][k] for k in ['total_return','cagr','max_drawdown','sharpe_zero_cash','observations','final_equity']}
    control = dict(id='M1258', control_name='buyhold', initial_cash='100000', allocation='100% fee-inclusive',
        fee_bps_each_side=8, slippage_bps_each_side=2, native_timeframe='1d', bars=731, input_sha256='c'*64,
        window_OOS=False, trusted=False, PIT='NOT_PROVEN', statistics=protocol['statistics'], metrics=metrics,
        evaluation_start='2023-01-01T00:00:00Z', evaluation_end_exclusive='2025-01-01T00:00:00Z')
    release = dict(source_id='M1258', status='RELEASED_FOR_EXACT_IDENTITY_REUSE', consumers=['M1396','M1463'],
                   new_controls_authorized=0, remote_public_core_commit=CONTROL_PIN)
    fields = {'id':rid, **{k:'Synthetic '+k for k in ['名称','市场','规则','作者或机构','标题','source_url','页码或文件','可回测','提出日期']}}
    redacted = {'别名来源': {'reason':'Private curation omitted', 'public_alias_url':'https://example.org/public'}}
    if rid == 'M1396':
        fields['别名来源'] = 'Synthetic public alias'; redacted = {}
    catalog = dict(fields=fields, original_field_count=11, redacted_fields=redacted)
    scope = dict(original_field_count=11, public_field_count=len(fields), omitted_fields=redacted, complete_original_fields_public=rid=='M1396')
    original['metrics']['periods']['full'] = deepcopy(original['metrics']['periods']['2023-2024'])
    original['metrics']['capital_state']['terminal_pending'] = None
    original['audit'] = dict(strict_reproductions=0, original_runtime_equivalence=False, PIT='NOT_PROVEN')
    original['lineage'].update(control_remote_commit=CONTROL_PIN)
    display_metrics = deepcopy(original['metrics'])
    display_metrics['cost_sensitivity'] = {str(fee):deepcopy(original['metrics']['cost_sensitivity'][name]) for fee,name in [(0,'fee0'),(20,'fee20')]}
    display_metrics['source_cost_key_aliases'] = {'fee0':'0','fee20':'20'}
    r.pop('source'); r.update(source_contract=CONTRACTS[rid], results={v['case']:v for v in cases}, monthly=None,
        monthly_status='NOT_PUBLISHED_IN_SELECTED_LIGHT_SUMMARY', new_control_runs=0, control_configurations=0,
        reused_control_configurations=1, catalog_fields=fields, catalog_public_scope=scope,
        rules={k:rules[k] for k in RULE_KEYS+SPECIFIC[rid]}, metric_conventions=protocol['statistics'], benchmark_curve=[],
        economic_basis=dict(paper=None,hypothesis=rules['economic_hypothesis'],status='INFERRED_RESEARCH_RATIONALE_NOT_SOURCE_VERIFIED'),
        benchmark_reference=dict(kind='REUSED_ACCEPTED_M1258_CONTROL',id='M1258',name='buyhold',source_commit=CONTROL_PIN,
            evidence_role='control_reference',acceptance_role='control_release',new_controls_for_this_strategy=0,
            allocation='100% fee-inclusive',initial_cash='100000',fee_bps_each_side=8,slippage_bps_each_side=2,timeframe='1d',
            observations=731,evaluation_start=control['evaluation_start'],evaluation_end_exclusive=control['evaluation_end_exclusive'],
            metrics=metrics,window_OOS=False))
    d.update(source_contract=CONTRACTS[rid], metrics=display_metrics,
        lab_counts=dict(strategy_ids=1,strategy_configurations=4,new_control_configurations=0,reused_control_configurations=1,strict_reproductions=0),
        spec=dict(params={**{k:rules[k] for k in ['capital','entry','exit']},'metric_conventions':protocol['statistics'],
                          'source_contract':CONTRACTS[rid]}, assumptions=[]))
    blobs.update({k:encoded(v) for k,v in dict(record=r,detail=d,summary=summary,protocol=protocol,C0=c0,rules=rules,
        catalog_fields=catalog,original_detail=original,control_reference=control,control_release=release).items()})
    seal(root,entry,blobs)
    return root,entry,blobs


def seal(root, entry, blobs):
    """Re-pin synthetic mutations to exercise semantics beyond hash rejection."""
    rid=entry['id'];prefix=f'research/public-strategies/{rid}/'
    def ref(role,body,pin,path=None):
        path=path or prefix+role+'.json'
        return dict(path=path,bytes=len(body),sha256=digest(body),url=f'https://github.com/KathenZK/quant-research-lab/blob/{pin}/{path}')
    c0=json.loads(blobs['C0']);c0['files']=[dict(path=k+'.json',bytes=len(blobs[k]),sha256=digest(blobs[k])) for k in ['protocol','rules','catalog_fields']]
    blobs['C0']=encoded(c0)
    original=json.loads(blobs['original_detail']);original['lineage'].update(C0_sha256=digest(blobs['C0']),control_reference_sha256=digest(blobs['control_reference']))
    blobs['original_detail']=encoded(original)
    release=json.loads(blobs['control_release']);release['control_reference']={'sha256':digest(blobs['control_reference'])};blobs['control_release']=encoded(release)
    roles=['summary','protocol','C0','rules','catalog_fields','original_detail','original_record','control_reference','control_release']
    refs={k:ref(k,blobs[k],'a'*40) for k in roles}
    blobs['origin_publication_manifest']=encoded(dict(id=rid,schema='batch016-fixed-publication/v1',original_C0_sha256=digest(blobs['C0']),files=list(refs.values())))
    refs['publication_manifest']=ref('publication_manifest',blobs['origin_publication_manifest'],'a'*40,prefix+'publication-manifest.v1.json')
    r,d=(json.loads(blobs[k]) for k in ['record','detail'])
    manifest=dict(schema_version=SCHEMA,manifest_kind=KIND,projection_profile=DAILY,source_contract=entry['source_contract'],
        id=rid,origin_run_id=entry['run_id'],variant_id=entry['variant_id'],origin_lab_commit='a'*40,
        original_private_result_manifest=False,original_results_modified=False,source_artifacts=refs,
        files={**refs,'base-nav-sampled.json':dict(bytes=len(blobs['curve']),sha256=digest(blobs['curve']))},
        curve_contract=d['curve_meta'],excluded_from_self_hash=['public-display-manifest.json','graph-record.json','graph-detail.json'])
    blobs['result_manifest']=encoded(manifest)
    binding=dict(origin_run_id=entry['run_id'],variant_id=entry['variant_id'],fidelity_class='HYPOTHESIS',execution_class='ADAPTED_EXECUTION_PROXY',
        protocol_sha256=digest(blobs['protocol']),manifest_sha256=digest(blobs['result_manifest']))
    rr=dict(binding,manifest_kind=KIND)
    r.update(source_artifacts=refs,related_results=[rr],implementations=[dict(rr,family='synthetic')])
    d.update(transport_binding=binding,lineage=dict(manifest_kind=KIND,source_contract=entry['source_contract'],
        manifest_sha256=digest(blobs['result_manifest']),source_display_manifest_sha256=digest(blobs['result_manifest']),
        protocol_sha256=digest(blobs['protocol']),C0_sha256=digest(blobs['C0']),lab_commit='a'*40,definition_revision_bound=False,source_artifacts=refs))
    blobs.update(record=encoded(r),detail=encoded(d))
    artifacts={k:ref(k,v,'b'*40,prefix+'publication-manifest.v1.json' if k=='origin_publication_manifest' else None)
               for k,v in blobs.items() if k!='publication_manifest'}
    previous={k:artifacts['origin_publication_manifest'][k] for k in ['path','bytes','sha256']}
    blobs['publication_manifest']=encoded(dict(id=rid,schema='batch016-fixed-publication/v2',revision=2,previous_publication_manifest=previous,
        original_C0_sha256=digest(blobs['C0']),actual_strategy_configurations=4,new_controls=0,projection_new_trials=0,projection_new_controls=0,files=list(artifacts.values())))
    artifacts['publication_manifest']=ref('publication_manifest',blobs['publication_manifest'],'b'*40,prefix+'publication-manifest.v2.json')
    entry['artifacts']=artifacts
    for k,raw in blobs.items():
        path=root/artifacts[k]['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)


@pytest.mark.parametrize('rid',['M1396','M1463'])
def test_pair_positive_preserves_source_counts_and_full_alias(tmp_path,rid):
    root,e,b=fixture(tmp_path,rid);r,d=project(e,verified_source(root,e))
    assert r['catalog_fields']==json.loads(b['catalog_fields'])['fields']
    assert len(r['catalog_fields'])==(11 if rid=='M1396' else 10)
    assert d['curve']==json.loads(b['original_detail'])['curve'] and len(d['curve'])==25
    assert d['metrics']['periods']['full']['observations']==731 and d['metrics']['additional_lag_unit']=='day'
    assert d['metrics']['periods']['full']==json.loads(b['original_detail'])['metrics']['periods']['full']
    assert d['metrics']['same_instrument_benchmark']['full']==r['benchmark_reference']['metrics'] | {
        'sharpe':.2,'start':'2023-01-01','end':'2024-12-31','annualization':365}
    assert d['lab_counts']['new_control_configurations']==0 and r['benchmark_reference']['id']=='M1258'
    assert r['monthly'] is None and r['benchmark_curve']==[]
    registry=dict(schema_version='quantgraph-approved-lab-display-sources/v1',records=[e])
    a,z=tmp_path/'first',tmp_path/'rebuild';status=prepare({'synthetic':root},a,registry=registry);prepare({'synthetic':root},z,registry=registry)
    assert status['active_merge_status'].startswith('BLOCKED_') and status['new_execution_trials']==0
    assert {f.relative_to(a):f.read_bytes() for f in a.rglob('*') if f.is_file()}=={f.relative_to(z):f.read_bytes() for f in z.rglob('*') if f.is_file()}
    with pytest.raises(ValueError):prepare({'synthetic':root},a,registry=registry)


@pytest.mark.parametrize('rid',['M1396','M1463'])
@pytest.mark.parametrize('change',['wrong_contract','missing_contract','wrong_manifest_contract','kind','cycle','source_hash','path','ref_kind','private',
                                  'current_publication_kind','previous_publication_hash'])
def test_pair_source_guards(tmp_path,rid,change):
    root,e,b=fixture(tmp_path,rid)
    if change=='wrong_contract':e['source_contract']=CONTRACTS['M1463' if rid=='M1396' else 'M1396']
    elif change=='missing_contract':e.pop('source_contract')
    elif change=='source_hash':
        (root/e['artifacts']['summary']['path']).write_bytes(b['summary']+b' ')
        with pytest.raises(ValueError):verified_source(root,e)
        return
    elif change=='path':
        e['artifacts']['summary']['path']+='/../../escape'
        with pytest.raises(ValueError):verified_source(root,e)
        return
    elif change in ['current_publication_kind','previous_publication_hash']:
        p=json.loads(b['publication_manifest'])
        if change=='current_publication_kind':p['schema']='NATIVE_GRAPH_MANIFEST'
        else:p['previous_publication_manifest']['sha256']='0'*64
        b['publication_manifest']=encoded(p)
    elif change in ['wrong_manifest_contract','kind','cycle']:
        m=json.loads(b['result_manifest'])
        if change=='wrong_manifest_contract':m['source_contract']='CATALOG_RSI5_FULLCASH_V1'
        elif change=='kind':m['manifest_kind']='PRIVATE_RESULT_MANIFEST'
        else:m['files']['graph-record.json']={}
        b['result_manifest']=encoded(m)
    else:
        r=json.loads(b['record'])
        if change=='ref_kind':r['related_results'][0]['manifest_kind']='NATIVE'
        else:r['limitations'].append('libfile_private_annotation')
        b['record']=encoded(r)
    with pytest.raises(ValueError):project(e,b)


@pytest.mark.parametrize('rid',['M1396','M1463'])
@pytest.mark.parametrize('change',['fraction95','fee_exclusive','promoted','control_id','control95','control_OOS','new_control',
    'new_projection_control','control_not_released','wrong_control_pin','benchmark_count','field_scope','scope_complete',
    'wrong_fee','wrong_lag','full_alias','null_to_zero','double_scale','731_points','curve_units','rules','monthly','economic_provenance'])
def test_pair_semantic_guards_after_repinning(tmp_path,rid,change):
    root,e,b=fixture(tmp_path,rid)
    obj={k:json.loads(b[k]) for k in ['record','detail','summary','rules','protocol','control_reference','control_release','original_detail']}
    r,d,s,rules,p,control,release,old=obj.values()
    if change=='fraction95':rules['capital']['fraction']='0.95';p['capital']=rules['capital']
    elif change=='fee_exclusive':rules['capital']['entry_fee_inclusive']=False;p['capital']=rules['capital']
    elif change=='promoted':r['research_fidelity']='STRICT'
    elif change=='control_id':control['id']='M1358'
    elif change=='control95':control['allocation']='95%'
    elif change=='control_OOS':control['window_OOS']=True
    elif change=='new_control':s['new_controls']=1
    elif change=='new_projection_control':d['projection_activity']['new_controls']=1
    elif change=='control_not_released':release['consumers']=[]
    elif change=='wrong_control_pin':s['control_remote_commit']='0'*40
    elif change=='benchmark_count':r['benchmark_reference']['new_controls_for_this_strategy']=1
    elif change=='field_scope':r['catalog_fields']['unexpected']='private value'
    elif change=='scope_complete':r['catalog_public_scope']['complete_original_fields_public']=rid!='M1396'
    elif change=='wrong_fee':
        next(v for v in s['cases'] if v['case']=='fee0')['fee_bps']=8;r['results']={v['case']:v for v in s['cases']}
    elif change=='wrong_lag':
        next(v for v in s['cases'] if v['case']=='delay2')['delay_bars']=1;r['results']={v['case']:v for v in s['cases']}
    elif change=='full_alias':d['metrics']['periods']['full']['cagr']=.99
    elif change=='null_to_zero':d['metrics']['capital_state']['terminal_pending']=0
    elif change=='double_scale':
        for point in old['curve']:point['equity']/=100000
        d['curve']=old['curve'];b['curve']=encoded(old['curve'])
    elif change=='731_points':d['curve_meta']['returned_points']=731
    elif change=='curve_units':d['curve_meta']['equity_unit']='USDT'
    elif change=='rules':r['rules']['entry']='invented'
    elif change=='monthly':r['monthly']={'invented':True}
    elif change=='economic_provenance':r['economic_basis']['status']='SOURCE_VERIFIED'
    b.update({k:encoded(v) for k,v in obj.items()});seal(root,e,b)
    with pytest.raises(ValueError):project(e,b)


def test_pair_reuse_one_control_and_merge_keep_existing_notes(tmp_path):
    controls=set()
    for rid in CONTRACTS:
        parent=tmp_path/rid;parent.mkdir();root,e,b=fixture(parent,rid)
        r,d=project(e,verified_source(root,e));controls.add(r['benchmark_reference']['id'])
        snapshot,receipt,shard=active(parent,r,d)
        assets,envelope=merge_snapshot([r],[d],snapshot,digest(encoded(receipt)),receipt['active_batch'])
        row=json.loads(gzip.decompress(assets[shard]))[rid]
        assert row['note_marker']=='unchanged' and len(row['related_results'])==3 and row['audit']=={'retained':'original'}
        assert set(envelope['results'][0])=={'origin_run_id','variant_id','manifest_sha256','record_id','detail_path','detail_sha256'}
        for path,raw in assets.items():
            target=snapshot/'assets'/path[1:];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            receipt['files'][path]=dict(sha256=digest(raw),bytes=len(raw))
        (snapshot/'active-snapshot.json').write_bytes(encoded(receipt))
        assert merge_snapshot([r],[d],snapshot,digest(encoded(receipt)),receipt['active_batch'])[0]=={}
        changed=deepcopy(d);changed['name']='different frozen bytes'
        with pytest.raises(ValueError,match='different bytes'):
            merge_snapshot([r],[changed],snapshot,digest(encoded(receipt)),receipt['active_batch'])
    assert controls=={'M1258'}

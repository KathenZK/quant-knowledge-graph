"""Synthetic public-only M1347 contract; no Lab data or source execution in CI."""
import calendar
from copy import deepcopy
import gzip
import json

import pytest

from quantgraph.graph import lab_display_m1347 as mod
from quantgraph.graph.lab_display_projection import (
    digest, encoded, encode_asset, merge_snapshot, prepare, project, verified_source,
)
from test_lab_display_projection import active


def derivation(b):
    """Synthetic equivalent of the already approved public v1-to-v2 export."""
    old=json.loads(b['origin_detail']); record=json.loads(b['origin_record'])
    for name in ['same_instrument_benchmark','additional_native_bar_lag']:
        old['metrics'][name]['full']=deepcopy(old['metrics'][name]['2023-2024'])
    fees=old['metrics']['cost_sensitivity']
    old['metrics']['cost_sensitivity']={str(f):dict(deepcopy(fees[n]),full=deepcopy(fees[n]['2023-2024']))
                                      for n,f in [('fee0',0),('fee20',20)]}
    meta=dict(version=2,period_aliases={'full':'2023-2024'},fee_labels_bps=['0','20'],
        retained_slippage_bps_each_side=2,v1_detail_sha256=digest(b['origin_detail']),summary_sha256=digest(b['summary']),
        new_strategy_configurations=0,new_controls=0,
        explanation='Default full-period consumer and numeric bps labels; all values, nulls and25sourcepoints unchanged')
    old['display_projection']=meta;record['display_projection']=deepcopy(meta)
    b['detail']=encoded(old);b['record']=encoded(record)


def seal(root,e,b):
    """Rebind outer display and publication hashes after an intentional mutation."""
    if 'result_manifest' not in b:
        b['result_manifest']=encoded(dict(schema=mod.SCHEMA,manifest_kind=mod.KIND,id=mod.ID,
            returned_points=25,metrics_observations=731,normalization_operations=0,
            original_research_counts=dict(strategy_configurations=4,new_controls=0),
            this_projection_counts=dict(strategy_configurations=0,new_controls=0),
            fixed_original_source_C0_and_results_unchanged=True))
    m=json.loads(b['result_manifest'])
    for key,roles in [('files',['curve','detail','record']),('source_files',['origin_detail','origin_record','origin_curve','summary'])]:
        m[key]=[dict(path=mod.PATHS[k].rsplit('/',1)[-1],bytes=len(b[k]),sha256=digest(b[k])) for k in roles]
    m['script_sha256']=digest(b['projection_script']);b['result_manifest']=encoded(m)
    if 'publication_manifest' not in b:
        b['publication_manifest']=encoded(dict(schema='M1347-fixed-publication/v1',id=mod.ID,delivery_revision=2,
            first_publication_manifest=True,source_commit=mod.ORIGIN,C0_sha256=digest(b['C0']),
            active_graph_projection=mod.PREFIX+mod.V2.rstrip('/')))
    pub=json.loads(b['publication_manifest'])
    pub['files']=[dict(path=mod.PREFIX+mod.PATHS[k],bytes=len(raw),sha256=digest(raw))
                  for k,raw in b.items() if k!='publication_manifest']
    b['publication_manifest']=encoded(pub)
    e['artifacts']={k:dict(path=mod.PREFIX+mod.PATHS[k],sha256=digest(raw),bytes=len(raw),
        url=f'https://github.com/KathenZK/quant-research-lab/blob/{mod.PIN}/{mod.PREFIX+mod.PATHS[k]}') for k,raw in b.items()}
    for k,raw in b.items():
        p=root/e['artifacts'][k]['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)


def fixture(tmp_path,monkeypatch):
    e=dict(id=mod.ID,group='synthetic',lab_commit=mod.PIN,run_id=mod.RUN,variant_id=mod.VARIANT,
        fidelity_class='HYPOTHESIS',source_contract=mod.CONTRACT,projection_profile=mod.PROFILE,manifest_kind=mod.KIND)
    rules={k:'Synthetic '+k for k in mod.RULE_KEYS}
    rules.update(id=mod.ID,classification=mod.FIDELITY+' / '+mod.EXECUTION+'; strict0',economic_hypothesis='Synthetic only',
        capital=dict(initial_cash='100000',fraction='1',entry_fee_inclusive=True,Decimal_precision=50),
        cost_cases=deepcopy(mod.COSTS),benchmark=dict(new_control_configurations=0,comparison='One existing base-cost control; no matched-cost fee0/20 controls'))
    metric=dict(total_return=-.24,cagr=-.1,max_drawdown=-.3,sharpe_zero_cash=None,observations=731,final_equity=76000.0)
    control=dict(id='M1258',source_commit='a'*40,input_sha256='f'*64,metrics=deepcopy(metric))
    catalog=dict(schema='catalog-public-excerpt/v1',fields={k:'Synthetic '+k for k in sorted(mod.FIELDS)},
        rule_original_operational_excerpt='Synthetic permitted excerpt',full_original_rule_public=False,source_webpage_fulltext_verified=False)
    catalog['fields'].update(id=mod.ID,source_url='https://example.org/source')
    blobs={'control_reference':encoded(control),'public_catalog':encoded(catalog),
           'license':b'Synthetic permission only','projection_script':b'# Synthetic public derivation only',
           'verification':encoded({'status':'SYNTHETIC'}),'correction_note':b'Synthetic correction'}
    rules['benchmark']['reference_sha256']=digest(blobs['control_reference'])
    protocol=dict(deepcopy(rules),source_url=catalog['fields']['source_url'],cases=deepcopy(mod.COSTS))
    blobs.update(root_rules=encoded(rules),protocol=encoded(protocol))
    c0=dict(schema='M1347-catalog-code-freeze/v1',id=mod.ID,new_controls=0,
        source_rule_sha256=digest(blobs['root_rules']),input_sha256='f'*64,
        files=[dict(path=mod.PATHS[k],sha256=digest(blobs[k]),bytes=len(blobs[k]))
               for k in ['public_catalog','root_rules','protocol','control_reference']])
    blobs['C0']=encoded(c0)
    cases=[dict(deepcopy(metric),case=c['name'],kind='STRATEGY',fee_bps=c['fee_bps_each_side'],
                slippage_bps=2,delay_bars=c['delay_bars'],terminal_pending=None) for c in mod.COSTS]
    summary=dict(id=mod.ID,classification=mod.FIDELITY,execution_class=mod.EXECUTION,
                 strategy_configurations=4,new_controls=0,strict_reproductions=0,cases=cases)
    blobs['summary']=encoded(summary)
    dates=['2023-01-01']+[f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}' for y in [2023,2024] for m in range(1,13)]
    curve=[dict(date=dt,equity=1.0-n*.01,drawdown=-n*.01) for n,dt in enumerate(dates)]
    blobs['curve']=blobs['origin_curve']=encoded(curve)
    view=dict(metric,sharpe=None,annualization=365,start='2023-01-01',end='2024-12-31')
    periods={'2023-2024':view}
    audit=dict(strict_reproductions=0,source_verification_status='CATALOG_ONLY_ORIGINAL_WEBPAGE_UNVERIFIED',
               original_runtime_equivalence=False,PIT='NOT_PROVEN')
    record=dict(id=mod.ID,name='Synthetic only',status='tested_proxy_only',reason='Four negative cases; synthetic only',
        audit=audit,families=['synthetic'],tested_variants=1,configuration_runs=4,new_control_runs=0,
        research_classification=mod.FIDELITY,implementations=[dict(variant_id=mod.VARIANT,family='synthetic',origin_run_id=mod.RUN,fidelity_class='HYPOTHESIS')])
    detail=dict(id=mod.ID,name='Synthetic only',run_id=mod.RUN,origin_run_id=mod.RUN,variant_id=mod.VARIANT,family='synthetic',
        fidelity_class='HYPOTHESIS',execution_class=mod.EXECUTION,research_classification=mod.FIDELITY,
        metrics=dict(periods={'full':deepcopy(view),'2023-2024':deepcopy(view)},same_instrument_benchmark=deepcopy(periods),
            additional_native_bar_lag=deepcopy(periods),cost_sensitivity={'fee0':deepcopy(periods),'fee20':deepcopy(periods)},
            capital_state=dict(initial_cash_usdt=100000,final_equity_usdt=76000.0,final_position_open=True,terminal_pending=None)),
        curve=curve,curve_meta=dict(observations=731,total_observations=731,returned_points=25,equity_unit='initial_capital_multiple',
            drawdown_unit='fraction',benchmark_curve_available=False),
        spec=dict(rule_excerpt=catalog['rule_original_operational_excerpt'],source_url=catalog['fields']['source_url'],assumptions=['Synthetic only'],
            params=dict(timeframe='1d',calendar='UTC_24_7',entry='day=month_length-2 at close',exit='day=3 at close',fraction='1',
                entry_fee_inclusive=True,fee_bps=8,slippage_bps=2,lag_bars=1)),
        lineage=dict(C0_sha256=digest(blobs['C0']),input_sha256='f'*64,control_reference_sha256=digest(blobs['control_reference'])),
        limitations=['Four negative results, no OOS; synthetic only'])
    blobs.update(origin_record=encoded(record),origin_detail=encoded(detail))
    derivation(blobs)
    monkeypatch.setattr(mod,'CORE_SHA',{k:digest(blobs[k]) for k in mod.CORE_SHA})
    root=tmp_path/'source';root.mkdir();seal(root,e,blobs)
    return root,e,blobs


def test_project_preserves_units_rules_types_and_no_cycle(tmp_path,monkeypatch):
    root,e,b=fixture(tmp_path,monkeypatch);before=deepcopy(b)
    r,d=project(e,verified_source(root,e))
    assert b==before and r['id']=='M1347' and len(r['catalog_fields'])==10 and '规则' not in r['catalog_fields']
    assert r['full_original_rule_public'] is False and r['economic_basis']['paper'] is None
    assert r['rules']==d['spec']['params']['rules'] and r['benchmark_reference']['matched_cost_controls_available'] is False
    assert d['metrics']['periods']['full']['sharpe'] is None and d['metrics']['additional_lag_unit']=='day'
    assert d['curve']==json.loads(b['curve']) and len(d['curve'])==25 and d['curve_meta']['observations']==731
    assert d['manifest_kind']==d['lineage']['manifest_kind']==r['related_results'][0]['manifest_kind']==mod.KIND
    assert d['lineage']['manifest_sha256']==digest(b['result_manifest'])
    assert digest(encoded(d)) not in b['result_manifest'].decode()  # Source hashes Lab detail, not Graph output.
    assert d['projection_activity']==dict(new_strategy_trials=0,new_controls=0)
    assert 'entity_id' not in r and 'definition_revision' not in d and not r['definition_revision_bound']


@pytest.mark.parametrize('field,value',[('id','M1266'),('source_contract','UNKNOWN'),('projection_profile','UNKNOWN'),
    ('manifest_kind','PUBLIC_DERIVED_DISPLAY_MANIFEST'),('lab_commit','a'*40),('run_id','wrong'),('variant_id','wrong'),('fidelity_class','ADAPTED')])
def test_identity_contract_pin_rejected_before_read(tmp_path,monkeypatch,field,value):
    root,e,b=fixture(tmp_path,monkeypatch);e[field]=value
    with pytest.raises(ValueError):verified_source(root,e)


@pytest.mark.parametrize('change',['hash','traversal','another_id','private_role','url','float_bytes','duplicate_pub','pub_omission','cycle','wrong_manifest_kind','wrong_manifest_schema'])
def test_hash_path_allowlist_and_manifest_guards(tmp_path,monkeypatch,change):
    root,e,b=fixture(tmp_path,monkeypatch)
    if change in ['hash','traversal','another_id','url','float_bytes']:
        ref=e['artifacts']['detail']
        if change=='hash':ref['sha256']='0'*64
        elif change=='traversal':ref['path']=mod.PREFIX+'../../private.json'
        elif change=='another_id':ref['path']=ref['path'].replace('M1347','M1266')
        elif change=='url':ref['url']=ref['url'].replace(mod.PIN,'a'*40)
        else:ref['bytes']=float(ref['bytes'])
    elif change=='private_role':e['artifacts']['private_nav']=dict(e['artifacts']['curve'])
    else:
        role='publication_manifest' if change.startswith('pub') or change=='duplicate_pub' else 'result_manifest'
        v=json.loads(b[role])
        if change=='duplicate_pub':v['files'].append(v['files'][0])
        elif change=='pub_omission':v['files']=v['files'][1:]
        elif change=='cycle':v['files'].append(dict(path='public-display-manifest.json',sha256='0'*64,bytes=1))
        elif change=='wrong_manifest_kind':v['manifest_kind']='NATIVE'
        else:v['schema']='unknown'
        b[role]=encoded(v)
        # Rebind only this object's outer digest, deliberately preserving the invalid contract.
        ref=e['artifacts'][role];ref.update(sha256=digest(b[role]),bytes=len(b[role]));(root/ref['path']).write_bytes(b[role])
        if role=='result_manifest':
            pub=json.loads(b['publication_manifest'])
            for f in pub['files']:
                if f['path']==ref['path']:f.update(sha256=ref['sha256'],bytes=ref['bytes'])
            b['publication_manifest']=encoded(pub);pr=e['artifacts']['publication_manifest']
            pr.update(sha256=digest(b['publication_manifest']),bytes=len(b['publication_manifest']));(root/pr['path']).write_bytes(b['publication_manifest'])
    with pytest.raises(ValueError):project(e,verified_source(root,e))


@pytest.mark.parametrize('role,path,value',[
 ('record',['configuration_runs'],4.0),('record',['configuration_runs'],True),('record',['new_control_runs'],False),
 ('record',['tested_variants'],1.0),('record',['tested_variants'],True),('record',['new_control_runs'],1),
 ('record',['research_classification'],'ADAPTED'),('record',['definition_revision'],'invented'),
 ('record',['audit','strict_reproductions'],False),('record',['audit','original_runtime_equivalence'],0),
 ('record',['audit','source_verification_status'],'VERIFIED'),
 ('detail',['curve_meta','observations'],731.0),('detail',['curve_meta','returned_points'],731),
 ('detail',['curve_meta','benchmark_curve_available'],0),('detail',['curve_meta','equity_unit'],'USDT'),
 ('detail',['spec','params','entry_fee_inclusive'],1),('detail',['spec','params','lag_bars'],2),
 ('detail',['metrics','periods','full','sharpe'],0),('detail',['metrics','periods','full','total_return'],.5),
 ('detail',['metrics','capital_state','terminal_pending'],0),('detail',['curve',0,'equity'],True),
 ('detail',['limitations'],['libfile_privateexample']),('detail',['spec','assumptions'],['api_key=secret']),
 ('summary',['strategy_configurations'],4.0),('summary',['new_controls'],False),
 ('summary',['cases',1,'fee_bps'],8),('summary',['cases',3,'delay_bars'],1),('summary',['cases',0,'terminal_pending'],0),
 ('result_manifest',['normalization_operations'],False),('result_manifest',['returned_points'],25.0),
 ('result_manifest',['original_research_counts','strategy_configurations'],4.0),
 ('result_manifest',['this_projection_counts','new_controls'],False),
 ('publication_manifest',['delivery_revision'],2.0),('publication_manifest',['delivery_revision'],True),
])
def test_complete_rebinding_still_rejects_semantic_changes(tmp_path,monkeypatch,role,path,value):
    root,e,b=fixture(tmp_path,monkeypatch)
    # Mutate the original too, then derive consistently, to reach semantic guards
    # rather than failing merely because the public v1-to-v2 alias changed.
    target={'record':'origin_record','detail':'origin_detail'}.get(role,role)
    v=json.loads(b[target]);node=v
    for key in path[:-1]:node=node[key]
    node[path[-1]]=value;b[target]=encoded(v)
    derivation(b);seal(root,e,b)
    with pytest.raises(ValueError):project(e,verified_source(root,e))


@pytest.mark.parametrize('role',['public_catalog','root_rules','protocol','C0','control_reference','license','projection_script'])
def test_frozen_permission_rule_or_control_cannot_be_rebound(tmp_path,monkeypatch,role):
    root,e,b=fixture(tmp_path,monkeypatch);b[role]+=b'\n';seal(root,e,b)
    with pytest.raises(ValueError,match='Frozen'):project(e,verified_source(root,e))


def test_offline_double_build_and_immutable_directory(tmp_path,monkeypatch):
    root,e,b=fixture(tmp_path,monkeypatch);reg=dict(schema_version='quantgraph-approved-lab-display-sources/v1',records=[e])
    outputs=[tmp_path/'first',tmp_path/'second']
    for out in outputs:
        status=prepare({'synthetic':root},out,registry=reg)
        assert status['records']==1 and status['new_execution_trials']==0 and status['active_merge_status'].startswith('BLOCKED_')
        assert not status['native_corpus_imported'] and not status['deployed'] and not (out/'site-sync-candidate.json').exists()
    assert {p.relative_to(outputs[0]):p.read_bytes() for p in outputs[0].rglob('*') if p.is_file()}=={
        p.relative_to(outputs[1]):p.read_bytes() for p in outputs[1].rglob('*') if p.is_file()}
    manifest=json.loads((outputs[0]/'manifest.json').read_bytes())
    assert manifest['manifest_kind']=='LAB_DISPLAY_ARTIFACT_INDEX' and manifest['source_manifest_kinds']==[mod.KIND]
    with pytest.raises(ValueError,match='immutable'):prepare({'synthetic':root},outputs[0],registry=reg)


def test_merge_preserves_old_records_and_notes_and_replays(tmp_path,monkeypatch):
    root,e,b=fixture(tmp_path,monkeypatch);r,d=project(e,verified_source(root,e));snap,receipt,shard=active(tmp_path,r,d)
    assets,envelope=merge_snapshot([r],[d],snap,digest(encoded(receipt)),receipt['active_batch'])
    row=json.loads(gzip.decompress(assets[shard]))[r['id']]
    assert row['audit']=={'retained':'original'} and row['note_marker']=='unchanged' and len(row['related_results'])==3
    assert set(envelope['results'][0])=={'origin_run_id','variant_id','manifest_sha256','record_id','detail_path','detail_sha256'}
    run=json.loads(assets['/data/manifest.json'])['runs'][-1]
    assert run==dict(run_id=mod.RUN,manifest_kind=mod.KIND,source_manifest_sha256=digest(b['result_manifest']))
    for path,raw in assets.items():
        p=snap/'assets'/path[1:];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        receipt['files'][path]=dict(sha256=digest(raw),bytes=len(raw))
    (snap/'active-snapshot.json').write_bytes(encoded(receipt))
    assert merge_snapshot([r],[d],snap,digest(encoded(receipt)),receipt['active_batch'])[0]=={}
    d['name']='different bytes'
    with pytest.raises(ValueError,match='different bytes'):merge_snapshot([r],[d],snap,digest(encoded(receipt)),receipt['active_batch'])


@pytest.mark.parametrize('change',['kind','contract','revision','seed','run_collision','orphan'])
def test_merge_typed_kind_active_binding_and_collision_gates(tmp_path,monkeypatch,change):
    root,e,b=fixture(tmp_path,monkeypatch);r,d=project(e,verified_source(root,e));snap,receipt,shard=active(tmp_path,r,d)
    if change=='kind':r['implementations'][0]['manifest_kind']='OTHER'
    elif change=='contract':d['source_contract']='UNKNOWN'
    elif change=='revision':receipt['bindings'][mod.ID]['definition_revision']='wrong'
    elif change=='seed':receipt['bundled_seed']=True
    elif change=='run_collision':
        p=snap/'assets/data/manifest.json';m=json.loads(p.read_bytes());m['runs'].append(dict(run_id=mod.RUN,manifest_kind='OTHER',source_manifest_sha256='a'*64))
        raw=encoded(m);p.write_bytes(raw);receipt['files']['/data/manifest.json']=dict(bytes=len(raw),sha256=digest(raw))
    else:
        path='/data/implementations/'+digest((mod.RUN+'\n'+mod.VARIANT).encode())[:24]+'.json.gz';raw=encode_asset({'old':'orphan'})
        p=snap/'assets'/path[1:];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);receipt['files'][path]=dict(bytes=len(raw),sha256=digest(raw))
    (snap/'active-snapshot.json').write_bytes(encoded(receipt))
    with pytest.raises(ValueError):merge_snapshot([r],[d],snap,digest(encoded(receipt)),receipt['active_batch'])


@pytest.mark.parametrize('route',['base','fee0','fee20','delay2','benchmark'])
@pytest.mark.parametrize('field',['total_return','cagr','max_drawdown','sharpe_zero_cash','final_equity'])
@pytest.mark.parametrize('bad',['numeric_string','boolean'])
def test_financial_number_contract_after_consistent_rebinding(tmp_path,monkeypatch,route,field,bad):
    root,e,b=fixture(tmp_path,monkeypatch)
    old=json.loads(b['origin_detail']);summary=json.loads(b['summary'])
    view=(old['metrics']['periods'] if route=='base' else old['metrics']['additional_native_bar_lag'] if route=='delay2'
          else old['metrics']['same_instrument_benchmark'] if route=='benchmark' else old['metrics']['cost_sensitivity'][route])
    value='-0.1' if bad=='numeric_string' else True
    for period in view.values():
        period[field]=value
        if field=='sharpe_zero_cash':period['sharpe']=value
    if route!='benchmark':
        next(c for c in summary['cases'] if c['case']==route)[field]=value
    # For benchmark, the control remains independently frozen. The public
    # consumer must reject the wrong type rather than coerce against it.
    b['origin_detail']=encoded(old);b['summary']=encoded(summary)
    derivation(b);seal(root,e,b)
    with pytest.raises(ValueError):project(e,verified_source(root,e))


@pytest.mark.parametrize('field',['total_return','cagr','max_drawdown','sharpe_zero_cash','final_equity'])
@pytest.mark.parametrize('value',['-0.1',True,False])
def test_matching_bad_scalar_is_not_a_metric_including_control(field,value):
    metric=dict(total_return=-.1,cagr=-.05,max_drawdown=-.2,sharpe_zero_cash=None,final_equity=90000.0,observations=731)
    metric[field]=value
    view=dict(metric,sharpe=metric['sharpe_zero_cash'],annualization=365,start='2023-01-01',end='2024-12-31')
    with pytest.raises(ValueError,match='number'):mod.match_metric(view,metric)

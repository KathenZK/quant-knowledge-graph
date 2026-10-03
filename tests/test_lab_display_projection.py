"""Market-free tests of the bounded display adapter and current-snapshot merge."""
from copy import deepcopy
import gzip
import json

import pytest

from quantgraph.graph.lab_display_projection import (
    MANIFEST_KIND, digest, encoded, encode_asset, merge_snapshot, prepare, project, verified_source,
)


def source(tmp_path, rid='M0300', *, curve=True):
    root=tmp_path/rid;root.mkdir()
    prefix=f'research/public-strategies/{rid}/'
    fidelity='HYPOTHESIS' if rid in {'M0298','M0304'} else 'ADAPTED'
    protocol=dict(record_id=rid,execution={'initial_cash':100000},
        evaluation={'start':'2024-01-01','end_exclusive':'2024-01-03'},
        source={'url':'https://example.org/pinned/source'},parameters={'signal':'synthetic only'})
    metric=dict(start='2024-01-01',end='2024-01-03',daily_observations=2,observations=576,
                total_return=.1,annualized_return=.2,sharpe=.3,max_drawdown=-.04 if rid=='M0298' else .04)
    summary=dict(id=rid,fidelity_class=fidelity,strategy_configurations=4,control_configurations=1,
        results={k:{'configuration':{'fee_bps':fee,'delay_bars':lag},'metrics':metric}
                 for k,fee,lag in [('base',8,1),('fee0',0,1),('fee20',20,1),('delay2',8,2),('buyhold',8,1)]})
    blobs=dict(protocol=encoded(protocol),summary=encoded(summary))
    blobs['result_manifest']=encoded({'files':{'summary.json':{'sha256':digest(blobs['summary']),'bytes':len(blobs['summary'])}}})
    ref=dict(origin_run_id='synthetic-'+rid,variant_id=rid+'-variant',fidelity_class=fidelity,
             protocol_sha256=digest(blobs['protocol']),manifest_sha256=digest(blobs['result_manifest']))
    record=dict(id=rid,name='Synthetic only',families=['synthetic'],audit={},related_results=[ref],limitations=[])
    if rid=='M0304':record=dict(record_id=rid,name='Synthetic summary only',family='synthetic',audit={},**ref)
    blobs['record']=encoded(record)
    if curve:
        if rid=='M0298':
            blobs['curve']=b'valuation_time_utc,equity,drawdown_from_full5m\n2024-01-02T00:00:00Z,99000,-0.04\n2024-01-03T00:00:00Z,110000,0\n'
            blobs['curve_meta']=encoded({'sampled_curve_sha256':digest(blobs['curve'])})
        else:
            blobs['curve']=b'date,equity,nav,drawdown\n2024-01-01,99000,0.99,-0.04\n2024-01-02,110000,1.1,0\n'
    refs={}
    for role,raw in blobs.items():
        path=prefix+role+'.json' if role!='curve' else prefix+'curve.csv'
        refs[role]=dict(path=path,sha256=digest(raw),bytes=len(raw),url=f'https://github.com/KathenZK/quant-research-lab/blob/{"a"*40}/{path}')
    publication=encoded(dict(id=rid,files=[{k:v for k,v in ref.items() if k!='url'} for ref in refs.values()]))
    blobs['publication_manifest']=publication
    path=prefix+'publication-manifest.json'
    refs['publication_manifest']=dict(path=path,sha256=digest(publication),bytes=len(publication),url=f'https://github.com/KathenZK/quant-research-lab/blob/{"a"*40}/{path}')
    for role,raw in blobs.items():
        p=root/refs[role]['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    entry=dict(id=rid,group='synthetic',lab_commit='a'*40,run_id=ref_run(record),
               variant_id=rid+'-variant',fidelity_class=fidelity,artifacts=refs)
    return root,entry,blobs


def ref_run(record):
    return record.get('origin_run_id') or record['related_results'][0]['origin_run_id']


def test_actual_units_aliases_and_origin_kind(tmp_path):
    root,entry,blobs=source(tmp_path)
    record,detail=project(entry,verified_source(root,entry))
    assert detail['fidelity_class']=='ADAPTED'
    assert detail['curve'][0]['equity']==.99  # First loss is not rebased to one.
    assert detail['curve'][0]['drawdown']==pytest.approx(-.01)
    assert detail['metrics']['periods']['full']['max_drawdown']==-.04
    assert detail['metrics']['periods']['full']['cagr']==.2
    assert set(detail['metrics']['cost_sensitivity'])=={'0','20'}
    assert detail['lineage']['manifest_kind']==MANIFEST_KIND
    assert not detail['lineage']['definition_revision_bound']
    assert record['tested_variants']==1 and detail['lab_counts']['strategy_configurations']==4


def test_boundary_timestamps_and_negative_mdd(tmp_path):
    root,entry,blobs=source(tmp_path,'M0298')
    _,d=project(entry,verified_source(root,entry))
    assert d['curve'][0]['date']=='2024-01-01'
    assert d['curve'][0]['valuation_time_utc']=='2024-01-02T00:00:00Z'
    assert d['curve'][-1]['date']=='2024-01-02'
    assert d['metrics']['periods']['full']['sharpe']==.3


def test_summary_only_cannot_invent_curve(tmp_path):
    root,entry,blobs=source(tmp_path,'M0304',curve=False)
    _,d=project(entry,verified_source(root,entry))
    assert d['curve']==[] and not d['curve_meta']['public_curve_available']
    assert any('不补造曲线' in v for v in d['limitations'])


@pytest.mark.parametrize('change', ['hash','path','identity','url','symlink','publication'])
def test_bad_source_boundary_rejected(tmp_path,change):
    root,entry,blobs=source(tmp_path)
    ref=entry['artifacts']['summary']
    if change=='hash':(root/ref['path']).write_bytes(blobs['summary']+b' ')
    elif change=='path':ref['path']=ref['path'].rsplit('/',1)[0]+'/../../escape'
    elif change=='identity':entry['id']='M9999'
    elif change=='url':ref['url']='https://example.org/unpinned'
    elif change=='symlink':
        target=root/ref['path'];target.unlink();target.symlink_to(root/'missing')
    else:
        raw=blobs['summary']+b' ';(root/ref['path']).write_bytes(raw)
        ref.update(sha256=digest(raw),bytes=len(raw))
    with pytest.raises(ValueError):verified_source(root,entry)


@pytest.mark.parametrize('change', ['id','run','curve','fee','private'])
def test_projection_rejects_wrong_identity_units_and_private_fields(tmp_path,change):
    _,entry,blobs=source(tmp_path)
    if change in {'id','run'}:
        r=json.loads(blobs['record'])
        if change=='id':r['id']='M9999'
        else:r['related_results'][0]['origin_run_id']='wrong'
        blobs['record']=encoded(r)
    elif change=='curve':blobs['curve']=blobs['curve'].replace(b'0.99',b'1.99')
    elif change=='fee':
        r=json.loads(blobs['summary']);r['results']['fee0']['configuration']['fee_bps']=8
        blobs['summary']=encoded(r)
        m=json.loads(blobs['result_manifest']);m['files']['summary.json']=dict(sha256=digest(blobs['summary']),bytes=len(blobs['summary']))
        blobs['result_manifest']=encoded(m)
        r=json.loads(blobs['record']);r['related_results'][0]['manifest_sha256']=digest(blobs['result_manifest']);blobs['record']=encoded(r)
    else:
        r=json.loads(blobs['record']);r['limitations']=['api_key=secret'];blobs['record']=encoded(r)
    with pytest.raises(ValueError):project(entry,blobs)


def active(tmp_path,record,detail):
    root=tmp_path/'active';root.mkdir()
    rid=record['id'];eid='entity-'+rid;revision='revision-1';shard='/data/workscope/records-0.json.gz'
    old=[dict(origin_run_id='old',variant_id=f'old-{n}',manifest_sha256=str(n)*64) for n in [1,2]]
    row=dict(id=rid,name='original',definition_revision=revision,research_scope={'entity_id':eid},
             audit={'retained':'original'},note_marker='unchanged',related_results=old,
             implementations=deepcopy(old),tested_variants=2,families=['old'])
    values={'/data/manifest.json':dict(default_run='old',runs=[{'run_id':'old'}],details={},
                workscope_records={rid:shard},workscope_entities={eid:rid},historical_count=2294),
            '/catalog/manifest.json':{eid:{'file':'entity','kind':'strategy'}},
            '/catalog/details/entity.json.gz':dict(entity_id=eid,definition_revision=revision,source_native_ids=[rid]),
            shard:{rid:row,'OTHER':{'audit':'preserve','definition_revision':'untouched'}}}
    receipt=dict(schema_version='quantgraph-active-readback/v1',source='CURRENT_SITE_READBACK',bundled_seed=False,
                 active_batch='batch-'+'b'*64,bindings={rid:dict(entity_id=eid,definition_revision=revision)},files={})
    for path,value in values.items():
        raw=encode_asset(value) if path.endswith('.gz') else encoded(value)
        p=root/'assets'/path[1:];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        receipt['files'][path]=dict(sha256=digest(raw),bytes=len(raw))
    (root/'active-snapshot.json').write_bytes(encoded(receipt))
    return root,receipt,shard


def test_workscope_additive_merge_replay_and_immutable_conflict(tmp_path):
    _,e,b=source(tmp_path);record,detail=project(e,b)
    root,receipt,shard=active(tmp_path,record,detail)
    before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assets,envelope=merge_snapshot([record],[detail],root,digest(encoded(receipt)),receipt['active_batch'])
    merged=json.loads(gzip.decompress(assets[shard]))
    assert merged['OTHER']=={'audit':'preserve','definition_revision':'untouched'}
    assert merged[e['id']]['note_marker']=='unchanged'
    assert merged[e['id']]['audit']=={'retained':'original'}
    assert len(merged[e['id']]['related_results'])==3
    assert envelope['entities']==[] and len(envelope['results'])==1
    assert not any(p.startswith('/data/records/') for p in assets)
    assert before=={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    # Simulate a separately verified successor snapshot, not a real Site write.
    for path,raw in assets.items():
        p=root/'assets'/path[1:];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        receipt['files'][path]=dict(sha256=digest(raw),bytes=len(raw))
    (root/'active-snapshot.json').write_bytes(encoded(receipt))
    again,replay=merge_snapshot([record],[detail],root,digest(encoded(receipt)),receipt['active_batch'])
    assert not again and not replay['results']
    changed=deepcopy(detail);changed['name']='changed frozen result'
    with pytest.raises(ValueError,match='different bytes'):
        merge_snapshot([record],[changed],root,digest(encoded(receipt)),receipt['active_batch'])


@pytest.mark.parametrize('change',['receipt','seed','revision','scope','bytes'])
def test_current_binding_gates(tmp_path,change):
    _,e,b=source(tmp_path);r,d=project(e,b);root,receipt,shard=active(tmp_path,r,d)
    if change=='receipt':pin='0'*64
    else:
        if change=='seed':receipt['bundled_seed']=True
        if change=='revision':receipt['bindings'][e['id']]['definition_revision']='wrong'
        if change=='scope':
            p=root/'assets/data/manifest.json';m=json.loads(p.read_bytes());m['workscope_records']={};raw=encoded(m);p.write_bytes(raw)
            receipt['files']['/data/manifest.json']=dict(sha256=digest(raw),bytes=len(raw))
        if change=='bytes':(root/'assets'/shard[1:]).write_bytes(b'changed')
        (root/'active-snapshot.json').write_bytes(encoded(receipt));pin=digest(encoded(receipt))
    with pytest.raises(ValueError):merge_snapshot([r],[d],root,pin,receipt['active_batch'])


def test_offline_prepare_is_deterministic_blocked_and_nonoverwriting(tmp_path):
    root,e,_=source(tmp_path)
    registry=dict(schema_version='quantgraph-approved-lab-display-sources/v1',records=[e])
    a,b=tmp_path/'a',tmp_path/'b'
    status=prepare({'synthetic':root},a,registry=registry)
    prepare({'synthetic':root},b,registry=registry)
    assert status['active_merge_status'].startswith('BLOCKED_') and not status['ready_for_direct_site_sync']
    assert not (a/'site-sync-candidate.json').exists()
    assert {p.relative_to(a):p.read_bytes() for p in a.rglob('*') if p.is_file()}=={p.relative_to(b):p.read_bytes() for p in b.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='immutable'):prepare({'synthetic':root},a,registry=registry)


def test_future_explicit_adapted_id_needs_no_pilot_expansion(tmp_path):
    root,e,_=source(tmp_path,'M0260')
    record,detail=project(e,verified_source(root,e))
    assert record['id']=='M0260' and detail['fidelity_class']=='ADAPTED'


@pytest.mark.parametrize('identical',[False,True])
def test_pinned_orphan_implementation_is_immutable_without_index(tmp_path,identical):
    _,e,b=source(tmp_path);record,detail=project(e,b)
    root,receipt,shard=active(tmp_path,record,detail)
    key=digest((detail['run_id']+'\n'+detail['variant_id']).encode())[:24]
    path='/data/implementations/'+key+'.json.gz'
    raw=encode_asset(detail) if identical else encode_asset({'id':e['id'],'frozen':'old orphan'})
    p=root/'assets'/path[1:];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    receipt['files'][path]=dict(sha256=digest(raw),bytes=len(raw))
    (root/'active-snapshot.json').write_bytes(encoded(receipt))
    if not identical:
        with pytest.raises(ValueError,match='path has different bytes'):
            merge_snapshot([record],[detail],root,digest(encoded(receipt)),receipt['active_batch'])
    else:
        assets,envelope=merge_snapshot([record],[detail],root,digest(encoded(receipt)),receipt['active_batch'])
        assert assets[path]==raw and envelope['results'][0]['detail_sha256']==digest(raw)
        m=json.loads(assets['/data/manifest.json'])
        assert m['details'][detail['run_id']+'|'+detail['variant_id']]==key
    assert p.read_bytes()==raw

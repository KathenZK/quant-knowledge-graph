"""Reviewed metadata plus synthetic-only import/immutability boundary tests."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError

from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.catalog_projection import item
from quantgraph.graph.metadata_pilot import (
    card, digest, encoded, merge_record, prepare, project, read_below,
    read_bindings, validate, verified_blobs,
)
from quantgraph.graph.personal_catalog import PersonalCatalogRepository
from quantgraph.graph.private_intake import import_cards

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))
    return digest(path.read_bytes())


def index(root):
    rows = []
    for kind in ['strategies', 'factors']:
        for path in sorted((root / kind).glob('*.json')):
            v = json.loads(path.read_bytes())
            rows.append(dict(path=str(path.relative_to(root)), sha256=digest(path.read_bytes()),
                             bytes=path.stat().st_size, **{k:v[k] for k in ['record_id','entity_type','identity_namespace']}))
    write(root / 'index.json', dict(schema_version='quantgraph-metadata-index/v1', records=rows))


@pytest.fixture
def metadata(tmp_path):
    root = tmp_path / 'metadata'
    shutil.copytree(ROOT / 'metadata', root)
    return root


def test_committed_records_preserve_two_ids_and_no_fabricated_factor():
    rows = validate(ROOT / 'metadata')
    assert [r['record_id'] for r in rows] == ['M0256', 'M0259']
    assert rows[0]['lab']['counts'] == dict(strategy_configurations=4, controls=1, strict_reproductions=0, market_replays=1)
    assert not any(rows[1]['lab']['counts'].values())
    assert all(r['economic_basis']['paper_support'] == [] for r in rows)


@pytest.mark.parametrize('change,match', [
    (lambda v:v.update(native_source_id='M9999'), 'renumbered'),
    (lambda v:v['strategy_fields']['entry'].update(evidence=['imagined-proof']), 'does not resolve'),
    (lambda v:v.update(original_fulltext='not allowed'), 'Additional properties'),
])
def test_invalid_metadata_rejected(metadata, change, match):
    p = metadata / 'strategies/M0256.json'; v = json.loads(p.read_bytes()); change(v); write(p, v); index(metadata)
    with pytest.raises((ValueError, ValidationError), match=match): validate(metadata)


def test_index_is_exact_hash_size_and_identity(metadata):
    p = metadata / 'strategies/M0256.json'; p.write_bytes(p.read_bytes() + b' ')
    with pytest.raises(ValueError, match='digest'): validate(metadata)
    index(metadata); rows = json.loads((metadata/'index.json').read_bytes()); rows['records'][0]['record_id']='wrong'
    write(metadata/'index.json', rows)
    with pytest.raises(ValueError, match='identity'): validate(metadata)
    index(metadata); (metadata/'strategies/unlisted.json').write_bytes(p.read_bytes())
    with pytest.raises(ValueError, match='exactly'): validate(metadata)


def test_factor_contract_can_explicitly_remain_unresearched(metadata):
    factor = deepcopy(validate(metadata)[0])
    factor.update(record_id='SYNTHETIC_FACTOR', native_source_id='SYNTHETIC_FACTOR', entity_type='factor', lab=None)
    factor.pop('strategy_fields')
    factor['factor_fields'] = {k:dict(text='尚未核实', status='MISSING', evidence=[])
                              for k in ['formula','inputs','calculation','economic_meaning','use_cases','availability']}
    write(metadata/'factors/SYNTHETIC_FACTOR.json', factor); index(metadata)
    assert len(validate(metadata)) == 3


@pytest.mark.parametrize('name', ['/etc/passwd', '../elsewhere', 'a/../b', 'a\\b', './x'])
def test_path_escape_is_rejected(tmp_path, name):
    with pytest.raises(ValueError, match='Unsafe'): read_below(tmp_path, name)


def test_symlink_evidence_is_rejected(tmp_path):
    p = tmp_path/'outside'; p.mkdir(); (p/'x').write_bytes(b'x'); (tmp_path/'link').symlink_to(p, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'): read_below(tmp_path, 'link/x')


@pytest.fixture
def synthetic_lab(metadata, tmp_path):
    """Small invented market-free artifacts, never read a second repository in CI."""
    lab = tmp_path/'lab'; lab.mkdir()
    rows = validate(metadata)
    for row in rows:
        rid = row['record_id']; refs = row['lab']['artifacts']
        src = row['sources'][0]
        common = {'source_manifest': encoded({'files':[{'url':src['url'],'sha256':src['sha256']}]}),
                  'independent_validation': encoded({'synthetic':True})}
        blobs = {role:encoded({'synthetic':True}) for role in refs if role != 'publication_manifest'}
        blobs.update(common)
        if rid == 'M0256':
            spec = dict(record_id=rid, input={'sha256':'7'*64}, execution={'initial_cash':100}, parameters={'synthetic':True})
            blobs['spec'] = encoded(spec)
            metric = dict(start='2024-01-01T00:00:00Z', end='2024-01-03T00:00:00Z', daily_observations=2,
                          total_return=.1, annualized_return=.2, sharpe=.3, max_drawdown=.02, trades=2)
            summary = dict(id=rid, origin_run_id='synthetic-run', variant_id='synthetic-variant', fidelity_class='HYPOTHESIS',
                           protocol_sha256=digest(blobs['spec']), input_sha256='7'*64,
                           strategy_configurations=4, control_configurations=1,
                           results={k:{'metrics':deepcopy(metric)} for k in ['base','fee0','fee20','delay2','buyhold']})
            blobs['summary'] = encoded(summary)
            blobs['daily_nav'] = b'date,timestamp_utc,equity,nav\n2024-01-01,2024-01-02T00:00:00Z,99,0.99\n2024-01-02,2024-01-03T00:00:00Z,110,1.1\n'
            blobs['trades'] = b'side,price\nbuy,9\nsell,11\n'
            original_hash = 'a'*64
            manifest = dict(id=rid, protocol_sha256=digest(blobs['spec']), input_sha256='7'*64,
                            source_manifest_sha256=digest(blobs['source_manifest']),
                            checks={'independent':digest(blobs['independent_validation'])},
                            files={name:dict(sha256=digest(blobs[role]), bytes=len(blobs[role]))
                                   for role,name in [('summary','summary.json'),('trades','base-trades.csv')]})
            manifest['files'].update({k:dict(sha256=original_hash, bytes=999) for k in ['base-daily-nav.csv','base-nav-light.csv']})
            blobs['result_manifest'] = encoded(manifest)
            blobs['curve_projection'] = encoded(dict(status='PASS_FIELD_PRESERVING_PROJECTION', public_projection_sha256=digest(blobs['daily_nav']),
                source_daily_ledger_sha256=original_hash, source_daily_independent_validation_sha256=digest(blobs['independent_validation']),
                rows=2, columns=['date','timestamp_utc','equity','nav']))
            reference = dict(origin_run_id='synthetic-run', variant_id='synthetic-variant', fidelity_class='HYPOTHESIS',
                             protocol_sha256=digest(blobs['spec']), manifest_sha256=digest(blobs['result_manifest']))
            graph = dict(id=rid, name='SYNTHETIC', status='tested_hypothesis_only', reason='synthetic fixture', tested_variants=1,
                         families=['synthetic'], audit={'strict_replication':False}, related_results=[reference], implementations=[dict(reference)])
        else:
            blobs['spec'] = encoded({'record_id':rid})
            blobs['summary'] = encoded(dict(id=rid, market_replay_runs=0, tested_strategy_configurations=0, tested_buyhold_controls=0))
            blobs['result_manifest'] = encoded(dict(id=rid,state='DATA_BLOCKED',market_replay_runs=0,planned_spec_sha256=digest(blobs['spec'])))
            graph = dict(id=rid, name='SYNTHETIC BLOCKER', status='data_blocked', reason='synthetic missing observation',
                         tested_variants=0, families=['synthetic'], audit={}, related_results=[], implementations=[])
        blobs['graph_record'] = encoded(graph)
        prefix = f'research/public-strategies/{rid}/'
        allowed = {refs[role]['path'][len(prefix):]:dict(sha256=digest(raw),bytes=len(raw)) for role,raw in blobs.items()}
        blobs['publication_manifest'] = encoded(dict(id=rid,public_allowlist=allowed))
        for role,raw in blobs.items():
            ref=refs[role]; ref.update(sha256=digest(raw),bytes=len(raw)); p=lab/ref['path']; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(raw)
        write(metadata/f'strategies/{rid}.json', row)
    index(metadata)
    return lab


def test_prepare_hashes_rebuild_and_never_replays(metadata, synthetic_lab, tmp_path):
    a,b = tmp_path/'a',tmp_path/'b'
    report=prepare(metadata,synthetic_lab,a); again=prepare(metadata,synthetic_lab,b)
    assert report == again and report['counts']['new_trials'] == 0
    assert not report['metadata_import_ready'] and not report['deployed']
    assert {str(p.relative_to(a)):digest(p.read_bytes()) for p in a.rglob('*') if p.is_file()} == {
        str(p.relative_to(b)):digest(p.read_bytes()) for p in b.rglob('*') if p.is_file()}
    detail=json.loads(gzip.decompress(next((a/'implementations').glob('*')).read_bytes()))
    assert detail['curve'][0]['equity'] == .99  # Initial cost is not normalized away.
    assert detail['curve'][0]['drawdown'] == pytest.approx(-.01)
    assert detail['metrics']['periods']['full']['max_drawdown'] == -.02
    assert detail['lineage']['manifest_kind'] == 'LAB_ORIGIN_RESULT_MANIFEST_NOT_GRAPH_COLLECTION'
    assert detail['lineage']['public_curve_projection']['source_daily_ledger_sha256'] != digest((a/'evidence/M0256/daily_nav.csv').read_bytes())
    with pytest.raises(ValueError,match='immutable'):prepare(metadata,synthetic_lab,a)
    assert not list((a/'implementations').glob('*M0259*'))


def test_five_gib_reserve_checked_before_writes(metadata,synthetic_lab,tmp_path,monkeypatch):
    monkeypatch.setattr('quantgraph.graph.metadata_pilot.shutil.disk_usage',lambda _:SimpleNamespace(free=5*1024**3))
    out=tmp_path/'low'
    with pytest.raises(ValueError,match='reserve'):prepare(metadata,synthetic_lab,out)
    assert not out.exists()


def test_public_allowlist_cannot_be_bypassed_by_updating_artifact_pin(metadata,synthetic_lab):
    row=validate(metadata)[0];ref=row['lab']['artifacts']['summary'];p=synthetic_lab/ref['path'];p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ValueError,match='digest'):verified_blobs(row,synthetic_lab)
    ref.update(sha256=digest(p.read_bytes()),bytes=p.stat().st_size)
    with pytest.raises(ValueError,match='allowlist'):verified_blobs(row,synthetic_lab)


def test_public_curve_requires_original_daily_ledger_chain(metadata,synthetic_lab):
    row=validate(metadata)[0];blobs=verified_blobs(row,synthetic_lab);v=json.loads(blobs['curve_projection']);v['source_daily_ledger_sha256']='f'*64;blobs['curve_projection']=encoded(v)
    with pytest.raises(ValueError,match='original frozen'):project(row,blobs)


def test_blocked_record_cannot_invent_result(metadata,synthetic_lab):
    row=validate(metadata)[1];blobs=verified_blobs(row,synthetic_lab);v=json.loads(blobs['summary']);v['market_replay_runs']=1;blobs['summary']=encoded(v)
    with pytest.raises(ValueError,match='Blocked'):project(row,blobs)


def catalog(tmp_path,rows):
    cat=CatalogRepository(tmp_path/'catalog.sqlite')
    with cat.connect() as con:
        for row in rows:
            value=item('strategy','synthetic:'+row['record_id'],'Synthetic original','StrategyVariant','original-revision',source_native_ids=[row['record_id']])
            cat._put(con,value,'synthetic',{'raw_record':{'规则':'合成原定义不可覆盖'},'personal_marker':'leave unchanged'})
    return cat


def test_exact_overlay_is_idempotent_and_preserves_definition_private_payload(metadata,tmp_path):
    rows=validate(metadata);cat=catalog(tmp_path,rows)
    pin=digest(cat.path.read_bytes());bindings=read_bindings(cat.path,pin,rows)
    source_before=cat.path.read_bytes()
    p=tmp_path/'cards.json';cards=[card(r,bindings[r['record_id']]) for r in rows];sha=write(p,cards)
    with cat.connect() as con:before=[tuple(r) for r in con.execute('SELECT * FROM catalog_items ORDER BY entity_id')]
    first=import_cards(cat,p,sha,'strategy');second=import_cards(cat,p,sha,'strategy')
    assert first['inserted_reviews']==2 and first['new_catalog_entries']==0
    assert second['inserted_reviews']==0 and second['unchanged_reviews']==2
    with cat.connect() as con:assert before==[tuple(r) for r in con.execute('SELECT * FROM catalog_items ORDER BY entity_id')]
    got=PersonalCatalogRepository(cat.path).get('synthetic:M0256')
    assert got['knowledge']['original_rule']=='合成原定义不可覆盖'
    assert got['knowledge']['reader_brief']['existing_record_overlay'] is True
    assert next(r for r in got['knowledge']['reader_brief']['trading'] if r['key']=='cost')['status']=='RESEARCH_ASSUMPTION'
    assert cat.path.read_bytes()!=source_before  # Only the private review table changed.


@pytest.mark.parametrize('change',[
    lambda row:row['relation'].update(expected_definition_revision='wrong-version'),
    lambda row:row['relation'].update(expected_entity_id='missing'),
    lambda row:row['relation'].update(id='M9999'),
    lambda row:row.update(native_source_id='M9999'),
    lambda row:row.update(entity_type='factor'),
    lambda row:row['relation'].update(binding_mode='CURRENT_OR_CREATE'),
])
def test_mismatched_exact_binding_fails_atomically(metadata,tmp_path,change):
    rows=validate(metadata);cat=catalog(tmp_path,rows);bindings=read_bindings(cat.path,digest(cat.path.read_bytes()),rows)
    cards=[card(r,bindings[r['record_id']]) for r in rows];change(cards[1]);p=tmp_path/'cards.json';sha=write(p,cards)
    before=cat.path.read_bytes()
    with pytest.raises(ValueError):import_cards(cat,p,sha,'strategy')
    assert cat.path.read_bytes()==before


def test_unbound_cards_cannot_create_new_same_number_entity(metadata,tmp_path):
    rows=validate(metadata);cat=catalog(tmp_path,rows);p=tmp_path/'cards.json';sha=write(p,[card(rows[0])])
    with pytest.raises(ValueError,match='exact current'):import_cards(cat,p,sha,'strategy')


def test_snapshot_digest_and_ambiguous_identity_are_rejected(metadata,tmp_path):
    rows=validate(metadata);cat=catalog(tmp_path,rows)
    with pytest.raises(ValueError,match='digest'):read_bindings(cat.path,'0'*64,rows)
    with cat.connect() as con:cat._put(con,item('strategy','duplicate','duplicate','StrategyVariant','rev2',source_native_ids=['M0256']),'synthetic',{})
    with pytest.raises(ValueError,match='one current'):read_bindings(cat.path,digest(cat.path.read_bytes()),rows)


def test_prepare_copies_catalog_without_mutating_source(metadata,synthetic_lab,tmp_path):
    cat=catalog(tmp_path,validate(metadata));before=cat.path.read_bytes()
    out=prepare(metadata,synthetic_lab,tmp_path/'stage',cat.path,digest(before))
    assert out['metadata_copy_dry_run']['catalog_definitions_unchanged']
    assert out['metadata_copy_dry_run']['replay']['unchanged_reviews']==2
    assert cat.path.read_bytes()==before and not out['active_site_written']


def test_merge_preserves_old_results_notes_audit_and_is_idempotent():
    oldref=dict(origin_run_id='old',variant_id='v0',manifest_sha256='1'*64)
    newref=dict(origin_run_id='new',variant_id='v1',manifest_sha256='2'*64)
    existing=dict(id='M0256',name='original name',status='old status',reason='old reason',audit={'old':True},
                  tested_variants=1,related_results=[oldref],implementations=[oldref],families=['old-family'],
                  research_scope={'entity_id':'s1'},user_notes='personal',lab_import_candidate={'prior':'kept'})
    addition=dict(id='M0256',status='tested_hypothesis_only',reason='new',audit={'new':True},families=['new-family'],
                  related_results=[newref],implementations=[newref])
    before=deepcopy(existing);merged=merge_record(existing,addition)
    assert existing==before and merge_record(merged,addition)==merged
    for k in ['name','status','reason','audit','research_scope','user_notes','lab_import_candidate']:assert merged[k]==existing[k]
    assert merged['tested_variants']==2 and merged['related_results']==[oldref,newref]
    addition['related_results'][0]['manifest_sha256']='3'*64
    with pytest.raises(ValueError,match='immutable'):merge_record(merged,addition)
    with pytest.raises(ValueError,match='different'):merge_record(existing,{'id':'M0259'})

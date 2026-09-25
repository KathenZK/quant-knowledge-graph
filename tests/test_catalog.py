import collections,json,pathlib,sqlite3,re
import pytest
from quantgraph.collectors.legacy_cli import DEFAULT_ROOT,check_sources,verify
from quantgraph.normalize.formula import parse
from quantgraph.collectors.common import uid

pytestmark = pytest.mark.skipif(not (DEFAULT_ROOT/'datasets/normalized/records.jsonl').exists(), reason='Requires local mixed-license research snapshot, not distributed publicly')

@pytest.fixture(scope='module')
def rows():return [json.loads(x) for x in (DEFAULT_ROOT/'datasets/normalized/records.jsonl').read_text().splitlines()]

def test_frozen_inputs_and_exports():
    assert verify(DEFAULT_ROOT)['status']=='PASS'

def test_tampered_frozen_source_is_rejected(tmp_path):
    item=json.loads((DEFAULT_ROOT/'datasets/raw/source_lock.json').read_text())[0]
    (tmp_path/'datasets/raw').mkdir(parents=True); (tmp_path/'datasets/raw/source_lock.json').write_text(json.dumps([item]))
    target=tmp_path/item['path'];target.parent.mkdir(parents=True);target.write_text('corrupted input')
    with pytest.raises(ValueError,match='checksum mismatch'):check_sources(tmp_path)

def test_real_cohort_counts(rows):
    counts=collections.Counter(r['source_id'] for r in rows)
    assert counts['qlib']==518 and counts['wq101']==101 and counts['gtja191']==191
    assert collections.Counter(r['record_kind'] for r in rows if r['source_id']=='osap')=={'signal':212,'placebo':114,'withdrawn':5}
    assert sum(r['parameters']['core_153'] for r in rows if r['source_id']=='jkp')==153

def test_qlib_exact_overlap_and_variant_separation(rows):
    by={r['source_native_id']:r for r in rows if r['source_id']=='qlib'}
    assert by['Alpha158:ROC5']['canonical_factor_id']==by['Alpha360:CLOSE5']['canonical_factor_id']
    assert by['Alpha158:ROC60']['canonical_factor_id']!=by['Alpha360:CLOSE59']['canonical_factor_id']
    assert by['Alpha158:OPEN0']['canonical_factor_id']==by['Alpha360:OPEN0']['canonical_factor_id']
    assert len({r['canonical_factor_id'] for r in by.values()})==510

def test_french_same_name_is_not_same_construction(rows):
    by={r['source_native_id']:r for r in rows if r['source_id']=='french'}
    assert by['SMB_FF3']['concept_id']==by['SMB_FF5']['concept_id']
    assert by['SMB_FF3']['canonical_factor_id']!=by['SMB_FF5']['canonical_factor_id']
    assert by['ST_Rev']['canonical_factor_id']!=by['LT_Rev']['canonical_factor_id']

def test_rights_fail_closed(rows):
    assert all(not r['formula'] and not r['raw_definition'] for r in rows if r['source_id']=='aqr')
    assert all(r['commercial_use_flag']=='noncommercial_only' for r in rows if r['source_id']=='jkp')
    assert all(r['commercial_use_flag']=='upstream_rights_review_required' for r in rows if r['source_id'] in {'wq101','gtja191'})
    assert {r['source_id'] for r in rows if r['commercial_use_flag']=='permitted_with_attribution'}=={'qlib'}

def test_primary_count_does_not_include_placebos_templates_or_mirrors(rows):
    high=[r for r in rows if r['high_quality_eligible']]
    assert len({r['canonical_factor_id'] for r in high})>=1000
    assert all(r['primary_source'] and r['raw_definition'] and r['record_kind']=='signal' for r in high)
    assert not any(r['source_native_id'] in {'Alpha360:CLOSE0','Alpha360:VOLUME0','inv_gr3a','nwc_gr3a'} for r in high)

def test_upstream_stubs_preserved():
    impl=[json.loads(x) for x in (DEFAULT_ROOT/'datasets/normalized/implementations.jsonl').read_text().splitlines()]
    assert sum(x['implementation_status']=='stub' for x in impl)==2
    assert all(not x['formula_ast'] for x in impl if x['implementation_status']=='stub')

def test_strategy_join_enforces_real_ids():
    source=sqlite3.connect(DEFAULT_ROOT/'datasets/normalized/factors.sqlite');con=sqlite3.connect(':memory:');source.backup(con);con.execute('PRAGMA foreign_keys=ON')
    sid=uid('strategy','local-test:001');iid=con.execute('SELECT implementation_id FROM implementations LIMIT 1').fetchone()[0]
    con.execute('INSERT INTO strategies VALUES (?,?,?,?,?,?,?)',(sid,'local-test','001','Temporary test strategy',None,None,'test_fixture'))
    con.execute('INSERT INTO strategy_implementations VALUES (?,?,?,?)',(sid,iid,'signal','{}'))
    assert con.execute('SELECT count(*) FROM factor_implementation_strategy WHERE strategy_id=?',(sid,)).fetchone()[0]>=1
    with pytest.raises(sqlite3.IntegrityError):con.execute('INSERT INTO strategy_implementations VALUES (?,?,?,?)',(sid,'qkg:impl:does-not-exist','signal','{}'))
    source.close();con.close()

def test_latex_escaped_ampersand_does_not_create_false_factor(rows):
    jk=[r for r in rows if r['source_id']=='jkp']
    assert all(re.fullmatch(r'[a-z][a-z0-9_]*',r['source_native_id']) for r in jk)
    target=next(r for r in jk if r['source_native_id']=='dsale_dsga')
    assert 'SG&A' in target['signal_name']
    assert target['definition_kind']=='latex'

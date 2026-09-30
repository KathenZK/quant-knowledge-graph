import hashlib
import json
import sqlite3

import pytest

from quantgraph.graph.catalog_projection import item
from quantgraph.graph.personal_catalog import PersonalCatalogRepository
from quantgraph.graph.factor_quality import import_assessments, apply_factor_quality


def setup_factor(tmp_path):
    cat=PersonalCatalogRepository(tmp_path/'catalog.sqlite')
    value=item('variant','synthetic:factor','合成价格比值','FactorVariant','rev1',source_name='Microsoft Qlib')
    raw={'formula':'Ref($close, 20)/$close','dialect':'qlib','source_id':'qlib','parameters':{'window_or_lag':20}}
    with cat.connect() as con:cat._put(con,value,'synthetic',raw)
    row={'entity_id':value['entity_id'],'definition_revision':'rev1','category':'BASIC_FEATURE',
         'archive_candidate':False,'missing_facts':['未做收益检验'],'source_formula_match_status':'PENDING',
         'review_status':'PENDING','calculation_explanation':'合成说明'}
    return cat,value,raw,row


def snapshot(tmp_path, rows, version='synthetic-review-v1'):
    path=tmp_path/'audit.json'
    path.write_text(json.dumps({'audit_version':version,'records':rows},ensure_ascii=False))
    return path,hashlib.sha256(path.read_bytes()).hexdigest()


def test_versioned_assessment_never_changes_source_and_cache_refreshes(tmp_path):
    cat,value,raw,row=setup_factor(tmp_path)
    before=cat.get(value['entity_id'])
    path,digest=snapshot(tmp_path,[row])
    assert import_assessments(cat,path,digest)['inserted']==1
    after=cat.get(value['entity_id'])
    assert after['factor_quality']['assessment_version']=='synthetic-review-v1'
    assert after['factor_quality']['source_status']=='PENDING'
    assert before['definition_revision']==after['definition_revision']=='rev1'
    assert before['formula']==after['formula']
    assert import_assessments(cat,path,digest)['unchanged']==1
    with cat.connect() as con:
        assert json.loads(con.execute('SELECT private_payload FROM catalog_items').fetchone()[0])==raw
        with pytest.raises(sqlite3.IntegrityError):con.execute('DELETE FROM factor_quality_assessments')
    row['source_formula_match_status']='invented-upgrade'
    path,digest=snapshot(tmp_path,[row])
    with pytest.raises(ValueError,match='immutable'):import_assessments(cat,path,digest)
    assert cat.get(value['entity_id'])['factor_quality']['source_status']=='PENDING'
    assert cat.search(kind='variant',factor_scope='research_cards')['total']==0
    assert cat.search(kind='variant',factor_scope='basic_features')['total']==1


@pytest.mark.parametrize('error',['revision','duplicate','archive','nonfinite'])
def test_bad_assessment_is_atomic(tmp_path,error):
    cat,_,_,row=setup_factor(tmp_path);rows=[row]
    if error=='revision':row['definition_revision']='rev2'
    if error=='duplicate':rows.append(dict(row))
    if error=='archive':row['archive_candidate']=True
    if error=='nonfinite':row['unexpected']=float('nan')
    path,digest=snapshot(tmp_path,rows)
    with pytest.raises(ValueError):import_assessments(cat,path,digest)
    with cat.connect() as con:
        exists=con.execute("SELECT 1 FROM sqlite_master WHERE name='factor_quality_assessments'").fetchone()
        assert not exists or con.execute('SELECT COUNT(*) FROM factor_quality_assessments').fetchone()[0]==0


def test_current_bar_fix_has_history_and_never_changes_formula_or_lookback():
    value={'kind':'variant','name':'KMID2','source_name':'Microsoft Qlib',
           'source_sha256':'814b7f7ab3d418ae3c87ce352220080b239eba2670eac9e38376b794be4075cb',
           'formula':'($close-$open)/($high-$low+1e-12)','parameters':{'window_or_lag':2},
           'lookback':{'value':1},'definition_revision':'immutable-rev',
           'knowledge':{'parameters':[{'name':'window_or_lag','value':2}]}}
    got=apply_factor_quality(value,{'source_id':'qlib'})
    assert got['parameters']['window_or_lag'] is None
    assert got['knowledge']['parameters'][0]['value'] is None
    assert got['lookback']['value']==1 and got['definition_revision']=='immutable-rev'
    assert got['factor_quality']['metadata_corrections'][0]['previous']==2
    assert got['formula']=='($close-$open)/($high-$low+1e-12)'

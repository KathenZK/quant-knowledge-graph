import hashlib
import json
from pathlib import Path

import pytest

from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.catalog_projection import item
from quantgraph.graph.personal_catalog import PersonalCatalogRepository
from quantgraph.graph.private_intake import import_cards
from quantgraph.graph.reading_brief import reading_brief


def test_collection_paper_does_not_become_empirical_support():
    value={'kind':'variant','papers':[{'paper_id':'synthetic','title':'Platform','metadata_status':'COLLECTION_REFERENCE'}]}
    k={'reading':[],'formula':'Slope($close, 20)/$close','dialect':'qlib','source':{}}
    got=reading_brief(value,k,('generic',[],[]))
    assert '不是股票对市场的 CAPM beta' in got['purpose']
    assert got['papers'][0]['relationship']=='平台或集合引用'
    assert got['economic_rationale']['status']=='UNKNOWN'
    assert got['empirical_status']=='NOT_ESTABLISHED_BY_CITATION'


@pytest.mark.parametrize('formula,expected',[
    ('Ref($close, 20)/$close','价格上涨时这个比值下降'),
    ('Std($close, 20)/$close','不是收益率波动率'),
    ('Mean($close, 20)/$close','小于 1 表示现价高于均价'),
])
def test_exact_formula_interpretation(formula,expected):
    got=reading_brief({'kind':'variant'},{'reading':[],'formula':formula,'dialect':'qlib'},('generic',[],[]))
    assert expected in got['purpose']


def write(path,rows):
    path.write_text(json.dumps(rows,ensure_ascii=False))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_private_cards_are_readable_idempotent_and_never_public(tmp_path):
    cat=CatalogRepository(tmp_path/'catalog.sqlite');p=tmp_path/'cards.json'
    card={'record_id':'synthetic:factor:one','name_zh':'合成因子','one_line':'观察合成量',
          'formula':'X/Y','formula_plain_zh':'X除以Y','native_source_id':'SYNTHETIC:ONE',
          'source_url':'https://example.com/?token=do-not-ship',
          'validation':{'definition_status':'REVIEW_REQUIRED','backtest_status':'NOT_RUN'}}
    digest=write(p,[card]);first=import_cards(cat,p,digest,'factor');second=import_cards(cat,p,digest,'factor')
    assert first['entity_ids']==second['entity_ids']
    assert first['new_catalog_entries']==1 and second['new_catalog_entries']==0
    assert second['unchanged_entries']==1
    eid=first['entity_ids'][0]
    with pytest.raises(KeyError):cat.get(eid)
    got=PersonalCatalogRepository(cat.path).get(eid)
    assert got['knowledge']['reader_brief']['purpose']=='观察合成量'
    assert not got['knowledge']['source_facts']
    assert got['knowledge']['reading'][0]['status']=='CARD_IMPLEMENTATION'
    assert not any(r['status']=='SOURCE_REPORTED' for r in got['knowledge']['reading'])
    assert got['results']['total']==0
    assert 'do-not-ship' not in json.dumps(got)
    with cat.connect() as con:
        assert con.execute('SELECT count(*) FROM catalog_versions WHERE entity_id=?',(eid,)).fetchone()[0]==1
    with pytest.raises(ValueError,match='digest'):import_cards(cat,p,'0'*64,'factor')


def test_source_overlay_preserves_original_definition_and_updates_cached_reading(tmp_path):
    cat=PersonalCatalogRepository(tmp_path/'catalog.sqlite');eid='synthetic:strategy';rule='若价格高于均线，买入；否则退出。'
    original=item('strategy',eid,'合成策略','StrategyVariant','original-revision',source_native_ids=['M9999'])
    private={'raw_record':{'规则':rule},'variant':{'original_rule_text':rule,'source_native_id':'M9999'}}
    with cat.connect() as con:cat._put(con,original,'test:synthetic',private)
    before=cat.get(eid)
    p=tmp_path/'cards.json';row={'record_id':'M9999','name_zh':'合成补证','one_line':'比较现价与均线后决定持有或退出',
        'admission_status':'QUARANTINE','original_rule_text':rule,
        'relation':{'type':'source_curation_overlay_for','also_in_frozen_5813':True,'id':'M9999'}}
    result=import_cards(cat,p,write(p,[row]),'strategy')
    after=cat.get(eid)
    assert result['existing_record_reviews']==1 and result['new_catalog_entries']==0
    assert before['definition_revision']==after['definition_revision']=='original-revision'
    assert after['knowledge']['original_rule']==rule
    assert after['knowledge']['reader_brief']['intake_status']=='QUARANTINE'
    assert after['knowledge']['reader_brief']['source_review_summary']==row['one_line']
    assert after['knowledge']['reader_brief']['existing_record_overlay'] is True
    with cat.connect() as con:
        assert json.loads(con.execute('SELECT private_payload FROM catalog_items').fetchone()[0])==private


def test_bad_overlay_and_duplicate_batch_are_atomic(tmp_path):
    cat=CatalogRepository(tmp_path/'catalog.sqlite');p=tmp_path/'cards.json'
    row={'record_id':'M9999','name_zh':'合成','relation':{'type':'source_curation_overlay_for','also_in_frozen_5813':True,'id':'M9999'}}
    with pytest.raises(ValueError,match='exactly one'):import_cards(cat,p,write(p,[row]),'strategy')
    row={'record_id':'synthetic:one','name_zh':'合成'}
    with pytest.raises(ValueError,match='Duplicate'):import_cards(cat,p,write(p,[row,row]),'strategy')
    with cat.connect() as con:assert con.execute('SELECT count(*) FROM catalog_items').fetchone()[0]==0


@pytest.mark.parametrize('status,origin',[('unknown','compiler_decision'),('pending','adaptation'),('partial','source_excerpt')])
def test_card_text_never_upgrades_its_evidence_status(status,origin):
    k={'reading':[{'key':'entry','status':'UNKNOWN'}]}
    card={'field_evidence':{'entry':{'value':'合成入场条件','verification_status':status,'origin':origin}}}
    result=reading_brief({'kind':'strategy'},k,('generic',[],[]),card)
    entry=next(x for x in result['trading'] if x['key']=='entry')
    assert entry['status']==status and entry['origin']==origin
    factor=reading_brief({'kind':'source'}, {'reading':[]},('generic',[],[]), {'formula_plain_zh':'合成公式','strategy_uses_zh':['可试用于筛选']})
    use=next(x for x in factor['trading'] if x['key']=='use')
    assert use['status']=='CARD_REPORTED' and use['origin']=='RESEARCH_DESIGN_SUGGESTION'


def test_rule_summary_has_asset_and_action_not_only_method_label():
    knowledge={'asset_scope':{'assets':['AAA','BBB']},'reading':[
        {'key':'entry','text':'AAA高于20期均线时买入AAA，否则持有BBB','status':'EXTRACTED'},
        {'key':'exit','text':'AAA高于20期均线时买入AAA，否则持有BBB','status':'EXTRACTED'}]}
    got=reading_brief({'kind':'strategy'},knowledge,('用均线观察趋势',[],[]))
    assert 'AAA、BBB' in got['purpose'] and got['purpose'].count('否则持有BBB')==1


@pytest.mark.parametrize('payload',[b'[{"record_id":"x","record_id":"y","name":"x"}]',b'[{"record_id":"x","name":"x","number":NaN}]'])
def test_strict_json_rejected_before_any_card_insert(tmp_path,payload):
    cat=CatalogRepository(tmp_path/'catalog.sqlite');p=tmp_path/'cards.json';p.write_bytes(payload)
    with pytest.raises(ValueError):import_cards(cat,p,hashlib.sha256(payload).hexdigest(),'factor')
    with cat.connect() as con:assert con.execute('SELECT count(*) FROM catalog_items').fetchone()[0]==0

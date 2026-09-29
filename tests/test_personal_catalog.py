"""Reading, source lineage and local search do not relax the public projection."""
import json
from pathlib import Path

import pytest

from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.catalog_projection import edge, item
from quantgraph.graph.personal_catalog import PersonalCatalogRepository, personal_url, private_text


def put(repo, kind, eid, *, raw=None, visibility='PUBLIC', **fields):
    value=item(kind,eid,fields.pop('name',eid),{'strategy':'StrategyVariant','variant':'FactorVariant','source':'SourceRecord'}.get(kind,'FactorConcept'),fields.pop('revision','rev1'),**fields)
    with repo.connect() as con:
        repo._put(con,value,'test:'+eid,raw or {})
        con.execute('UPDATE catalog_items SET visibility=? WHERE entity_id=?',(visibility,eid))
    return value


def strategy_raw(rule, native='M1', url='https://example.com/paper?paper_id=7&page=3#section'):
    return {'raw_record':{'规则':rule,'市场':'ETF','作者或机构':'Reported Author','source_url':url},
            'variant':{'original_rule_text':rule,'source_url_raw':url,'source_native_id':native,
                'rule_ast':None,'parse_status':'UNSUPPORTED_SYNTAX','source_locator':'page 3',
                'source_publication_date':'2001-01-01','raw_proposed_date':'2001','date_status':'UNVERIFIED_REPORTED_DATE'}}


@pytest.fixture
def repo(tmp_path):
    return PersonalCatalogRepository(tmp_path/'catalog.sqlite')


def test_unparsed_reading_is_complete_and_never_changes_public_visibility(repo):
    text='若 RSI(14) 低于 30，等权买入。高于 70 退出；每月调仓。'+('原文说明。'*750)+'原文最后一行'
    put(repo,'strategy','s1',raw=strategy_raw(text),visibility='HIDDEN',source_native_ids=['M1'],
        strategy={'parse_status':'UNSUPPORTED_SYNTAX','template_id':None})
    personal=repo.detail('strategy','s1')
    assert personal['strategy']['original_rule']==text
    assert personal['knowledge']['original_rule'].endswith('原文最后一行')
    assert personal['knowledge']['reading'][0]['status']=='SOURCE_REPORTED'
    assert any('费用' in v for v in personal['knowledge']['unknowns'])
    assert personal['visibility']=='HIDDEN'
    public=CatalogRepository(repo.path)
    with pytest.raises(KeyError):
        public.get('s1')
    with repo.connect() as con:
        assert con.execute('SELECT visibility FROM catalog_items').fetchone()[0]=='HIDDEN'
        assert json.loads(con.execute('SELECT private_payload FROM catalog_items').fetchone()[0])['raw_record']['规则']==text


def test_factor_source_keeps_formula_without_ast_and_is_in_factor_browse(repo):
    put(repo,'source','wq1',raw={'formula':'rank(volume) - rank(close)','raw_definition':'原始定义',
        'required_fields':['volume','close'],'parameters':{'window':20},'source_native_id':'Alpha001'},
        name='WorldQuant Alpha001',source_type='factor_source_record')
    got=repo.detail('source','wq1')
    assert got['formula']=='rank(volume) - rank(close)'
    assert got['knowledge']['original_definition']=='原始定义'
    assert got['knowledge']['parameters'][0]['value']==20
    assert repo.search(kind='variant',q='成交量')['items'][0]['kind']=='source'
    assert repo.metadata()['layer_counts']['normalized_factor_records']==1


def test_safe_url_preserves_document_locator_but_removes_secrets_and_tracking():
    url='https://example.com/paper?abstract_id=42&page=7&token=secret&utm_source=x#L12'
    assert personal_url(url)=='https://example.com/paper?abstract_id=42&page=7#L12'
    assert personal_url('javascript:alert(1)') is None
    assert personal_url('https://user:pass@example.com/') is None
    text=private_text('引用 '+url+'， token=abcd')
    assert 'secret' not in text and 'abcd' not in text
    assert 'abstract_id=42' in text and 'page=7' in text


def test_nested_private_credentials_never_ship(repo):
    put(repo,'variant','f1',raw={'raw_formula':'Mean($close, 5)/$close','parameters':{'token':'credential','link':'https://example.com/?id=1&api_key=bad'},'dialect':'qlib'})
    value=repo.detail('variant','f1')
    body=json.dumps(value)
    assert 'credential' not in body and 'api_key=bad' not in body
    assert value['knowledge']['example'] and '假设数据' in value['knowledge']['example']['basis']


def test_synonym_search_is_field_explainable_and_token_bounded(repo):
    put(repo,'strategy','rsi',name='RSI strategy',raw=strategy_raw('使用 RSI(14) 入场'))
    put(repo,'strategy','stoch',name='StochRSI strategy',raw=strategy_raw('使用 StochRSI(14) 入场',native='M2'))
    got=repo.search(q='相对强弱',kind='strategy')
    assert [v['entity_id'] for v in got['items']]==['rsi']
    assert got['items'][0]['matches'][0]['term']=='rsi'
    assert got['items'][0]['matches'][0]['label']=='名称'
    assert repo.search(q='RSI ETF',kind='strategy')['total']==0  # No invented input fields.


def test_filters_use_recorded_fields_and_templates_only_collapse_explicit_ids(repo):
    for eid,n in [('a',5),('b',20)]:
        put(repo,'strategy',eid,name=f'MA{n}',raw=strategy_raw(f'每日 SMA({n}) 均线高于收盘价则满仓。',native=eid),
            family='moving_average',strategy={'template_id':'real-template'})
    put(repo,'variant','f',raw={'raw_formula':'Mean($close, 5)/$close','dialect':'qlib','frequency':'daily',
        'required_fields':['close'],'required_fields_status':'syntax_extracted_unexpanded'})
    assert repo.search(kind='strategy',collapse_templates=True)['total']==1
    assert repo.search(kind='strategy',collapse_templates=True)['record_total']==2
    assert repo.search(kind='strategy',method_family='moving_average')['total']==2
    assert repo.search(kind='variant',daily_ohlcv=True)['items'][0]['entity_id']=='f'
    assert repo.search(kind='strategy',daily_ohlcv=True)['total']==0
    assert repo.search(kind='strategy',allowed_ids={'b'})['items'][0]['entity_id']=='b'


def test_relation_two_hops_batch_nodes_and_no_attribution_claim(repo):
    for kind,eid in [('strategy','a'),('variant','b'),('concept','c'),('source','d')]:
        put(repo,kind,eid)
    with repo.connect() as con:
        repo._edge(con,edge('a','b','USES_FACTOR','明确规则引用',confidence=.8),'test')
        repo._edge(con,edge('b','c','VARIANT_OF','模板关系',confidence=1),'test')
        repo._edge(con,edge('d','a','DESCRIBES','来源记录',confidence=1),'test')
    result=repo.relations('a',hops=2)
    assert result['total']==3 and len(result['nodes'])==4
    use=next(r for r in result['items'] if r['relation']=='USES_FACTOR')
    assert '不表示' in use['explanation']['text']
    assert repo.relations('a',hops=2,layer='source')['total']==1
    assert repo.relations('a',hops=2,confidence=.9)['total']==1


def test_exact_version_and_old_identity_do_not_substitute_current_definition(repo):
    put(repo,'strategy','old',raw=strategy_raw('RSI(5) 低于 20 入场'),source_native_ids=['M1'])
    with repo.connect() as con:
        con.execute("UPDATE catalog_items SET active=0 WHERE entity_id='old'")
    put(repo,'strategy','new',raw=strategy_raw('RSI(14) 低于 30 入场'),source_native_ids=['M1'],revision='rev2')
    current=repo.get('new'); old=repo.detail('strategy','old')
    assert current['stable_knowledge_id']=='grokbot:M1'
    assert current['prior_version_ids']==['old']
    assert old['is_historical'] and old['current_entity_id']=='new'
    assert old['current_definition_revision']=='rev2'
    assert 'RSI(5)' in old['knowledge']['original_rule']
    assert repo.detail_version('strategy','old','rev1')['knowledge']['original_rule']=='RSI(5) 低于 20 入场'
    with pytest.raises(KeyError):
        repo.detail_version('strategy','old','rev2')
    assert repo.search(kind='strategy')['total']==1


def test_user_notes_search_and_layer_remain_separate_and_refresh(repo,tmp_path):
    from quantgraph.graph.personal_store import PersonalStore
    put(repo,'strategy','a',raw=strategy_raw('来源规则'))
    repo.personal_store=PersonalStore(tmp_path/'personal.sqlite')
    repo.personal_store.update(repo.get('a'),{'aliases':['我的新别名'],'questions':'成本可能抵消优势','note':'独立阅读笔记'})
    found=repo.search(q='我的新别名')['items'][0]
    assert found['matches'][0]['field']=='user_aliases'
    assert '我的新别名' not in found['aliases']
    assert found['knowledge']['layers']['hypotheses'][0]['status']=='USER_HYPOTHESIS'
    assert found['knowledge']['original_rule']=='来源规则'
    repo.personal_store.update(repo.get('a'),{'aliases':['更新别名']})
    assert repo.search(q='我的新别名')['total']==0
    assert repo.search(q='更新别名')['total']==1


def test_compare_reports_concrete_field_differences_and_limits(repo):
    put(repo,'variant','a',raw={'raw_formula':'Mean(close,5)'})
    put(repo,'variant','b',raw={'raw_formula':'Mean(close,20)'})
    result=repo.compare(['variant/a','variant/b'])
    assert next(r for r in result['differences'] if r['key']=='formula')['same'] is False
    assert '公式' in result['conclusions'][0]
    with pytest.raises(ValueError):
        repo.compare(['variant/a','variant/a'])


def test_confirmed_duplicate_collapses_but_undo_keeps_both_originals(repo,tmp_path):
    from quantgraph.graph.personal_store import PersonalStore
    put(repo,'strategy','a',name='Alpha',raw=strategy_raw('相同规则'))
    put(repo,'strategy','b',name='Beta',raw=strategy_raw('相同规则',native='M2'))
    repo.personal_store=PersonalStore(tmp_path/'personal.sqlite')
    left,right=repo.get('a'),repo.get('b')
    suggestion=repo.personal_store.suggest(left,right,'POSSIBLE_DUPLICATE','人工确认相同规则')
    repo.personal_store.decide(suggestion['suggestion_id'],'confirm',canonical_id='a')
    found=repo.search(kind='strategy')
    assert found['total']==1 and found['items'][0]['entity_id']=='a'
    assert found['items'][0]['merged_from']==['b']
    assert repo.get('b')['entity_id']=='b' and repo.get('b')['canonical_id']=='a'
    assert repo.search(kind='strategy',q='Beta')['items'][0]['entity_id']=='b'
    assert repo.search(kind='strategy',q='Beta')['items'][0]['canonical_id']=='a'
    repo.personal_store.decide(suggestion['suggestion_id'],'undo')
    assert repo.search(kind='strategy')['total']==2


def test_strategy_extraction_excludes_negative_context_and_keeps_missing_fields_unknown(repo):
    rule='本条只写已印出的规则。每个交易日观察收盘价是否高于均线，满足则持有A。不是另一个每周成交的突破方法。未印仓位%、手续费。'
    put(repo,'strategy','negative',name='均线条件',raw=strategy_raw(rule))
    value=repo.get('negative');k=value['knowledge']
    assert k['method_family']['value']=='moving_average'
    assert not value['frequency']=='weekly'
    assert next(r for r in k['reading'] if r['key']=='costs')['status']=='UNKNOWN'
    assert next(r for r in k['reading'] if r['key']=='position')['status']=='UNKNOWN'
    assert next(r for r in k['reading'] if r['key']=='rebalance')['status']=='UNKNOWN'
    assert '本条只写' not in k['summary'] and '不是' not in k['summary']


def test_parameter_balancing_negative_signs_and_source_rule_frequency(repo):
    rule='使用小时数据。指标是ROC(EMA(High−Low,10),10)，止损 -10%。每个交易日最多评估一次。不是21日短反转，也不是每周轮动。'
    put(repo,'strategy','nested',raw=strategy_raw(rule))
    value=repo.get('nested')
    parameters=[p['name'] for p in value['knowledge']['parameters']]
    assert 'ROC(EMA(High−Low,10),10)' in parameters
    assert '-10%' in parameters and '21日' not in parameters
    assert value['frequency']=='hourly'
    assert value['knowledge']['frequencies']['observation']=='daily'


def test_structured_reading_independent_of_closed_execution_ast(repo):
    dsl={'asset':'A','signal':'ZSCORE_REVERSION','entry':'closed z < negative threshold','exit':'otherwise cash',
         'parameters':[20,1.5],'schedule':'daily_eod','allocation':'all_equity',
         'derivation':'costs and next-open timing are research assumptions'}
    put(repo,'strategy','dsl',raw=strategy_raw('QG-DSL/1\n'+json.dumps(dsl)))
    k=repo.get('dsl')['knowledge']
    assert k['parameters'][0]['value']==[20,1.5]
    assert '下一开盘价' in next(r for r in k['reading'] if r['key']=='execution')['text']
    assert '研究假设' in next(r for r in k['reading'] if r['key']=='costs')['text']
    assert 'QG-DSL' not in k['summary']


def test_article_title_is_not_required_price_field_and_rule_reference_is_unknown(repo):
    put(repo,'strategy','high_yield',raw=strategy_raw('参考 High Yield Bonds，收盘价高于 **20** 日均线。'))
    value=repo.get('high_yield')
    assert value['required_fields']==['close']
    assert '20 日' in [p['name'] for p in value['knowledge']['parameters']]
    put(repo,'variant','mfi',source_type='RULE_LINK_ONLY',required_fields=['close'],name='MFI(14)')
    reference=repo.get('mfi')
    assert reference['required_fields']==[]
    assert reference['required_fields_status']=='RULE_REFERENCE_INPUTS_UNVERIFIED'


def test_compare_missing_fields_are_unknown_not_equal(repo):
    put(repo,'variant','a');put(repo,'variant','b')
    result=repo.compare(['variant/a','variant/b'])
    formula=next(r for r in result['differences'] if r['key']=='formula')
    assert formula['status']=='UNKNOWN' and formula['same'] is False
    assert not any('公式' in line and '不同之处' in line for line in result['conclusions'])
    assert any('公式' in line and '暂不能比较' in line for line in result['conclusions'])
    assert next(r for r in result['differences'] if r['key']=='method')['status']=='UNKNOWN'


def test_confirmed_canonical_cannot_replace_a_filtered_out_personal_state(repo,tmp_path):
    from quantgraph.graph.personal_store import PersonalStore
    put(repo,'strategy','a',name='Alpha',raw=strategy_raw('相同规则'))
    put(repo,'strategy','b',name='Beta',raw=strategy_raw('相同规则',native='M2'))
    repo.personal_store=PersonalStore(tmp_path/'personal.sqlite')
    repo.personal_store.update(repo.get('a'),{'starred':True,'status':'值得研究'})
    suggestion=repo.personal_store.suggest(repo.get('a'),repo.get('b'),'POSSIBLE_DUPLICATE','人工证据')
    repo.personal_store.decide(suggestion['suggestion_id'],'confirm',canonical_id='a')
    filtered=repo.search(kind='strategy',allowed_ids={'b'})
    assert filtered['total']==1
    assert filtered['items'][0]['entity_id']=='b'
    assert filtered['items'][0]['canonical_id']=='a'
    assert repo.search(kind='strategy',allowed_ids={'a'})['items'][0]['entity_id']=='a'


def test_summary_keeps_return_comparison_context_and_entry_exit_roles(repo):
    rule='本条只写来源规则。月末比较 A 与 B 过去 3 个月总回报。若 A≥B 则持有 A，否则 B。'
    put(repo,'strategy','rotation',raw=strategy_raw(rule))
    summary=repo.get('rotation')['knowledge']['summary']
    assert '过去 3 个月总回报' in summary and '若 A≥B' in summary
    rule='多：价格突破则买入。平多：价格跌破时退出。shortentry：空头/SELL 条件为价格跌破。'
    put(repo,'strategy','roles',raw=strategy_raw(rule,native='M2'))
    rows=repo.get('roles')['knowledge']['reading']
    entry=next(r for r in rows if r['key']=='entry')['text']
    exit=next(r for r in rows if r['key']=='exit')['text']
    assert '平多' not in entry and 'shortentry' in entry
    assert 'shortentry' not in exit and '平多' in exit


def test_position_uses_allocation_not_duration_exit_constraint(repo):
    rule='每笔100个标的单位，最多5仓。live持仓超24h平仓。custom_sell：若条件成立则卖出。'
    put(repo,'strategy','position',raw=strategy_raw(rule))
    rows=repo.get('position')['knowledge']['reading']
    position=next(r for r in rows if r['key']=='position')['text']
    entry=next(r for r in rows if r['key']=='entry')['text']
    assert '每笔100' in position and '最多5仓' in position
    assert '24h' not in position and 'custom_sell' not in entry


def test_default_method_layer_includes_explicit_factor_and_distinct_relation_labels(repo):
    for kind,eid in [('strategy','s'),('variant','f'),('concept','c')]:put(repo,kind,eid)
    with repo.connect() as con:
        repo._edge(con,edge('s','f','USES_FACTOR','明确规则引用'),'test')
        repo._edge(con,edge('s','c','IN_FAMILY','来源方法归类'),'test')
    result=repo.relations('s',layer='method')
    assert result['total']==2
    assert {r['explanation']['label'] for r in result['items']}=={'策略使用的因子','所属方法族'}


def test_known_strategy_parameter_role_is_explained_from_archived_structure(repo):
    raw=strategy_raw('若收盘价高于20日简单移动平均则持有A，否则B。')
    raw['variant']['rule_ast']={'condition':{'right':{'type':'indicator','name':'SMA','parameters':[20]}}}
    put(repo,'strategy','ma',raw=raw)
    param=repo.get('ma')['knowledge']['parameters'][0]
    assert param['value']==20 and param['meaning']=='计算简单移动平均的观察窗口'


def test_incremental_projection_and_search_documents_touch_only_changed_rows(repo,monkeypatch):
    import quantgraph.graph.personal_catalog as module
    reading,documents=[],[]
    original_reader=module.readable_item;original_document=repo._document
    def record_read(value,raw):
        reading.append(value['entity_id']);return original_reader(value,raw)
    def record_document(value):
        documents.append(value['entity_id']);return original_document(value)
    monkeypatch.setattr(module,'readable_item',record_read)
    monkeypatch.setattr(repo,'_document',record_document)
    put(repo,'strategy','a',raw=strategy_raw('规则甲',native='A'))
    put(repo,'strategy','b',raw=strategy_raw('规则乙',native='B'))
    assert repo.search()['total']==2
    assert sorted(reading)==['a','b'] and sorted(documents)==['a','b']
    reading.clear();documents.clear()
    put(repo,'strategy','a',raw=strategy_raw('规则甲',native='A'))
    repo.search()
    assert reading==[] and documents==[]
    put(repo,'strategy','c',raw=strategy_raw('规则丙',native='C'))
    repo.search()
    assert reading==['c'] and documents==['c']
    reading.clear();documents.clear()
    put(repo,'strategy','a',raw=strategy_raw('修订后的规则甲',native='A'),revision='rev2')
    assert repo.search(q='修订后的规则甲')['total']==1
    assert reading==['a'] and documents==['a']


def test_incremental_source_hydration_tracks_parent_and_removed_relationship(repo,monkeypatch):
    import quantgraph.graph.personal_catalog as module
    put(repo,'strategy','a',raw=strategy_raw('父条目规则甲'))
    put(repo,'source','source')
    link=edge('source','a','DESCRIBES','归档来源')
    with repo.connect() as con:repo._edge(con,link,'test-link')
    assert repo.get('source')['knowledge']['original_rule']=='父条目规则甲'
    assert repo._base_rows['source'][1]['knowledge']['original_definition'] is None
    reading=[];original=module.readable_item
    def counted(value,raw):
        reading.append(value['entity_id']);return original(value,raw)
    monkeypatch.setattr(module,'readable_item',counted)
    put(repo,'strategy','a',raw=strategy_raw('父条目规则修订'),revision='rev2')
    assert repo.get('source')['knowledge']['original_rule']=='父条目规则修订'
    assert reading==['a']
    assert repo.search(kind='source',q='父条目规则甲')['total']==0
    reading.clear()
    with repo.connect() as con:con.execute("UPDATE catalog_edge_origins SET active=0 WHERE owner='test-link'")
    assert repo.get('source')['knowledge']['original_rule'] is None
    assert repo.search(kind='source',q='父条目规则修订')['total']==0
    assert reading==[]


def test_asset_scope_is_explicit_and_includes_cash_alternatives(repo):
    for eid,assets in [('single',['A']),('multi',['A','B'])]:
        raw=strategy_raw('已有结构化规则',native=eid)
        raw['variant']['rule_ast']={'assets':assets}
        put(repo,'strategy',eid,raw=raw)
    put(repo,'strategy','unknown',raw=strategy_raw('名称提到 A 与 B，但没有完整资产范围',native='U'))
    for scope in ['single','multi','unknown']:
        rows=repo.search(asset_scope=scope)['items']
        assert [i['entity_id'] for i in rows]==[scope]
        assert rows[0]['knowledge']['filters']['asset_scope']==scope
    assert '同时持仓' in repo.get('multi')['knowledge']['asset_scope']['basis']


def test_migration_observation_time_is_not_original_collection_time(repo):
    raw=strategy_raw('规则')
    raw['variant']['auditable_metadata']={'collected_at':'2026-09-26T00:00:00Z',
        'metadata':{'collected_at_basis':'MIGRATION_OBSERVATION_TIME_ORIGINAL_COLLECTION_UNKNOWN'}}
    put(repo,'strategy','migration',raw=raw)
    source=repo.get('migration')['knowledge']['source']
    assert source['collected_at'] is None
    assert source['ingestion_observed_at']=='2026-09-26T00:00:00Z'
    assert '原始采集时间未知' in source['collection_time_notice']


def test_qlib_mean_ratio_method_is_classified_from_formula(repo):
    put(repo,'variant','obscure_name',raw={'raw_formula':'Mean($close, 5)/$close','dialect':'qlib'})
    method=repo.get('obscure_name')['knowledge']['method_family']
    assert method['value']=='moving_average' and '原式' in method['basis']


def test_source_excerpt_preserves_boilerplate_sentence_with_definition(repo):
    raw=strategy_raw('本条只写某来源月末比较 A 和 B 过去3个月总回报。若A≥B持A，否则B。')
    put(repo,'strategy','context',raw=raw)
    assert '过去3个月总回报' in repo.get('context')['knowledge']['summary']
    put(repo,'strategy','trail',raw=strategy_raw('Trail Long/Short Loss默认4%。',native='TRAIL'))
    entry=next(r for r in repo.get('trail')['knowledge']['reading'] if r['key']=='entry')
    assert entry['status']=='UNKNOWN'

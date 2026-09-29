"""Semantic search regressions, independent of private corpus availability."""
import pytest

from quantgraph.graph.catalog_projection import item
from quantgraph.graph.personal_catalog import PersonalCatalogRepository
from quantgraph.graph.personal_search import QueryVocabulary, search_pattern


def put(repo,eid,name,rule='',*,aliases=None,kind='strategy',raw=None,**fields):
    value=item(kind,eid,name,'StrategyVariant' if kind=='strategy' else 'FactorVariant','rev1',aliases=aliases or [],**fields)
    if raw is None:
        raw={'raw_record':{'规则':rule},'variant':{'original_rule_text':rule,'source_native_id':eid}}
    with repo.connect() as con:
        repo._put(con,value,'test:'+eid,raw)


@pytest.fixture
def repo(tmp_path):
    return PersonalCatalogRepository(tmp_path/'catalog.sqlite')


def ids(repo,q,**kw):
    return [i['entity_id'] for i in repo.search(q=q,**kw)['items']]


@pytest.mark.parametrize('query,units',[
    ('均线动量',['均线','动量']), ('均线 动量',['均线','动量']),
    ('RSI均值回归',['rsi','均值回归']), ('RSI 均值回归',['rsi','均值回归']),
    ('moving average momentum',['moving average','momentum']),
    ('moving   average momentum',['moving average','momentum']),
    ('低波动',['低波动']), ('低波动率',['低波动率']),
    ('成交量突破',['成交量','突破']), ('成交量 突破',['成交量','突破']),
    ('SMA crossover',['sma','crossover']), ('简单均线交叉',['简单均线','交叉']),
    ('RSI14',['rsi14']), ('MA200',['ma200']), ('RSI(14)',['rsi(14)']),
    ('12-1 Momentum',['12-1 momentum']), ('12−1 Momentum',['12−1 momentum']),
    ('资金费率动量',['资金费率','动量']), ('配对交易',['配对交易']),
    ('均线神秘词XYZ',['均线','神秘词','xyz']),
    ('Mean($close, 5)/$close',['mean($close, 5)/$close']),
])
def test_query_units_keep_financial_phrases_parameters_and_unknowns(query,units):
    plan=QueryVocabulary([]).plan(query)
    assert [u['text'] for u in plan['units']]==units
    assert plan['logic']=='AND_BETWEEN_UNITS_OR_WITHIN_SYNONYMS'


def test_synonyms_are_or_but_concepts_are_and_with_real_highlights(repo):
    put(repo,'both','A moving average momentum','SMA(20) 与 momentum 同时用于条件。')
    put(repo,'ma','B moving average','只有均线条件。')
    put(repo,'mom','C momentum','只有动量条件。')
    for query in ['均线动量','均线 动量','moving average momentum']:
        found=repo.search(q=query)
        assert [i['entity_id'] for i in found['items']]==['both']
        assert len(found['items'][0]['matches'])==2
        for match in found['items'][0]['matches']:
            assert match['text'][match['start']:match['end']]
    assert ids(repo,'均线神秘词XYZ')==[]
    assert ids(repo,'均线 momentum missingword')==[]


def test_broad_category_titles_and_shared_urls_do_not_supply_method_evidence(repo):
    put(repo,'trend','Trend only','趋势持续则持仓。')
    put(repo,'momentum','Momentum only','动量大于零持仓。')
    put(repo,'different','Unrelated method','每月固定资产配置。',source_url='https://example.com/rsi/momentum/crossover')
    assert repo.get('trend')['knowledge']['method_family']['label']=='动量与趋势'
    assert ids(repo,'动量')==['momentum']
    assert ids(repo,'RSI')==[]
    assert ids(repo,'https://example.com/rsi/momentum/crossover')==['different']


def test_distinct_method_names_are_not_equated(repo):
    put(repo,'reversal','Reversal','反转条件。')
    put(repo,'mean','Mean reversion','均值回归条件。')
    put(repo,'low','Low volatility','低波动条件。')
    put(repo,'vol','Volatility','波动率条件。')
    put(repo,'sma','SMA method','SMA(20) 条件。')
    put(repo,'ema','EMA method','EMA(20) 条件。')
    put(repo,'pairs','Four pairs allocation','四组资产轮动。')
    put(repo,'pairtrading','Pair trading','协整价差回归。')
    assert ids(repo,'均值回归')==['mean']
    assert ids(repo,'低波动')==['low']
    assert ids(repo,'简单均线')==['sma']
    assert set(ids(repo,'均线'))=={'sma','ema'}
    assert ids(repo,'配对交易')==['pairtrading']


def test_parameterized_identifiers_do_not_drop_or_partially_match_numbers(repo):
    for eid,name in [('14','RSI14'),('paren','RSI(14)'),('space','RSI ( 14 )'),('140','RSI140'),('5','RSI5'),('stoch','StochRSI14'),('ma','MA200'),('sma','SMA200'),('ma2000','MA2000')]:
        put(repo,eid,name)
    found=repo.search(q='RSI14')
    assert {i['entity_id'] for i in found['items']}=={'14','paren','space'}
    assert found['items'][0]['entity_id']=='14'
    assert ids(repo,'MA200')==['ma']
    assert search_pattern('12-1 momentum').search('12−1 momentum')
    assert not search_pattern('12-1 momentum').search('12-12 momentum')


def test_complete_numbered_name_stays_one_unit_and_exact_alias_wins(repo):
    put(repo,'bothwords','A generic momentum','Momentum uses 12-1 months.')
    put(repo,'phrase','B 12-1 Momentum','源名称含完整词组。')
    put(repo,'exact','Z exact alias',aliases=['12-1 Momentum'])
    assert ids(repo,'12-1 Momentum')==['exact','phrase']
    assert len(repo.search(q='12-1 Momentum')['query']['units'])==1


def test_exact_full_name_alias_and_original_formula_rank_before_mentions(repo):
    put(repo,'mention','AAA use Alpha24','Alpha24 的引用。')
    put(repo,'alias','ZZZ aliased',aliases=['Alpha24'])
    assert ids(repo,'Alpha24')[0]=='alias'
    put(repo,'named','Alpha24')
    assert ids(repo,'Alpha24')[0]=='named'
    put(repo,'f5','Mean5',kind='variant',raw={'raw_formula':'Mean($close, 5)/$close','dialect':'qlib'})
    put(repo,'f50','Mean50',kind='variant',raw={'raw_formula':'Mean($close, 50)/$close','dialect':'qlib'})
    assert ids(repo,'Mean($close,5)/$close',kind='variant')==['f5']
    assert set(ids(repo,'均线',kind='variant'))=={'f5','f50'}


def test_frequency_constraints_use_explicit_data_and_only_daily_is_strict(repo):
    put(repo,'daily','Daily RSI',kind='variant',raw={'raw_formula':'RSI(close,14)','frequency':'daily',
        'required_fields':['close'],'required_fields_status':'syntax_extracted_unexpanded'})
    put(repo,'extra','Daily RSI funding',kind='variant',raw={'raw_formula':'RSI(close,14)','frequency':'daily',
        'required_fields':['close','funding_rate'],'required_fields_status':'syntax_extracted_unexpanded'})
    put(repo,'unknown','Unknown RSI',kind='variant',raw={'raw_formula':'RSI(close,14)'})
    put(repo,'weekly','Weekly RSI',kind='variant',raw={'raw_formula':'RSI(close,14)','frequency':'weekly',
        'required_fields':['close'],'required_fields_status':'syntax_extracted_unexpanded'})
    assert set(ids(repo,'日线RSI',kind='variant'))=={'daily','extra'}
    assert ids(repo,'只用日线RSI',kind='variant')==['daily']
    plan=repo.search(q='只用日线RSI',kind='variant')['query']
    assert plan['constraints'][0]['key']=='daily_ohlcv'
    assert '未知' in plan['constraints'][0]['explanation']
    assert ids(repo,'周线RSI',kind='variant')==['weekly']


def test_source_and_personal_aliases_remain_distinct_search_evidence(repo,tmp_path):
    from quantgraph.graph.personal_store import PersonalStore
    put(repo,'source','RSI strategy','RSI(14) 均值回归。',aliases=['来源短语'])
    put(repo,'competitor','A 独立别名战术','名称只包含个人别名片段。')
    repo.personal_store=PersonalStore(tmp_path/'personal.sqlite')
    repo.personal_store.update(repo.get('source'),{'aliases':['独立别名']})
    found=repo.search(q='独立别名')
    assert found['items'][0]['entity_id']=='source'
    assert found['items'][0]['matches'][0]['field']=='user_aliases'
    assert '独立别名' not in found['items'][0]['aliases']
    assert ids(repo,'来源短语RSI')==['source']


def test_warm_queries_reuse_documents_reading_and_vocabulary(repo,monkeypatch):
    import quantgraph.graph.personal_catalog as module
    put(repo,'one','RSI mean reversion','RSI(14) 均值回归。',aliases=['专属别名'])
    assert ids(repo,'RSI均值回归')==['one']
    vocabulary=repo._search_vocabulary
    def forbidden(*a,**kw):
        pytest.fail('Warm search rebuilt source reading/documents/vocabulary')
    monkeypatch.setattr(module,'readable_item',forbidden)
    monkeypatch.setattr(repo,'_document',forbidden)
    monkeypatch.setattr(module,'QueryVocabulary',forbidden)
    for query in ['RSI均值回归','RSI14','专属别名RSI','unknown','只用日线']:
        repo.search(q=query)
    assert repo._search_vocabulary is vocabulary


def test_catalog_alias_vocabulary_refreshes_on_source_change(repo):
    put(repo,'one','RSI rule','RSI(14) 条件。',aliases=['蓝海词'])
    assert ids(repo,'蓝海词RSI')==['one']
    put(repo,'one','RSI rule','RSI(14) 条件。',aliases=['青山词'])
    assert ids(repo,'蓝海词RSI')==[]
    assert ids(repo,'青山词RSI')==['one']


def test_literal_full_name_is_not_lost_to_frequency_interpretation(repo):
    put(repo,'literal','日频动量','来源未报告频率。')
    result=repo.search(q='日频动量')
    assert result['items'][0]['entity_id']=='literal'
    assert result['items'][0]['matches'][0]['match_type']=='EXACT_LITERAL'
    assert result['items'][0]['frequency'] is None
    assert '字面匹配' in result['query']['exact_literal_precedence']
    # An explicit UI filter is never bypassed by exact name priority.
    assert ids(repo,'日频动量',frequency='daily')==[]


def test_rsi_acronym_does_not_expand_to_generic_relative_strength_rotation(repo):
    put(repo,'rsi','RSI indicator','RSI(14) 低于30。')
    put(repo,'rotation','Relative strength rotation','比较两资产相对强弱后轮动。')
    assert ids(repo,'RSI')==['rsi']
    assert set(ids(repo,'相对强弱'))=={'rsi','rotation'}


def test_hyphenated_mean_reversion_is_same_phrase_not_reversal(repo):
    put(repo,'mean','Mean-Reversion','完整金融短语。')
    put(repo,'rev','Reversal','独立方法。')
    assert ids(repo,'均值回归')==['mean']


def test_one_sources_compound_alias_does_not_hide_two_concepts_for_others(repo):
    put(repo,'alias','Aliased',aliases=['均线动量'])
    put(repo,'separate','EMA condition','momentum 必须大于零。')
    assert ids(repo,'均线动量')==['alias','separate']
    assert len(repo.search(q='均线动量')['query']['units'])==2


def test_named_bollinger_bands_operator_is_a_supported_spelling(repo):
    put(repo,'bands','Band condition','BollingerBands(20,2) mean reversion。')
    assert ids(repo,'布林带均值回归')==['bands']

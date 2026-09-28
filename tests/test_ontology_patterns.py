import pytest
from quantgraph.normalize.strategy.parser import parse_rule, template_signature
from quantgraph.graph.ontology.canonical import map_records, relation_decision


@pytest.mark.parametrize('rule,kind', [
    ('日频：若 UO(7,14,28)>63 → 满仓 QQQ，否则 SHV。', 'threshold_switch'),
    ('日频：若 QQQ21日实现波动×√252<0.12 → 满仓 QQQ，否则 SHV。', 'threshold_switch'),
    ('日频：SMA(8)上穿SMA(24)→满仓 QQQ；SMA(8)下穿SMA(24)→满仓 SHV。', 'moving_average_crossover'),
    ('月末：若 QQQ过去7月总分收益>0→满仓 QQQ，否则 SHV。', 'absolute_momentum_zero'),
    ('日频：QQQ收盘>此前21日最高收盘→满仓 QQQ；QQQ收盘<此前8日最低收盘→满仓 SHV。', 'channel_breakout'),
    ('日频：QQQ的ZScore(21)<-2→满仓 QQQ；ZScore(21)>0→满仓 SHV。', 'zscore_mean_reversion'),
    ('月末：在[QQQ,GLD,SHV]按过去7月总收益降序取前2个等权；并列按代码升序。', 'cross_sectional_momentum_ranking'),
    ('日频：配对(QQQ,SPY)；价差=log(QQQ)-log(SPY)；ZScore(21)>2→空QQQ多SPY；ZScore(21)<-2→多QQQ空SPY；|ZScore(21)|<0.5→平仓。', 'pairs_zscore'),
])
def test_closed_grammars(rule, kind):
    parsed = parse_rule(rule)
    assert parsed['rule_ast']['type'] == kind
    assert not parsed['executable']
    assert parse_rule(rule + '另加3%止损。')['rule_ast'] is None


def test_asset_mismatch_arity_and_template_stability():
    cross_asset = parse_rule('日频：若 QQQ21日实现波动×√252<0.12 → 满仓 SPY，否则 SHV。')['rule_ast']
    assert cross_asset['condition']['left']['asset'] == 'QQQ'
    assert cross_asset['then']['asset'] == 'SPY'
    assert cross_asset['costs'] is None
    assert parse_rule('日频：若 RSI(7,9)>53 → 满仓 QQQ，否则 SHV。')['rule_ast'] is None
    a = parse_rule('日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。')['rule_ast']
    b = parse_rule('日频：若 RSI(9)>62 → 满仓 GLD，否则 BIL。')['rule_ast']
    assert template_signature(a) == template_signature(b)


def test_cross_source_no_name_or_formula_merge():
    rows = [dict(record_id='one', source_id='jkp', factor_concept='历史价格动量', source_url='https://example.org/a', normalized_formula='x'),
            dict(record_id='two', source_id='wq101', factor_concept='wq101:alpha001', source_url='https://example.org/b', normalized_formula='x')]
    mapped = map_records(rows)
    assert len(mapped['links']) == len(mapped['unresolved']) == len(mapped['conflicts']) == 1
    assert mapped['summary']['same_as_merges'] == 0
    assert mapped['links'][0]['relation'] == 'RELATED_TO'
    assert relation_decision(rows[0], rows[1])['status'] == 'REVIEW_REQUIRED'
    evidence = {'source': 'https://example.org', 'reviewed_by': 'fixture'}
    assert relation_decision(rows[0], rows[1], evidence=evidence)['relation'] == 'RELATED_TO'

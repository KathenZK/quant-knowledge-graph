import pytest
from quantgraph.normalize.strategy.parser import parse_rule


@pytest.mark.parametrize('rule',[
 '日频：若收盘>EMA(20)+1×ATR(10)→满仓SPY，否则BIL。',
 '日频：若ADX(14)>25且+DI(14)>-DI(14)→满仓SPY，否则BIL。',
 '日频：若SMA(10)>SMA(20)>SMA(50)>SMA(100)>SMA(200)→满仓SPY，否则BIL。',
 '日频：若Open<PriorClose→满仓SPY，否则BIL。',
 '月末：若SPY近36个月总分收益<0→次月满仓SPY，否则BIL。',
 '月末若SPY收盘>=过去200交易日最高收盘→次月满仓SPY；否则现金。',
])
def test_complete_additional_syntax_is_fully_preserved(rule):
    value=parse_rule(rule)
    assert value['parse_status']=='PARSED'
    assert value['rule_ast']['costs'] is None and not value['executable']


@pytest.mark.parametrize('rule',[
 '日频：若ADX(14)>25且+DI>-DI→满仓SPY，否则BIL。',
 '日频：若收盘>EMA(20)+ATR→满仓SPY，否则BIL。',
 '日频：若MACD(12,26)>0→满仓SPY，否则BIL。',
 '日频：若收盘>云顶→满仓SPY，否则BIL。',
 '日频：若ROC(0)>0→满仓SPY，否则BIL。',
 '月末：若SPY近0月总分收益<0→次月满仓SPY，否则BIL。',
 '日频：若Open<PriorClose→满仓SPY，否则BIL。随后遇止损反手。',
])
def test_unspecified_inputs_and_unconsumed_clauses_stay_review(rule):
    assert parse_rule(rule)['rule_ast'] is None


def test_cross_asset_signal_and_lag_are_not_replaced_with_allocated_asset():
    ast=parse_rule('日频；若SPY收盘>其20日简单均线则满仓HYG，否则满仓SHY。')['rule_ast']
    assert ast['condition']['left']['asset']=='SPY'
    assert ast['then']['asset']=='HYG'
    ast=parse_rule('日频：若CMF(20)_t>CMF(20)_{t-1}→满仓SPY，否则BIL。')['rule_ast']
    assert ast['condition']['right']['type']=='lag'
    assert ast['condition']['right']['periods']==1


def test_dsl_requires_complete_spec_and_never_grants_execution():
    import json
    spec=dict(type='long_only_signal',signal='PRICE_SMA',asset='BTC/USD',schedule='daily_eod',parameters=[50],
       comparison='gt_else_cash',allocation='all_equity_net_of_costs',cash='USD_ZERO_INTEREST',initial_position='cash',
       indicator_semantics='SMA complete 50 closing prices',entry='close>SMA50',exit='close<=SMA50',
       rebalance='signal_change_only',stop_loss_fraction=None,take_profit_fraction=None,parent_record_id='M0234',
       derivation='Explicit long-only research adaptation; not a native source claim')
    r=parse_rule('QG-DSL/1\n'+json.dumps(spec))
    assert r['rule_ast']['else']['cash'] and not r['executable']
    del spec['exit']
    assert parse_rule('QG-DSL/1\n'+json.dumps(spec))['parse_status']=='REVIEW'

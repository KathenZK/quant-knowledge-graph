import pytest
from quantgraph.normalize.formula import parse,normalize,dsl

def test_dialects_do_not_collapse_rank():
    assert parse('Rank($close,5)','qlib')['op']=='qlib:ts_rank'
    assert parse('rank(close)','wq101')['op']=='wq101:cs_rank'

def test_power_precedence_and_numeric_preservation():
    a=parse('-2^3^2','wq101')
    assert a['type']=='unary' and a['args'][0]['op']=='pow'
    assert a['args'][0]['args'][1]['op']=='pow'
    n=normalize('correlation(close,volume,6.28259)','wq101')
    assert '6.28259' in n['numeric_literals']
    assert normalize('close+1e-12','wq101')['ast']['args'][1]['value']=='0.000000000001'

def test_nested_conditional():
    a=parse('(close<open)?-1:((close==open)?0:1)','wq101')
    assert a['type']=='if' and a['args'][2]['type']=='if'

def test_invalid_formula_not_repaired():
    assert normalize('SUM(CLOSE, 5))','gtja191')['parse_status']=='parse_error'
    assert normalize('close * __import__("os")','wq101')['parse_status']=='parse_error'

def test_aliases_structural_only():
    a=normalize('Ref($close, 5)/$close','qlib')
    b=normalize('Ref( $close , 5.0 ) / $close','qlib')
    assert a['formula_hash']==b['formula_hash']
    assert a['formula_hash']!=normalize('Ref($close, 6)/$close','qlib')['formula_hash']
    assert normalize('close+open','wq101')['formula_hash']!=normalize('open+close','wq101')['formula_hash']


def test_input_span_handles_nested_delays_without_inventing_windows():
    from quantgraph.normalize.formula.lookback import lookback
    assert lookback(parse('Ref($close,5)/$close','qlib'),'qlib')['value']==6
    assert lookback(parse('Mean(Ref($close,2),5)','qlib'),'qlib')['value']==7
    assert lookback(parse('Quantile($close,5,0.8)','qlib'),'qlib')['value']==5
    assert lookback(parse('Mean($close,0)','qlib'),'qlib') is None
    assert lookback(parse('Ref($close,-1)','qlib'),'qlib') is None
    assert lookback(parse('correlation(close,volume,6.28259)','wq101'),'wq101') is None

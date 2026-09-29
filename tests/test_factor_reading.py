from copy import deepcopy

from quantgraph.graph.factor_reading import enrich_factor_reading
from quantgraph.normalize.formula.parser import normalize


def record(formula, dialect='qlib', **extra):
    parsed = normalize(formula, dialect)
    return dict(raw_formula=formula, dialect=dialect, formula_ast=parsed['ast'],
                required_fields=parsed['required_fields'], **extra)


def test_original_ratio_orientation_and_hypothetical_values():
    raw = record('Ref($close, 60)/$close', lookback={'value': 61, 'unit': 'observations', 'scope': 'includes current observation'})
    original = deepcopy(raw)
    guide = enrich_factor_reading({'name': 'ROC60'}, raw)
    assert '60 个观测之前的收盘价' in guide['summary']
    assert '除以（收盘价）' in guide['summary']
    assert '0.909091' in guide['example']['text']
    assert '不是市场结果' in guide['example']['basis']
    assert '61' in guide['semantics'][0]['text']
    assert raw == original


def test_qlib_rank_and_worldquant_rank_never_conflated():
    ts = enrich_factor_reading({'name': 'Rank'}, record('Rank($close, 20)'))
    cs = enrich_factor_reading({'name': 'rank'}, record('rank(close)', 'wq101'))
    assert '时序排名' in ts['summary'] and '截面排名' in cs['summary']
    assert '不是股票之间' in ts['semantics'][0]['text']
    assert '不是单个对象' in cs['semantics'][0]['text']
    assert ts['example'] is None and cs['example'] is None


def test_three_argument_sma_retains_smoothing_identity():
    guide = enrich_factor_reading({'name': 'Alpha151'}, record('SMA(CLOSE-DELAY(CLOSE,20),20,1)', 'gtja191'))
    assert '20 个观测之前' in guide['summary']
    assert '三参数递推平滑' in guide['summary'] and '权重参数 1' in guide['summary']
    assert guide['example'] is None
    assert any('不能替换成 Qlib Mean' in row['text'] for row in guide['semantics'])


def test_missing_variance_convention_prevents_fake_example():
    guide = enrich_factor_reading({'name': 'WVMA5'}, record('Std(Abs($close/Ref($close,1)-1)*$volume,5)/(Mean(Abs($close/Ref($close,1)-1)*$volume,5)+1e-12)'))
    assert '标准差' in guide['summary'] and '均值' in guide['summary']
    assert '成交量' in guide['summary']
    assert guide['example'] is None
    assert any('未指定 ddof' in row['text'] for row in guide['semantics'])


def test_arithmetic_examples_match_complete_expression():
    mean = enrich_factor_reading({'name': 'MA5'}, record('Mean($close,5)/$close'))
    assert '0.927273' in mean['example']['text']
    subtraction = enrich_factor_reading({'name': '市场超额收益'}, record('market_return-risk_free_return', 'portfolio'))
    assert '0.06' in subtraction['example']['text']
    assert '市场组合收益率' in subtraction['summary'] and '无风险收益率' in subtraction['summary']
    fractional = enrich_factor_reading({'name': 'fractional'}, record('Mean($close,5.5)/$close'))
    assert '5.5' in fractional['summary']
    assert fractional['example'] is None


def test_simple_latex_keeps_lags_and_not_macro_as_operator():
    guide = enrich_factor_reading({'name': 'Momentum'}, {'description': r'$\frac{RI\mbox{*}_{t-1}}{RI\mbox{*}_{t-3}} - 1$', 'required_fields': ['RI']})
    assert '滞后 1 期的RI*除以滞后 3 期的RI*' in guide['summary']
    assert '减去 1' in guide['summary'] and '0.1' in guide['example']['text']
    assert [v['name'] for v in guide['variables']] == ['RI*']
    difference = enrich_factor_reading({'name': 'Net Equity Payout'}, {'description': r'$log\left(\frac{RI\mbox{*}_t}{RI\mbox{*}_{t-1}}\right) - log\left(\frac{ME\mbox{*}_t}{ME\mbox{*}_{t-1}}\right)$'})
    assert '再减去' in difference['summary']
    assert not any(v['name'] == 'left' for v in difference['variables'])


def test_textual_residual_definition_does_not_infer_from_title():
    raw = {'description': 'Run a rolling regression over 36 months of excess return (retrf) on excess market return (mktrf), size and value factors (smb, hml) and compute idiosyncratic returns as the one-month lagged residual. ResidualMomentum is the rolling mean of the residual divided by the rolling standard deviation of the residual, both computed over the past 11 months.'}
    guide = enrich_factor_reading({'name': 'Momentum based on FF3 residuals'}, raw)
    assert '36 个月' in guide['summary'] and '11 个月' in guide['summary']
    assert '滞后一个月' in guide['summary']
    assert {v['name'] for v in guide['variables']} == {'retrf', 'mktrf', 'smb', 'hml'}
    raw['required_fields'] = ['retrf', 'mktrf']
    original = deepcopy(raw)
    guide = enrich_factor_reading({'name': 'Momentum based on FF3 residuals'}, raw)
    assert {v['name'] for v in guide['variables']} == {'retrf', 'mktrf', 'smb', 'hml'}
    assert raw == original
    assert all(v['evidence'] == '(smb, hml)' for v in guide['variables'] if v['name'] in {'smb', 'hml'})
    raw = {'description': 'Keep fpi = 1. Binary variable equal to 1 if mean analyst earnings forecast for the next quarter (meanest) has improved over the previous month, and 0 otherwise.'}
    guide = enrich_factor_reading({'name': 'Down forecast EPS'}, raw)
    assert '提高，指标取 1' in guide['summary']
    assert any(s['status'] == 'REVIEW_REQUIRED' for s in guide['semantics'])
    assert {v['name'] for v in guide['variables']} == {'fpi', 'meanest'}


def test_prose_symbols_require_explicit_definition_evidence():
    value = {'name': 'FF3 smb hml profitable signal'}
    no_definition = enrich_factor_reading(value, {})
    assert no_definition['variables'] == []
    guide = enrich_factor_reading(value, {'description': 'Measure return (monthly), from a paper (2011); see (Table 2). Universe (NYSE). Market excess return (market_excess), accounting assets (at). Keep flag = 1.'})
    assert {v['name'] for v in guide['variables']} == {'market_excess', 'at', 'flag'}
    assert all('EXPLICIT_DESCRIPTION_SYMBOL' == v['basis'] for v in guide['variables'])
    assert all('原文' in v['meaning'] for v in guide['variables'])


def test_unknown_reference_and_unsupported_formula_are_candid():
    missing = enrich_factor_reading({'name': 'Famous profitable strategy'}, {})
    assert '尚未收录完整定义' in missing['summary']
    assert missing['example'] is None
    unsupported = enrich_factor_reading({'name': 'private formula'}, {'formula': '__import__("os").system("touch /tmp/not-executed")', 'dialect': 'qlib'})
    assert '无法可靠生成' in unsupported['summary']
    assert unsupported['example'] is None
    mismatched = record('$close/$open')
    mismatched['formula_ast'] = normalize('$open/$close','qlib')['ast']
    assert enrich_factor_reading({'name': 'mismatch'}, mismatched)['example'] is None


def test_deep_archived_source_keeps_formula_instead_of_crashing_catalog():
    formula = '$close'
    for _ in range(25):
        formula = 'Mean(' + formula + ',5)'
    guide = enrich_factor_reading({'name': 'Deep source definition', 'source_type': 'factor_source_record'}, record(formula))
    assert guide['summary'] and guide['example'] is None
    assert any('mean' in v['name'] for v in guide['variables'])

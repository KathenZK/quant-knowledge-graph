"""Independent contracts for classifying reported rule text, not admitting it.

These small descriptions exercise semantic boundaries found in the CSV review.
They do not verify the upstream sources or imply that a strategy is executable.
"""
from copy import deepcopy

import pytest

from quantgraph.graph.metadata_classification import infer, positive_passages


def record(rule, *, name="", source_url="https://example.org/source"):
    return {
        "reported_fields": {
            "名称": {"value": name},
            "source_url": {"value": source_url},
            "规则": {"value": rule},
        }
    }


@pytest.mark.parametrize("name", ["RSI因子", "买入卖出动量策略", "交易工具教程"])
def test_name_does_not_supply_missing_body_evidence(name):
    result = infer(record("仅有一段说明，无法辨认输出用途。", name=name))
    assert result["kind"] == "unclassified"
    assert result["confidence"] == "LOW"


@pytest.mark.parametrize(
    "rule,kind,subtype",
    [
        ("因子定义：过去20日收益率的标准差。", "factor", "signal_definition"),
        ("计算过去20日收益率的标准差得到波动值。", "factor", "signal_definition"),
        ("截面回归价格与市值，取回归残差作为特征。", "factor", "signal_definition"),
        ("信号定义为过去一年成交量调整动量，未给出调整公式。", "factor", "signal_definition"),
        ("价格回归长期均值时做均值回归。", "strategy", "strategy_component"),
        ("RSI低于30买入，高于70卖出。", "strategy", "trading_rule"),
        ("未持仓且收盘价突破20日高点时买入，跌破10日低点时卖出。", "strategy", "trading_rule"),
        ("未投资时若动量为正则set_holdings(SPY, 1)。", "strategy", "trading_rule"),
        ("每月按ROE筛选股票，取前20只。", "strategy", "selection_outline"),
        ("组合配置60% SPY与40% TLT。", "strategy", "portfolio_rule"),
        ("对股票组合采用EqualWeightingPortfolioConstructionModel。", "strategy", "portfolio_rule"),
        ("对每只股票的质量因子和动量因子等权合成，得到综合因子。", "factor", "composite_signal"),
        ("因子检验：计算RankIC，再比较各因子分组表现。", "reference", "research_protocol"),
        ("页印年化收益率=20%，RankIC均值约0.05；没有给出计算定义。", "unclassified", "insufficient_description"),
    ],
    ids=[
        "explicit-feature", "numeric-feature", "regression-residual",
        "incomplete-is-still-feature", "mean-reversion-is-not-regression-feature",
        "indicator-used-for-trading", "not-invested-is-state", "not-invested-code",
        "security-selection", "asset-weights", "portfolio-construction-api",
        "feature-combination", "research-protocol", "performance-is-not-definition",
    ],
)
def test_rule_body_output_controls_type(rule, kind, subtype):
    result = infer(record(rule))
    assert (result["kind"], result["subtype"]) == (kind, subtype)


@pytest.mark.parametrize(
    "rule",
    [
        "未提供买入、卖出或调仓规则。",
        "没有给出买入和卖出的规则。",
        "无固定持仓或调仓规则。",
        "不是买入SPY并持有的策略。",
        "并非开仓或平仓的规则。",
        "本条只写来源已印出的规则。未披露交易规则。",
        "**未提供买入、卖出或调仓规则**。",
        "**不是买入SPY并持有的策略**。",
    ],
    ids=["missing", "not-provided", "no-fixed-rule", "not-trading", "not-position-rule",
         "boilerplate", "markdown-negation", "markdown-not-strategy"],
)
def test_negative_description_does_not_create_trading_rule(rule):
    assert infer(record(rule))["kind"] == "unclassified"


@pytest.mark.parametrize(
    "rule",
    [
        "因子=过去20日收益率的标准差；不是买入SPY的规则。",
        "因子=过去20日收益率的标准差，不同于每月调仓股票的策略。",
        "不是固定持仓策略：本条为信号定义，因子=过去20日收益率的标准差。",
        "相对已收买入SPY的策略：本条是信号定义，因子=过去20日收益率的标准差。",
    ],
    ids=["negated-tail", "comparison-tail", "positive-restatement", "comparison-restatement"],
)
def test_comparison_actions_do_not_override_actual_feature(rule):
    result = infer(record(rule))
    assert result["kind"] == "factor"
    assert all(item["quote"] in rule for item in result["evidence"])
    assert all("买入SPY" not in item["quote"] for item in result["evidence"])


@pytest.mark.parametrize(
    "rule,kind",
    [
        ("信号（Signal Browser Definition）：计算过去12个月动量。组合规则：每月买入最高分股票，卖出最低分股票。", "factor"),
        ("特征构造：过去12个月收益率。组合（Documentation）：每月调仓，做多最高组、做空最低组。", "factor"),
        ("依据Ken French《因子定义》，SMB=(小盘组合收益-大盘组合收益)。做多小盘、做空大盘形成该因子收益序列。", "factor"),
        ("每月买入排名最高的股票。附录参考信号（Signal Browser Definition）：过去12个月动量。", "strategy"),
    ],
    ids=["osap-definition-plus-test-portfolio", "jkp-definition-plus-test-portfolio",
         "factor-return-construction", "template-label-in-tail-is-not-template"],
)
def test_definition_templates_and_factor_returns_keep_primary_object(rule, kind):
    result = infer(record(rule))
    assert result["kind"] == kind
    if rule.startswith("信号（Signal Browser Definition）"):
        assert all("每月买入" not in item["quote"] for item in result["evidence"])


@pytest.mark.parametrize(
    "rule",
    [
        "若收盘价高于均线则**买入**SPY。",
        "若收盘价高于均线则`set_holdings(SPY, 1)`。",
        "动量为正→**SPY**；其余情况→**BIL**。",
        "多：SPY；空：QQQ。",
    ],
    ids=["markdown-action", "inline-code-action", "markdown-target", "position-colon"],
)
def test_formatting_does_not_hide_trade_or_target(rule):
    result = infer(record(rule))
    assert result["kind"] == "strategy"
    assert all(item["quote"] in rule for item in result["evidence"])


@pytest.mark.parametrize(
    "rule",
    [
        "因子定义：主动买入成交量减去主动卖出成交量，再除以总成交量。",
        "定义成交量因子=对过去20日成交量排序的百分位。",
        "对每只股票的质量分与动量分按权重1:1合成，定义综合信号=质量分+动量分。",
    ],
    ids=["transaction-flow-is-input", "time-series-rank-is-feature", "signal-weights-are-not-holdings"],
)
def test_feature_operations_are_not_portfolio_instructions(rule):
    assert infer(record(rule))["kind"] == "factor"


@pytest.mark.parametrize(
    "rule",
    [
        "因子定义：过去12个月收益率。按因子排序选股，取前20只股票。",
        "因子定义：过去12个月收益率。股票组合按动量排名比例配置权重。",
        "对股票定义波动率指标=过去20日收益率标准差。用波动率倒数作为资产配置权重。",
        "因子定义：过去12个月收益率。若信号为正，则买入股票。",
        "因子定义：主动买入成交量减去主动卖出成交量。信号为正则买入股票。",
    ],
    ids=["factor-then-selection", "factor-then-allocation", "indicator-then-weights",
         "factor-then-trading", "flow-input-then-trading"],
)
def test_feature_used_for_actual_asset_choice_is_strategy(rule):
    assert infer(record(rule))["kind"] == "strategy"


def test_missing_computation_details_do_not_erase_identifiable_type():
    result = infer(record("信号定义为过去一年成交量调整动量，未给出调整公式。"))
    assert result["kind"] == "factor"
    assert "DEFINITION_DETAILS_MISSING" in result["quality_flags"]


def test_positive_dependency_is_flagged_but_negated_comparison_is_not():
    actual = infer(record("因子计算沿用M1234的规则。"))
    comparison = infer(record("因子=过去20日收益率标准差；不是基于M1234的策略。"))
    assert "CROSS_RECORD_DEPENDENCY" in actual["quality_flags"]
    assert "CROSS_RECORD_DEPENDENCY" not in comparison["quality_flags"]


def test_extraction_damage_remains_separate_from_type():
    result = infer(record("入场后设置止损，strategy.entry使用Sh或t参数。"))
    assert result["kind"] == "strategy"
    assert "POSSIBLE_EXTRACTION_ERROR" in result["quality_flags"]


def test_evidence_is_exact_original_text_and_input_is_not_mutated():
    rule = "不是固定持仓策略：本条为信号定义，**因子**=过去20日收益率标准差。"
    source = record(rule, name="误导性的买入策略名称", source_url="https://example.org/buy-sell")
    before = deepcopy(source)
    result = infer(source)
    assert result["kind"] == "factor"
    assert source == before
    assert result["evidence"]
    assert all(item["field"] == "规则" and item["quote"] in rule for item in result["evidence"])
    assert all(part in rule for part in positive_passages(rule))

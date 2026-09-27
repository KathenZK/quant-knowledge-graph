"""Review-queue labels only. A keyword match never constructs an AST."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class RuleArchetype:
    name: str
    pattern: str


ARCHETYPES = [RuleArchetype(*row) for row in [
    ('source_code_fragment', r'strategy\.entry|strategy\.exit|input\(|Pine|代码'),
    ('source_factor_portfolio', r'Signal Browser Definition|Documentation\.pdf'),
    ('pairs_trading', r'配对|配對|pairs|价差|協整'),
    ('dual_momentum', r'dual.momentum|双动量|双重动量'),
    ('absolute_momentum', r'absolute.momentum|绝对动量|Intrinsic.Momentum'),
    ('relative_momentum', r'relative.momentum|相对动量|满仓较高者'),
    ('volatility_targeting', r'目标.{0,4}波动|波动.{0,4}目标|volatility.target'),
    ('trend_volatility_filter', r'(?:均线|SMA|EMA).*(?:波动|ATR)|(?:波动|ATR).*(?:SMA|EMA|均线)'),
    ('cross_sectional_ranking', r'横截面|截面|排名|排序|Top\d|前\d'),
    ('etf_rotation', r'轮动|輪動|配对切换|Paired.Switching'),
    ('risk_on_off', r'风险开|风险关|risk.on|risk.off|金丝雀'),
    ('rsi', r'RSI'), ('macd', r'MACD'), ('roc', r'ROC|RoC'),
    ('bollinger', r'Bollinger|布林|BBW'),
    ('ema_crossover', r'EMA.*(?:上穿|下穿|交叉|金叉|死叉)'),
    ('sma_crossover', r'SMA.*(?:上穿|下穿|交叉|金叉|死叉)'),
    ('price_ma', r'SMA|EMA|均线|均線'),
    ('oscillator', r'Stoch|Williams|CCI|MFI|UO\(|CMO\(|STC\(|Aroon|RVI'),
    ('volatility_filter', r'波动|波動|ATR|VIX'),
    ('breakout_donchian', r'突破|新高|Donchian|通道'),
    ('zscore', r'ZScore|Z-score|z.score'),
    ('mean_reversion', r'回归|回歸|reversion'),
    ('momentum_other', r'动量|動量|Momentum|收益>'),
    ('threshold_allocation', r'阈值|阈|满仓|否则'),
]]


def classify(text):
    return next((a.name for a in ARCHETYPES if re.search(a.pattern, text, re.I)), 'other_or_ambiguous')


def review_reason(text):
    from .parser import rule_body
    if re.search(r'strategy\.entry|strategy\.exit|input\(', text):
        return 'SOURCE_CODE_REQUIRES_REPRODUCTION'
    if re.search(r'公式未公开|周期未公开|细节不补|未在该行写出|规则同[WM]\d', text):
        return 'EXPLICIT_MISSING_OR_CROSS_RECORD_DEFINITION'
    if rule_body(text) is None:
        return 'ENVELOPE_OR_ADDITIONAL_CLAUSES_REQUIRE_REVIEW'
    return 'UNSUPPORTED_GRAMMAR_COMPLETENESS_UNVERIFIED'

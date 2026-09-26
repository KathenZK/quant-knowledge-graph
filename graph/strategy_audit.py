"""Aggregate-only corpus diagnostics. Rules and IDs stay in private datasets."""
from collections import Counter
import re
from quantgraph.graph.grokbot import normalize_bundle, content_hash
from quantgraph.normalize.strategy.parser import VERSION

ARCHETYPES = [
    ('source_code_fragment', r'strategy\.entry|strategy\.exit|input\(|Pine|代码'),
    ('source_factor_portfolio', r'Signal Browser Definition|Documentation\.pdf'),
    ('pairs', r'配对|配對|pairs|价差|協整'),
    ('cross_sectional_ranking', r'横截面|截面|排名|排序|Top\d|前\d'),
    ('etf_rotation', r'轮动|輪動|满仓较高者|配对切换|Paired Switching'),
    ('oscillator', r'RSI|Stoch|Williams|CCI|MFI|UO\(|CMO\(|STC\('),
    ('moving_average', r'SMA|EMA|均线|均線'),
    ('volatility', r'波动|波動|ATR|VIX'),
    ('momentum', r'动量|動量|Momentum|收益>'),
    ('breakout', r'突破|新高|Donchian|通道'),
    ('mean_reversion', r'回归|回歸|ZScore|Z-score'),
    ('threshold_allocation', r'阈值|阈|满仓|否则'),
]


def archetype(text):
    return next((name for name, pattern in ARCHETYPES if re.search(pattern, text, re.I)), 'other_or_ambiguous')


def audit_bundle(bundle, baseline):
    rows, concepts, templates = normalize_bundle(bundle)
    success = sum(r['definition_admitted'] for r in rows)
    return {'schema_version': '1.0', 'input_sha256': bundle['sha256'], 'parser_version': VERSION,
            'raw_records': len(rows), 'before_parsed': baseline['parse_success'], 'after_parsed': success,
            'before_review': baseline['parse_failure'], 'after_review': len(rows) - success,
            'coverage_before': baseline['parse_success'] / len(rows), 'coverage_after': success / len(rows),
            'review_queue_reduction': success - baseline['parse_success'],
            'concepts': len(concepts), 'templates': len(templates), 'variants': len(rows),
            'factor_linked': success, 'link_status': 'RULE_LINK_ONLY', 'rights_review_required': len(rows),
            'executable': 0, 'public_corpus_records': 0,
            'top_archetypes': dict(Counter(archetype(r['raw_record']['规则']) for r in rows)),
            'remaining_archetypes': dict(Counter(archetype(r['raw_record']['规则']) for r in rows if not r['definition_admitted'])),
            'review_errors': dict(Counter(reason for r in rows for reason in r['review_reasons'])),
            'stable_identity_policy': 'Source native ID + original rule/market/source hash; templates use structural slots. Parser upgrades add projections, never rewrite raw.',
            'methodology_sha256': content_hash({'archetypes': ARCHETYPES, 'version': VERSION})}

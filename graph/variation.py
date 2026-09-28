"""Observed sibling differences are query-time facts, not immutable identities."""
from collections import defaultdict
import json


def signature(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def components(node, keys, path=()):
    values = []
    if isinstance(node, dict):
        for key, value in sorted(node.items()):
            if key in keys and value is not None:
                values.append((path + (key,), value))
            else:
                values.extend(components(value, keys, path + (key,)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            values.extend(components(value, keys, path + (str(index),)))
    return values


def apply_observed_axes(rows):
    groups = defaultdict(list)
    for row in rows:
        variant = row['variant']
        variant['variation_axes'] = []
        ast = variant.get('rule_ast') or {}
        variant['possible_variation_axes'] = [name for name, keys in (
            ('PARAMETER_VARIANT', {'parameters', 'value', 'threshold', 'exit_threshold'}),
            ('ASSET_VARIANT', {'asset', 'assets', 'risk_asset', 'safe_asset'})) if components(ast, keys)]
        if variant.get('strategy_template_id'):
            groups[variant['strategy_template_id']].append(row)
    for group in groups.values():
        observed = defaultdict(set)
        for row in group:
            v, ast = row['variant'], row['variant']['rule_ast']
            for name, keys in (
                ('PARAMETER_VARIANT', {'parameters', 'value', 'threshold', 'exit_threshold'}),
                ('ASSET_VARIANT', {'asset', 'assets', 'risk_asset', 'safe_asset'}),
                ('UNIVERSE_VARIANT', {'universe'}),
                ('TIMEFRAME_VARIANT', {'schedule', 'timeframe'}),
                ('EXECUTION_VARIANT', {'execution_timing', 'execution_price', 'rebalance'})):
                value = components(ast, keys)
                if value:
                    observed[name].add(signature(value))
            market = {k: value for k, value in v.get('market_taxonomy', {}).items()
                      if k in {'asset_class', 'market_type', 'exchange', 'venue'}
                      and value not in (None, '', 'unknown', 'UNKNOWN', [])
                      and (not isinstance(value, list) or all(x not in ('unknown', 'UNKNOWN', None, '') for x in value))}
            if market:
                observed['MARKET_VARIANT'].add(signature(market))
        axes = sorted(name for name, values in observed.items() if len(values) > 1)
        for row in group:
            row['variant']['variation_axes'] = axes
            row['variation_evidence'] = {'basis': 'CURRENT_SIBLING_DIFFERENCES',
                                         'sibling_count': len(group),
                                         'axes': axes}
    return rows

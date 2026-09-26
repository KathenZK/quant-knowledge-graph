"""Closed, full-match grammars. No extraction from arbitrary prose or code."""
import re

SYMBOL = r'[A-Z][A-Z0-9.-]{0,9}'


def switch_ast(expr, operand):
    """Explicit conjunctions and full allocations only; no context inference.

    An unnamed +DI, upper band or signal line remains unsupported because its
    period/input is not stated in the expression. Cash is an unresolved asset,
    not a fabricated zero-return ETF.
    """
    m = re.fullmatch(rf'(?:若)?(.+?)(?:→|则)(次月|下月)?满仓({SYMBOL})[;；,，]?否则(满仓)?({SYMBOL}|现金(?:\(T-bill\))?)', expr)
    if not m:
        return None
    condition, timing, risk, _, safe = m.groups()
    conditions = []
    for clause in re.split('且|∧', condition):
        comparison = re.fullmatch(r'(.+?)(>=|<=|>|<)(.+)', clause)
        if not comparison:
            return None
        left, right = operand(comparison[1]), operand(comparison[3])
        if not left or not right or left['type'] == 'number':
            return None
        if any(x.get('asset') not in {None, risk} for x in (left, right)):
            return None
        conditions.append({'operator': comparison[2], 'left': left, 'right': right})
    if not 1 <= len(conditions) <= 3:
        return None
    cash = safe.startswith('现金')
    return {'type': 'threshold_switch' if len(conditions) == 1 else 'conjunctive_switch',
            **({'condition': conditions[0]} if len(conditions) == 1 else {'conditions': conditions, 'operator': 'AND'}),
            'then': {'asset': risk, 'allocation': 'full'},
            'else': {'asset': None if cash else safe, 'allocation': 'full' if m[4] or cash else None},
            'safe_asset_description': safe if cash else None,
            'reported_execution_period': 'following_month' if timing else None}


def monthly_ast(expr):
    m = re.fullmatch(rf'若({SYMBOL})(?:过去|近)(\d+)个?月总分收益>0(?:→|则)(?:次月|下月)?满仓\1[;；,，]?否则(现金(?:\(T-bill\))?|满仓{SYMBOL})', expr)
    if m and int(m[2]) > 0:
        cash = m[3].startswith('现金')
        return {'type': 'absolute_momentum_zero', 'assets': [m[1], None if cash else m[3][2:]],
                'lookback': {'value': int(m[2]), 'unit': 'months'}, 'threshold': 0,
                'return_basis': 'total_return_as_reported', 'allocation': 'full',
                'safe_asset_description': m[3] if cash else None, 'safe_allocation': 'full'}
    m = re.fullmatch(rf'若({SYMBOL})(?:月收|月收盘)(?:价)?>(?:近|过去)(\d+)个?月(?:收盘SMA|简单均线)(?:→|则)(?:次月|下月)满仓\1[;；,，]?否则(现金(?:\(T-bill\))?)', expr)
    if not m:
        m = re.fullmatch(rf'若({SYMBOL})月收盘价高于其过去(\d+)个月收盘均价则下月满仓\1[,，]否则(现金)', expr)
    if m and int(m[2]) > 0:
        return {'type': 'threshold_switch', 'condition': {'operator': '>',
                'left': {'type': 'price', 'field': 'close', 'asset': m[1]},
                'right': {'type': 'indicator', 'name': 'SMA', 'parameters': [int(m[2])],
                          'sampling_unit': 'months', 'asset': m[1], 'smoothing': None}},
                'then': {'asset': m[1], 'allocation': 'full'},
                'else': {'asset': None, 'allocation': 'full'}, 'safe_asset_description': m[3],
                'reported_execution_period': 'following_month'}
    return None


def extended_ast(expr):
    # Exact paired rotation with an explicitly stated tie rule.
    m = re.fullmatch(rf'比较({SYMBOL})与({SYMBOL})(?:过去|近)(\d+)个?月总分收益[,，]满仓较高者[;；]平手偏({SYMBOL})', expr)
    if m and int(m[3]) > 0 and m[4] in {m[1], m[2]} and m[1] != m[2]:
        return {'type': 'relative_momentum_rotation', 'assets': [m[1], m[2]],
                'lookback': {'value': int(m[3]), 'unit': 'months'}, 'allocation': 'full',
                'return_basis': 'total_return_as_reported', 'tie_policy': {'asset_index': 0 if m[4] == m[1] else 1}}
    m = re.fullmatch(rf'若({SYMBOL})(?:过去|近)(\d+)个?月总分收益>0→满仓({SYMBOL})[,，]否则(满仓)?({SYMBOL})', expr)
    if m and m[1] == m[3] and int(m[2]) > 0:
        return {'type': 'absolute_momentum_zero', 'assets': [m[1], m[5]],
                'lookback': {'value': int(m[2]), 'unit': 'months'}, 'threshold': 0,
                'return_basis': 'total_return_as_reported', 'allocation': 'full',
                'safe_allocation': 'full' if m[4] else None}
    m = re.fullmatch(rf'(SMA|EMA)\((\d+)\)上穿\1\((\d+)\)→满仓({SYMBOL})[;；]\1\(\2\)下穿\1\(\3\)→满仓({SYMBOL})', expr)
    if m and 0 < int(m[2]) < int(m[3]):
        return {'type': 'moving_average_crossover', 'assets': [m[4], m[5]], 'indicator': m[1],
                'parameters': [int(m[2]), int(m[3])], 'allocation': 'full',
                'cross_definition': 'previous_le_current_gt_and_previous_ge_current_lt', 'initial_position': None}
    m = re.fullmatch(rf'({SYMBOL})收盘>此前(\d+)日最高收盘→满仓\1[;；]\1收盘<此前(\d+)日最低收盘→满仓({SYMBOL})', expr)
    if m and int(m[2]) > 0 and int(m[3]) > 0:
        return {'type': 'channel_breakout', 'assets': [m[1], m[4]], 'parameters': [int(m[2]), int(m[3])],
                'window_excludes_current': True, 'field': 'close', 'allocation': 'full', 'initial_position': None}
    m = re.fullmatch(rf'({SYMBOL})的ZScore\((\d+)\)<(-\d+(?:\.\d+)?)→满仓\1[;；]ZScore\(\2\)>0→满仓({SYMBOL})', expr)
    if m and int(m[2]) > 1 and float(m[3]) < 0:
        return {'type': 'zscore_mean_reversion', 'assets': [m[1], m[4]],
                'parameters': [int(m[2]), float(m[3])], 'exit_threshold': 0,
                'allocation': 'full', 'standard_deviation_ddof': None, 'initial_position': None}
    m = re.fullmatch(rf'在\[({SYMBOL}(?:,{SYMBOL})+)\]按过去(\d+)月总收益降序取前(\d+)个等权[;；]并列按代码升序', expr)
    if m:
        assets = m[1].split(',')
        if len(set(assets)) == len(assets) and int(m[2]) > 0 and 0 < int(m[3]) <= len(assets):
            return {'type': 'cross_sectional_momentum_ranking', 'assets': sorted(assets),
                    'lookback': {'value': int(m[2]), 'unit': 'months'}, 'parameters': [int(m[3])],
                    'allocation': 'equal_weight', 'tie_policy': 'symbol_ascending', 'return_basis': 'total_return_as_reported'}
    m = re.fullmatch(rf'配对\(({SYMBOL}),({SYMBOL})\)[;；]价差=log\(\1\)-log\(\2\)[;；]ZScore\((\d+)\)>(\d+(?:\.\d+)?)→空\1多\2[;；]ZScore\(\3\)<-(\4)→多\1空\2[;；]\|ZScore\(\3\)\|<(\d+(?:\.\d+)?)→平仓', expr)
    if m and m[1] != m[2] and int(m[3]) > 1 and 0 <= float(m[6]) < float(m[4]):
        return {'type': 'pairs_zscore', 'assets': [m[1], m[2]],
                'parameters': [int(m[3]), float(m[4]), float(m[6])],
                'spread': 'log_first_minus_log_second', 'hedge_ratio': 1,
                'allocation': None, 'standard_deviation_ddof': None, 'initial_position': None}
    return None

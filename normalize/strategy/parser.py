"""A closed grammar, not a keyword-to-AST guesser. Syntax is not execution approval."""
import json
import re
import unicodedata

VERSION = 'grok-rule-v4.0'
SYMBOL = r'[A-Z][A-Z0-9.-]{0,9}'
NUMBER = r'-?\d+(?:\.\d+)?'
INDICATORS = r'RSI|CCI|MFI|CMF|ATR|TRIX|ADX|ROC|StochRSI|%R|UI|PVO|UO|STC|CMO|Slow%K|Fast%K|Williams%R|\+VI|-VI|AroonUp|AroonDown|RVI|PPO|TSI|MACD|BOP|DPO|NATR'


def canonical_text(text):
    text = unicodedata.normalize('NFKC', text).replace('−', '-').replace('**', '').replace('≥', '>=').replace('≤', '<=')
    return re.sub(r'\s+', '', text)


def rule_body(text):
    text = canonical_text(text)
    # Only this known narrative envelope is stripped. Extra rules fail closed.
    if text.startswith('本条只写'):
        parts = text.split('。')
        prefix, *parts = parts
        if re.search(r'止损|止盈|杠杆|仓位|并且|同时', prefix):
            return None
        body = []
        # Some legacy envelopes put the complete rule after a colon in the
        # introductory sentence. Preserve that clause instead of discarding it.
        inline = re.search(r'[:：]((?:日频|月末).+)$', prefix)
        if inline:
            body.append(inline[1])
        in_metadata = False
        for part in parts:
            if not part:
                continue
            if part.startswith(('不是', '计入', '提出日期', 'OVERRIDE同URL')):
                in_metadata = True
                if re.search(r'止损|止盈|但|然后|次日|执行|加仓|减仓', part):
                    return None
                continue
            if in_metadata:
                return None
            body.append(part)
        text = '。'.join(body)
    return text.rstrip('。.')


def operand(text):
    if re.fullmatch(NUMBER, text):
        return {'type': 'number', 'value': float(text)}
    if text in {'收盘', 'Close', 'close'}:
        return {'type': 'price', 'field': 'close', 'asset': None}
    if text in {'VIX', 'IBS', 'OBV'}:
        return {'type': 'indicator', 'name': text, 'parameters': [], 'asset': None}
    m = re.fullmatch(rf'(Wilder)?({INDICATORS}|SMA|EMA|WMA)\((\d+(?:,\d+)*)\)', text)
    if m:
        params = [int(v) for v in m[3].split(',')]
        arity = {'UO': 3, 'STC': 3, 'Slow%K': 2, 'Fast%K': 1, 'PPO': 2, 'TSI': 2, 'MACD': 3}.get(m[2], 1)
        if any(p <= 0 for p in params) or len(params) != arity:
            return None
        return {'type': 'indicator', 'name': m[2], 'parameters': params,
                'smoothing': 'Wilder' if m[1] else None, 'asset': None}
    m = re.fullmatch(r'([A-Z][A-Z.-]{0,9})(\d+)日实现波动×√252', text)
    if m and int(m[2]) > 1:
        return {'type': 'indicator', 'name': 'realized_volatility', 'asset': m[1],
                'parameters': [int(m[2])], 'annualization': 252, 'return_basis': None, 'ddof': None}
    m = re.fullmatch(r'(SMA|EMA)\((\d+)ofOBV\)', text)
    if m and int(m[2]) > 0:
        return {'type': 'indicator', 'name': m[1], 'parameters': [int(m[2])],
                'input': {'type': 'indicator', 'name': 'OBV'}, 'asset': None}
    return None


def parse_rule(text):
    if text.startswith('QG-DSL/1\n'):
        from .dsl import parse_dsl
        ast = parse_dsl(text)
        return {'parse_status':'PARSED' if ast else 'REVIEW','rule_ast':ast,
                'normalized_rule':json.dumps(ast,ensure_ascii=False,sort_keys=True,separators=(',', ':')) if ast else None,
                'parser_version':VERSION,'parse_reason':'EXPLICIT_DSL_REQUIRES_SOURCE_REVIEW' if ast else 'INVALID_DSL',
                'executable':False}
    body = rule_body(text)
    failure = {'parse_status': 'REVIEW', 'rule_ast': None, 'normalized_rule': None,
               'parser_version': VERSION, 'parse_reason': 'UNSUPPORTED_OR_AMBIGUOUS_RULE',
               'executable': False}
    if not body:
        return failure
    m = re.fullmatch(r'(日频(?:EOD)?|月末)(?:[:：;；]|(?=比较|若))(.+)', body)
    if not m:
        return failure
    schedule = 'daily_eod' if m[1].startswith('日频') else 'month_end'
    expr = m[2]
    from .patterns import extended_ast, switch_ast, monthly_ast
    from .patterns_v3 import parse_explicit
    ast = monthly_ast(expr) if schedule == 'month_end' else None
    if ast is None:
        ast = extended_ast(expr)
    if ast is None:
        ast = switch_ast(expr, operand)
    rotation = re.fullmatch(rf'比较({SYMBOL})与({SYMBOL})过去(\d+)个?月总分收益[,，]满仓较高者', expr)
    if rotation and int(rotation[3]) > 0:
        ast = {'type': 'relative_momentum_rotation', 'assets': [rotation[1], rotation[2]],
               'lookback': {'value': int(rotation[3]), 'unit': 'months'},
               'return_basis': 'total_return_as_reported', 'allocation': 'full', 'tie_policy': None}
    m = re.fullmatch(rf'(?:若)?(.+?)→(满仓)?({SYMBOL})[,，]?否则(满仓)?({SYMBOL})', expr)
    if m:
        condition, risk, safe = m[1], m[3], m[5]
        allocation = 'full' if m[2] else None
        absolute = re.fullmatch(rf'({SYMBOL})过去(\d+)个?月总分收益>([A-Z][A-Z0-9.-]*)同期', condition)
        if absolute and absolute[1] == risk and absolute[3] == safe and int(absolute[2]) > 0:
            ast = {'type': 'absolute_momentum', 'risk_asset': risk, 'safe_asset': safe,
                   'lookback': {'value': int(absolute[2]), 'unit': 'months'},
                   'comparison': '>', 'return_basis': 'total_return_as_reported', 'allocation': allocation}
        else:
            comparison = re.fullmatch(r'(.+?)(>=|<=|>|<)(.+)', condition)
            if comparison:
                left, right = operand(comparison[1]), operand(comparison[3])
                if left and right and left['type'] != 'number' and left.get('asset') in {None, risk}:
                    ast = {'type': 'threshold_switch', 'condition': {'operator': comparison[2], 'left': left, 'right': right},
                           'then': {'asset': risk, 'allocation': allocation}, 'else': {'asset': safe, 'allocation': 'full' if m[4] else None}}
    if ast is None:
        ast = parse_explicit(expr, operand, schedule)
    if ast is None:
        return failure
    ast.update(schedule=schedule, execution_timing=None, price_adjustment=None,
               missing_data_policy=None, costs=None)
    return {'parse_status': 'PARSED', 'rule_ast': ast,
            'normalized_rule': json.dumps(ast, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
            'parser_version': VERSION, 'parse_reason': 'SUPPORTED_SYNTAX_EXECUTION_CONTRACT_PENDING',
            'executable': False}


def family_key(ast):
    if ast['type'] == 'long_only_signal':
        return 'mean_reversion' if ast['signal']=='ZSCORE_REVERSION' else 'moving_average'
    if ast['type'] != 'threshold_switch':
        return ast['type']
    signal = ast['condition']['left']
    if signal['type'] == 'price' or signal.get('name') in {'SMA', 'EMA', 'WMA'}:
        return 'moving_average'
    return 'indicator:' + signal.get('name', signal['type']).lower()


def template_signature(ast):
    """Parameters/assets become slots; operator, signal and schedule stay distinct."""
    def visit(value, key=''):
        if key in {'asset', 'risk_asset', 'safe_asset'}:
            return '$asset' if value is not None else None
        if key == 'assets':
            return ['$asset' for _ in value]
        if key in {'parameters'}:
            return ['$parameter' for _ in value]
        if key == 'value' and isinstance(value, (int, float)):
            return '$parameter'
        if isinstance(value, dict):
            return {k: visit(v, k) for k, v in value.items()
                    if k not in {'parent_record_id', 'derivation'}}
        if isinstance(value, list):
            return [visit(v) for v in value]
        return value
    return visit(ast)

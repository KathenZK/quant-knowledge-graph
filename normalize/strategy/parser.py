"""A closed grammar, not a keyword-to-AST guesser. Syntax is not execution approval."""
import json
import re
import unicodedata

VERSION = 'grok-rule-v1.0'
SYMBOL = r'[A-Z][A-Z0-9.-]{0,9}'
NUMBER = r'-?\d+(?:\.\d+)?'
INDICATORS = r'RSI|CCI|MFI|CMF|ATR|TRIX|ADX|ROC|StochRSI|%R|UI|PVO'


def canonical_text(text):
    text = unicodedata.normalize('NFKC', text).replace('−', '-').replace('**', '')
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
        in_metadata = False
        for part in parts:
            if not part:
                continue
            if part.startswith(('不是', '计入', '提出日期')):
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
    if text in {'VIX', 'IBS'}:
        return {'type': 'indicator', 'name': text, 'parameters': [], 'asset': None}
    m = re.fullmatch(rf'(Wilder)?({INDICATORS}|SMA|EMA|WMA)\((\d+(?:,\d+)*)\)', text)
    if m:
        params = [int(v) for v in m[3].split(',')]
        if any(p <= 0 for p in params):
            return None
        return {'type': 'indicator', 'name': m[2], 'parameters': params,
                'smoothing': 'Wilder' if m[1] else None, 'asset': None}
    return None


def parse_rule(text):
    body = rule_body(text)
    failure = {'parse_status': 'REVIEW', 'rule_ast': None, 'normalized_rule': None,
               'parser_version': VERSION, 'parse_reason': 'UNSUPPORTED_OR_AMBIGUOUS_RULE',
               'executable': False}
    if not body:
        return failure
    m = re.fullmatch(r'(日频(?:EOD)?|月末)[:：](.+)', body)
    if not m:
        return failure
    schedule = 'daily_eod' if m[1].startswith('日频') else 'month_end'
    expr = m[2]
    ast = None
    rotation = re.fullmatch(rf'比较({SYMBOL})与({SYMBOL})过去(\d+)个?月总分收益[,，]满仓较高者', expr)
    if rotation and int(rotation[3]) > 0:
        ast = {'type': 'relative_momentum_rotation', 'assets': [rotation[1], rotation[2]],
               'lookback': {'value': int(rotation[3]), 'unit': 'months'},
               'return_basis': 'total_return_as_reported', 'allocation': 'full', 'tie_policy': None}
    m = re.fullmatch(rf'(?:若)?(.+?)→(满仓)?({SYMBOL})[,，]?否则({SYMBOL})', expr)
    if m:
        condition, risk, safe = m[1], m[3], m[4]
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
                if left and right and left['type'] != 'number':
                    ast = {'type': 'threshold_switch', 'condition': {'operator': comparison[2], 'left': left, 'right': right},
                           'then': {'asset': risk, 'allocation': allocation}, 'else': {'asset': safe, 'allocation': None}}
    if ast is None:
        return failure
    ast.update(schedule=schedule, execution_timing=None, price_adjustment=None,
               missing_data_policy=None, costs=None)
    return {'parse_status': 'PARSED', 'rule_ast': ast,
            'normalized_rule': json.dumps(ast, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
            'parser_version': VERSION, 'parse_reason': 'SUPPORTED_SYNTAX_EXECUTION_CONTRACT_PENDING',
            'executable': False}


def family_key(ast):
    if ast['type'] != 'threshold_switch':
        return ast['type']
    signal = ast['condition']['left']
    if signal['type'] == 'price' or signal.get('name') in {'SMA', 'EMA', 'WMA'}:
        return 'moving_average'
    return 'indicator:' + signal['name'].lower()


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
            return {k: visit(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [visit(v) for v in value]
        return value
    return visit(ast)

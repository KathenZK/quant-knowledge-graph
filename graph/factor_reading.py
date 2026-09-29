"""Deterministic Chinese reading guide for archived factor definitions.

No inference about profitability, authorship, validity, or execution readiness.
The original expression is immutable. Only a small, explicit algebra evaluator
is used for labeled hypothetical examples; source strings are never executed.
"""
import math
from decimal import Decimal, InvalidOperation
import re

from quantgraph.normalize.formula.parser import parse

VERSION = 'factor-reading/v1'
FIELD_LABELS = {
    'close': '收盘价', 'open': '开盘价', 'high': '最高价', 'low': '最低价',
    'volume': '成交量', 'vwap': '成交量加权平均价', 'returns': '收益率',
    'market_return': '市场组合收益率', 'risk_free_return': '无风险收益率',
    'small_value': '小市值价值组收益', 'big_value': '大市值价值组收益',
    'small_growth': '小市值成长组收益', 'big_growth': '大市值成长组收益',
    'small_low': '小市值低特征组收益', 'big_low': '大市值低特征组收益',
    'small_high': '小市值高特征组收益', 'big_high': '大市值高特征组收益',
    'small_robust': '小市值强盈利组收益', 'big_robust': '大市值强盈利组收益',
    'small_weak': '小市值弱盈利组收益', 'big_weak': '大市值弱盈利组收益',
    'small_conservative': '小市值低投资组收益', 'big_conservative': '大市值低投资组收益',
    'small_aggressive': '小市值高投资组收益', 'big_aggressive': '大市值高投资组收益',
    'retrf': '来源记号 retrf（定义中的超额收益）',
    'mktrf': '来源记号 mktrf（定义中的市场超额收益）',
    'meanest': '来源记号 meanest（定义中的分析师盈利预测均值）',
}
OPS = {
    'delay': '取前若干观测的值', 'mean': '历史窗口均值', 'std': '历史窗口标准差；自由度需核对实现',
    'sum': '历史窗口求和', 'delta': '当前值减去滞后值', 'abs': '绝对值', 'log': '自然对数',
    'sign': '取正、零、负的符号', 'ts_max': '历史窗口最大值', 'ts_min': '历史窗口最小值',
    'ts_rank': '同一对象在历史窗口中的时序排名；尺度及并列值处理需核对实现',
    'cs_rank': '同一时点在多个对象之间的截面排名；样本范围及并列值处理需核对实现',
    'ts_argmax': '历史窗口最大值的位置；索引方向、起点及并列值处理需核对实现',
    'ts_argmin': '历史窗口最小值的位置；索引方向、起点及并列值处理需核对实现',
    'elementwise_max': '同一观测下逐项取较大值', 'elementwise_min': '同一观测下逐项取较小值',
    'corr': '两列观测在历史窗口内的相关系数', 'cov': '两列观测在历史窗口内的协方差',
    'sma_cn': '三参数递推平滑均值；不是简单滚动平均，初值需核对实现',
    'decay_linear': '历史窗口线性加权；权重方向及缺失处理需核对来源实现',
    'slope': '历史窗口线性回归斜率；回归自变量口径需核对实现',
    'rsquare': '历史窗口线性回归拟合优度', 'resi': '历史窗口线性回归残差',
    'quantile': '历史窗口分位数；插值方法需核对实现',
    'industry_neutralize': '行业分组中性化；行业分类及具体算法需核对来源',
}


def _walk(node):
    # Bounded iterative traversal also tolerates deeply nested archived syntax.
    stack, count = [node], 0
    while stack and count <= 200:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        yield current
        count += 1
        children = current.get('args', [])
        if isinstance(children, list):
            stack.extend(reversed(children))


def _field(name):
    return FIELD_LABELS.get(name, f'来源字段 {name}')


def _number(node):
    if not isinstance(node, dict) or node.get('type') != 'number':
        return None
    try:
        value = float(node['value'])
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def _label_number(node):
    if not isinstance(node, dict) or node.get('type') != 'number':
        return None
    try:
        value = Decimal(str(node['value'])).normalize()
        if not value.is_finite():
            return None
        return format(value, 'f') if -9 <= value.adjusted() <= 20 else str(value).lower()
    except (InvalidOperation, KeyError, ValueError):
        return None


def _phrase(node, depth=0):
    if depth > 14:
        raise ValueError('Expression too deep for a reading guide')
    kind, args = node.get('type'), node.get('args', [])
    if kind == 'number':
        return _label_number(node)
    if kind == 'field':
        return _field(node['name'])
    parts = [_phrase(arg, depth + 1) for arg in args]
    if any(part is None for part in parts):
        return None
    op = node.get('op', '')
    if kind == 'unary' and len(parts) == 1:
        return {'-': f'（{parts[0]}）的相反数', '+': parts[0], '!': f'不满足（{parts[0]}）', '~': f'不满足（{parts[0]}）'}.get(op)
    if kind == 'binary' and len(parts) == 2:
        words = {'+': '加上', '-': '减去', '*': '乘以', '/': '除以', 'pow': '的幂，指数为', 'and': '并且', 'or': '或者', '%': '取余于'}
        return f'（{parts[0]}）{words[op]}（{parts[1]}）' if op in words else None
    if kind == 'compare':
        words = {'>': '大于', '<': '小于', '>=': '不小于', '<=': '不大于', '==': '等于', '!=': '不等于'}
        operators = node.get('ops', [])
        if len(operators) != len(parts) - 1 or any(o not in words for o in operators):
            return None
        return '，且'.join(f'{parts[i]}{words[o]}{parts[i+1]}' for i, o in enumerate(operators))
    if kind == 'if' and len(parts) == 3:
        return f'若{parts[0]}，取{parts[1]}；否则取{parts[2]}'
    if kind != 'call' or ':' not in op:
        return None
    dialect, op = op.split(':', 1)
    if dialect not in {'qlib', 'wq101', 'gtja191', 'portfolio'}:
        return None
    if op == 'delay' and len(parts) == 2:
        return f'{parts[1]} 个观测之前的{parts[0]}'
    if op == 'delta' and len(parts) == 2:
        return f'{parts[0]}当前值减去{parts[1]}个观测之前的值'
    if op in {'abs', 'log', 'sign'} and len(parts) == 1:
        return f'（{parts[0]}）的' + {'abs': '绝对值', 'log': '自然对数', 'sign': '正负符号'}[op]
    window_ops = {'mean': '均值', 'std': '标准差', 'sum': '总和', 'ts_max': '最大值', 'ts_min': '最小值',
                  'ts_rank': '时序排名', 'ts_argmax': '最大值位置', 'ts_argmin': '最小值位置',
                  'decay_linear': '线性加权值', 'slope': '回归斜率', 'rsquare': '回归拟合优度', 'resi': '回归残差'}
    if op in window_ops and len(parts) == 2:
        return f'窗口参数为 {parts[1]} 的（{parts[0]}）{window_ops[op]}'
    if op == 'cs_rank' and len(parts) == 1:
        return f'同一时点对多个对象的（{parts[0]}）作截面排名'
    if op in {'corr', 'cov'} and len(parts) == 3:
        return f'窗口参数为 {parts[2]} 的（{parts[0]}）与（{parts[1]}）' + ('相关系数' if op == 'corr' else '协方差')
    if op in {'elementwise_max', 'elementwise_min'} and len(parts) == 2:
        return f'同一观测下在（{parts[0]}）与（{parts[1]}）之间取' + ('较大值' if op == 'elementwise_max' else '较小值')
    if op == 'sma_cn' and len(parts) == 3:
        return f'对（{parts[0]}）作三参数递推平滑，窗口参数 {parts[1]}、权重参数 {parts[2]}；初值另行核对'
    if op == 'quantile' and len(parts) == 3:
        return f'取窗口参数 {parts[1]} 下（{parts[0]}）的 {parts[2]} 分位数'
    return None


def _hypothetical_example(ast, dialect):
    """Evaluate only unambiguous scalar arithmetic and explicit Qlib delay/mean.

    Statistics with unknown ddof, ranks, fractional windows and indexed extrema
    deliberately get no numerical example.
    """
    calls = [n for n in _walk(ast) if n.get('type') == 'call']
    if any(n['op'] not in {'qlib:delay', 'qlib:mean', 'qlib:sum', 'qlib:abs', 'qlib:log'} for n in calls):
        return None
    fields = sorted({n['name'] for n in _walk(ast) if n.get('type') == 'field'})
    simple_prices = {'close', 'open', 'high', 'low', 'volume'}
    portfolio_fields = set(FIELD_LABELS) - simple_prices
    if not fields or not (set(fields) <= simple_prices or (dialect == 'portfolio' and set(fields) <= portfolio_fields)):
        return None
    assumptions = {'close': (100, 110), 'open': (100, 100), 'high': (120, 120), 'low': (90, 90), 'volume': (1000, 1200)}
    for index, field in enumerate(fields):
        if field not in assumptions:
            if field == 'market_return':
                assumptions[field] = (0.08, 0.08)
            elif field == 'risk_free_return':
                assumptions[field] = (0.02, 0.02)
            else:
                assumptions[field] = (0.01*(index+1), 0.01*(index+1))
    offsets = set()
    def calc(node, offset=0):
        if offset > 600:
            raise ValueError('Example window too long')
        kind, args = node.get('type'), node.get('args', [])
        if kind == 'field':
            offsets.add(offset)
            return assumptions[node['name']][0 if offset else 1]
        if kind == 'number':
            value = _number(node)
            if value is None:
                raise ValueError('Invalid number')
            return value
        op = node.get('op')
        if kind == 'unary' and op in {'-', '+'}:
            return (-1 if op == '-' else 1)*calc(args[0], offset)
        if kind == 'binary' and op in {'+', '-', '*', '/'}:
            a, b = calc(args[0], offset), calc(args[1], offset)
            if op == '+':
                return a + b
            if op == '-':
                return a - b
            if op == '*':
                return a*b
            return a/b
        if kind == 'call':
            if op in {'qlib:abs', 'qlib:log'}:
                value = calc(args[0], offset)
                return abs(value) if op == 'qlib:abs' else math.log(value)
            window = _number(args[1])
            if window is None or not window.is_integer() or not 0 <= window <= 500:
                raise ValueError('Unknown window semantics')
            n = int(window)
            if op == 'qlib:delay':
                return calc(args[0], offset+n)
            if n == 0:
                raise ValueError('Expanding windows not demonstrated')
            values = [calc(args[0], offset+i) for i in range(n)]
            return sum(values)/n if op == 'qlib:mean' else sum(values)
        raise ValueError('Example semantics not supported')
    try:
        result = calc(ast)
        if not math.isfinite(result):
            return None
    except (ValueError, ZeroDivisionError, OverflowError, IndexError, TypeError):
        return None
    statements = []
    for field in fields:
        older, current = assumptions[field]
        statements.append(f'{_field(field)}当前为 {current:g}' + (f'，所有所需历史观测均为 {older:g}' if max(offsets, default=0) else ''))
    return dict(text='假设' + '；'.join(statements) + f'。逐项代入本页原式，得到 {result:.6g}。',
                basis='仅为原式的假设数据演算；观测齐全、无缺失且价格口径一致，不是市场结果，也不证明运行时边界处理已验证。')


def _latex_term(token):
    token = token.strip()
    match = re.fullmatch(r'([A-Za-z][A-Za-z0-9_]*)(\*)?_\{?t(?:-([0-9]+))?\}?', token)
    if not match:
        return None
    variable = match[1] + (match[2] or '')
    lag = int(match[3] or 0)
    return {'variable': variable, 'lag': lag, 'text': ('当期' if lag == 0 else f'滞后 {lag} 期的') + variable}


def _latex_reading(formula):
    """Recognize only complete simple LaTeX ratios, preserving source symbols."""
    cleaned = formula.strip().strip('$').strip()
    cleaned = re.sub(r'\\mbox\{\*\}', '*', cleaned)
    cleaned = cleaned.replace('\\left', '').replace('\\right', '').replace('\\log', 'log')
    cleaned = re.sub(r'\\(?:,|;|!| )', '', cleaned)
    token = r'[A-Za-z][A-Za-z0-9_]*\*?_\{?t(?:-\d+)?\}?'
    ratio = r'\\frac\{(' + token + r')\}\{(' + token + r')\}'
    match = re.fullmatch(ratio + r'\s*(-\s*1)?', cleaned)
    if match:
        numerator, denominator = _latex_term(match[1]), _latex_term(match[2])
        if not numerator or not denominator:
            return None
        minus = bool(match[3])
        summary = f"将{numerator['text']}除以{denominator['text']}" + ('，再减去 1，得到这一比值对应的相对变化。' if minus else '，得到来源定义的比率。')
        summary += '星号及变量的具体处理口径以来源变量表为准。' if '*' in cleaned else '变量的具体口径以来源定义为准。'
        value = 110/100-(1 if minus else 0)
        example = dict(text=f"仅作代数说明：假设{numerator['text']}为110、{denominator['text']}为100，按原式得到110/100" + ('−1' if minus else '') + f' = {value:.3g}。',
                       basis='假设数值，不是实际财务、价格或收益数据；不证明该变量已完成可用时点、复权或缺失值验证。')
        return dict(summary=summary, example=example, variables=[dict(name=s, meaning='来源记号；中文定义、单位及星号含义需核对原始变量表') for s in dict.fromkeys([numerator['variable'], denominator['variable']])])
    single = _latex_term(cleaned)
    if single:
        return dict(summary=f"直接取{single['text']}的数值。该来源记号的具体构造和单位需结合变量表核对。", example=None,
                    variables=[dict(name=single['variable'], meaning='来源记号；具体构造、单位及星号含义需核对原始变量表')])
    match = re.fullmatch(r'log\(' + ratio + r'\)\s*-\s*log\(' + ratio + r'\)', cleaned)
    if match:
        terms = [_latex_term(match[i]) for i in range(1, 5)]
        if all(terms):
            phrases = [t['text'] for t in terms]
            return dict(summary=f'先取{phrases[0]}与{phrases[1]}比值的对数，再减去{phrases[2]}与{phrases[3]}比值的对数。对数和各变量口径保持原式，需核对来源定义。',
                        example=None, variables=[dict(name=t['variable'], meaning='来源记号；具体口径及单位需核对原始变量表') for t in terms])
    return None


def _description_reading(description):
    """A few complete textual patterns, not a title-based factor interpretation."""
    if not description:
        return None
    text = description.strip()
    if re.search(r'[\u4e00-\u9fff]', text):
        return text if len(text) <= 320 else text[:320] + '…（完整来源定义见下方）'
    regression = re.search(r'rolling regression over (\d+) months of excess return \(retrf\) on excess market return \(mktrf\), size and value factors \(smb, hml\)', text, re.I)
    window = re.search(r'both computed over the past (\d+) months', text, re.I)
    if regression and window and 'one-month lagged residual' in text and 'rolling mean of the residual divided by the rolling standard deviation' in text:
        return f'用过去 {regression[1]} 个月的超额收益对市场、规模和价值三个因子作滚动回归，取滞后一个月的残差。再用过去 {window[1]} 个月残差的均值除以其标准差，构造来源报告的残差动量。'
    if 'Binary variable equal to 1' in text and 'meanest' in text and 'has improved over the previous month' in text and '0 otherwise' in text:
        prefix = '保留 fpi=1 的记录；' if re.search(r'Keep fpi\s*=\s*1', text) else ''
        return prefix + '如果来源中分析师对下一季度盈利的平均预测（meanest）比上个月提高，指标取 1，否则取 0。此处按定义文本解释，名称中的方向不能替代原文。'
    if text == 'Market excess return in the US factor library.':
        return '市场组合收益率减去同期无风险收益率，表示市场的超额收益。'
    if text == 'Size-balanced value portfolio spread.':
        return '分别在小市值组和大市值组中比较价值组与成长组收益，再将两组差值平均。'
    return None


def enrich_factor_reading(value, raw):
    """Return explanation-only fields for the private reading projection."""
    raw = raw if isinstance(raw, dict) else {}
    formula = raw.get('raw_formula') or raw.get('formula') or value.get('formula')
    description = raw.get('raw_definition') or raw.get('description')
    if not formula and str(description or '').strip().startswith('$'):
        formula = description
    dialect = raw.get('dialect') or ''
    ast = raw.get('formula_ast')
    if formula and dialect:
        try:
            parsed = parse(formula, dialect)
            # Refuse a stale AST whose structure is not the displayed expression.
            ast = parsed if ast is None or ast == parsed else None
        except Exception:
            ast = None
    fields = raw.get('required_fields') or value.get('required_fields') or []
    variables = [dict(name=f, meaning=FIELD_LABELS.get(f, f'来源字段 {f}；具体中文定义、单位及可用时点需核对来源')) for f in fields]
    semantics = []
    summary, example = None, None
    basis = '依据本机归档定义作确定性说明；不是原作者额外经济结论。'
    if ast and len(list(_walk(ast))) <= 150:
        try:
            phrase = _phrase(ast)
        except (ValueError, TypeError, KeyError, IndexError, RecursionError):
            phrase = None
        if phrase:
            summary = '按原式计算：' + phrase + '。'
            if len(summary) > 440:
                # A short top-level account plus complete operator guide is more
                # honest than truncating the expression into a different rule.
                top = ast.get('op', '')
                groups = {'*': '相乘', '/': '相除', '+': '相加', '-': '相减'}
                operator_list = list(dict.fromkeys(n['op'].split(':')[-1] for n in _walk(ast) if n.get('type') == 'call'))
                summary = '原式将多个中间特征' + groups.get(top, '组合') + '；用到' + '、'.join(OPS.get(o, o) for o in operator_list[:4]) + '。完整嵌套次序以保留的原式为准。'
            example = _hypothetical_example(ast, dialect)
            basis = f'根据归档原式及 {dialect} 方言的结构逐项转述；不把同名算子视为跨来源等价。'
        calls = list({n['op']: n for n in _walk(ast) if n.get('type') == 'call'}.values())
        for call in calls:
            op = call['op'].split(':')[-1]
            variables.append(dict(name=call['op'], meaning=OPS.get(op, '来源方言算子；具体公式及边界处理待核对')))
        if any(n['op'].endswith(':cs_rank') for n in calls):
            semantics.append(dict(label='排名范围', text='原式含截面排名：同一时点比较多个对象；不是单个对象的历史排名。样本池、并列名次和归一化尺度需按来源核对。', status='STRUCTURAL_EXPLANATION'))
        if any(n['op'].endswith(':ts_rank') for n in calls):
            semantics.append(dict(label='排名范围', text='原式含时序排名：比较同一对象窗口内的历史观测；不是股票之间的截面排名。并列名次和输出尺度需核对实现。', status='STRUCTURAL_EXPLANATION'))
        if any(n['op'].endswith(':sma_cn') for n in calls):
            semantics.append(dict(label='平滑口径', text='该方言的三参数 SMA 是递推平滑结构，不能替换成 Qlib Mean 或普通简单移动平均；初始值与递推边界未在本层验证。', status='STRUCTURAL_EXPLANATION'))
        if any(n['op'].endswith(':std') for n in calls):
            semantics.append(dict(label='标准差口径', text='标准差的自由度、最少有效观测数和缺失值跳过规则需核对来源实现；本层未指定 ddof。', status='UNKNOWN'))
    if not summary and formula and str(formula).strip().startswith('$'):
        latex = _latex_reading(str(formula))
        if latex:
            summary, example = latex['summary'], latex['example']
            variables = latex['variables']
            basis = '仅按完整匹配的 LaTeX 比值、滞后和减法结构转述；保留来源符号，不把格式命令当计算算子。'
    if not summary:
        summary = _description_reading(description)
        if summary:
            basis = '对归档定义中明确列出的运算、窗口和条件作有限模式转述；原始英文或公式另行保留。'
    if not formula and not description:
        summary = '本机只保存了此条目的来源与方法引用，尚未收录完整定义；需要沿来源继续核对，不能据此还原计算。'
    if not summary and formula:
        summary = '此项是来源给出的公式构造。请按下方变量和算子逐项阅读；当前无法可靠生成完整中文转述，原式仍完整保留。'
    if not summary and description:
        summary = '现有定义以来源原文保存，尚无可靠的完整中文转述：' + (description[:260] + '…' if len(description) > 260 else description)
    lookback = raw.get('lookback') or value.get('lookback')
    if isinstance(lookback, dict) and lookback.get('value') is not None:
        semantics.append(dict(label='历史输入跨度', text=f"归档结构推导的最少输入跨度为 {lookback['value']} {lookback.get('unit', '观测')}；含义为 {lookback.get('scope', '按来源字段')}。这是结构下界，不等同于运行时预热通过。", status='STRUCTURAL_NOT_RUNTIME_VERIFIED'))
    semantics.extend([
        dict(label='缺失值与预热', text='本层不补定缺失值填充、窗口最少有效观测数或预热起点；需核对来源实现及测试。', status='UNKNOWN'),
        dict(label='价格与时间口径', text='复权、币种、时区、可用时点及数据发布延迟未在本层验证；同名字段不能证明口径一致。', status='UNKNOWN'),
    ])
    if description and re.search(r'\bdown\b', value.get('name', ''), re.I) and 'has improved' in description:
        semantics.append(dict(label='名称与定义冲突', text='名称含 Down，但归档定义写 has improved（提高）。两者冲突已保留，不能按名称反转公式；需回查来源。', status='REVIEW_REQUIRED'))
    unique = {item['name']: item for item in variables}
    return dict(summary=summary, variables=list(unique.values()), example=example, semantics=semantics,
                explanation_basis=basis, version=VERSION)

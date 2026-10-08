"""Local-only reading projection over the Catalog's existing private snapshots.

Nothing here changes source bytes, admission, public visibility or execution ASTs.
Reading is available even when a closed execution parser cannot understand a rule.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from functools import lru_cache
import json
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from quantgraph.api.web_read_model import FIELD_LABELS, normalize, safe_url
from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.catalog_projection import empty_results
from quantgraph.graph.personal_search import QueryVocabulary, accepts_constraints, search_pattern, search_anchor, compact_formula

VERSION = 'personal-reading/v1'
UNKNOWN = '本机快照未收录'
OHLCV = {'open', 'high', 'low', 'close', 'volume'}
FIELD_NAMES = FIELD_LABELS | {'amount': '成交额', 'returns': '收益率', 'return': '收益率',
    'market_cap': '市值', 'industry': '行业分类', 'funding_rate': '资金费率'}
METHODS = [
    ('pairs', '配对与价差', ('配对', 'pairs trading', 'pair trading', '协整', 'cointegration')),
    ('rotation', '相对强弱与轮动', ('轮动', 'rotation', 'relative_momentum', 'relative_momentum_rotation')),
    ('mean_reversion', '均值回归与反转', ('均值回归', 'mean reversion', 'mean_reversion', '反转', 'reversal')),
    ('moving_average', '均线方法', ('均线', 'moving average', 'moving_average', 'monthly_price_ma', 'sma', 'ema', 'maribbon', 'tilson', 'tillson', 't3')),
    ('price_level', '价格水平与枢轴', ('枢轴', 'pivot')),
    ('breakout', '突破与通道', ('突破', 'breakout', 'donchian')),
    ('momentum', '动量与趋势', ('动量', 'momentum', 'absolute_momentum', 'absolute_momentum_zero', '趋势', 'trend', 'trix', 'roc')),
    ('volatility', '波动与风险', ('波动', 'volatility', 'realized_volatility', 'variance', 'atr', 'std', 'vstd')),
    ('oscillator', '震荡与强弱指标', ('rsi', 'stoch', 'cci', 'williams', '强弱', 'mfi', 'cmo')),
    ('liquidity', '成交量与流动性', ('流动性', 'liquidity', '成交量', 'volume', 'vwap', 'obv', 'cmf')),
    ('scoring', '多指标打分与组合', ('综合分', '综合得分', 'multi-factor', '多因子', '打分')),
    ('value', '价值与估值', ('价值', 'value', 'valuation', 'book-to-market', 'earnings yield')),
    ('quality', '质量与盈利', ('质量', 'quality', 'profitability', '盈利', 'earnings', 'accrual', '利润率')),
    ('investment', '投资与资产增长', ('investment', 'asset growth', '投资', '资产增长')),
    ('size', '规模', ('market capitalization', 'market equity', 'size', '规模')),
    ('carry', '持有收益与期限结构', ('carry', 'term structure', '期限结构', '资金费率', 'funding rate')),
    ('arbitrage', '套利', ('套利', 'arbitrage')),
    ('dividend', '股息与公司行为', ('股息', 'dividend', '拆股', 'stock split')),
]
METHOD_LABELS = {key: label for key, label, _ in METHODS} | {'unknown': '尚未归类'}
METHOD_GUIDES = {
 'moving_average': ('用平滑后的价格观察趋势位置或变化。', ['价格与均线比较','快慢均线交叉','多条均线排列','均线斜率'], ['窗口单位与平滑方法是什么？','条件失效后空仓还是切换资产？']),
 'pairs': ('把两个或多个相关标的放在一起观察价差。', ['形成期筛选配对','价差或标准化偏离触发','收敛或到期退出'], ['配对如何选择，多久更新？','对冲比例与两条腿的成交规则是否完整？']),
 'rotation': ('在候选资产之间比较同一口径的强弱并切换持仓。', ['资产池相对排名','第一名或前若干名','避险资产切换'], ['排名对象与收益口径一致吗？','并列、缺数据和换仓时间怎样处理？']),
 'mean_reversion': ('观察价格或指标偏离参考水平后是否回归。', ['偏离均值或标准分数','超买超卖阈值','回到参考水平退出'], ['参考水平与波动尺度如何计算？','进入与退出是否使用不同阈值？']),
 'price_level': ('将当前价格与已报告的参考价位比较。', ['昨高昨低昨收构造枢轴','价格高于或低于参考水平','支撑阻力分级'], ['参考价位只使用已完成的数据吗？','越过、触及和收盘确认是否区分？']),
 'breakout': ('观察价格穿过历史区间或通道边界。', ['滚动高低点','价格通道','收盘突破或盘中触发'], ['通道是否排除当前观测？','回到通道内如何处理？']),
 'momentum': ('比较过去一段时间的变化或趋势持续性。', ['历史收益率','变化率或斜率','动量阈值与方向'], ['回看窗口、跳过期和复权口径是什么？','信号方向如何转换成仓位？']),
 'volatility': ('观察收益或价格波幅的大小及变化。', ['标准差','真实波幅','波动阈值或目标风险'], ['波动计算用什么数据与估计方法？','风险缩放是否有仓位上限？']),
 'oscillator': ('把价格变化放到有界或标准化指标中观察。', ['强弱或超买超卖阈值','指标交叉','指标区间切换'], ['指标平滑与初始化是否明确？','高值低值代表的动作在规则中是什么？']),
 'liquidity': ('观察交易活跃度、成交量或流动性条件。', ['成交量均值与相对变化','价量组合','交易成本或非流动性度量'], ['需要成交额、盘口或仅成交量？','价格单位与成交量单位是否匹配？']),
 'scoring': ('把多个报告指标合成为选取或配置分数。', ['标准化后加权打分','排名选取','多方法组合'], ['各项方向、权重和缺失值怎样处理？','排名的候选对象是什么？']),
 'value': ('用价格相对于账面、盈利或其他价值基准的比例描述估值。', ['账面市值比','收益率或估值倍数','价值分组'], ['财务数据何时真正可用？','负值和行业差异怎样处理？']),
 'quality': ('用盈利能力、会计质量或经营特征描述企业。', ['利润率与资本回报','应计项目','盈利变化'], ['会计字段和报告时点是否明确？','方向来自原研究还是后来整理？']),
 'investment': ('观察企业投资、资产扩张或资本使用的变化。', ['资产增长','资本开支','投资比例'], ['分母、滞后与报告期间如何定义？','并购或缺失财报怎样处理？']),
 'size': ('按资产或企业规模度量进行描述或分组。', ['市值或资产规模','规模分位数组合'], ['规模是主信号还是入池条件？','规模字段何时可观察？']),
 'carry': ('观察持有资产时报告的利息、费率或期限结构。', ['资金费率','远近月价差','期限或利息条件'], ['收益流的收付方向与结算时间是什么？','价格风险和融资约束是否另列？']),
 'arbitrage': ('比较相关资产或市场之间报告的价格关系。', ['跨资产或跨市场价差','现货与衍生品组合'], ['各条腿与融资成本是否齐全？','所谓价差是否可同时成交？']),
 'dividend': ('围绕股息、拆股等公司行为记录持仓或事件规则。', ['持有收息','事件前后交易','拆股调整'], ['价格复权与现金分配是否重复计算？','事件何时公告并可被交易者知道？']),
 'unknown': ('现有资料可以阅读，但不足以可靠归入现有方法分类。', ['保留来源原始定义','单独检查尚未结构化的规则'], ['核心比较对象和触发条件是什么？','来源是否只提供实现片段或元信息？']),
}
FREQUENCY_LABELS = {'daily': '日频', 'daily_eod': '每日收盘观察', 'weekly': '周频',
    'monthly': '月频', 'month_end': '月末', 'weekly_eod': '每周收盘观察'}
READING_FIELDS = [
    ('scope', '适用范围', r'投资范围|投资标的|资产池|标的池|股票池|universe'),
    ('entry', '入场或选取规则', r'若|如果|当|买入|开仓|做多|做空|(?<!平)多[:：]|(?<!平)空[:：]|取|选择|超过|高于|低于|排名|select|enter|buy|long|short'),
    ('exit', '退出或切换规则', r'退出|平仓|平多|平空|卖出|止损|止盈|否则|收敛|exit|sell|stop'),
    ('position', '仓位与权重', r'满仓|半仓|仓位(?:比例|大小|上限|按|为|设|占|不超过|\s*[=<>≥≤\d])|等权|持仓(?:比例|数量|上限)|(?:最多|每笔|每次|单笔).{0,12}(?:仓|份|股|单位|数量|资金)|(?:组合|资金|资产|股票|证券|基金).{0,10}权重|allocation|set_holdings'),
    ('rebalance', '调仓规则', r'再平衡|调仓|rebalance|周度最后交易日.*交易'),
    ('observation', '观察频率', r'日频|周频|月频|日线|周线|月线|每日.{0,10}(?:检查|监控|观察)|daily|weekly|monthly'),
    ('execution', '成交时点', r'次日开盘|下一根|下一交易日|次日收盘|(?:收盘|开盘)(?:价)?(?:交易|成交|买入|卖出)|前一交易日收盘|最后交易日收盘|next.open|next.bar'),
    ('costs', '费用与滑点', r'手续费|滑点|佣金|交易成本|commission|slippage|transaction cost'),
]
PARAM_MEANINGS = {'window_or_lag': '来源记录的窗口或滞后长度', 'unit': '来源记录的参数单位',
    'numeric_literals': '公式中的数值常量，未逐项解释用途', 'operators': '来源记录的计算算子',
    'accounting_availability_lag_months': '财报可用性的滞后月数', 'portfolio_period_months': '来源组合持有月数',
    'sign': '来源组合构建方向，不代表已验证的收益方向', 'original_sign': '原来源记录的方向',
    'long_short_quantile': '来源多空分组比例', 'start_month': '来源组合起始月份',
    'stock_weight': '来源组合权重方法', 'theme': '来源主题分组', 'alpha_number': '来源原生 Alpha 编号'}


def private_text(value):
    """Keep full reading text; mask credentials without the public 3000-char cap."""
    if value is None:
        return None
    text = str(value)
    text = re.sub(r'https?://[^\s<>"\u3000]+', lambda m: personal_url(m.group(0)) or '[无效来源链接]', text)
    text = re.sub(r'(?i)(?:api[_ -]?key|secret|password|(?:access[_ -]?)?token|bearer)\s*[:=]\s*[^\s,;]+', '[凭证已移除]', text)
    return re.sub(r'\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}\b', '[凭证已移除]', text)


def personal_url(value):
    """Preserve document IDs, page numbers and anchors; discard secrets/tracking."""
    value = safe_url(value)
    if not value:
        return None
    parsed = urlsplit(value)
    def allowed(key):
        key = key.casefold().replace('-', '_')
        return not (key.startswith(('utm_', 'x_amz_', 'x_goog_')) or key in {
            'token', 'access_token', 'refresh_token', 'id_token', 'api_key', 'apikey', 'key',
            'secret', 'password', 'authorization', 'auth', 'signature', 'sig', 'credential',
            'fbclid', 'gclid', 'msclkid', 'mc_cid', 'mc_eid'})
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if allowed(k)])
    fragment = parsed.fragment
    if '=' in fragment:
        fragment = urlencode([(k, v) for k, v in parse_qsl(fragment, keep_blank_values=True) if allowed(k)])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, fragment))


def _text(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _clean_private(value):
    if isinstance(value, str):
        return private_text(value)
    if isinstance(value, list):
        return [_clean_private(v) for v in value]
    if isinstance(value, dict):
        return {k: ('[凭证已移除]' if re.fullmatch(r'(?i)(?:api[_-]?key|token|access[_-]?token|secret|password|authorization)', k)
                    else _clean_private(v)) for k,v in value.items()}
    return value


@lru_cache(maxsize=2048)
def _term_pattern(term):
    term=normalize(term)
    if re.fullmatch(r'[a-z0-9_ .%-]+', term):
        return re.compile(r'(?<![a-z_])' + re.escape(term) + r'(?![a-z_])')
    return re.compile(re.escape(term))


def _contains(text, term):
    """Do not confuse RSI with StochRSI, or MA with market/maximum."""
    return _term_pattern(term).search(normalize(text))


def _method(value, raw):
    # This is a reading index inferred from explicit vocabulary, never equivalence.
    formula=raw.get('raw_formula') or raw.get('formula') or value.get('formula')
    if raw.get('dialect')=='qlib' and re.fullmatch(r'Mean\(\s*\$close\s*,\s*\d+\s*\)\s*/\s*\$close',formula or ''):
        return dict(value='moving_average',label=METHOD_LABELS['moving_average'],
            basis='原式明确为窗口收盘均值除以当前收盘价；归为均线方法，未声明收益有效性',evidence='Mean($close, n)/$close')
    fields = [('来源方法标识', value.get('family') or ''),
              ('来源主题', _text(raw.get('parameters', {}).get('theme'))),
              ('名称', value.get('name', ''))]
    fields.append(('来源规则/定义', _text(raw.get('original_rule_text') or raw.get('raw_formula') or raw.get('description'))))
    for field, text in fields:
        normalized=normalize(_positive_text(text))
        # These words can describe a smoothing coefficient or an eligibility
        # constraint; they are not evidence of a volume/size mechanism.
        normalized=re.sub(r'volume\s+factor\s*[-+]?\d*(?:\.\d+)?', '', normalized)
        normalized=re.sub(r'规模\s*[>≥<≤=]+\s*[\d.]+\s*(?:亿元?|万元?|元)?', '', normalized)
        normalized=re.sub(r'value[- ]+weight(?:ed|ing|s)?|size[- ]+adjusted|未投资|总投资|投资金额|投资组合', '', normalized)
        for key, label, terms in METHODS:
            for term in terms:
                if field not in {'来源主题','来源方法标识'} and term in {'投资','investment','规模','size','价值','value'}:
                    # Generic allocation/weight words are not the economic
                    # characteristic used as a signal.
                    continue
                if term in normalized and _term_pattern(term).search(normalized):
                    return dict(value=key, label=label, basis=f'{field}中出现“{term}”；仅为阅读归类', evidence=term)
    return dict(value='unknown', label='尚未归类', basis='现有来源不足以可靠归入方法族', evidence=None)


def _sentences(text):
    return [s.strip() for s in re.split(r'[\n。；;]+', text or '') if s.strip()]


def _positive_text(text):
    # Exclusion/lineage prose is retained verbatim in the source layer. It cannot
    # serve as affirmative evidence that a strategy belongs to the excluded type.
    text=re.sub(r'(?:也?不是|并非|而非|不用|不属于|不同于)[^。；;\n]*', '', text or '')
    return re.sub(r'≠[^。；;\n]*', '', text)


def _summary_sentences(text):
    result=[]
    for sentence in _sentences(_positive_text(text)):
        if re.match(r'计入|提出日期|相对锚定划分|不是|不用',sentence):
            continue
        if sentence.startswith('本条只写') and not re.search(r'比较|定义|收益|回报|信号|若|买入|卖出|做多|做空|持仓|→|高于|低于',sentence):
            continue
        if re.match(r'^[`*\s]*(?:timeframe|inf_tf|startup_candle_count|use_sell_signal|trailing_stop|buy_params|sell_params)[`*\s]*[:=]',sentence,re.I):
            continue
        result.append(sentence)
    # A contiguous, explicitly labeled source excerpt is safer than moving a
    # later action ahead of its definitions and then inventing the missing link.
    return result or _sentences(text)[:1]


def _rule_fragments(sentences, key, pattern):
    found=[]
    for sentence in sentences:
        if not re.search(pattern,sentence,re.I):
            continue
        explicit_entry=bool(re.search(r'买入|开仓(?!价)|开多|开空|做多|做空|(?<!平)多[:：]|(?<!平)空[:：]|(?:long|short)[ _-]?entry|entry[ _-]?(?:long|short)',sentence,re.I))
        explicit_exit=bool(re.search(r'平多|平空|平仓|退出|出场|卖出|止盈|止损|custom_sell|custom_stoploss|trail(?:ing)?\b.{0,30}\bloss(?![A-Za-z_])|(?:long|short)[ _-]?exit|exit[ _-]?(?:long|short)',sentence,re.I))
        if key=='entry' and explicit_exit and not explicit_entry:
            continue
        if key=='exit' and explicit_entry and not explicit_exit:
            continue
        found.append(sentence)
    return found


def _dsl_rule(rule):
    if not (rule or '').startswith('QG-DSL/1\n'):
        return None
    try:
        data=json.loads(rule.split('\n',1)[1])
        return data if isinstance(data,dict) else None
    except (ValueError,TypeError):
        return None


def _source_parameters(rule):
    rule=re.sub(r'\*\*(.*?)\*\*',r'\1',rule or '').replace('`','')
    values=[]
    # Balanced scans preserve nested calls such as ROC(EMA(High-Low,10),10).
    for match in re.finditer(r'(?<![A-Za-z])(?:SMA|EMA|RSI|ATR|ROC|MA|T3|ZSCORE)\s*\(',rule or '',re.I):
        depth=1; end=match.end()
        while end<len(rule) and depth:
            depth += (rule[end]=='(')-(rule[end]==')')
            end+=1
        if depth==0:
            values.append(rule[match.start():end])
    values.extend(m.group(0) for m in re.finditer(r'(?:[-+−]?\d+(?:\.\d+)?\s*(?:个交易日|交易日|日|个月|月|周|年|倍|%)|%\s*[-+−]?\d+(?:\.\d+)?|(?<![A-Za-z])(?:SMA|EMA|RSI|ATR|ROC|MA)\s*\d+|(?:窗口|长度|倍数|因子|阈值|Volume Factor)\s*[-+−]?\d+(?:\.\d+)?)',rule or '',re.I))
    return [dict(name=v,value=v,meaning='来源规则原文参数；含义以完整上下文为准') for v in dict.fromkeys(values)]


def _frequencies(rule, name=''):
    text=_positive_text(rule or '')
    data=[]
    for count in re.findall(r'(\d+)\s*分钟(?:数据|K线|级|图|周期|收盘)',text,re.I):
        data.append(count+'min')
    leading=re.match(r'(\d+)分钟',name)
    if leading:
        data.append(leading[1]+'min')
    for code,pattern in [('hourly',r'小时数据|小时K线|小时线'),('daily',r'日线|日度数据'),('weekly',r'周线'),('monthly',r'月线')]:
        if re.search(pattern,text):
            data.append(code)
    observation=next((code for code,pattern in [('daily',r'日频|每日.{0,12}(?:观察|评估|检查|监控)|每个交易日.{0,12}评估|daily_eod'),
        ('monthly',r'月频|月末|每月.{0,12}(?:观察|评估|检查|监控)'),('weekly',r'周频|每周.{0,12}(?:观察|评估|检查|监控)')] if re.search(pattern,text,re.I)),None)
    data=list(dict.fromkeys(data))
    return dict(data=data,observation=observation,display=data[0] if len(data)==1 else 'multi_timeframe' if data else observation,
        status='EXTRACTED_FROM_AFFIRMATIVE_SOURCE_TEXT',notice='行情周期、观察频率与调仓动作分别记录')


def _strategy_example(ast):
    if not isinstance(ast,dict) or not ast.get('condition') or not ast.get('then',{}).get('asset') or not ast.get('else',{}).get('asset'):
        return None
    then,otherwise=ast['then']['asset'],ast['else']['asset']
    return dict(text=f'只演示条件分支：假设本次来源规则的判断条件成立，目标为 {then}；假设条件不成立，目标改为 {otherwise}。这不设定成交价格或未来收益。',
        basis='依据已记录条件与分支构造的教学情形；不是回测或执行结果')


def _structured_parameters(ast):
    values=[];seen=set()
    def walk(node):
        if isinstance(node,dict):
            if node.get('type')=='indicator' and node.get('name') and isinstance(node.get('parameters'),list):
                name=node['name'];parameters=node['parameters']
                key=(name,_text(parameters))
                if key not in seen:
                    seen.add(key)
                    meanings={'SMA':'计算简单移动平均的观察窗口','EMA':'计算指数移动平均的观察窗口；初始化仍需核对来源实现',
                        'RSI':'计算 RSI 的回看窗口；平滑方式仍需核对来源实现','ATR':'计算 ATR 波幅的观察窗口；平滑方式仍需核对来源实现'}
                    for index,value in enumerate(parameters):
                        meaning=meanings.get(name.upper()) if len(parameters)==1 else None
                        values.append(dict(name=f'{name} 参数 {index+1}',value=value,
                            meaning=meaning or f'来源已解析 {name} 的第 {index+1} 个参数；具体作用需核对来源定义'))
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(ast)
    return values


def _asset_scope(ast, raw, dsl=None):
    assets=set()
    def walk(node):
        if isinstance(node,dict):
            for key,value in node.items():
                if key in {'asset','risk_asset','safe_asset'} and isinstance(value,str) and value and not value.startswith('$'):
                    assets.add(value)
                elif key=='assets' and isinstance(value,list):
                    assets.update(v for v in value if isinstance(v,str) and v and not v.startswith('$'))
                elif isinstance(value,(dict,list)):
                    walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(ast)
    if dsl:
        walk(dsl)
        cash=dsl.get('cash')
        if isinstance(cash,str) and cash.endswith('_ZERO_INTEREST'):
            assets.add(cash.removesuffix('_ZERO_INTEREST'))
    if assets:
        return dict(value='single' if len(assets)==1 else 'multi',assets=sorted(assets),
            basis='来源结构中明确命名的信号、目标或现金替代资产；不表示同时持仓数量')
    universe=raw.get('universe') or ''
    if re.search(r'cross.sectional.*(?:universe|equities)|global equities|US equities',universe,re.I):
        return dict(value='multi',assets=[],basis='来源明确描述多证券的适用范围；成员与同时持仓数未固定')
    return dict(value='unknown',assets=[],basis='现有结构未完整列出涉及资产；不从名称或市场类别推定数量')


def _reading(key, label, text, source=None, status='SOURCE_REPORTED'):
    return dict(key=key, label=label, text=private_text(text) if text else UNKNOWN,
                status=status if text else 'UNKNOWN', evidence=source if text else None)


def _formula_notes(formula, dialect):
    """Vocabulary guide from the original expression, independent of formula AST."""
    operators = sorted(set(re.findall(r'(?<![\\\w])([A-Za-z_][A-Za-z_0-9]*)\s*\(', formula or '')))
    if (formula or '').lstrip().startswith('$') and dialect is None:
        operators=[]
    meanings = {'Ref': '取历史观测；具体滞后由第二参数给出', 'Delay': '取历史观测',
        'DELAY': '取历史观测', 'Mean': '窗口均值', 'SMA': '平滑均值；不同来源的递推定义可能不同',
        'Sum': '窗口求和', 'SUM': '窗口求和', 'Std': '窗口标准差', 'STD': '窗口标准差',
        'Abs': '绝对值', 'ABS': '绝对值', 'Log': '对数', 'LOG': '对数',
        'Corr': '窗口相关系数', 'CORRELATION': '窗口相关系数',
        'Greater': 'Qlib 两个表达式逐元素取较大值', 'Less': 'Qlib 两个表达式逐元素取较小值'}
    out = []
    for op in operators:
        meaning = meanings.get(op)
        if op in {'Greater', 'Less'} and dialect != 'qlib':
            meaning = None
        if op in {'Rank', 'RANK', 'rank'}:
            meaning = ('Qlib 窗口内的时序排名' if dialect == 'qlib' else
                       '排名算子；时序或截面范围须按该来源方言核对')
        out.append(dict(name=op, meaning=meaning or '来源算子；精确定义及边界处理需查看该来源实现'))
    return out


def _example(formula, dialect):
    # Only demonstrate exactly recognizable expressions, never evaluate arbitrary code.
    if dialect == 'qlib':
        match = re.fullmatch(r'Mean\(\$close,\s*(\d+)\)/\$close', formula or '')
        if match and int(match[1]) >= 2:
            n = int(match[1])
            return dict(text=f'假设窗口为 {n} 个观测：前 {n-1} 个收盘价都是 100，当前为 110。窗口均值 = (100×{n-1}+110)/{n}，再除以当前 110，结果约为 {(100*(n-1)+110)/n/110:.4f}。', basis='教学假设数据，按原公式代数计算；不是回测或收益预测')
    return None


def stable_knowledge_id(value):
    native = (value.get('source_native_ids') or [None])[0]
    if value['kind'] == 'strategy' and native:
        return 'grokbot:' + native
    if value['kind'] in {'variant', 'source'} and native:
        return 'factor:' + str(value.get('source_name') or value.get('source_type')) + ':' + native
    return value['entity_id']


def readable_item(value, raw):
    """Project an allowlist, never ship the raw/private payload as a JSON blob."""
    value = deepcopy(value)
    raw = raw if isinstance(raw, dict) else {}
    strategy = value['kind'] == 'strategy'
    variant = raw.get('variant', {}) if strategy else raw
    record = raw.get('raw_record', {}) if strategy else raw
    rule = (record.get('规则') or variant.get('original_rule_text') or
            variant.get('auditable_metadata', {}).get('raw_rule')) if strategy else None
    formula = None if strategy else (raw.get('raw_formula') or raw.get('formula') or value.get('formula'))
    if not strategy and not formula and str(raw.get('description', '')).strip().startswith('$'):
        formula = raw['description']
    definition = rule if strategy else (raw.get('raw_definition') or raw.get('description') or formula)
    collected_basis=variant.get('auditable_metadata',{}).get('metadata',{}).get('collected_at_basis') or raw.get('collected_at_basis')
    reported_collection=variant.get('auditable_metadata',{}).get('collected_at') or raw.get('retrieved_at')
    migration_time=reported_collection if collected_basis=='MIGRATION_OBSERVATION_TIME_ORIGINAL_COLLECTION_UNKNOWN' else None
    source_url = personal_url(variant.get('source_url_raw') or record.get('source_url') or variant.get('source_url') or value.get('source_url'))
    source = dict(url=source_url, locator=variant.get('source_locator') or value.get('source_locator'),
        native_ids=value.get('source_native_ids') or ([raw['source_native_id']] if raw.get('source_native_id') else []),
        revision=variant.get('source_revision') or value.get('source_revision'),
        sha256=variant.get('source_sha256') or raw.get('source_file_sha256') or value.get('source_sha256'),
        author=private_text(record.get('作者或机构')) if strategy else raw.get('authors', value.get('authors', [])),
        code_url=personal_url(raw.get('code_url')), terms_url=personal_url(variant.get('terms_url') or value.get('terms_url')),
        publication_date=variant.get('source_publication_date'), reference_year=raw.get('paper_year'),
        reported_date=variant.get('raw_proposed_date'), date_status=variant.get('date_status') or ('REPORTED_REFERENCE_YEAR' if raw.get('paper_year') else None),
        collected_at=None if migration_time else reported_collection, collected_at_basis=collected_basis,
        ingestion_observed_at=migration_time or raw.get('created_at'),
        collected_at_label='原始采集时间（未知）' if migration_time else '来源记录的采集时间',
        collection_time_notice='迁移/入库观察时间；原始采集时间未知' if migration_time else None,
        variant_created_at=variant.get('variant_created_at'))
    value['source_url'] = source_url
    for key in ['source_locator', 'source_revision', 'source_sha256']:
        lookup = {'source_locator': 'locator', 'source_revision': 'revision', 'source_sha256': 'sha256'}[key]
        if source[lookup]:
            value[key] = source[lookup]
    if not strategy:
        for key in ['description', 'economic_logic', 'parameters', 'required_fields', 'frequency', 'lookback', 'authors', 'license']:
            if raw.get(key) is not None:
                value[key] = _clean_private(raw[key])
        value['formula'] = private_text(formula)
        if raw.get('asset_class'):
            value['markets'] = [raw['asset_class']] if isinstance(raw['asset_class'], str) else raw['asset_class']
        value['aliases'] = list(dict.fromkeys(_clean_private(value.get('aliases', []) + raw.get('aliases', []))))
    readings, parameters, unknowns = [], [], []
    if strategy:
        value['strategy'] = value.get('strategy', {}) | {'original_rule': private_text(rule),
            'original_rule_notice': '本机来源快照中的采集规则；来源作者是否提出该具体版本须另行核对。'}
        sentences = [s for s in _sentences(_positive_text(rule)) if not re.search(r'未(?:印|写|说明|给出|注明|提供|披露|提及)',s)]
        dsl=_dsl_rule(rule)
        readings.append(_reading('core', '完整规则', rule, source_url))
        for key, label, pattern in READING_FIELDS:
            found = _rule_fragments(sentences,key,pattern)
            text = '；'.join(found) if found else None
            if key == 'scope' and not text:
                text = record.get('市场') or variant.get('raw_market')
            if dsl:
                mapping={'scope':'asset','entry':'entry','exit':'exit','position':'allocation','rebalance':'rebalance','observation':'schedule','execution':'execution_timing','costs':'costs'}
                text=_text(dsl.get(mapping.get(key,key))) or None
                if key=='execution' and not text and re.search(r'next.open',str(dsl.get('derivation','')),re.I):
                    text='下一开盘价；采集文本将成交时点标为研究假设：'+str(dsl['derivation'])
                if key=='costs' and not text and 'costs' in str(dsl.get('derivation','')):
                    text='采集文本将费用标为研究假设，未给出费用数值：'+str(dsl['derivation'])
                    unknowns.append('费用数值：采集的结构化规则只声明成本假设，未给出具体费率与滑点')
            readings.append(_reading(key, label, text, source_url, 'EXTRACTED'))
            if not text:
                readings[-1]['text']='采集文本中未单独提取到，需核对完整规则'
                unknowns.append(f'{label}：采集文本中未单独提取到，需核对完整规则')
        # Exact source fragments preserve threshold/window context; no AST gate.
        parameters=(_structured_parameters(variant.get('rule_ast'))+_source_parameters('；'.join(sentences))) if not dsl else [dict(name='parameters',value=dsl.get('parameters'),meaning='采集规则中的参数顺序；对应指标含义以来源说明为准')]
        if dsl:
            readings[0]=_reading('core','方法规则',f"信号：{dsl.get('signal', UNKNOWN)}；入场：{dsl.get('entry', UNKNOWN)}；退出：{dsl.get('exit', UNKNOWN)}",source_url,'EXTRACTED')
            if dsl.get('indicator_semantics'):
                readings.append(_reading('indicator_semantics','来源计算口径',dsl['indicator_semantics'],source_url))
        frequencies=_frequencies(rule,record.get('名称') or value['name'])
        frequencies['previous_projection']=value.get('frequency')
        value['frequency']=frequencies['display']
        # Existing parser fields are not sufficient evidence of all input fields.
        field_patterns = {'close': r'收盘(?:价)?|\$close\b|close\s*price', 'open': r'开盘价|\$open\b|open\s*price',
                          'high': r'最高价|最高\s*[-−+*/]|昨高|\$high\b|bar\.high|\bhigh\s*[-−+*/]', 'low': r'最低价|[-−+*/]\s*最低|昨低|\$low\b|bar\.low|[-−+*/]\s*low\b',
                          'volume': r'成交量|\$volume\b|\bvolume\s*[-−+*/]'}
        fields = set()
        fields.update(k for k,p in field_patterns.items() if re.search(p, _positive_text(rule or ''), re.I))
        if dsl and re.search(r'\bclose\b',str(dsl.get('indicator_semantics','')),re.I):
            fields.add('close')
        value['required_fields'] = sorted(fields)
        value['required_fields_status']='EXPLICIT_SOURCE_MENTIONS_COMPLETENESS_UNVERIFIED'
        method_raw = {'original_rule_text': rule}
        value['description'] = private_text(rule) if rule else value.get('description')
    else:
        readings = [_reading('definition', '来源定义', definition, source_url),
                    _reading('formula', '原始公式', formula, source_url),
                    _reading('intuition', '经济含义（来源报告）', raw.get('economic_logic'), source_url),
                    _reading('universe', '适用范围', raw.get('universe'), source_url),
                    _reading('frequency', '频率', value.get('frequency'), source_url),
                    _reading('direction', '方向解释', None, source_url)]
        params = raw.get('parameters') or value.get('parameters') or {}
        parameters = [dict(name=k, value=v, meaning=PARAM_MEANINGS.get(k, '来源记录字段；具体含义需核对来源')) for k,v in _clean_private(params).items()]
        unknowns = [f"{r['label']}：{UNKNOWN}" for r in readings if r['status']=='UNKNOWN']
        method_raw = raw
    fields = value.get('required_fields') or []
    if value.get('source_type')=='RULE_LINK_ONLY':
        # The public projection's generic close placeholder is not a verified
        # input list for indicators such as MFI/ATR which need other fields.
        fields=[]
        value['required_fields']=[]
        value['required_fields_status']='RULE_REFERENCE_INPUTS_UNVERIFIED'
        unknowns.append('仅收录规则中的指标引用；完整公式与所需数据尚未核对')
    dialect = raw.get('dialect')
    variables = [dict(name=f, meaning=FIELD_NAMES.get(f, '来源数据字段；完整定义和可用时点待核对')) for f in fields]
    operators = _formula_notes(formula, dialect)
    variables.extend(operators)
    if strategy:
        axis = 'time_series' if re.search(r'均线|sma|ema|rsi|atr|突破|过去\d+|动量', rule or '', re.I) else 'unknown'
        if re.search(r'横截面|截面排名|资产.{0,10}排名|股票.{0,10}排名|基金.{0,10}排名|配对|轮动', _positive_text(rule or '')):
            axis = 'cross_sectional'
    else:
        axis = 'cross_sectional' if raw.get('source_id') in {'osap', 'jkp'} else ('time_series' if dialect=='qlib' and re.search(r'\b(?:Mean|Ref|Std|Sum|Rank|Corr|Slope)\(', formula or '') else 'unknown')
    field_status = raw.get('required_fields_status') or value.get('required_fields_status', '')
    extra_fields = [f for f in fields if f not in OHLCV]
    daily_ohlcv = bool(fields) and not extra_fields and value.get('frequency') in {'daily', 'daily_eod'} and not strategy and field_status in {'syntax_extracted_unexpanded', 'AST_DERIVED_NOT_RUNTIME_VERIFIED'}
    # This is a source-field fit, never a claim of computation readiness.
    if extra_fields:
        extra_data = 'required'
    elif daily_ohlcv:
        extra_data = 'not_reported'
    else:
        extra_data = 'unknown'
    method = _method(value, method_raw)
    complete = 'readable' if definition else 'metadata_only'
    facts = [dict(label='采集规则' if strategy else '来源定义', text=private_text(definition), source=source_url)] if definition else []
    if formula and formula != definition:
        facts.append(dict(label='原始公式', text=private_text(formula), source=source_url))
    summary_parts=_summary_sentences(definition)
    summary_text = '。'.join(summary_parts[:4]) if definition else '当前只有来源元信息，原文定义尚未收录。'
    if strategy and len(summary_parts)>4:
        summary_text+='。（其余条件见完整规则）'
    if strategy and dsl:
        summary_text=f"{dsl.get('asset', UNKNOWN)} · {dsl.get('signal', UNKNOWN)}：{dsl.get('entry', UNKNOWN)}；{dsl.get('allocation', UNKNOWN)}。采集文本中的研究改编，成交与费用假设另列。"
    summary = private_text(summary_text)
    if len(summary)>320:
        summary=summary[:320]+'…（完整内容见下方来源定义）'
    explanations = [dict(label='方法归类', text=method['basis'], status='READING_INDEX')]
    explanations += [dict(label=o['name'], text=o['meaning'], status='READING_GUIDE') for o in operators]
    asset_scope=_asset_scope(variant.get('rule_ast'),raw,dsl if strategy else None)
    value['knowledge'] = dict(version=VERSION, summary=summary, method_family=method, dialect=dialect,
        summary_basis='按原顺序摘录来源部分规则；完整定义另行保留' if strategy else '来源定义及单独列出的整理说明',
        asset_scope=asset_scope,
        original_rule=private_text(rule), formula=private_text(formula), normalized_formula=private_text(raw.get('normalized_formula')),
        original_definition=private_text(definition),
        reading=readings, parameters=parameters, variables=variables, source=_clean_private(source), source_facts=facts,
        unknowns=unknowns, example=_strategy_example(variant.get('rule_ast')) if strategy else _example(formula, dialect),
        layers=dict(source_facts=facts, explanations=explanations, user_notes=[], hypotheses=[]),
        filters=dict(axis=axis, daily_ohlcv=daily_ohlcv, extra_data=extra_data, completeness=complete,asset_scope=asset_scope['value']),
        boundaries=dict(reading='可阅读性独立于执行语法解析', semantics=raw.get('semantic_status') or variant.get('semantics_status') or 'NOT_VERIFIED',
            economic_validity='NOT_ESTABLISHED_BY_DEFINITION', commercial_use=variant.get('commercial_use') or raw.get('commercial_use_flag') or 'REVIEW_REQUIRED'))
    if strategy:
        value['knowledge']['frequencies']=frequencies
    if value['kind'] in {'variant','concept'} or value.get('source_type')=='factor_source_record':
        from quantgraph.graph.factor_reading import enrich_factor_reading
        try:
            guide=enrich_factor_reading(value,raw)
        except (ValueError,TypeError,KeyError,IndexError,RecursionError,ArithmeticError):
            # A complex or incomplete single source must not make the whole
            # local library unreadable. Its original expression remains intact.
            guide=dict(summary='本机保留了来源原式；该结构暂不能可靠转成中文计算说明，请按完整原式与来源核对。',variables=[],example=None,
                semantics=[dict(label='中文计算说明',text='当前整理器未完成此结构的解释，原式仍完整保留。',status='UNKNOWN')],
                explanation_basis='未生成可靠的计算解释；不补写来源中不存在的含义。')
        knowledge=value['knowledge']
        knowledge['summary']=private_text(guide['summary'])
        if guide['variables']:
            knowledge['variables']=_clean_private(guide['variables'])
        if guide['example']:
            knowledge['example']=_clean_private(guide['example'])
        knowledge['explanation_basis']=guide['explanation_basis']
        knowledge['layers']['explanations'].append(dict(label='计算说明依据',text=guide['explanation_basis'],status='ORGANIZED_EXPLANATION'))
        for index,semantic in enumerate(guide['semantics']):
            knowledge['reading'].append(dict(key=f'calculation_{index}',evidence=source_url,**semantic))
            knowledge['layers']['explanations'].append(deepcopy(semantic))
            if semantic['status'] in {'UNKNOWN','REVIEW_REQUIRED'}:
                knowledge['unknowns'].append(semantic['label']+'：'+semantic['text'])
        if value['kind']=='concept':
            # These records are ontology summaries, not quotations from a paper.
            knowledge['source_facts']=[]
            knowledge['layers']['source_facts']=[]
            if knowledge['reading']:
                knowledge['reading'][0].update(label='分类整理说明',status='ORGANIZED_EXPLANATION')
    from quantgraph.graph.reading_brief import reading_brief
    value['knowledge']['reader_brief'] = _clean_private(reading_brief(value, value['knowledge'], METHOD_GUIDES[method['value']], raw.get('intake_card')))
    if raw.get('intake_card') and not strategy:
        # A collected implementation formula is not a quotation from the linked
        # paper or exchange API. Keep the detailed fallback consistent with the
        # evidence-aware card instead of relabelling it SOURCE_REPORTED.
        knowledge=value['knowledge'];brief=knowledge['reader_brief']
        knowledge['reading']=[dict(key=r['key'],label=r['label'],text=r['text'],status=r['status'],origin=r.get('origin')) for r in brief['trading']]
        if formula:
            knowledge['reading'].insert(0,dict(key='formula',label='资料卡的实现公式',text=private_text(formula),status='CARD_IMPLEMENTATION'))
        knowledge['source_facts']=[]
        knowledge['layers']['source_facts']=[]
        knowledge['unknowns']=[r['label']+'：'+r['text'] for r in brief['trading'] if r['status']=='UNKNOWN']
    from quantgraph.graph.factor_quality import apply_factor_quality
    value = apply_factor_quality(value, raw)
    if 'factor_quality' in value:
        value['factor_quality'] = _clean_private(value['factor_quality'])
    value['knowledge']['summary'] = value['knowledge']['reader_brief']['purpose']
    value['knowledge']['summary_basis'] = value['knowledge']['reader_brief']['purpose_basis']
    value['statuses']['display'] = '个人本机资料 · 公开权限与原有可见性未改变'
    value['stable_knowledge_id'] = stable_knowledge_id(value)
    value['prior_version_ids'] = []
    value['is_historical'] = False
    value['current_entity_id'] = value['entity_id']
    value['current_definition_revision'] = value['definition_revision']
    return value


class PersonalCatalogRepository(CatalogRepository):
    """An explicit local reader. Never pass this object into the public app."""
    def __init__(self, path, *, ingestion=None):
        super().__init__(path, ingestion=ingestion)
        self._cache_stamp = None
        self._cache = {}
        self._edges = []
        self._documents = {}
        self._lineage = {}
        self._personal_stamp = None
        self._personal_cache = {}
        self._redirects = {}
        self._content_digest = None
        self._base_rows = {}
        self._view_stamps = {}
        self._document_stamps = {}
        self._search_vocabulary = None

    def _stamp(self):
        return tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None
                     for p in (self.path, self.path.with_name(self.path.name + '-wal')))

    def _load(self):
        stamp = self._stamp()
        with self.lock:
            if stamp == self._cache_stamp:
                return self._cache
            with self.connect() as con:
                rows = con.execute('SELECT * FROM catalog_items WHERE active=1').fetchall()
                historical = con.execute('SELECT entity_id,payload FROM catalog_items WHERE active=0').fetchall()
                edges = con.execute('''SELECT e.payload,e.patch,e.visibility FROM catalog_edges e
                    WHERE EXISTS(SELECT 1 FROM catalog_edge_origins o WHERE o.relationship_id=e.relationship_id AND o.active=1)''').fetchall()
                reviews = (con.execute('SELECT entity_id,revision,payload FROM private_intake_reviews WHERE sequence IN (SELECT MAX(sequence) FROM private_intake_reviews GROUP BY entity_id)').fetchall()
                           if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='private_intake_reviews'").fetchone() else [])
                review_by_id={r['entity_id']:r for r in reviews}
                assessments=(con.execute('SELECT * FROM factor_quality_assessments ORDER BY sequence').fetchall()
                    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='factor_quality_assessments'").fetchone() else [])
                assessment_by_id={(r['entity_id'],r['definition_revision']):r for r in assessments}
            # SQLite/WAL housekeeping and an idempotent import can change mtimes
            # without changing any source row. Avoid repeating expensive reading.
            digest=hashlib.sha256(); row_stamps={}
            for batch in (rows,historical,edges,reviews,assessments):
                for row in batch:
                    serialized=json.dumps(tuple(row),ensure_ascii=False).encode()
                    digest.update(serialized)
                    if batch is rows:
                        if row['entity_id'] in review_by_id:
                            serialized+=review_by_id[row['entity_id']]['payload'].encode()
                        assessment=assessment_by_id.get((row['entity_id'],row['definition_revision']))
                        if assessment:serialized+=assessment['payload'].encode()+assessment['input_sha256'].encode()
                        row_stamps[row['entity_id']]=hashlib.sha256(serialized).digest()
            content_digest=digest.digest()
            if content_digest==self._content_digest:
                self._cache_stamp=self._stamp()
                return self._cache
            # Keep clean row projections separate from relation-enriched views.
            # Otherwise a removed/changed DESCRIBES edge could leave the old
            # parent's rule embedded in an unchanged source row indefinitely.
            base_rows={}
            for row in rows:
                eid=row['entity_id']; fingerprint=row_stamps[eid]
                previous=self._base_rows.get(eid)
                private=json.loads(row['private_payload'])
                if eid in review_by_id:
                    private['intake_card']=json.loads(review_by_id[eid]['payload'])
                assessment=assessment_by_id.get((eid,row['definition_revision']))
                if assessment:
                    private['_factor_quality_review']=json.loads(assessment['payload'])
                    private['_factor_quality_version']=assessment['assessment_version']
                    private['_factor_quality_sha256']=assessment['input_sha256']
                base_rows[eid]=previous if previous and previous[0]==fingerprint else (
                    fingerprint,readable_item(self._value(row),private))
            base={eid:entry[1] for eid,entry in base_rows.items()}
            lineage = defaultdict(list)
            for r in historical:
                lineage[stable_knowledge_id(json.loads(r['payload']))].append(r['entity_id'])
            self._lineage = {v['stable_knowledge_id']: v['entity_id'] for v in base.values()}
            self._edges = [json.loads(r['payload']) | json.loads(r['patch']) | {'visibility':r['visibility']} for r in edges]
            source_parents={}
            for link in sorted(self._edges,key=lambda e:e['relationship_id']):
                if link['relation']=='DESCRIBES' and link['from_id'] in base and link['to_id'] in base:
                    source, target = base[link['from_id']], base[link['to_id']]
                    if source['kind']=='source' and not source['knowledge']['original_definition'] and target['knowledge']['original_rule']:
                        source_parents.setdefault(source['entity_id'],target['entity_id'])
            groups = Counter(v.get('strategy', {}).get('template_id') for v in base.values() if v['kind']=='strategy' and not v.get('test_record'))
            cache={};view_stamps={};documents={};document_stamps={}
            for eid,original in base.items():
                prior=tuple(sorted(lineage[original['stable_knowledge_id']]))
                group=original.get('strategy',{}).get('template_id')
                group_count=groups[group] if group else 1
                parent=source_parents.get(eid)
                document_stamp=(row_stamps[eid],parent,row_stamps[parent] if parent else None)
                view_stamp=(document_stamp,prior,group_count)
                if self._view_stamps.get(eid)==view_stamp:
                    value=self._cache[eid]
                else:
                    # Only the top-level lineage/group fields change here. All
                    # nested base values stay immutable; readers receive copies.
                    value=original.copy()
                    value['prior_version_ids']=list(prior)
                    if parent:
                        target=base[parent]
                        k=value['knowledge']=deepcopy(original['knowledge'])
                        k['original_definition']=target['knowledge']['original_rule']
                        k['original_rule']=target['knowledge']['original_rule']
                        k['source_facts']=deepcopy(target['knowledge']['source_facts'])
                        k['layers']['source_facts']=deepcopy(k['source_facts'])
                        k['reading']=[_reading('definition','采集规则',k['original_rule'],target['source_url'])]
                        k['summary']=target['knowledge']['summary']
                        k['source']=deepcopy(target['knowledge']['source'])
                        k['filters']['completeness']='readable'
                        value['source_url']=target['source_url']
                group = value.get('strategy', {}).get('template_id')
                value['group']=dict(id=group or eid,count=group_count)
                cache[eid]=value;view_stamps[eid]=view_stamp;document_stamps[eid]=document_stamp
                documents[eid]=(self._documents[eid] if self._document_stamps.get(eid)==document_stamp
                                else self._document(value))
            self._base_rows=base_rows
            self._view_stamps=view_stamps
            self._document_stamps=document_stamps
            self._cache = cache
            self._documents = documents
            self._cache_stamp = self._stamp()
            self._content_digest = content_digest
            self._search_vocabulary = QueryVocabulary(cache.values(), METHODS)
            return cache

    @staticmethod
    def _document(value):
        k=value['knowledge']
        fields = [('name','名称',value['name']),('aliases','别名',value.get('aliases')),
                  ('native_id','来源原生 ID',value.get('source_native_ids')),('entity_id','条目 ID',value['entity_id']),
                  ('formula','公式',k['formula']),('rule','来源规则',k['original_rule']),
                  ('definition','来源定义',k['original_definition']),('family','方法族',value.get('family')),
                  ('description','描述',value.get('description')),
                  ('source','来源',value.get('source_name')),('source_url','来源链接',value.get('source_url')),
                  ('frequency','频率',value.get('frequency')),('fields','数据字段',value.get('required_fields')),
                  ('market','市场',value.get('markets')),('parameters','参数',value.get('parameters'))]
        # A broad category title is not evidence for every word in that title.
        # Only the explicitly recognized rolling-price-mean formula gets this
        # literal mathematical alias; no trend-to-momentum inference is added.
        if k['method_family'].get('evidence')=='Mean($close, n)/$close':
            fields.append(('formula_semantics','公式结构释义','简单均线 simple moving average SMA'))
        return [(key,label,_text(text),normalize(_text(text))) for key,label,text in fields if text]

    def _personal_notes(self):
        store = getattr(self, 'personal_store', None)
        if store is None:
            return {}
        stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None
                      for p in (store.path, store.path.with_name(store.path.name+'-wal')))
        if stamp != self._personal_stamp:
            notes = store.list()['items']
            self._personal_cache = {note['entity_id']: note for note in notes}
            with store.connect() as con:
                direct=dict(con.execute('SELECT old_id,canonical_id FROM personal_redirects').fetchall())
            redirects={}
            for eid in direct:
                current=eid; seen=set()
                while current in direct and current not in seen:
                    seen.add(current); current=direct[current]
                if current not in seen:
                    redirects[eid]=current
            self._redirects=redirects
            self._personal_stamp = stamp
        return self._personal_cache

    def _notes_for(self, item, notes=None):
        notes = self._personal_notes() if notes is None else notes
        canonical=self._redirects.get(item['entity_id'],item['entity_id'])
        ids = [item['entity_id'],canonical] + item.get('prior_version_ids', [])
        ids += [eid for eid,target in self._redirects.items() if target==canonical]
        stable = item['stable_knowledge_id']
        return [note for eid, note in notes.items() if eid in ids or note.get('stable_knowledge_id')==stable]

    def _overlay(self, item):
        notes = self._notes_for(item)
        item['canonical_id']=self._redirects.get(item['entity_id'],item['entity_id'])
        item['merged_from']=[eid for eid,target in self._redirects.items() if target==item['canonical_id']]
        item['merged_count']=len(item['merged_from'])+1
        item['knowledge']['layers']['user_notes'] = deepcopy(notes)
        item['knowledge']['layers']['hypotheses'] = [dict(text=n['questions'], entity_id=n['entity_id'],
            definition_revision=n['definition_revision'], status='USER_HYPOTHESIS') for n in notes if n.get('questions')]
        return item

    def get(self, entity_id, *, admin=False, include_tests=False):
        value=self._load().get(entity_id)
        if value is None:
            with self.connect() as con:
                row=con.execute('SELECT * FROM catalog_items WHERE entity_id=? AND active=0', (entity_id,)).fetchone()
            if row:
                value=readable_item(self._value(row),json.loads(row['private_payload']))
                # The public classifier marks ownerless inactive rows as tests;
                # historical identity instead follows its original snapshot.
                value['test_record']=bool(json.loads(row['payload']).get('test_record',False))
                value['is_historical']=True
                value['current_entity_id']=self._lineage.get(value['stable_knowledge_id'])
                current=self._cache.get(value['current_entity_id'])
                value['current_definition_revision']=current['definition_revision'] if current else None
        if not value or (value.get('test_record') and not include_tests and not admin):
            raise KeyError(entity_id)
        return self._overlay(deepcopy(value))

    def all_items(self, *, admin=False, include_tests=False):
        return [deepcopy(v) for v in self._load().values() if include_tests or admin or not v.get('test_record')]

    def _terms(self, query):
        self._load()
        return self._search_vocabulary.plan(query)['expanded_terms']

    def _match(self, eid, groups, extra_documents=(), *, exact_text=''):
        if exact_text:
            value=self._cache[eid]
            candidates=[('name','名称',value['name'])]
            candidates += [('aliases','别名',alias) for alias in value.get('aliases',[])]
            candidates += [(key,label,text) for key,label,text,_ in extra_documents if key=='user_aliases']
            candidates += [('formula','公式',value['knowledge'].get('formula') or '')]
            for key,label,text in candidates:
                same=(compact_formula(text)==compact_formula(exact_text) if key=='formula' else normalize(text)==normalize(exact_text))
                if same:
                    return [dict(field=key,label=label,text=text,term=normalize(exact_text),start=0,end=len(text),match_type='EXACT_LITERAL')]
        matches=[]
        for group in groups:
            found=None
            for key,label,text,norm in [*self._documents[eid], *extra_documents]:
                for term in group:
                    # Source URLs remain searchable by URL; words in a shared
                    # discussion URL do not establish the current rule's method.
                    if key=='source_url' and not term.startswith(('https://','http://')):
                        continue
                    if search_anchor(term) not in norm:
                        continue
                    match=search_pattern(term).search(norm)
                    if match:
                        start=max(0,match.start()-60); end=min(len(text),match.end()+100)
                        found=dict(field=key,label=label,text=text[start:end],term=term,
                                   start=match.start()-start,end=match.end()-start)
                        break
                if found:
                    break
            if not found:
                return None
            matches.append(found)
        return matches

    def search(self, *, q='', kind='strategy', category='', family='', field='', market='', frequency='', source_type='', result_status='', page=1, page_size=20, admin=False,
               method_family='', daily_ohlcv=False, axis='', extra_data='', completeness='', collapse_templates=False, include_tests=False, allowed_ids=None, collapse_duplicates=True, template_id='', asset_scope='', factor_scope=''):
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError('Invalid pagination')
        data=self._load(); plan=self._search_vocabulary.plan(q); groups=plan['expanded_terms']; matched=[]
        exact_ids=self._search_vocabulary.exact_ids(q)
        notes=self._personal_notes()
        researched = {ref['entity_id'] for r in self.results().get('items', []) for ref in r.get('entity_refs', [])} if result_status else set()
        for eid,value in data.items():
            if allowed_ids is not None and eid not in allowed_ids:
                continue
            if value.get('test_record') and not include_tests and not admin:
                continue
            if template_id and value.get('strategy',{}).get('template_id')!=template_id:
                continue
            factor_source = kind=='variant' and value['kind']=='source' and value.get('source_type')=='factor_source_record'
            if kind and kind!='all' and value['kind']!=kind and not factor_source:
                continue
            if factor_scope and factor_scope!='all' and value.get('factor_quality',{}).get('group')!=factor_scope:
                continue
            if any(wanted and value.get(key)!=wanted for key,wanted in [('category',category),('family',family),('frequency',frequency),('source_type',source_type)]):
                continue
            if field and field not in value.get('required_fields',[]) or market and market not in value.get('markets',[]):
                continue
            k=value['knowledge']; filters=k['filters']
            if method_family and k['method_family']['value']!=method_family:
                continue
            if daily_ohlcv and not filters['daily_ohlcv']:
                continue
            if any(wanted and filters[key]!=wanted for key,wanted in [('axis',axis),('extra_data',extra_data),('completeness',completeness),('asset_scope',asset_scope)]):
                continue
            status='researched' if eid in researched else 'unresearched'
            if result_status and result_status!=status:
                continue
            item_notes=self._notes_for(value,notes)
            extra_documents=[]
            for note in item_notes:
                for key,label in [('aliases','我的别名'),('tags','我的标签'),('note','我的备注'),('summary','我的整理'),('questions','我的假设'),('reason','我的研究理由')]:
                    if note.get(key):
                        texts=note[key] if key=='aliases' else [_text(note[key])]
                        for text in texts:
                            extra_documents.append(('user_'+key,label,text,normalize(text)))
            exact_user_alias=bool(q) and any(normalize(q)==normalize(alias) for note in item_notes for alias in note.get('aliases',[]))
            exact=eid in exact_ids or exact_user_alias
            if not exact and not accepts_constraints(value, plan['constraints']):
                continue
            matches=self._match(eid,groups,extra_documents,exact_text=q if exact else '')
            if matches is None:
                continue
            score=(-1000 if eid in exact_ids or exact_user_alias else 0)+sum({'name':0,'native_id':0,'aliases':1,'user_aliases':1,'formula':2,'rule':3,'definition':3}.get(m['field'],4) for m in matches)
            matched.append((score,value,matches))
        matched.sort(key=lambda x:(x[0],x[1]['name'],x[1]['entity_id']))
        record_total=len(matched)
        if collapse_duplicates and self._redirects:
            collapsed=[]; seen=set(); matched_ids={value['entity_id'] for _,value,_ in matched}
            for score,value,matches in matched:
                canonical=self._redirects.get(value['entity_id'],value['entity_id'])
                if canonical not in seen:
                    seen.add(canonical)
                    # Notes stay owned by their original records. A canonical
                    # item which did not pass the query must not be substituted
                    # into the filtered results merely because it was merged.
                    representative=data[canonical] if canonical in matched_ids else value
                    collapsed.append((score,representative,matches))
            matched=collapsed
        if collapse_templates:
            seen=set(); collapsed=[]
            for row in matched:
                key=row[1]['group']['id']
                if key not in seen:
                    seen.add(key);collapsed.append(row)
            matched=collapsed
        offset=(page-1)*page_size
        items=[]
        for _,value,matches in matched[offset:offset+page_size]:
            item=self._overlay(deepcopy(value))
            item['matches']=matches;item['matched_fields']=list(dict.fromkeys(m['label'] for m in matches))
            if result_status:
                item['result_status']='researched' if item['entity_id'] in researched else 'unresearched'
            items.append(item)
        return dict(items=items,total=len(matched),record_total=record_total,page=page,page_size=page_size,
                    scope='personal_local',sort='exact_name_alias_formula_then_source_relevance_then_name',collapsed=collapse_templates,
                    query=deepcopy(plan) | {'text':q})

    def detail(self, kind, eid):
        value=self.get(eid)
        if value['kind']!=kind:
            raise KeyError(eid)
        relation=self.relations(eid)
        value['relations']=relation['items']
        related_ids=list(dict.fromkeys(e['to_id'] if e['from_id']==eid else e['from_id'] for e in relation['items']))
        value['related']=[self.get(i) for i in related_ids]
        value['related_strategies']=[dict(strategy_id=n['entity_id'],canonical_name=n['name']) for n in value['related'] if n['kind']=='strategy']
        value['results']=self.results(kind,eid)
        if value['results']['items']:
            value['statuses']['result']='已有研究记录 · 结论级别与适用范围见原记录'
        return value

    def detail_version(self, kind, eid, definition_revision):
        """Resolve the exact archived definition; never substitute current text."""
        with self.connect() as con:
            row = con.execute('SELECT payload,private_payload FROM catalog_versions WHERE entity_id=? AND revision=?',
                              (eid, definition_revision)).fetchone()
        if not row:
            raise KeyError(eid)
        payload = json.loads(row['payload'])
        if payload.get('kind') != kind or payload.get('definition_revision') != definition_revision:
            raise KeyError(eid)
        result = readable_item(payload, json.loads(row['private_payload']))
        result['snapshot_status'] = 'ARCHIVED_EXACT_REVISION'
        result['is_historical'] = True
        result['current_entity_id'] = self._lineage.get(result['stable_knowledge_id'])
        return result

    @staticmethod
    def relation_explanation(relation):
        labels={'DESCRIBES':'来源记录描述','SOURCED_FROM':'来源于','IMPLEMENTED_BY':'计算实现','CITES':'文献引用',
            'USES_FACTOR':'策略使用的因子','HAS_COMPONENT':'组成部分','VARIANT_OF':'所属概念或模板','IN_FAMILY':'所属方法族',
            'PARAMETER_VARIANT':'参数变体','ASSET_VARIANT':'资产变体','DERIVED_FROM':'衍生来源','CATEGORY_LINK_ONLY':'同来源概念内的定义',
            'EQUIVALENT_TO':'经记录的等价关系','IMPLEMENTS':'实现该定义'}
        if relation in {'DESCRIBES','SOURCED_FROM','IMPLEMENTED_BY','CITES'}:
            return dict(category='source',label=labels.get(relation,relation),text='说明资料出处或实现引用，不保证该来源证明了具体策略收益。')
        if relation in {'USES_FACTOR','HAS_COMPONENT'}:
            return dict(category='component',label=labels.get(relation,relation),text='规则中明确使用或组成；不表示这个因子驱动了收益。')
        return dict(category='structure',label=labels.get(relation,relation),text='来源分类、模板或观察到的差异；同族、同名均不代表数学等价或相同收益。')

    def relations(self, entity_id, *, hops=1, relation='', limit=40, offset=0, admin=False, confidence=0, layer='all'):
        if not 1<=hops<=2 or not 1<=limit<=100 or offset<0 or not 0<=confidence<=1:
            raise ValueError('Invalid relation query')
        data=self._load(); root=self.get(entity_id,admin=admin)
        if root['is_historical']:
            return dict(items=[],total=0,offset=offset,limit=limit,hops=hops,
                nodes=[{k:root[k] for k in ['entity_id','name','kind','entity_type']}], types=[], categories=[],
                notice='历史版本仅展示原定义；当前关系请查看新版本，避免用新关系改写旧版本。')
        allowed={eid for eid,v in data.items() if admin or not v.get('test_record')}
        candidates=[e for e in self._edges if e['from_id'] in allowed and e['to_id'] in allowed and
                    (not relation or e['relation']==relation) and (e.get('confidence') or 0)>=confidence and
                    (layer in {'','all'} or self.relation_explanation(e['relation'])['category'] in ({'structure','component'} if layer=='method' else {layer}))]
        frontier={entity_id};visited={entity_id};found={}
        for _ in range(hops):
            next_frontier=set()
            for edge in candidates:
                if edge['from_id'] in frontier or edge['to_id'] in frontier:
                    found[edge['relationship_id']]=edge
                    next_frontier.update([edge['from_id'],edge['to_id']])
            frontier=next_frontier-visited;visited.update(next_frontier)
        ordered=sorted(found.values(),key=lambda e:(e['relation'],e['relationship_id']))
        edges=deepcopy(ordered[offset:offset+limit]);node_ids={entity_id}
        for edge in edges:
            a,b=data[edge['from_id']],data[edge['to_id']]
            edge.update(from_name=a['name'],to_name=b['name'],from_kind=a['kind'],to_kind=b['kind'],
                        from_type=a['entity_type'],to_type=b['entity_type'],explanation=self.relation_explanation(edge['relation']))
            edge['source']=personal_url(edge.get('source'))
            node_ids.update([edge['from_id'],edge['to_id']])
        return dict(items=edges,total=len(ordered),offset=offset,limit=limit,hops=hops,
                    nodes=[{k:data[eid][k] for k in ['entity_id','name','kind','entity_type']} for eid in sorted(node_ids)],
                    types=sorted({e['relation'] for e in found.values()}),
                    categories=[dict(value=k,label=v) for k,v in [('source','来源与实现'),('component','策略与因子使用关系'),('structure','概念、模板与变体')]])

    def compare(self, refs):
        if not 2<=len(refs)<=4 or len(set(refs))!=len(refs):
            raise ValueError('请选择 2–4 个不同条目')
        items=[]
        for ref in refs:
            kind,sep,eid=ref.partition('/')
            if not sep:
                raise ValueError('Invalid reference')
            items.append(self.detail(kind,eid))
        fields=[('name','名称',lambda i:i['name']),('rule','规则或定义',lambda i:i['knowledge']['original_rule'] or i['knowledge']['original_definition']),
                ('formula','公式',lambda i:i['formula']),('parameters','参数',lambda i:i['knowledge']['parameters']),
                ('fields','输入数据',lambda i:i['required_fields']),('frequency','频率',lambda i:i['frequency']),
                ('scope','适用市场',lambda i:i['markets']),('method','方法归类',lambda i:i['knowledge']['method_family']['label']),
                ('axis','比较对象与计算范围',lambda i:i['knowledge']['filters']['axis']),
                ('source','来源',lambda i:i['source_url']),('unknowns','未说明事项',lambda i:i['knowledge']['unknowns'])]
        differences=[]
        for key,label,extract in fields:
            values=[extract(i) for i in items]
            known=all(v is not None and v not in ('','unknown','尚未归类','未分类','待分类','待确认') and v!=[] and v!={} for v in values)
            differences.append(dict(key=key,label=label,values=values,same=known and len({_text(v) for v in values})==1,
                                    status='KNOWN' if known else 'UNKNOWN',known=known))
        changed=[d['label'] for d in differences if d['known'] and not d['same'] and d['key']!='name']
        uncertain=[d['label'] for d in differences if not d['known']]
        conclusions=[]
        sets=[set(i['required_fields']) for i in items]
        if all(sets) and len({tuple(sorted(s)) for s in sets})>1:
            common=set.intersection(*sets)
            summaries=[f"{i['name']} 单独需要 {', '.join(FIELD_NAMES.get(f,f) for f in sorted(s-common)) or '无额外已报告字段'}" for i,s in zip(items,sets)]
            conclusions.append('输入数据存在具体差异：'+'；'.join(summaries)+'。字段清单的完整性仍需核对。')
        axes=[i['knowledge']['filters']['axis'] for i in items]
        if 'unknown' not in axes and len(set(axes))>1:
            conclusions.append('比较范围不同：'+ '；'.join(f"{i['name']}：{'横向比较多个对象' if a=='cross_sectional' else '沿时间比较同一对象'}" for i,a in zip(items,axes))+'。')
        formulas=[i.get('formula') for i in items]
        if all(formulas) and len({i['knowledge'].get('dialect') for i in items})==1:
            normalized=[re.sub(r'\s+','',f).casefold() for f in formulas]
            mask=lambda f:re.sub(r'(?<![a-z_])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?','#',f)
            if len(set(normalized))==1:
                conclusions.append('已收录的原始公式相同；来源版本、缺失值与计算实现仍需分别核对，未据此声明等价。')
            elif len({mask(f) for f in normalized})==1:
                windows=[i.get('parameters',{}).get('window_or_lag') for i in items]
                if all(w is not None for w in windows):
                    conclusions.append('公式的运算结构相同，来源窗口或滞后分别为 '+ ' / '.join(map(str,windows))+'；其余计算语义尚未据此验证。')
                else:
                    conclusions.append('公式在移除数值常量后结构相同；差异在常量或窗口数值，具体含义须按参数说明核对。')
        templates=[i.get('strategy',{}).get('template_id') for i in items]
        if all(templates) and len(set(templates))==1:
            def leaves(value,path=''):
                if isinstance(value,dict):
                    return {k:v for name,item in value.items() for k,v in leaves(item,path+'.'+name).items()}
                if isinstance(value,list):
                    return {k:v for index,item in enumerate(value) for k,v in leaves(item,path+f'[{index}]').items()}
                return {path:value}
            definitions=[leaves(i.get('strategy',{}).get('structured_rule') or {}) for i in items]
            changed_paths=[key for key in sorted(set().union(*definitions)) if len({_text(d.get(key)) for d in definitions})>1]
            if changed_paths:
                asset_changes=[p for p in changed_paths if any(k in p for k in ['.asset','.risk_asset','.safe_asset'])]
                parameter_changes=[p for p in changed_paths if any(k in p for k in ['.parameters','.value','.threshold'])]
                pieces=[]
                if asset_changes:
                    pieces.append('资产槽位不同（'+ '；'.join(p.lstrip('.')+': '+ ' / '.join(_text(d.get(p)) for d in definitions) for p in asset_changes[:4])+')')
                if parameter_changes:
                    pieces.append('参数槽位不同（'+ '；'.join(p.lstrip('.')+': '+ ' / '.join(_text(d.get(p)) for d in definitions) for p in parameter_changes[:4])+')')
                other=[p for p in changed_paths if p not in asset_changes+parameter_changes]
                if other:
                    pieces.append('另有结构字段变化：'+', '.join(p.lstrip('.') for p in other[:4]))
                conclusions.append('共享已记录模板；'+'；'.join(pieces)+'。这仅比较已解析部分，完整来源与执行缺项仍需逐项核对。')
        if not conclusions:
            conclusions.append('现有证据不足以断言只改变窗口、只改变资产或规则结构相同；下表保留可核对的原文差异。')
        conclusions.append('当前条目的已知不同之处：'+'、'.join(changed)+'。' if changed else
            '已知且可比较的字段未显示可确定差异；仍不能认定等价。')
        if uncertain:
            conclusions.append('暂不能比较、需要核对的字段：'+'、'.join(uncertain)+'。缺值不代表相同或不同。')
        conclusions.append('空白字段表示未知，不能当作相同规则；比较不据此判断收益或独立策略数量。')
        return dict(items=items,differences=differences,conclusions=conclusions)

    def metadata(self):
        items=[v for v in self._load().values() if not v.get('test_record')]
        counts=Counter(v['kind'] for v in items)
        def facet(key,multiple=False,labels=None):
            c=Counter(v for i in items for v in (i.get(key) or [] if multiple else [i.get(key)]) if v)
            return [dict(value=v,label=(labels or FIELD_NAMES).get(v,v),count=n) for v,n in sorted(c.items())]
        method_items=[i for i in items if i['kind'] in {'strategy','variant'} or i.get('source_type')=='factor_source_record']
        methods=Counter(i['knowledge']['method_family']['value'] for i in method_items)
        method_rows=[]
        for value,count in methods.most_common():
            candidates=[i for i in method_items if i['knowledge']['method_family']['value']==value]
            chosen=[]; signatures=set()
            # Include real strategy and factor examples, then diversify templates.
            for domain in ['strategy','factor','any']:
                for i in candidates:
                    if domain=='strategy' and i['kind']!='strategy' or domain=='factor' and i['kind']=='strategy':
                        continue
                    signature=(i['kind'],i.get('strategy',{}).get('template_id') or i.get('family') or i['entity_id'])
                    if i['entity_id'] not in {x['entity_id'] for x in chosen} and signature not in signatures:
                        chosen.append(i);signatures.add(signature)
                        break
            representatives=[dict(entity_id=i['entity_id'],kind=i['kind'],name=i['name']) for i in chosen]
            description,structures,questions=METHOD_GUIDES[value]
            method_rows.append(dict(value=value,label=METHOD_LABELS[value],count=count,representatives=representatives,
                description=description,common_structures=structures,questions=questions,
                guidance_status='READING_GUIDE_NOT_PROFITABILITY_EVIDENCE'))
        filters={key:Counter(i['knowledge']['filters'][key] for i in items if i['kind'] in {'strategy','variant','source'}) for key in ['axis','extra_data','completeness','asset_scope']}
        quality=Counter(i['knowledge']['filters']['completeness'] for i in items)
        source_counts=Counter(i.get('source_name') or '来源未标注' for i in items if i['kind'] in {'strategy','variant','source'})
        valid_ids={i['entity_id'] for i in items}
        relations=[e for e in self._edges if e['from_id'] in valid_ids and e['to_id'] in valid_ids]
        relation_layers=Counter(self.relation_explanation(e['relation'])['category'] for e in relations)
        reviewed=[i['knowledge']['reader_brief'] for i in items if i['knowledge']['reader_brief'].get('intake_status')]
        from quantgraph.graph.factor_quality import quality_summary
        return dict(factor_quality_summary=quality_summary(items),mode='personal_local',release='local-catalog',graph_api='v1',graph_version='0.2.0',adapter_version=VERSION,
            intake_summary=dict(reviewed_records=len(reviewed),by_status=dict(Counter(r['intake_status'] for r in reviewed)),
                by_type=dict(Counter(r.get('entry_type','unknown') for r in reviewed)),
                source_reviews=sum(bool(r.get('existing_record_overlay')) for r in reviewed),new_backtests_from_import=0),
            counts={k:counts[k] for k in ['strategy','variant','concept','family','template','source']},
            visible_counts=dict(counts),test_counts=dict(Counter(v['kind'] for v in self._load().values() if v.get('test_record'))),
            result_count=self.results()['total'],legacy_result_count=0,
            facets=dict(categories=facet('category'),families=facet('family'),fields=facet('required_fields',True),markets=facet('markets',True),
                frequencies=facet('frequency',labels=FREQUENCY_LABELS),source_types=facet('source_type'),
                method_families=[{k:r[k] for k in ['value','label','count']} for r in method_rows],
                axes=[dict(value=k,label={'time_series':'时序','cross_sectional':'截面','unknown':'待确认'}[k],count=v) for k,v in filters['axis'].items()],
                asset_scopes=[dict(value=k,label={'single':'规则涉及单一资产','multi':'规则涉及多种资产','unknown':'涉及资产未确认'}[k],count=v) for k,v in filters['asset_scope'].items()],
                extra_data=[dict(value=k,label={'required':'需要额外数据','not_reported':'已报告字段限于OHLCV','unknown':'待确认'}[k],count=v) for k,v in filters['extra_data'].items()],
                completeness=[dict(value=k,label={'readable':'已有可读定义','metadata_only':'仅来源元信息'}[k],count=v) for k,v in filters['completeness'].items()]),
            method_families=method_rows,reading_coverage=dict(quality),definitions_quality=dict(quality),
            source_layers=[dict(source=s,count=n) for s,n in source_counts.most_common()],relation_count=len(relations),relation_layers=dict(relation_layers),
            layer_counts=dict(source_fact_records=sum(bool(i['knowledge']['source_facts']) for i in items),
                readable_strategy_rules=sum(i['kind']=='strategy' and bool(i['knowledge']['original_rule']) for i in items),
                formula_records=sum(bool(i['knowledge']['formula']) for i in items),
                normalized_factor_records=sum(i.get('source_type')=='factor_source_record' for i in items),
                factor_browse_records=sum(i['kind']=='variant' or i.get('source_type')=='factor_source_record' for i in items),
                factor_definitions=sum(i['kind']=='variant' and i['record_level']!='rule_reference' for i in items),
                rule_reference_factors=sum(i['kind']=='variant' and i['record_level']=='rule_reference' for i in items)),
            contracts=dict(request='research-request/v1',result='factor-study-result/v1',status='LOCAL_REFERENCE_ONLY',export_enabled=True),
            knowledge_counts=dict(collected_strategy_records=counts['strategy'],structured_strategy_variants=sum(i['kind']=='strategy' and i['record_level']=='variant' for i in items),
                readable_strategy_records=sum(i['kind']=='strategy' and bool(i['knowledge']['original_rule']) for i in items),
                strategy_families=counts['family'],strategy_templates=counts['template'],relations=len(relations),independent_strategies=None,
                explanation='采集条目、阅读方法归类、结构化模板与参数变体分别计数；不把条目数当作独立策略数。'))

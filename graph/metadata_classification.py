"""Evidence-bound content classification; never definition admission or source verification."""
import re

KINDS = {'strategy', 'factor', 'reference', 'unclassified'}
VERSION = 'content-classifier/v1'


def plain(text):
    return re.sub(r'[*`]', '', text)


def search(pattern, text):
    return re.search(pattern, plain(text), re.I)


def quality_flags(record):
    text = record['reported_fields']['规则']['value']
    flags = []
    if re.search(r'数据不足|(?:未|没有|缺少).{0,22}(?:写|印|披露|展开|给出|定义|公式|规则|参数|阈值)|摘录截断', text):
        flags.append('DEFINITION_DETAILS_MISSING')
    if re.search(r'Sh或t|process_或ders|多条件=(?:input\(|array\.new|0,\s*margin)|空条件=[\'"]', text):
        flags.append('POSSIBLE_EXTRACTION_ERROR')
    if any(re.search(r'(?:同|见|依赖|继承|沿用|基于).{0,10}[MWC]\d{2,}|同上|框架内|原式同', p)
           for p in positive_passages(text)):
        flags.append('CROSS_RECORD_DEPENDENCY')
    return flags


def positive_passages(text):
    """Keep source substrings; discard comparison/negation/date boilerplate."""
    passages = []
    for sentence in re.split(r'[。\n]', text):
        sentence = sentence.strip()
        if not sentence:
            continue
        # Comparison tails are frequent in this corpus and describe other rows.
        restatement = re.search(r'(?:不是|相对).+?[：:]\s*(本条(?:是|为).+)', sentence)
        sentence = re.split(r'^(?:不是|并非)|[，；]\s*(?:不是|并非)|相对已收|相对原|相对纯|区别于|不同于', sentence, maxsplit=1)[0].strip()
        if restatement:
            passages.append(restatement.group(1))
        if not sentence or re.match(r'^(?:不是|并非|未(?:给|写|提供|公布|披露|展开|说明|采|找到)|不(?:补|包含|涉及|纳入|作为|代表)|无(?:机械|明确|固定|具体|额外)|没有(?:给|写|提供|明确)|缺(?:少|乏)|计入|提出日期|Notes[:：])', plain(sentence)):
            continue
        if re.match(r'^相对.{0,90}[:：]\s*本条', sentence):
            continue
        if sentence.startswith('本条只写') and re.search(r'规则[。]?$', sentence):
            continue
        passages.append(sentence)
    return passages


def infer(record):
    """Return a type hypothesis with exact quotes from the rule body, not the name."""
    text = record['reported_fields']['规则']['value']
    passages = positive_passages(text)
    body = '\n'.join(passages)

    def decision(kind, subtype, rule, reason, quotes):
        evidence = [{'field': '规则', 'quote': q[:900]} for q in quotes[:3] if q]
        return dict(kind=kind, subtype=subtype, rule_id=rule, reason=reason, evidence=evidence,
                    confidence=('LOW' if kind == 'unclassified' else 'MEDIUM'
                                if subtype in {'selection_outline', 'strategy_component'} else 'HIGH'),
                    quality_flags=quality_flags(record))

    if text.startswith('信号（Signal Browser Definition）'):
        quote = text.split('组合规则', 1)[0].strip()
        return decision('factor', 'characteristic_definition', 'F_SIGNAL_DEFINITION',
                        '正文主要对象为信号定义；所附标准测试组合不改变该对象类型。', [quote])
    if text.startswith('特征构造'):
        quote = text.split('组合（Documentation', 1)[0].strip()
        return decision('factor', 'characteristic_definition', 'F_FEATURE_EXCERPT',
                        '正文主要对象为特征构造摘录；通用组合测试方法另行保留。', [quote])
    if search(r'Ken French|French《', body) and search(r'(?:因子|SMB|HML|RMW|CMA|WML|MOM)\s*[=＝]', body):
        quotes = [p for p in passages if search(r'(?:因子|SMB|HML|RMW|CMA|WML|MOM)\s*[=＝]', p)]
        return decision('factor', 'factor_portfolio', 'F_RETURN_CONSTRUCTION',
                        '正文给出因子收益序列或因子组合的构造公式。', quotes)

    action = re.compile(r'做多|做空|开多|开空|平多|平空|买入|卖出|开仓|平仓|清仓|持有|满仓|建仓|加仓|减仓|入场|进场|离场|出场|持仓|再平衡|调仓|反手|翻仓|追多|追空|多最高|多最低|空最高|空最低|买单|卖单|持股|持现金|转为.*现金|(?<!支)持\s*[*`]*(?:[A-Z]{2,}|\d+\s*(?:月|日|年|%))|[买卖改转]\s*[*`]*(?:[A-Z]{2,}|100%|现金)|[买卖][:：]|[买卖][，、；。]|→\s*[*`]*(?:\d+%\s*)?[*`]*(?:SPY|QQQ|BIL|TLT|GLD|SHY|IEF|AGG)\b|(?<![A-Za-z0-9_])set_?holdings(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])liquidate(?![A-Za-z0-9_])|strategy\.(?:entry|order|close)|\b(?:entry|entries|exit|buy|sell)(?:\b|[A-Z])', re.I)
    def action_text(passage):
        # Executed-volume inputs name buyers/sellers; those nouns are not orders.
        return re.sub(r'(?:主动)?(?:买入|卖出)(?:的)?成交量', '成交量', plain(passage))

    hits = [p for p in passages if action.search(action_text(p)) or search(r'entry|exit|入多|入空|持多|持空|换入|换仓|[多空][:：]|多\s*[A-Z]\s*空|空\s*[A-Z]\s*多|做多头|为空头|为多头|market_?order|Insight.*(?:UP|DOWN)', action_text(p))]
    if hits:
        portfolio = any(re.search(r'再平衡|调仓|配置|权重|等权|组合|轮动', p) for p in hits)
        return decision('strategy', 'portfolio_rule' if portfolio else 'trading_rule', 'S_POSITION_RULE',
                        '正文描述资产选择、目标持仓、交易动作或组合再平衡；类型不等于规则已完整。', hits)
    definitions = [p for p in passages if search(r'(?:因子|指标|特征|信号)(?:定义[:：]|\s*[=＝])|定义.{0,15}(?:因子|指标|特征|信号)', p)]
    selections = [p for p in passages if search(r'选股|选取|筛选|排序|top\s*\d|取前|取最|选得分|选.{0,8}股', p)
                  and search(r'股票|组合|等权|市值|股息|收益|动量|PE|ROE|因子|ETF|行业|公司', body)
                  and (p not in definitions or search(r'选股|筛选.{0,12}股票|取前.{0,12}只|选取.{0,12}ETF', p))]
    if selections:
        return decision('strategy', 'selection_outline', 'S_SECURITY_SELECTION',
                        '正文明确描述资产筛选或排名用途；具体计算与执行条件仍需另审。', selections)
    composite = [p for p in passages if search(r'合成.{0,8}因子|因子.{0,20}合成|相对均价因子', p)]
    if composite:
        return decision('factor', 'composite_signal', 'F_COMPOSITE_SIGNAL',
                        '正文的合成输出是因子数值，而不是资产持仓权重。', composite)
    study = [p for p in passages if search(r'单因子测试|因子检验|回测约束|验证.{0,20}报告|测试设置', p)]
    if study:
        return decision('reference', 'research_protocol', 'R_RESEARCH_PROTOCOL',
                        '正文描述研究检验的设置或报告，未给出新的交易用途或信号定义。', study)
    allocations = [p for p in passages if search(r'权重|等权|市值加权|配置|比例加权|风险平价|最小方差|风险名义|投资于|净资产投于|资产投指数|跟踪.*指数|抽样复制|PortfolioConstruction|(?:\d+%\s*[A-Z]{2,}|[A-Z]{2,}\s*\d+%)', p)
                   and search(r'资产|组合|股票|ETF|SPY|TLT|指数|基金|行业|个股|宇宙|portfolio', body)]
    # An explicit feature definition may rank or weight observations. Only a
    # separate portfolio instruction (or explicit asset allocation) overrides it.
    if definitions:
        allocations = [p for p in allocations if p not in definitions
                       or search(r'资产配置|组合.{0,15}配置|持仓权重', p)]
    if allocations:
        return decision('strategy', 'portfolio_rule', 'S_ALLOCATION',
                        '正文输出为资产配置或组合权重规则。', allocations)
    if definitions:
        return decision('factor', 'signal_definition', 'F_EXPLICIT_DEFINITION',
                        '正文明确以数值因子或信号为定义对象；窗口排序和特征加权不等于资产选择。', definitions)
    factors = [p for p in passages if re.search(r'因子|指标|特征|信号', p)
               and re.search(r'计算|构建|构造|定义|比率|残差|标准差|均值|相关|协方差|收益率|分位|[=＝]', p)]
    if factors:
        return decision('factor', 'signal_definition', 'F_SIGNAL_CONSTRUCTION',
                        '正文描述数值信号或指标的构造，未找到明确的持仓映射。', factors)
    numeric = [p for p in passages if re.search(r'计算|构建|构造|定义[:：]|截面回归|回归残差|得[A-Z]|[A-Z][A-Za-z0-9_]*\s*[=＝]', p)
               and re.search(r'收益|价格|成交|分钟|残差|标准差|相关|波动|利润|交易量|回归|市值|股本', p)
               and not re.search(r'页印|绩效非参数|年化约|RankIC均值约', p)]
    if numeric:
        return decision('factor', 'signal_definition', 'F_NUMERIC_CONSTRUCTION',
                        '正文给出由市场或财务输入构成的数值特征，未描述明确持仓用途。', numeric)
    risk = [p for p in passages if search(r'止损|止盈|仓位|网格|grid levels|底单|take.?profit|stop.?loss|挂单|双边报价|交易次日预测|按分数交易|统计套利|做趋势跟踪|做均值回归|定投', p)]
    if risk:
        return decision('strategy', 'strategy_component', 'S_PARTIAL_TRADING_RULE',
                        '正文描述交易方法、风险控制或订单配置；作为策略组成部分收录，缺少的执行条件不补造。', risk)
    return decision('unclassified', 'insufficient_description', 'U_NO_CLEAR_OUTPUT',
                    '正文未明确给出可辨识的交易/组合用途或信号构造，需要逐条判断。', [text])

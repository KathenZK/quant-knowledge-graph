"""Small, deterministic query planner for local reading search.

Aliases within one unit are alternatives; independently typed concepts are AND.
Unknown characters remain literal units. No language model, stemming, or silent
fallback broadens an unsuccessful query.
"""
from functools import lru_cache
import re

from quantgraph.api.web_read_model import normalize

# Keep broader families separate: reversal is not a synonym for mean reversion,
# trend is not a synonym for momentum, and EMA is not the same operator as SMA.
SEARCH_SYNONYMS = [
    ('均线','移动平均','moving average','moving_average','sma','ema','简单均线','指数均线'),
    ('简单均线','简单移动平均','simple moving average','sma'),
    ('指数均线','指数移动平均','exponential moving average','ema'),
    ('动量','momentum'), ('趋势','trend'), ('反转','reversal'),
    ('均值回归','mean reversion','mean_reversion','mean-reversion'),
    ('低波动','低波动率','low volatility','low-volatility','low_volatility'),
    ('配对','配对交易','pairs trading','pair trading'),
    ('相对强弱指标','相对强弱指数','rsi','relative strength index'),
    ('波动','波动率','volatility','realized_volatility'),
    ('布林','布林带','bollinger','bollinger bands','bollingerbands','bollinger_bands'), ('成交量','volume'),
    ('突破','breakout','channel breakout'), ('交叉','crossover','cross over','cross'),
    ('价值','value'), ('质量','quality'), ('盈利','profitability'),
    ('规模','size'), ('流动性','liquidity'), ('投资','investment'),
    ('套利','arbitrage'), ('轮动','rotation'),
    ('收盘价','close'), ('最高价','high'), ('最低价','low'), ('开盘价','open'),
    ('资金费率','funding rate','funding_rate'), ('分红','dividend'),
    ('财报','accounting','fundamental'),
]
FREQUENCIES = {
    '日线': ('daily','daily_eod'), '日频': ('daily','daily_eod'),
    'daily': ('daily','daily_eod'), 'daily_eod': ('daily','daily_eod'),
    '周线': ('weekly','weekly_eod'), '周频': ('weekly','weekly_eod'),
    'weekly': ('weekly','weekly_eod'), 'weekly_eod': ('weekly','weekly_eod'),
    '月线': ('monthly','month_end'), '月频': ('monthly','month_end'),
    'monthly': ('monthly','month_end'), 'month_end': ('monthly','month_end'),
}
DAILY_ONLY = {'只用日线','仅用日线','只用日线数据','仅用日线数据'}
IDENTIFIER = re.compile(r'(?:rsi|sma|ema|ma|roc|atr|adx|cci|std)\s*(?:\(\s*(\d+)\s*\)|(\d+))(?![a-z0-9_])')
MOMENTUM_NAME = re.compile(r'\d+\s*[-−–]\s*\d+\s+momentum(?![a-z0-9_])')
ASCII_TOKEN = re.compile(r'[a-z0-9_$]+(?:[._:%/−–-][a-z0-9_$]+)*')
HAN = re.compile(r'[\u3400-\u9fff]')


def compact_formula(text):
    return re.sub(r'\s+', '', normalize(text))


def is_formula(text):
    return bool(re.search(r'[a-z_]\w*\s*\([^)]*[,\$+*/][^)]*\)',text,re.I) or
                ('$' in text and re.search(r'[+*/]',text)))


@lru_cache(maxsize=4096)
def search_pattern(term):
    term=normalize(term)
    parameter=IDENTIFIER.fullmatch(term)
    if parameter:
        name=re.match(r'[a-z]+',term)[0];number=parameter[1] or parameter[2]
        return re.compile(r'(?<![a-z0-9_])'+name+r'\s*(?:\(\s*'+number+r'\s*\)|'+number+r'(?!\d))(?![a-z_])')
    if is_formula(term):
        return re.compile(r'\s*'.join(re.escape(c) for c in compact_formula(term)))
    pattern=re.escape(term).replace(r'\ ',r'\s+')
    if MOMENTUM_NAME.fullmatch(term):
        first,last=re.match(r'(\d+)\s*[-−–]\s*(\d+)',term).groups()
        pattern=first+r'\s*[-−–]\s*'+last+r'\s+momentum'
    # Plain indicator acronyms can match their numbered variants. A numbered
    # identifier itself cannot match a longer number (MA5 must not match MA50).
    if re.fullmatch(r'[a-z0-9_ .%−–-]+',term):
        boundary=r'(?![a-z0-9_])' if any(c.isdigit() for c in term) else r'(?![a-z_])'
        pattern=r'(?<![a-z0-9_])'+pattern+boundary
    return re.compile(pattern)


@lru_cache(maxsize=4096)
def search_anchor(term):
    """Cheap necessary substring before running the more flexible regex."""
    chunks=re.findall(r'[a-z_]+|[\u3400-\u9fff]+|\d+',normalize(term))
    return max(chunks,key=len) if chunks else term


class QueryVocabulary:
    """Built once per Catalog content change, then reused by every warm query."""
    def __init__(self, items, methods=()):
        synonyms={}
        # The later, more specific SMA/EMA groups win for those inputs; broad
        # '均线' still permits either kind without claiming their equivalence.
        for group in SEARCH_SYNONYMS:
            for term in group:
                synonyms[term]=group
        # Chinese '相对强弱' is ambiguous: users may mean the named RSI
        # indicator or a relative-strength comparison. Only that broader input
        # includes both; the explicit RSI acronym never expands to all rotation.
        synonyms['相对强弱']=('相对强弱',*synonyms['rsi'])
        self.synonyms=synonyms
        self.aliases=set()
        self.exact_names={};self.exact_formulas={}
        vocabulary=set(synonyms)|set(FREQUENCIES)|DAILY_ONLY
        for key,_,terms in methods:
            vocabulary.add(key);vocabulary.update(normalize(term) for term in terms)
        for item in items:
            if item.get('test_record'):
                continue
            eid=item['entity_id']
            for name in [item['name'],*item.get('aliases',[])]:
                normalized=normalize(name)
                if normalized:
                    self.exact_names.setdefault(normalized,set()).add(eid)
            for alias in item.get('aliases',[]):
                alias=normalize(alias)
                if 1<len(alias)<=64:
                    self.aliases.add(alias)
                    # A source alias such as 均线动量 must not hide the two
                    # ordinary concepts for all other records. Exact aliases
                    # already have their own identity/priority index above.
                    if alias in vocabulary or not any(term in alias for term in synonyms):
                        vocabulary.add(alias)
            formula=item.get('knowledge',{}).get('formula')
            if formula:
                self.exact_formulas.setdefault(compact_formula(formula),set()).add(eid)
        # Buckets avoid a full dictionary scan at every character. Longest match
        # preserves financial phrases; ties are deterministic.
        self.starts={}
        for term in vocabulary:
            self.starts.setdefault(term[0],[]).append(term)
        for terms in self.starts.values():
            terms.sort(key=lambda term:(-len(term),term))
        self._plans={}

    def plan(self, query):
        normalized=re.sub(r'\s+', ' ', normalize(query))
        if normalized in self._plans:
            return self._plans[normalized]
        units=[];constraints=[]
        if normalized.startswith(('https://','http://')):
            units=[dict(text=normalized,kind='url',alternatives=[normalized])]
        elif is_formula(normalized):
            units=[dict(text=normalized,kind='formula',alternatives=[normalized])]
        else:
            i=0
            while i<len(normalized):
                if normalized[i].isspace():
                    i+=1;continue
                start=i
                protected=MOMENTUM_NAME.match(normalized,i) or IDENTIFIER.match(normalized,i)
                if protected:
                    term=protected[0];i=protected.end();kind='identifier'
                else:
                    term=None
                    for known in self.starts.get(normalized[i],[]):
                        if normalized.startswith(known,i):
                            end=i+len(known)
                            if (known[-1].isascii() and known[-1].isalnum() and end<len(normalized)
                                and re.match(r'[a-z0-9_]',normalized[end])):
                                continue
                            term=known;i=end;break
                    if term is None:
                        ascii_token=ASCII_TOKEN.match(normalized,i)
                        if ascii_token:
                            term=ascii_token[0];i=ascii_token.end()
                        else:
                            i+=1
                            while i<len(normalized) and not normalized[i].isspace() and not ASCII_TOKEN.match(normalized,i) and not any(normalized.startswith(k,i) for k in self.starts.get(normalized[i],[])):
                                i+=1
                            term=normalized[start:i]
                        kind='literal'
                    else:
                        kind='synonym' if term in self.synonyms else 'catalog_term'
                if term in DAILY_ONLY:
                    constraints.append(dict(key='daily_ohlcv',values=[True],text=term,
                        explanation='已知日频数据，且已确认输入仅为 OHLCV；未知字段不算满足'))
                elif term in FREQUENCIES:
                    constraints.append(dict(key='frequency',values=list(FREQUENCIES[term]),text=term,
                        explanation='按明确的数据频率筛选，不把调仓频率或回看天数当数据频率'))
                else:
                    alternatives=list(self.synonyms.get(term,(term,)))
                    units.append(dict(text=term,kind=kind,alternatives=alternatives))
        plan=dict(text=query,units=units,constraints=constraints,
            expanded_terms=[u['alternatives'] for u in units],logic='AND_BETWEEN_UNITS_OR_WITHIN_SYNONYMS',
            exact_literal_precedence='完整名称、别名或原式精确相同时，保留字面匹配；自然语言条件仅用于其余结果')
        # Keep query cache bounded, including arbitrary unknown user phrases.
        if len(self._plans)>=512:
            self._plans.clear()
        self._plans[normalized]=plan
        return plan

    def exact_ids(self, query):
        return self.exact_names.get(normalize(query),set()) | self.exact_formulas.get(compact_formula(query),set())


def accepts_constraints(value, constraints):
    for constraint in constraints:
        actual=(value.get('frequency') if constraint['key']=='frequency' else
                value['knowledge']['filters'][constraint['key']])
        if actual not in constraint['values']:
            return False
    return True

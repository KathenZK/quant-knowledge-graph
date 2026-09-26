"""Reported dates are not established origins; source buckets are not equivalence."""
import re
from urllib.parse import urlsplit, urlunsplit


def canonical_url(url):
    try:
        p = urlsplit(url.strip())
        if p.scheme.lower() not in {'http', 'https'} or not p.hostname or p.username or p.password:
            return None
        # Keep query AND fragment: they may identify a strategy. No tracking guessing.
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, p.fragment))
    except ValueError:
        return None


def market_taxonomy(raw):
    rules = [('crypto', r'加密|数字货币|比特币|BTC|ETH'), ('equity', r'股票|美股|A股|股指|国家ETF'),
             ('fixed_income', r'债|固收'), ('commodity', r'商品|黄金|原油|贵金属'),
             ('fx', r'外汇|货币对'), ('multi_asset', r'多资产|混合')]
    classes = [label for label, pattern in rules if re.search(pattern, raw, re.I)]
    regions = [name for name, pattern in [('US', r'美股|美国|CRSP'), ('CN', r'A股|中国|沪|深'),
                                         ('GLOBAL', r'全球|国际|国家ETF')] if re.search(pattern, raw)]
    instruments = [name for name, pattern in [('ETF', r'ETF'), ('FUTURE', r'期货|永续'),
                                              ('SPOT', r'现货'), ('OPTION', r'期权')] if re.search(pattern, raw, re.I)]
    return {'asset_class': classes or ['unknown'], 'regions': regions, 'instruments': instruments,
            'taxonomy_status': 'MAPPED_REPORTED_SCOPE' if classes or instruments else 'REVIEW_REQUIRED'}


def provenance(row, ast):
    url = canonical_url(row['source_url']) or ''
    host = urlsplit(url).hostname or ''
    text = row['规则']
    switch = bool(re.search(r'否则\s*BIL|满仓|新标|换参|换阈', text))
    doc = host in {'chartschool.stockcharts.com', 'school.stockcharts.com', 'www.fidelity.com', 'www.incrediblecharts.com'}
    method = 'absolute-momentum' in url.lower() or 'dual-momentum-investing' in url.lower()
    if switch and (doc or method):
        return {'provenance_type': 'BOT_DERIVED', 'source_support': 'INDICATOR_DEFINITION' if doc else 'METHOD_FRAMEWORK',
                'provenance_evidence': 'GrokBot rule applies a cited definition/framework to a concrete trading variant; original source strategy not established.'}
    if host == 'github.com' and re.search(r'\.(py|ipynb|pine|r)(?:[?#]|$)', url, re.I):
        return {'provenance_type': 'SOURCE_IMPLEMENTATION', 'source_support': 'IMPLEMENTATION_REFERENCE_UNVERIFIED',
                'provenance_evidence': 'Reported URL points to implementation; code content and original-paper equivalence not verified.'}
    return {'provenance_type': 'UNKNOWN', 'source_support': 'UNVERIFIED_REFERENCE',
            'provenance_evidence': 'Citation alone cannot establish native strategy authorship or derivation.'}


def reported_family(row, ast):
    from .parser import family_key
    if ast:
        return family_key(ast)
    url = (canonical_url(row['source_url']) or '').lower()
    if url.endswith('/00d_absolute-momentum_gary_antonacci.pdf'):
        return 'absolute_momentum'
    if url.endswith('/relative-strength-index-rsi'):
        return 'indicator:rsi'
    return None

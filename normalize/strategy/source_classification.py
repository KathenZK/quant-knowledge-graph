"""URL routing hints; no URL heuristic can establish source support or rights."""
from urllib.parse import urlsplit


def classify_source(url):
    host=(urlsplit(url).hostname or '').lower()
    if host=='github.com':kind='OPEN_SOURCE_IMPLEMENTATION'
    elif host.endswith(('stockcharts.com','fidelity.com','tradingview.com')):kind='INDICATOR_DOCUMENTATION' if 'tradingview.com' not in host else 'COMMUNITY_POST'
    elif host.endswith(('arxiv.org','ssrn.com')):kind='ACADEMIC_PAPER'
    elif host.endswith(('quantpedia.com','cxoadvisory.com')):kind='SECONDARY_SUMMARY'
    elif host.endswith(('reddit.com','x.com','twitter.com','fmz.com')):kind='COMMUNITY_POST'
    else:kind='UNKNOWN'
    return {'source_type_hint':kind,'classification_basis':'URL_ROUTING_ONLY','source_evidence_level':'UNKNOWN',
       'source_support_type':'UNKNOWN','supported_rule_components':{},'unsupported_rule_components':{},'verification_status':'UNVERIFIED'}

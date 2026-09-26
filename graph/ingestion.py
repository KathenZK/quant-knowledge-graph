"""Shared conservative projection for HTTP ingestion and private corpus replay."""
from quantgraph.collectors.common import uid
from quantgraph.graph.grokbot import normalize_bundle, content_hash
from quantgraph.normalize.strategy.parser import family_key


def project_record(record, batch_id, revision, record_hash):
    raw = {'id': record.record_id, '名称': record.name, '规则': record.raw_rule,
           '市场': record.raw_market, 'source_url': record.source_url,
           '作者或机构': record.author or '', '标题': record.name,
           '提出日期': record.source_publication_date or 'UNKNOWN', '可回测': record.backtestability or ''}
    rows, concepts, templates = normalize_bundle({'rows': [raw], 'members': {'quant-master-draft.csv': b''}})
    row = rows[0]
    variant = row['variant']
    variant.update(source_sha256=record_hash, source_locator=f'grokbot:{record.record_id}:revision:{revision}',
                   ingestion_lineage={'batch_id': batch_id, 'record_id': record.record_id,
                                      'revision': revision, 'record_hash': record_hash},
                   auditable_metadata=record.audit_payload())
    links = []
    if variant['rule_ast']:
        key = family_key(variant['rule_ast'])
        links.append(dict(strategy_id=variant['strategy_id'],
                          factor_id=uid('factor-concept', 'grokbot-rule-reference:' + key),
                          variant_id=uid('factor-variant', variant['source_id'] + ':' + content_hash(variant['rule_ast'])),
                          role='signal', confidence=1.0, evidence='Explicit reference in the fully parsed rule.',
                          source=record.source_url, link_reason='PARSED_RULE_SIGNAL_REFERENCE',
                          parser_version=variant['parser_version'], attribution_status='RULE_LINK_ONLY'))
    return {**row, 'concepts': concepts, 'templates': templates, 'factor_links': links,
            'research_allowed': False, 'research_rights_status': 'REVIEW_REQUIRED',
            'review_reasons': row['review_reasons'] + ['RIGHTS_REVIEW_REQUIRED', 'EXECUTION_CONTRACT_PENDING']}

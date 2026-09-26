"""Stable source -> method -> template -> variant identities; no guessed merges."""
from quantgraph.collectors.common import uid
from quantgraph.graph.grokbot import content_hash

VERSION = 'strategy-ontology-v2'


def enrich(row):
    v = row['variant']
    ast = v.get('rule_ast')
    relationships = []
    def link(relation, left, right, evidence):
        relationships.append({'relationship_id': uid('edge', content_hash([relation, left, right])),
                              'relation': relation, 'from_id': left, 'to_id': right,
                              'evidence': evidence, 'source': v['source_url'],
                              'confidence': 1.0, 'ontology_version': VERSION})
    if v['strategy_template_id']:
        link('VARIANT_OF', v['strategy_variant_id'], v['strategy_template_id'], 'Explicit structured template slots')
        link('VARIANT_OF', v['strategy_template_id'], v['strategy_concept_id'], 'Parsed rule method family')
        # These are axes against the parameterized template, independent of which
        # sibling records happen to have been ingested before or after this row.
        v['variation_axes'] = ['PARAMETER_VARIANT', 'ASSET_VARIANT']
    link('SOURCED_FROM', v['strategy_variant_id'], v['source_id'], 'Reported source URL; authorship not verified')
    if v['provenance_type'] in {'BOT_DERIVED', 'SOURCE_DERIVED'}:
        link('DERIVED_FROM', v['strategy_variant_id'], v['source_id'], v['provenance_evidence'])
    implementations = []
    if v['provenance_type'] == 'SOURCE_IMPLEMENTATION':
        iid = uid('strategy-implementation', v['source_url'])
        implementations.append({'implementation_id': iid, 'code_url': v['source_url'],
                                'code_hash': None, 'validation_status': 'REVIEW_REQUIRED'})
        link('IMPLEMENTATION_OF', iid, v['strategy_variant_id'], 'Unverified source implementation reference')
        relationships[-1].update(confidence=0.5, validation_status='REVIEW_REQUIRED')
    links = []
    signals = {}
    def visit(node):
        if isinstance(node, dict):
            if node.get('type') == 'indicator':
                definition = {k: value for k, value in node.items() if k != 'asset'}
                signals[content_hash(definition)] = definition
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    if ast:
        visit(ast)
        if not signals:
            # No implied attribution: retain the complete reported method signal.
            definition = {k: val for k, val in ast.items() if k not in {'assets', 'risk_asset', 'safe_asset', 'costs', 'execution_timing', 'allocation'}}
            signals[content_hash(definition)] = definition
        for signature, definition in sorted(signals.items()):
            name = definition.get('name', definition.get('type'))
            factor_id = uid('factor-concept', 'rule-reference:' + name)
            factor_variant_id = uid('factor-variant', 'rule-reference:' + signature)
            links.append({'link_id': uid('strategy-factor-link', v['strategy_id'] + ':' + factor_variant_id),
                          'strategy_id': v['strategy_id'], 'factor_id': factor_id,
                          'factor_variant_id': factor_variant_id, 'variant_id': factor_variant_id,
                          'role': 'signal', 'link_reason': 'EXPLICIT_AST_REFERENCE',
                          'evidence': definition, 'source': v['source_url'], 'confidence': 1.0,
                          'parser_version': v['parser_version'], 'validation_status': 'RULE_LINK_ONLY',
                          'attribution_status': 'RULE_LINK_ONLY'})
            link('USES_FACTOR', v['strategy_variant_id'], factor_variant_id, 'Explicit AST signal reference only')
    return {**row, 'ontology_version': VERSION, 'relationships': relationships,
            'implementations': implementations, 'factor_links': links}

"""Versioned economic taxonomy; source definitions remain separate nodes."""
from collections import Counter, defaultdict
from quantgraph.collectors.common import uid
from quantgraph.graph.grokbot import content_hash
from quantgraph.normalize.taxonomy.rules import category

VERSION = 'factor-taxonomy-v2'
FAMILIES = ('momentum', 'value', 'quality', 'reversal', 'liquidity', 'volatility',
            'investment', 'profitability', 'carry', 'sentiment', 'size', 'growth', 'low_risk')
SOURCE_THEMES = {'Momentum': 'momentum', 'Value': 'value', 'Quality': 'quality',
                 'Investment': 'investment', 'Low Risk': 'low_risk', 'Size': 'size',
                 'Short-Term Reversal': 'reversal', 'Profitability': 'profitability',
                 'Liquidity': 'liquidity', 'Growth': 'growth'}


def concepts():
    return [{'canonical_factor_id': uid('factor-concept', 'economic:' + name),
             'canonical_name': name.title(), 'scope': 'ECONOMIC_TAXONOMY',
             'mapping_version': VERSION, 'formula_equivalence': False} for name in FAMILIES]


def map_records(records):
    """Only existing reviewed economic categories are routed, never name similarity.

    Alpha101/191 composite expressions need specific evidence. Missing evidence is
    an unresolved mapping, not an invented economic identity.
    """
    links, unresolved, conflicts = [], [], []
    source_counts, mapped_counts = Counter(), Counter()
    hashes = defaultdict(list)
    variants = defaultdict(list)
    for row in records:
        source = row['source_id']
        source_counts[source] += 1
        cat = row.get('category') or category(row)
        evidence = 'Reviewed source category: ' + cat
        theme = row.get('parameters', {}).get('theme')
        if source == 'jkp' and theme in SOURCE_THEMES and row.get('source_file_sha256'):
            cat = SOURCE_THEMES[theme]
            evidence = 'Source JKP theme column: ' + theme + '; snapshot ' + row['source_file_sha256']
        if source == 'aqr' and row.get('source_native_id') == 'BAB':
            cat = 'low_risk'
            evidence = 'Source-native BAB construction; category only, no equivalence to market beta'
        rid = row.get('record_id') or row['factor_variant_id']
        if cat in FAMILIES:
            mapped_counts[source] += 1
            links.append({'mapping_id': uid('factor-mapping', rid + ':' + cat), 'from_id': rid,
                          'to_id': uid('factor-concept', 'economic:' + cat), 'relation': 'RELATED_TO',
                          'confidence': 1.0, 'evidence': evidence,
                          'source': row['source_url'], 'source_id': source, 'mapping_version': VERSION,
                          'definition_sha256': content_hash({k: row.get(k) for k in (
                              'formula', 'formula_ast', 'raw_definition', 'universe', 'holding_period',
                              'rebalance', 'parameters', 'source_file_sha256', 'source_revision')}),
                          'status': 'CATEGORY_LINK_ONLY'})
            # Group only an existing source-scoped definition family. These are
            # candidates for review, never cross-source equality assertions.
            variants[(source, row.get('factor_concept', rid))].append(rid)
        else:
            unresolved.append({'record_id': rid, 'source_id': source, 'reason': 'NO_REVIEWED_ECONOMIC_MAPPING'})
        normalized = row.get('normalized_formula')
        if normalized:
            hashes[normalized].append(row)
    for group in hashes.values():
        if len({r['source_id'] for r in group}) > 1:
            conflicts.append({'record_ids': sorted(r.get('record_id', r.get('factor_variant_id')) for r in group),
                              'reason': 'CROSS_SOURCE_FORMULA_SIMILARITY_REQUIRES_SEMANTICS_AND_CONSTRUCTION_REVIEW',
                              'status': 'REVIEW_REQUIRED'})
    return {'version': VERSION, 'concepts': concepts(), 'links': links,
            'unresolved': unresolved, 'conflicts': conflicts,
            'alias_groups': [],
            'variant_groups': [{'source_id': source, 'family': family, 'record_ids': sorted(ids),
                                'relation': 'VARIANT_OF', 'status': 'REVIEW_REQUIRED'}
                               for (source, family), ids in sorted(variants.items()) if len(ids) > 1],
            'summary': {'input_records': len(records), 'mapped_records': len(links),
                        'canonical_concepts': len(FAMILIES), 'alias_groups': 0,
                        'variant_groups': sum(len(ids) > 1 for ids in variants.values()),
                        'unresolved_records': len(unresolved), 'conflict_groups': len(conflicts),
                        'same_as_merges': 0,
                        'by_source': {s: {'input': n, 'mapped': mapped_counts[s], 'unresolved': n - mapped_counts[s]}
                                      for s, n in sorted(source_counts.items())}}}


def relation_decision(left, right, *, evidence=None):
    """A review helper, never a merge operation. No evidence means RELATED_TO."""
    if not evidence or not evidence.get('reviewed_by') or not evidence.get('source'):
        return {'relation': 'RELATED_TO', 'status': 'REVIEW_REQUIRED'}
    required = ('dialect', 'normalized_formula', 'universe', 'frequency', 'holding_period',
                'rebalance', 'portfolio_construction', 'data_adjustment')
    if all(left.get(k) is not None and left.get(k) == right.get(k) for k in required):
        return {'relation': 'SAME_AS', 'status': 'CONFIRMED', 'evidence': evidence}
    requested = evidence.get('relation')
    if requested in {'ALIAS_OF', 'VARIANT_OF', 'DERIVED_FROM', 'IMPLEMENTATION_OF'}:
        return {'relation': requested, 'status': 'REVIEW_REQUIRED', 'evidence': evidence}
    return {'relation': 'RELATED_TO', 'status': 'REVIEW_REQUIRED', 'evidence': evidence}

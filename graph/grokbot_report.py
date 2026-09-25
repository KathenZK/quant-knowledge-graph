"""Allowlisted aggregate report: neither free-form corpus fields nor URLs may escape."""
import re

LIMITATIONS = [
    'Candidate records are not independent strategies.',
    'Families use supported parsed methods or explicit RSI/Absolute Momentum citation families; unresolved source buckets are not families.',
    'Shared URLs and exact-text candidates do not establish strategy equivalence.',
    'All three dates remain null until independent evidence distinguishes their meaning.',
    'Source pages and original authorship have not been independently verified.',
    'Parsed syntax is not executable: timing, adjustments, indicator semantics, costs and missing-data policies need review.',
    'All records require rights review; private curation does not grant use or redistribution rights.',
    'Legacy screens preserve reported proxy rules and data caveats, not lab reproduction or factor attribution.',
]
COUNT_FIELDS = '''raw_records normalized_records candidate_variants strategy_concepts_families templates
curated_variants curated_strategies unclassified_records factor_linked factor_links parse_success parse_failure
 definition_review_required executable execution_review_required rights_review_required exact_duplicate_groups
exact_duplicate_records family_groups_with_multiple_variants legacy_screens legacy_screens_unmatched
legacy_screens_curated public_corpus_records commercial_corpus_records'''.split()
HASH_FIELDS = ['input_sha256', 'raw_csv_sha256', 'importer_code_sha256']
DISTRIBUTIONS = {
    'provenance_distribution': {'SOURCE_NATIVE', 'SOURCE_IMPLEMENTATION', 'SOURCE_DERIVED', 'BOT_DERIVED', 'PARAMETER_VARIANT', 'MARKET_VARIANT', 'ASSET_VARIANT', 'UNKNOWN'},
    'variation_axes': {'PARAMETER_VARIANT', 'MARKET_VARIANT', 'ASSET_VARIANT'},
    'attribution_distribution': {'RULE_LINK_ONLY'},
    'license_distribution': {'UNKNOWN'},
    'rights_distribution': {'REVIEW_REQUIRED'},
    'market_taxonomy_distribution': {'commodity', 'crypto', 'equity', 'fixed_income', 'fx', 'multi_asset', 'unknown'},
    'legacy_screen_reported_buckets': {'仍有效', '已衰减', '失败', '数据不足', 'unknown'},
    'source_url_statistics': {'raw_unique', 'normalized_unique', 'source_buckets', 'invalid_records', 'shared_source_groups', 'records_in_shared_sources'},
}


def validate_public_report(report):
    expected = set(COUNT_FIELDS + HASH_FIELDS) | set(DISTRIBUTIONS) | {'report_version', 'limitations'}
    if set(report) != expected:
        raise ValueError('Unexpected aggregate report fields')
    if report['report_version'] != 'grok_strategy_import_v1' or report['limitations'] != LIMITATIONS:
        raise ValueError('Free-form text is forbidden in public corpus reports')
    for key in HASH_FIELDS:
        if not isinstance(report[key], str) or not re.fullmatch('[a-f0-9]{64}', report[key]):
            raise ValueError('Invalid report hash')
    def count(value):
        return type(value) is int and value >= 0
    if not all(count(report[k]) for k in COUNT_FIELDS):
        raise ValueError('Invalid aggregate counter')
    for key, allowed in DISTRIBUTIONS.items():
        value = report[key]
        if not isinstance(value, dict) or not set(value) <= allowed or not all(count(v) for v in value.values()):
            raise ValueError('Unsafe distribution field: ' + key)
    n = report['raw_records']
    if not (n == report['normalized_records'] == report['candidate_variants'] == report['rights_review_required']
            == report['execution_review_required'] == report['parse_success'] + report['parse_failure']):
        raise ValueError('Report conservation mismatch')
    if sum(report['provenance_distribution'].values()) != n:
        raise ValueError('Provenance conservation mismatch')
    if any(report[k] for k in ('executable', 'public_corpus_records', 'commercial_corpus_records')):
        raise ValueError('Unreviewed execution or public clearance claim')
    return True

"""Private, reproducible raw -> normalized -> curated GrokBot corpus release.

Only the aggregate report may be committed. No source is licensed by URL alone.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile

from quantgraph.collectors.common import uid
from quantgraph.collectors.grokbot.collector import read_bundle, preserve_bundle, sha256
from quantgraph.models.entities import ENTITY_MODELS, StrategyVariant, StrategyProvenance, BacktestResult
from quantgraph.normalize.strategy.parser import parse_rule, family_key, template_signature
from quantgraph.normalize.strategy.metadata import canonical_url, market_taxonomy, provenance, reported_family
from quantgraph.graph.build import write_json, manifest
from quantgraph.graph.store import write_graph
from quantgraph.graph.curate import commercial_subset
from quantgraph.graph.verify import verify_graph
from quantgraph.graph.grokbot_report import LIMITATIONS, validate_public_report

LICENSE_ID = 'grokbot:rights:unreviewed'


def stable_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def content_hash(value):
    return sha256(stable_json(value).encode())


def unknown_rights():
    return dict(license='UNKNOWN', license_id=LICENSE_ID, commercial_use='REVIEW_REQUIRED',
                redistribution_allowed='REVIEW_REQUIRED', derivative_allowed='REVIEW_REQUIRED',
                attribution_required=None, raw_data_allowed='REVIEW_REQUIRED',
                rights_status='REVIEW_REQUIRED', rights_scope='Private candidate metadata and rule references; no redistribution clearance',
                terms_url='')


def normalize_bundle(bundle):
    rows, concepts, templates = [], {}, {}
    csv_hash = sha256(bundle['members']['quant-master-draft.csv'])
    for position, raw in enumerate(bundle['rows'], 2):
        parsed = parse_rule(raw['规则'])
        ast = parsed['rule_ast']
        source_url = canonical_url(raw['source_url'])
        bucket = uid('grok-source-bucket', source_url or raw['source_url'])
        family = reported_family(raw, ast)
        concept_id = uid('strategy-concept', family) if family else None
        signature = template_signature(ast) if ast else None
        template_id = uid('strategy-template', content_hash(signature)) if ast else None
        if family:
            concepts[concept_id] = dict(strategy_concept_id=concept_id, canonical_name=family)
        if ast:
            templates[template_id] = dict(strategy_template_id=template_id, strategy_concept_id=concept_id, template_ast=signature)
        spec_hash = content_hash({'rule': raw['规则'], 'market': raw['市场'], 'source_url': raw['source_url']})
        identity = raw['id'] + ':' + spec_hash
        strategy_id = uid('strategy', 'grokbot:' + identity)
        variant = StrategyVariant(
            strategy_variant_id=uid('strategy-variant', 'grokbot:' + identity), strategy_id=strategy_id,
            strategy_concept_id=concept_id, strategy_template_id=template_id,
            source_id=uid('source', bucket), source_native_id=raw['id'], source_sha256=csv_hash,
            source_locator=f'quant-master-draft.csv:record:{position - 1}', original_rule_text=raw['规则'],
            **parsed, **provenance(raw, ast), raw_proposed_date=raw['提出日期'],
            raw_market=raw['市场'], market_taxonomy=market_taxonomy(raw['市场']),
            source_url=source_url or '', source_url_raw=raw['source_url'], source_bucket_id=bucket,
            spec_sha256=spec_hash, **unknown_rights()).model_dump(mode='json')
        reasons = []
        if not ast:
            reasons.append(parsed['parse_reason'])
        if not source_url:
            reasons.append('INVALID_SOURCE_URL')
        if variant['market_taxonomy']['taxonomy_status'] == 'REVIEW_REQUIRED':
            reasons.append('UNKNOWN_MARKET')
        rows.append({'raw_record': dict(raw), 'variant': variant,
                     'definition_admitted': not reasons, 'review_reasons': reasons,
                     'rights_review_required': True})
    from quantgraph.graph.variation import apply_observed_axes
    apply_observed_axes(rows)
    return rows, list(concepts.values()), list(templates.values())


def source_groups(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[r['variant']['source_bucket_id']].append(r['variant'])
    return [dict(source_bucket_id=k, source_url=v[0]['source_url'], record_count=len(v),
                 native_ids=sorted(x['source_native_id'] for x in v),
                 variant_ids=sorted(x['strategy_variant_id'] for x in v),
                 family_ids=sorted({x['strategy_concept_id'] for x in v if x['strategy_concept_id']}),
                 status='SHARED_CITATION_NOT_STRATEGY_EQUIVALENCE') for k, v in sorted(groups.items())]


def legacy_screens(bundle, rows):
    by_id = {r['variant']['source_native_id']: r['variant'] for r in rows}
    results, unmatched = [], []
    for screen in bundle['screens']:
        raw = screen['row']
        if raw['id'] not in by_id:
            unmatched.append(screen)
            continue
        v = by_id[raw['id']]
        bid = uid('backtest', bundle['sha256'] + ':' + screen['member'] + ':' + raw['id'])
        # Preserve supplied metric strings and all data/cost/proxy caveats without validating profitability.
        result = BacktestResult(backtest_result_id=bid, strategy_id=v['strategy_id'],
            result_kind='LEGACY_GROKBOT_SCREEN', research_project='GrokBot legacy recent performance screen',
            artifact_uri=f"grokbot-snapshot:{bundle['sha256']}/{screen['member']}#{raw['id']}",
            artifact_sha256=screen['sha256'], metrics={'reported': raw,
                'limitations': ['NOT_REPRODUCED', 'NOT_ATTRIBUTION_EVIDENCE', 'RECENT_SCREEN_ONLY',
                                'PROXY_RULE_MAY_DIFFER', 'REPORTED_SAFE_ASSET_RETURNS_MAY_BE_ZERO']},
            validation_status='LEGACY_GROKBOT_SCREEN', created_at='UNKNOWN').model_dump(mode='json')
        results.append(result)
    return results, unmatched


def curate_corpus(rows, concepts, templates, screens, bundle):
    tables = {name: [] for name in ENTITY_MODELS}
    tables.update(aliases=[], source_records=[], id_map=[])
    maps = {name: {} for name in ('sources', 'datasets', 'factor_concepts', 'factor_variants', 'source_records')}
    admitted = [r for r in rows if r['definition_admitted']]
    tables['strategy_variants'] = [deepcopy(r['variant']) for r in admitted]
    concept_ids = {v['strategy_concept_id'] for v in tables['strategy_variants']}
    template_ids = {v['strategy_template_id'] for v in tables['strategy_variants']}
    tables['strategy_concepts'] = [c for c in concepts if c['strategy_concept_id'] in concept_ids]
    tables['strategy_templates'] = [t for t in templates if t['strategy_template_id'] in template_ids]
    tables['licenses'] = [dict(**unknown_rights(), evidence_urls=[], reviewed_at='NOT_REVIEWED',
                              notes='Uploaded corpus has no source-by-source rights grant. Quarantined from public/commercial exports.')]
    edges = {}
    def edge(relation, left, ltype, right, rtype, evidence, source, status='CONFIRMED'):
        eid = uid('edge', stable_json([relation, left, right]))
        edges[eid] = dict(relationship_id=eid, relation=relation, from_id=left, from_type=ltype,
                         to_id=right, to_type=rtype, confidence=1.0, evidence=evidence, source=source, status=status)
    for r in admitted:
        v, raw = r['variant'], r['raw_record']
        sid, vid = v['strategy_id'], v['strategy_variant_id']
        source_id, ast = v['source_id'], v['rule_ast']
        source = v['source_url']
        maps['sources'][source_id] = dict(source_id=source_id, source_name='GrokBot reported citation', url=source,
            license_id=LICENSE_ID, revisions=[bundle['sha256']], collected_at='UNKNOWN', storage_policy='PRIVATE_REVIEW_REQUIRED')
        did = uid('dataset', source_id + ':' + bundle['sha256'])
        maps['datasets'][did] = dict(dataset_id=did, name='GrokBot uploaded rule candidates', source_id=source_id,
            content_type='reported_strategy_rules', revision=bundle['sha256'], license_id=LICENSE_ID, source_url=source)
        # A signal-reference factor is new, source-scoped and never SAME_AS a Qlib feature.
        signal = ast['condition'] if ast['type'] == 'threshold_switch' else {k: val for k, val in ast.items() if k not in {'execution_timing', 'price_adjustment', 'missing_data_policy', 'costs', 'allocation'}}
        key = family_key(ast)
        cid = uid('factor-concept', 'grokbot-rule-reference:' + key)
        fid = uid('factor-variant', source_id + ':' + content_hash(signal))
        rid = uid('source-record', 'grokbot-rule:' + raw['id'] + ':' + v['spec_sha256'])
        maps['factor_concepts'][cid] = dict(canonical_factor_id=cid, canonical_name='GrokBot rule signal: ' + key,
            short_id='GROK-' + content_hash(key)[:12], aliases=[], description='Rule-reference signal family; not a verified economic factor.',
            economic_logic=None, category='momentum' if 'momentum' in key else 'technical_indicator',
            scope='grokbot_rule_reference_only', created_at='UNKNOWN', updated_at='UNKNOWN')
        if fid not in maps['factor_variants']:
            maps['factor_variants'][fid] = dict(canonical_factor_id=cid, canonical_name=maps['factor_concepts'][cid]['canonical_name'],
                factor_concept=key, factor_variant_id=fid, variant_name='Reported rule signal ' + content_hash(signal)[:12], aliases=[],
                description=stable_json(signal), economic_logic=None, category=maps['factor_concepts'][cid]['category'],
                raw_formula=None, normalized_formula=None, formula_ast=None, formula_id=None, dialect=None,
                parameters={'reported_signal': signal}, required_fields=[], required_fields_status='NOT_VERIFIED',
                lookback=ast.get('lookback'), frequency=ast['schedule'], asset_class='unknown', universe=None, holding_period=None,
                rebalance=None, source_id=source_id, source_name='GrokBot reported rule signal', source_url=source,
                source_record_ids=[], source_native_ids=[], source_sha256=v['source_sha256'], source_revision=bundle['sha256'],
                source_locator='quant-master-draft.csv', paper_title=None, paper_year=None, authors=[], paper_ids=[], code_url=None,
                quality_status='CURATED_DEFINITION', semantic_status='NOT_VERIFIED', backtest_ready=False,
                issue_codes=['RULE_REFERENCE_ONLY', 'EXECUTION_CONTRACT_PENDING', 'SOURCE_NOT_INDEPENDENTLY_VERIFIED'],
                created_at='UNKNOWN', updated_at='UNKNOWN', **unknown_rights())
        factor = maps['factor_variants'][fid]
        factor['source_record_ids'].append(rid)
        factor['source_native_ids'].append(raw['id'])
        maps['source_records'][rid] = dict(record_id=rid, factor_variant_id=fid, source_id=source_id,
            source_native_id=raw['id'], source_url=source, source_locator=v['source_locator'], sha256=v['source_sha256'], dataset_id=did)
        links = dict(strategy_id=sid, factor_id=cid, variant_id=fid, role='signal', confidence=1.0,
            evidence='Explicit signal reference in parsed uploaded rule; no empirical attribution.', source=source,
            attribution_status='RULE_LINK_ONLY', backtest_result_id=None,
            link_reason='PARSED_RULE_SIGNAL_REFERENCE', parser_version=v['parser_version'])
        tables['strategy_factor'].append(links)
        related_results = [b['backtest_result_id'] for b in screens if b['strategy_id'] == sid]
        tables['strategies'].append(dict(strategy_id=sid, canonical_name=raw['名称'], description=raw['规则'],
            factor_ids=[cid], source=[{'source_id': source_id, 'url': source, 'native_id': raw['id'], 'sha256': v['source_sha256']}],
            original_backtest=related_results, external_namespace='grokbot', external_id=raw['id'],
            spec_sha256=v['spec_sha256'], status='CURATED_RULE_SYNTAX_PRIVATE_REVIEW_REQUIRED',
            asset_class=v['market_taxonomy']['asset_class'], frequency=ast['schedule'], created_at='UNKNOWN', updated_at='UNKNOWN'))
        edge('VARIANT_OF', vid, 'StrategyVariant', v['strategy_template_id'], 'StrategyTemplate', 'Parsed template slots; not independent profitability.', source)
        edge('VARIANT_OF', v['strategy_template_id'], 'StrategyTemplate', v['strategy_concept_id'], 'StrategyConcept', 'Explicit method family; not SAME_AS.', source)
        edge('IMPLEMENTATION_OF', vid, 'StrategyVariant', sid, 'Strategy', 'Compatibility projection of this concrete rule candidate.', source)
        edge('SOURCED_FROM', vid, 'StrategyVariant', source_id, 'Source', 'Citation retained from uploaded corpus.', source)
        if v['provenance_type'] == 'BOT_DERIVED':
            edge('DERIVED_FROM', vid, 'StrategyVariant', source_id, 'Source', v['provenance_evidence'], source, 'REVIEW_REQUIRED')
        edge('USES_FACTOR', sid, 'Strategy', fid, 'FactorVariant', links['evidence'], source)
        edge('VARIANT_OF', fid, 'FactorVariant', cid, 'FactorConcept', 'Source-scoped rule-reference signal.', source)
        edge('SOURCED_FROM', fid, 'FactorVariant', source_id, 'Source', v['source_locator'], source)
    strategy_ids = {s['strategy_id'] for s in tables['strategies']}
    tables['backtest_results'] = [b for b in screens if b['strategy_id'] in strategy_ids]
    for name, data in maps.items():
        tables[name] = list(data.values())
    tables['relationships'] = list(edges.values())
    for name, model in ENTITY_MODELS.items():
        tables[name] = [model.model_validate(r).model_dump(mode='json') for r in tables[name]]
    return tables


def aggregate_report(bundle, rows, concepts, templates, groups, screens, unmatched, tables):
    variants = [r['variant'] for r in rows]
    duplicates = Counter(v['spec_sha256'] for v in variants)
    family_members = Counter(v['strategy_concept_id'] for v in variants if v['strategy_concept_id'])
    raw_urls = {v['source_url_raw'] for v in variants}
    return dict(report_version='grok_strategy_import_v1', input_sha256=bundle['sha256'],
        importer_code_sha256=importer_digest(),
        raw_csv_sha256=sha256(bundle['members']['quant-master-draft.csv']), raw_records=len(bundle['rows']),
        normalized_records=len(rows), candidate_variants=len(variants),
        strategy_concepts_families=len(concepts), templates=len(templates),
        curated_variants=len(tables['strategy_variants']), curated_strategies=len(tables['strategies']),
        unclassified_records=sum(v['strategy_concept_id'] is None for v in variants),
        provenance_distribution={p.value: sum(v['provenance_type'] == p.value for v in variants) for p in StrategyProvenance},
        variation_axes=dict(Counter(a for v in variants for a in v['variation_axes'])),
        factor_linked=len({x['strategy_id'] for x in tables['strategy_factor']}), factor_links=len(tables['strategy_factor']),
        attribution_distribution=dict(Counter(x['attribution_status'] for x in tables['strategy_factor'])),
        parse_success=sum(v['parse_status'] == 'PARSED' for v in variants),
        parse_failure=sum(v['parse_status'] == 'REVIEW' for v in variants),
        definition_review_required=sum(not r['definition_admitted'] for r in rows),
        executable=0, execution_review_required=len(rows), rights_review_required=len(rows),
        exact_duplicate_groups=sum(n > 1 for n in duplicates.values()),
        exact_duplicate_records=sum(n - 1 for n in duplicates.values()),
        family_groups_with_multiple_variants=sum(n > 1 for n in family_members.values()),
        source_url_statistics=dict(raw_unique=len(raw_urls), normalized_unique=len({v['source_url'] for v in variants if v['source_url']}),
            source_buckets=len(groups), invalid_records=sum(not v['source_url'] for v in variants),
            shared_source_groups=sum(g['record_count'] > 1 for g in groups),
            records_in_shared_sources=sum(g['record_count'] for g in groups if g['record_count'] > 1)),
        license_distribution=dict(Counter(v['license'] for v in variants)),
        rights_distribution=dict(Counter(v['rights_status'] for v in variants)),
        market_taxonomy_distribution=dict(Counter(a for v in variants for a in v['market_taxonomy']['asset_class'])),
        legacy_screens=len(screens), legacy_screens_unmatched=len(unmatched),
        legacy_screens_curated=len(tables['backtest_results']),
        legacy_screen_reported_buckets=dict(Counter(b['metrics']['reported'].get('bucket') if b['metrics']['reported'].get('bucket') in {'仍有效', '已衰减', '失败', '数据不足'} else 'unknown' for b in screens)),
        public_corpus_records=0, commercial_corpus_records=0,
        limitations=LIMITATIONS)


def write_jsonl(path, rows):
    path.write_text(''.join(stable_json(r) + '\n' for r in rows))


def report_markdown(report):
    validate_public_report(report)
    lines = ['# GrokBot Strategy Corpus V1 import audit', '',
             'Aggregate-only report. Complete rules, source lists and legacy results remain private.', '',
             '| Measure | Count |', '|---|---:|']
    for key in ('raw_records', 'normalized_records', 'candidate_variants', 'strategy_concepts_families', 'templates',
                'curated_variants', 'unclassified_records', 'factor_linked', 'parse_success', 'parse_failure',
                'executable', 'execution_review_required', 'rights_review_required', 'exact_duplicate_groups',
                'legacy_screens', 'legacy_screens_curated', 'legacy_screens_unmatched', 'public_corpus_records'):
        lines.append(f'| {key} | {report[key]} |')
    for label in ('provenance_distribution', 'variation_axes', 'source_url_statistics', 'license_distribution', 'rights_distribution', 'attribution_distribution'):
        lines.extend(['', f'## {label}', '', '```json', json.dumps(report[label], indent=2, ensure_ascii=False, sort_keys=True), '```'])
    lines.extend(['', '## Scope and limitations', ''] + ['- ' + s for s in report['limitations']])
    lines.extend(['', '## Reproduction', '', f"Input archive SHA-256: `{report['input_sha256']}`.",
                  f"Raw CSV SHA-256: `{report['raw_csv_sha256']}`.", '',
                  '`uv run quantgraph import-grokbot /private/path/input.tar.gz`',
                  '`uv run quantgraph verify-grokbot`', '',
                  'The importer checks record conservation, raw bytes, typed models, graph references and commercial isolation.',
                  'Only this Markdown and its aggregate JSON are public; neither file is evidence of strategy profitability.'])
    return '\n'.join(lines) + '\n'


def importer_digest():
    import quantgraph.collectors.grokbot.collector as collector
    import quantgraph.normalize.strategy.parser as parser
    import quantgraph.normalize.strategy.metadata as metadata
    import quantgraph.models.entities as entities
    import quantgraph.graph.grokbot_report as reporting
    paths = [Path(__file__), Path(collector.__file__), Path(parser.__file__), Path(metadata.__file__), Path(entities.__file__), Path(reporting.__file__)]
    return content_hash({p.name: sha256(p.read_bytes()) for p in paths})


def import_grokbot(root, archive):
    root = Path(root).resolve()
    lock = root / 'datasets/.grokbot-import.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError('Another GrokBot import holds the lock')
    try:
        return _import_grokbot(root, archive)
    finally:
        lock.rmdir()


def _import_grokbot(root, archive):
    root = Path(root).resolve()
    bundle = read_bundle(archive)
    raw_path = preserve_bundle(root, bundle)
    rows, concepts, templates = normalize_bundle(bundle)
    groups = source_groups(rows)
    screens, unmatched = legacy_screens(bundle, rows)
    tables = curate_corpus(rows, concepts, templates, screens, bundle)
    report = aggregate_report(bundle, rows, concepts, templates, groups, screens, unmatched, tables)
    validate_public_report(report)
    normalized = root / 'datasets/normalized/grokbot' / bundle['sha256'] / report['importer_code_sha256']
    normalized.mkdir(parents=True, exist_ok=True)
    write_jsonl(normalized / 'records.jsonl', rows)
    write_json(normalized / 'source_groups.json', groups)
    write_jsonl(normalized / 'legacy_screens.jsonl', screens)
    write_json(normalized / 'unmatched_screens.json', unmatched)
    write_json(normalized / 'review_queue.json', [dict(native_id=r['variant']['source_native_id'], reasons=r['review_reasons']) for r in rows if r['review_reasons']])
    parent = root / 'datasets/curated/grokbot'
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.build-', dir=parent))
    try:
        write_graph(staging, tables)
        write_graph(staging / 'commercial', commercial_subset(tables))
        verify_graph(staging)
        verify_graph(staging / 'commercial', commercial=True)
        write_json(staging / 'release.json', report)
        write_json(staging / 'normalized_manifest.json', manifest(normalized))
        hashes = manifest(staging)
        release_id = content_hash(hashes)[:20]
        write_json(staging / 'manifest.json', hashes)
        target = parent / 'releases' / release_id
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            if manifest(target) != hashes:
                raise ValueError('Immutable corpus release was modified')
            shutil.rmtree(staging)
        else:
            staging.rename(target)
        result = verify_grokbot(root, release_id=release_id)
        pointer = parent / '.CURRENT-next'
        pointer.write_text(release_id + '\n')
        os.replace(pointer, parent / 'CURRENT')
        if sha256(raw_path.read_bytes()) != bundle['sha256']:
            raise ValueError('Raw snapshot changed during import')
        write_json(root / 'reports/grok_strategy_import_v1.json', report)
        (root / 'reports/grok_strategy_import_v1.md').write_text(report_markdown(report))
        return {'status': 'PASS', 'release_id': release_id, 'report': report, 'verification': result}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_grokbot(root, *, release_id=None):
    root = Path(root)
    parent = root / 'datasets/curated/grokbot'
    release_id = release_id or (parent / 'CURRENT').read_text().strip()
    if len(release_id) != 20 or any(c not in '0123456789abcdef' for c in release_id):
        raise ValueError('Invalid corpus release pointer')
    release = parent / 'releases' / release_id
    hashes = json.loads((release / 'manifest.json').read_text())
    if manifest(release) != hashes or content_hash(hashes)[:20] != release_id:
        raise ValueError('Corpus release checksum mismatch')
    report = json.loads((release / 'release.json').read_text())
    archive = root / 'datasets/raw/sources/grokbot' / report['input_sha256'] / 'input.tar.gz'
    bundle = read_bundle(archive)
    if bundle['sha256'] != report['input_sha256']:
        raise ValueError('Raw checksum mismatch')
    normalized = root / 'datasets/normalized/grokbot' / report['input_sha256'] / report['importer_code_sha256']
    if manifest(normalized) != json.loads((release / 'normalized_manifest.json').read_text()):
        raise ValueError('Normalized checksum mismatch')
    rows = [json.loads(line) for line in (normalized / 'records.jsonl').read_text().splitlines()]
    if [r['raw_record'] for r in rows] != bundle['rows'] or len(rows) != report['raw_records']:
        raise ValueError('Record conservation/raw preservation failed')
    for r in rows:
        StrategyVariant.model_validate(r['variant'])
        if r['variant']['original_rule_text'] != r['raw_record']['规则']:
            raise ValueError('Original rule changed')
    expected_rows, concepts, templates = normalize_bundle(bundle)
    if rows != expected_rows:
        raise ValueError('Normalized rules differ from deterministic replay')
    screens, unmatched = legacy_screens(bundle, rows)
    tables = curate_corpus(rows, concepts, templates, screens, bundle)
    expected = aggregate_report(bundle, rows, concepts, templates, source_groups(rows), screens, unmatched, tables)
    if report != expected:
        raise ValueError('Audit counters differ from replay')
    # Compare persisted typed graph with the deterministic projection, not just counters.
    for name, items in tables.items():
        saved = [json.loads(line) for line in (release / (name + '.jsonl')).read_text().splitlines()]
        model = ENTITY_MODELS.get(name)
        if model:
            items = [model.model_validate(r).model_dump(mode='json') for r in items]
        if sorted(map(stable_json, saved)) != sorted(map(stable_json, items)):
            raise ValueError('Curated replay mismatch: ' + name)
    private = verify_graph(release)
    commercial = verify_graph(release / 'commercial', commercial=True)
    if any(commercial.values()):
        raise ValueError('Private GrokBot content leaked to commercial profile')
    return {'status': 'PASS', 'raw_records': len(rows), 'curated_variants': private['strategy_variants'],
            'commercial_records': 0, 'raw_unchanged': True, 'deterministic_replay': True}

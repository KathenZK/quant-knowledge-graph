"""Validate reviewed knowledge metadata and stage a bounded Lab evidence import.

No network, backtest, live database mutation, Site upload or deployment occurs.
Metadata uses private_intake's existing revision-bound review overlay. Research
projections use the existing detail/compare shape but are not corpus imports.
"""
import argparse
from copy import deepcopy
import csv
from datetime import date, timedelta
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from jsonschema import Draft202012Validator
from quantgraph.graph.corpus_research import _finite, _loads, _read_file

RESERVE = 5 * 1024**3


def publication_screen(values):
    """Conservative field screen; report only field names/codes, never secret values.

    A clean screen still requires review of every field before public publication.
    """
    patterns = {
        'CREDENTIAL_OR_SIGNED_URL': r'(?i)(?:\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|authorization|signature|credential|sig|key)|[?&]x-(?:amz|goog)-(?:signature|credential|security-token))\s*[=:]|\bBearer\s+\S+|\b(?:ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})',
        'PRIVATE_LIBRARY_OR_APP_REFERENCE': r'(?i)\b(?:libfile_[a-z0-9]+|file_[0-9a-f]{16,}|appgprj_[a-z0-9]+)|sediment://|app://',
        'LOCAL_PATH': r'(?i)(?:^|[\s\"\'(:])/(?:workspace|home|Users|tmp|private|mnt|root|Volumes)/|\b[A-Z]:\\|file://',
        'PRIVATE_ANNOTATION': r'(?i)private[-_ ]only|confidential|私人批注|私密|个人批注|个人备注|我的备注|不要公开|不公开|仅供私人',
        'URL_USERINFO': r'https?://[^\s/]+:[^\s/]+@',
    }
    hits = [(field, code) for field, value in values.items() for code, pattern in patterns.items()
            if re.search(pattern, str(value))]
    return dict(status='PRIVATE_ONLY_BLOCKED' if hits else 'FIELD_REVIEW_REQUIRED',
                sensitive_fields=sorted({field for field, _ in hits}),
                reason_codes=sorted({code for _, code in hits}), all_fields_reviewed=False)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_below(root, name, limit=8 * 1024**2):
    if type(limit) is not int or not 1 <= limit <= 64 * 1024**2:
        raise ValueError('Evidence read limit must be bounded at 64 MiB')
    if not isinstance(name, str) or '\\' in name or any(p in {'', '.', '..'} for p in name.split('/')):
        raise ValueError('Unsafe relative evidence path')
    path = Path(root)
    if path.is_symlink() or not path.is_dir():
        raise ValueError('Input root must be an existing non-symlink directory')
    for part in name.split('/'):
        path = path / part
        if path.is_symlink():
            raise ValueError('Evidence cannot traverse symlinks')
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('Evidence escapes input root')
    return _read_file(path, limit)


def validate(root):
    root = Path(root)
    schema = _loads(read_below(root, 'schema.json'))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    source_validator = None
    index = _loads(read_below(root, 'index.json'))
    if index.get('schema_version') != 'quantgraph-metadata-index/v1':
        raise ValueError('Unsupported metadata index')
    records, seen, paths = [], set(), set()
    for ref in index['records']:
        raw = read_below(root, ref['path'])
        if digest(raw) != ref['sha256'] or len(raw) != ref['bytes']:
            raise ValueError('Metadata index digest mismatch')
        record = _loads(raw)
        if record.get('entity_type') == 'source_record':
            if source_validator is None:
                source_schema = _loads(read_below(root, 'source-record.schema.json'))
                Draft202012Validator.check_schema(source_schema)
                source_validator = Draft202012Validator(source_schema)
            source_validator.validate(record)
            values = {k: v['value'] for k, v in record['reported_fields'].items()}
            row_hash = digest(json.dumps(values, ensure_ascii=False, sort_keys=True,
                                        separators=(',', ':'), allow_nan=False).encode())
            if (values['id'] != record['record_id'] or row_hash != record['provenance']['row_sha256']
                    or digest(values['规则'].encode()) != record['provenance']['rule_sha256']):
                raise ValueError('Source record fields do not reconstruct the pinned CSV row')
            screened_values = {**values, 'classification_reason': record['classification']['reason'],
                'classification_evidence': json.dumps(record['classification']['evidence'], ensure_ascii=False)}
            if (record['publication']['status'] == 'PRIVATE_ONLY_BLOCKED'
                    or publication_screen(screened_values)['status'] == 'PRIVATE_ONLY_BLOCKED'):
                raise ValueError('Private-only source record cannot enter public-review metadata')
        else:
            validator.validate(record)
        identity = (record['identity_namespace'], record['entity_type'], record['record_id'])
        folder = dict(strategy='strategies', factor='factors', source_record='source-records')[record['entity_type']]
        expected = f"{folder}/{record['record_id']}.json"
        # A source namespace directory permits identical native IDs from distinct
        # upstreams in future batches; legacy pinned paths remain unchanged.
        namespaced = f"{folder}/{digest(record['identity_namespace'].encode())[:24]}/{record['record_id']}.json"
        if ref['path'] not in {expected, namespaced} or identity in seen or ref['path'] in paths:
            raise ValueError('Metadata filename, type or stable identity conflicts')
        if record['native_source_id'] != record['record_id']:
            raise ValueError('Original stable ID must not be renumbered')
        if any(ref[k] != record[k] for k in ['record_id', 'entity_type', 'identity_namespace']):
            raise ValueError('Metadata index identity differs from record')
        source_ids = [s['id'] for s in record.get('sources', [])]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError('Duplicate source reference')
        artifacts = (record.get('lab') or {}).get('artifacts', {})
        evidence_ids = set(source_ids) | {'lab:' + role for role in artifacts}
        if record.get('catalog_origin'):
            evidence_ids.add('catalog-row')
        for field in (record.get('strategy_fields') or record.get('factor_fields') or {}).values():
            if not set(field['evidence']) <= evidence_ids:
                raise ValueError('Field evidence reference does not resolve')
            if field['status'] != 'MISSING' and not field['evidence']:
                raise ValueError('Asserted metadata field requires evidence')
        seen.add(identity); paths.add(ref['path']); records.append(record)
    actual = {str(p.relative_to(root)) for kind in ['strategies', 'factors', 'source-records']
              for p in (root / kind).rglob('*.json')}
    if actual != paths:
        raise ValueError('Metadata index does not cover exactly the numbered records')
    return records


def verified_blobs(record, lab_root):
    """Copy only explicitly reviewed Lab publication entries, with pinned byte hashes."""
    refs = record['lab']['artifacts']
    prefix = 'research/public-strategies/' + record['record_id'] + '/'
    blobs = {}
    for role, ref in refs.items():
        if not ref['path'].startswith(prefix):
            raise ValueError('Lab evidence belongs to a different stable ID')
        expected_url = ('https://github.com/' + record['lab']['repository'] + '/blob/'
                        + record['lab']['commit'] + '/' + ref['path'])
        if ref['url'] != expected_url:
            raise ValueError('Lab artifact URL must pin the same commit and path')
        raw = read_below(lab_root, ref['path'])
        if digest(raw) != ref['sha256'] or len(raw) != ref['bytes']:
            raise ValueError('Frozen Lab artifact digest or size mismatch: ' + role)
        blobs[role] = raw
    publication = _loads(blobs['publication_manifest'])
    if publication['id'] != record['record_id'] or refs['publication_manifest']['path'] != prefix + 'publication-manifest.json':
        raise ValueError('Wrong publication manifest identity')
    for role, ref in refs.items():
        if role == 'publication_manifest':
            continue  # Self-excluded manifest is pinned by reviewed Graph metadata.
        allowed = publication['public_allowlist'].get(ref['path'][len(prefix):])
        if allowed != {'sha256': ref['sha256'], 'bytes': ref['bytes']}:
            raise ValueError('Lab artifact is not in the reviewed publication allowlist: ' + role)
    source_manifest = _loads(blobs['source_manifest'])
    declared_sources = source_manifest.get('files') or source_manifest.get('retrieval_files') or []
    if any(not any(s['sha256'] == item['sha256'] and s['revision'] in item.get('url', '')
                   for item in declared_sources) for s in record['sources']):
        raise ValueError('Source hash/revision is not declared by frozen Lab source manifest')
    return blobs


def read_bindings(catalog_path, expected_sha256, records):
    """Read a pinned closed SQLite snapshot; never instantiate a creating repository."""
    path = Path(catalog_path)
    raw = _read_file(path, 512 * 1024**2)
    if digest(raw) != expected_sha256:
        raise ValueError('Catalog snapshot digest mismatch')
    if any(path.with_name(path.name + suffix).exists() for suffix in ['-wal', '-shm']):
        raise ValueError('Use a closed consistent catalog snapshot without WAL/SHM')
    bindings = {}
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
        con.row_factory = sqlite3.Row
        candidates = [dict(r) for r in con.execute(
            'SELECT entity_id,kind,definition_revision,payload FROM catalog_items WHERE active=1')]
        for record in records:
            kinds = {'strategy'} if record['entity_type'] == 'strategy' else {'factor', 'source'}
            rows = [r for r in candidates if r['kind'] in kinds and record['record_id'] in
                    _loads(r['payload']).get('source_native_ids', [])]
            if len(rows) != 1:
                raise ValueError('Expected one current Catalog identity for ' + record['record_id'])
            row = rows[0]
            bindings[record['record_id']] = {k: row[k] for k in ['entity_id', 'kind', 'definition_revision']}
    if path.read_bytes() != raw:
        raise ValueError('Catalog snapshot changed during binding')
    return bindings


def card(record, binding=None):
    fields = record.get('strategy_fields') or {}
    mapped = {'assets': 'asset', 'universe': 'universe', 'signal': 'signal',
              'entry': 'entry', 'exit': 'exit', 'position': 'position',
              'risk': 'risk', 'cost': 'cost', 'execution_time': 'fill_timing',
              'timeframe': 'timeframe'}
    primary = record['sources'][0]
    relation = dict(type='source_curation_overlay_for', id=record['record_id'],
                    binding_mode='EXACT_CURRENT_REVISION',
                    expected_entity_id=(binding or {}).get('entity_id'),
                    expected_definition_revision=(binding or {}).get('definition_revision'))
    return dict(record_id=record['record_id'], native_source_id=record['native_source_id'],
                entity_type=record['entity_type'], name=record['name'], one_line=record['one_line'],
                source_url=primary['url'], source_revision=primary['revision'], source_sha256=primary['sha256'],
                relation=relation, admission_status='SOURCE_REVIEW_NOT_STRICT_REPRODUCTION',
                field_evidence={mapped[k]: dict(value=v['text'] if v['status'] != 'MISSING' else None,
                    verification_status=v['status'], origin=v['status'], source_evidence_refs=v['evidence'])
                    for k, v in fields.items()},
                assets_entry_exit={mapped[k]: v['text'] for k, v in fields.items()},
                economic_rationale=dict(summary_zh=record['economic_basis']['hypothesis'],
                                        evidence_type='RESEARCH_HYPOTHESIS_NOT_PROVEN'),
                definition_sources=[dict(url=s['url'], locator=s['locator'], supports=s['supports'])
                                    for s in record['sources']],
                blocked_reasons=record['missing_information'],
                evidence_links=[dict(url=v['url'], source_sha256=v['sha256'],
                                     support_scope='Frozen Lab ' + role)
                                for role, v in (record.get('lab') or {}).get('artifacts', {}).items()])


def period(metric):
    return dict(start=metric['start'][:10], end=(date.fromisoformat(metric['end'][:10]) - timedelta(days=1)).isoformat(),
                observations=metric['daily_observations'], total_return=metric['total_return'],
                cagr=metric['annualized_return'], sharpe=metric['sharpe'],
                max_drawdown=-metric['max_drawdown'],
                max_drawdown_basis='original unsampled 4h close equity; positive Lab magnitude mapped to negative Graph return',
                oos_claim=False)


def project(record, blobs):
    source = _loads(blobs['graph_record'])
    if source['id'] != record['record_id']:
        raise ValueError('Lab record identity mismatch')
    projected = deepcopy(source)
    projected.update(coverage_history=[], projection_status='STAGED_NOT_IMPORTED',
                     definition_revision_bound=False)
    summary, spec, manifest = (_loads(blobs[k]) for k in ['summary', 'spec', 'result_manifest'])
    _finite(summary)
    if any(v[k] != record['record_id'] for v, k in [(summary, 'id'), (spec, 'record_id'), (manifest, 'id')]):
        raise ValueError('Lab summary/spec/manifest identity mismatch')
    if source['tested_variants'] == 0:
        if (source['implementations'] or source['related_results'] or summary['market_replay_runs'] != 0
                or summary['tested_strategy_configurations'] != 0 or summary['tested_buyhold_controls'] != 0
                or manifest['state'] != 'DATA_BLOCKED' or manifest['market_replay_runs'] != 0
                or manifest['planned_spec_sha256'] != digest(blobs['spec'])
                or record['lab']['status'] != 'DATA_BLOCKED'
                or any(record['lab']['counts'].values())):
            raise ValueError('Blocked record cannot contain a result')
        return projected, None
    ref = source['related_results'][0]
    if (len(source['related_results']) != 1 or source['tested_variants'] != 1
            or summary['id'] != source['id'] or summary['origin_run_id'] != ref['origin_run_id']
            or summary['variant_id'] != ref['variant_id'] or summary['fidelity_class'] != 'HYPOTHESIS'
            or digest(blobs['spec']) != ref['protocol_sha256']
            or digest(blobs['result_manifest']) != ref['manifest_sha256']
            or manifest['protocol_sha256'] != digest(blobs['spec'])
            or summary['protocol_sha256'] != digest(blobs['spec'])
            or manifest['source_manifest_sha256'] != digest(blobs['source_manifest'])
            or manifest['input_sha256'] != spec['input']['sha256']
            or summary['input_sha256'] != spec['input']['sha256']
            or summary['strategy_configurations'] != record['lab']['counts']['strategy_configurations']
            or summary['control_configurations'] != record['lab']['counts']['controls']
            or record['lab']['status'] != 'HYPOTHESIS_DIAGNOSTIC'):
        raise ValueError('Frozen result identities or protocol do not reconcile')
    for role, name in [('summary', 'summary.json'), ('trades', 'base-trades.csv')]:
        if manifest['files'][name] != {'sha256': digest(blobs[role]), 'bytes': len(blobs[role])}:
            raise ValueError('Retained result does not match original result manifest')
    projection = _loads(blobs['curve_projection'])
    if (projection['status'] != 'PASS_FIELD_PRESERVING_PROJECTION'
            or projection['public_projection_sha256'] != digest(blobs['daily_nav'])
            or projection['source_daily_ledger_sha256'] != manifest['files']['base-daily-nav.csv']['sha256']
            or projection['source_daily_ledger_sha256'] != manifest['files']['base-nav-light.csv']['sha256']
            or projection['source_daily_independent_validation_sha256'] != digest(blobs['independent_validation'])
            or manifest['checks']['independent'] != digest(blobs['independent_validation'])):
        raise ValueError('Public curve projection does not link to original frozen daily ledger')
    metrics = summary['results']['base']['metrics']
    rows = list(csv.DictReader(io.StringIO(blobs['daily_nav'].decode())))
    if (len(rows) != metrics['daily_observations'] or len(rows) != projection['rows']
            or len({r['date'] for r in rows}) != len(rows)
            or list(rows[0]) != projection['columns']):
        raise ValueError('Daily curve count/dates differ from retained summary')
    peak, previous, curve = 1.0, None, []
    for r in rows:
        nav = float(r['nav'])
        current = date.fromisoformat(r['date'])
        if not math.isfinite(nav) or nav <= 0 or (previous and current != previous + timedelta(days=1)):
            raise ValueError('Daily curve must be positive finite and strictly chronological')
        if not math.isclose(float(r['equity']) / spec['execution']['initial_cash'], nav, rel_tol=1e-11):
            raise ValueError('Daily equity and normalized NAV differ')
        peak = max(peak, nav); previous = current
        curve.append(dict(date=r['date'], equity=nav, drawdown=nav / peak - 1))
    if not math.isclose(curve[-1]['equity'] - 1, metrics['total_return'], rel_tol=1e-10):
        raise ValueError('Curve terminal return differs from original result')
    if rows[0]['date'] != metrics['start'][:10] or rows[-1]['date'] != period(metrics)['end']:
        raise ValueError('Public curve dates differ from original evaluation')
    trades = list(csv.DictReader(io.StringIO(blobs['trades'].decode())))
    if len(trades) != metrics['trades']:
        raise ValueError('Retained fill count differs from summary')
    result = dict(run_id=ref['origin_run_id'], origin_run_id=ref['origin_run_id'], id=source['id'],
        variant_id=ref['variant_id'], name=source['name'], family=source['families'][0],
        fidelity_class='HYPOTHESIS', fidelity_reason=source['reason'],
        metrics=dict(periods={'full': period(metrics)},
            same_instrument_benchmark={'full': period(summary['results']['buyhold']['metrics'])},
            cost_sensitivity={k: {'full': period(summary['results'][k]['metrics'])} for k in ['fee0', 'fee20']},
            additional_native_bar_lag={'full': period(summary['results']['delay2']['metrics'])},
            original_lab_summary=summary),
        spec=dict(source_url=record['sources'][0]['url'], assumptions=record['missing_information'],
                  params=spec['parameters'], original_lab_spec=spec), audit=source['audit'], curve=curve,
        curve_meta=dict(observations=len(curve), total_observations=len(curve), returned_points=len(curve),
                        sampling='all retained UTC daily closing NAV; not intraday equity', benchmark_curve_available=False),
        lineage=dict(manifest_sha256=ref['manifest_sha256'], protocol_sha256=ref['protocol_sha256'],
                     lab_commit=record['lab']['commit'], definition_revision_bound=False,
                     publication_manifest_sha256=digest(blobs['publication_manifest']),
                     public_curve_projection=projection,
                     manifest_kind='LAB_ORIGIN_RESULT_MANIFEST_NOT_GRAPH_COLLECTION',
                     new_execution_trials=0, input_retrieved_or_backtested_here=False),
        limitations=record['missing_information'] + ['Staged projection only; active Catalog binding and additive Site acceptance remain required.',
                     'Four strategy configurations are one strategy ID; only the baseline has a retained public curve.',
                     'Daily display drawdown is not the original unsampled 4h maximum drawdown.'])
    return projected, result


def merge_record(existing, addition):
    """Append result references without overwriting an active definition or notes."""
    if existing.get('id') != addition.get('id'):
        raise ValueError('Cannot merge different stable IDs')
    out = deepcopy(existing)
    previous_count = out.get('tested_variants', 0)
    added_results = 0
    for key in ['related_results', 'implementations']:
        rows = out.setdefault(key, [])
        for new in addition.get(key, []):
            identity = (new.get('origin_run_id'), new.get('variant_id'))
            if not all(isinstance(v, str) and v for v in identity):
                raise ValueError('New result needs immutable origin run and variant identity')
            found = [r for r in rows if (r.get('origin_run_id'), r.get('variant_id')) == identity]
            if found and found[0] != new:
                raise ValueError('Existing immutable result reference conflicts')
            if not found:
                rows.append(deepcopy(new))
                added_results += key == 'related_results'
    out['tested_variants'] = max(previous_count + added_results, len(out.get('related_results', [])))
    out['families'] = sorted(set(out.get('families', [])) | set(addition.get('families', [])))
    candidate = {k: deepcopy(addition[k]) for k in ['status', 'reason', 'audit']}
    candidates = out.setdefault('lab_import_candidates', [])
    if candidate not in candidates:
        candidates.append(candidate)
    return out


def prepare(metadata_root, lab_root, output, catalog=None, catalog_sha256=None):
    # The knowledge catalog may grow; this replay projection remains a fixed two-ID pilot.
    records = [r for r in validate(metadata_root) if r['identity_namespace'] == 'grokbot'
               and r['entity_type'] == 'strategy' and r['record_id'] in {'M0256', 'M0259'}]
    records.sort(key=lambda r: r['record_id'])
    if len(records) != 2:
        raise ValueError('This bounded pilot requires M0256 and M0259; no batch expansion')
    output = Path(output)
    if output.exists():
        raise ValueError('Use a new immutable output directory')
    if shutil.disk_usage(output.parent).free < RESERVE + 64 * 1024**2:
        raise ValueError('Five GiB disk reserve required')
    bindings = read_bindings(catalog, catalog_sha256, records) if catalog else {}
    files, counts = {}, {'strategy_ids': 2, 'replayed_ids': 1, 'blocked_ids': 1,
                        'strategy_configurations': 4, 'controls': 1, 'strict_reproductions': 0, 'new_trials': 0}
    for record in records:
        blobs = verified_blobs(record, lab_root)
        for role, raw in blobs.items():
            ref = record['lab']['artifacts'][role]
            files[f"evidence/{record['record_id']}/{role}" + Path(ref['path']).suffix] = raw
        row, detail = project(record, blobs)
        files[f"records/{record['record_id']}.json"] = encoded(row)
        if detail:
            key = digest((detail['run_id'] + '\n' + detail['variant_id']).encode())[:24]
            files[f'implementations/{key}.json.gz'] = gzip.compress(encoded(detail), mtime=0)
    cards = [card(r, bindings.get(r['record_id'])) for r in records]
    files['strategy-cards.json'] = encoded(cards)
    files['factor-cards.json'] = encoded([])
    files['metadata-records.json'] = encoded(records)
    report = dict(schema_version='quantgraph-lab-pilot-dry-run/v1', counts=counts,
        frozen_lab_bytes_verified=True, metadata_import_ready=bool(bindings),
        research_database_import_ready=False, active_site_written=False, deployed=False,
        catalog_binding=bindings, catalog_snapshot_sha256=catalog_sha256 if catalog else None,
        blockers=[] if bindings else ['PINNED_ACTIVE_CATALOG_SNAPSHOT_REQUIRED_FOR_METADATA_OVERLAY'],
        research_blockers=['ACTIVE_RECORDS_AND_MANIFEST_REQUIRED_FOR_ADDITIVE_MERGE',
                           'LAB_LIGHT_RECORDS_ARE_NOT_COMPLETE_NATIVE_CORPUS_COLLECTIONS'],
        required_active_inputs=['closed catalog.sqlite and its SHA256 (metadata overlay dry-run)',
            'current active batch ID and complete file hash inventory',
            '/catalog/manifest.json and the two exact entity detail assets',
            '/data/manifest.json and current M0256/M0259 record assets; existing result refs',
            'final active-parent CAS and original detail/compare page acceptance by sole Site worker'],
        integration=dict(metadata='quantgraph.graph.private_intake.import_cards; exact revision overlay',
                         records='merge_record(existing, staged); preserve every existing result, audit and note',
                         implementation='same key algorithm as scripts/export_research_site.py',
                         restrictions='never replace active with bundled; never regenerate historical collection counts from these two rows'))
    if catalog:
        from quantgraph.graph.catalog import CatalogRepository
        from quantgraph.graph.private_intake import import_cards
        with tempfile.TemporaryDirectory(prefix='quantgraph-metadata-dryrun-') as tmp:
            copy = Path(tmp) / 'catalog.sqlite'
            shutil.copyfile(catalog, copy)
            c = CatalogRepository(copy)
            with c.connect() as con:
                before = [tuple(r) for r in con.execute('SELECT * FROM catalog_items ORDER BY entity_id')]
            inp = Path(tmp) / 'cards.json'; inp.write_bytes(files['strategy-cards.json'])
            first = import_cards(c, inp, digest(inp.read_bytes()), 'strategy')
            again = import_cards(c, inp, digest(inp.read_bytes()), 'strategy')
            with c.connect() as con:
                after = [tuple(r) for r in con.execute('SELECT * FROM catalog_items ORDER BY entity_id')]
            if before != after or again['inserted_reviews'] or again['unchanged_reviews'] != len(cards):
                raise ValueError('Metadata dry-run changed definitions or failed idempotence')
            report['metadata_copy_dry_run'] = dict(first=first, replay=again, catalog_definitions_unchanged=True)
    files['dry-run.json'] = encoded(report)
    manifest = dict(schema_version='quantgraph-lab-pilot-staging/v1', execute_new_trials=False,
        ready_for_direct_site_sync=False, files={n: dict(sha256=digest(b), bytes=len(b)) for n, b in sorted(files.items())})
    files['manifest.json'] = encoded(manifest)
    output.mkdir()
    for name, raw in files.items():
        target = output / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    return dict(manifest_sha256=digest(files['manifest.json']), files=len(files), bytes=sum(map(len, files.values())), **report)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--metadata', type=Path, required=True)
    p.add_argument('--lab', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--catalog', type=Path)
    p.add_argument('--catalog-sha256')
    a = p.parse_args()
    if bool(a.lab) != bool(a.output) or bool(a.catalog) != bool(a.catalog_sha256):
        p.error('lab/output and catalog/catalog-sha256 must be paired')
    print(json.dumps(prepare(a.metadata, a.lab, a.output, a.catalog, a.catalog_sha256)
                     if a.output else {'valid_metadata_records': len(validate(a.metadata))}, ensure_ascii=False))


if __name__ == '__main__':
    main()

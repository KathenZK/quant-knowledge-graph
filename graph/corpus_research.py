"""Private retained strategy-screen collections; no Lab jobs or computation launch.

The CLI is deliberately two-step: prepare fixed-name artifacts, review the
manifest digest independently, then import with that exact external digest.
Only the Personal Workbench installs this module's read API.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from datetime import date, datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import zlib

SCHEMA = 'private-strategy-screen-collection/v1'
DATABASE = 'corpus-research.sqlite'
FIDELITY_CLASSES = ('STANDARDIZED', 'PROXY', 'HYPOTHESIS', 'PROXY_HYPOTHESIS')
RESULT_STATUSES = {'tested', 'tested_proxy_only', 'tested_hypothesis_only', 'tested_mixed'}
FIDELITY_STATUS = {'STANDARDIZED': 'tested', 'PROXY': 'tested_proxy_only', 'HYPOTHESIS': 'tested_hypothesis_only', 'PROXY_HYPOTHESIS': 'tested_mixed'}

def _empty_period(period):
    """An empty sample may describe its scope but cannot assert performance."""
    metadata={'observations','n','start','end','status','reason','annualization','sharpe_cash_basis'}
    if any(value is not None for key,value in period.items() if key not in metadata):
        _fail('Empty sample cannot contain performance statistics')
    if period.get('n',0)!=0 or period.get('observations',0)!=0:
        _fail('Empty sample counts disagree')


ARTIFACTS = {
    'run_manifest.json': 'results', 'run_summary.json': 'results',
    'strategy_metrics.json': 'results', 'implemented_specs.json': 'results',
    'all_record_coverage.csv': 'results', 'daily_returns.csv.gz': 'results',
    'deep_validation.json': 'results', 'record_audit.jsonl': 'audit',
    'source_verification.json': 'audit',
}
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_RETURN_BYTES = 256 * 1024 * 1024
MAX_CURVE_POINTS = 1200
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,199}\Z')
SHA256 = re.compile(r'[a-f0-9]{64}\Z')
LIMITATIONS = [
    'Retained independent standardized strategy screen; not a source-exact historical reproduction or a completed Lab research envelope.',
    'Unsupported, unavailable and unimplemented records remain untested; lack of a result is not evidence of ineffectiveness.',
    'Source attribution, implementation assumptions and economic evidence are separate. Source checks are selective and do not verify the entire corpus.',
    'Catalog references identify source-native records only; they do not establish an exact Catalog definition-revision binding.',
    'Imported artifact bytes are verified against the supplied pin; engine and market-data lineage hashes remain declarations unless separately audited.',
    'Daily curves compound retained strategy returns, with an initial unit of capital. Benchmark metrics are retained; benchmark curves are not supplied.',
]
AUDIT_FIELDS = {
    'id', '名称', '市场', '规则', '作者或机构', '标题', 'source_url', '页码或文件',
    '可回测', '别名来源', '提出日期', 'source_domain', 'canonical_url',
    'date_precision_shape', 'date_january_1', 'github_commit_pinned',
    'source_verification_status', 'source_rule_attribution_status',
    'data_screen_primary', 'market_tags', 'known_etf_tokens', 'mechanical_flags',
    'data_requirements_flags', 'all_five_rule_components_mentioned',
    'structured_provenance_fields_present', 'template_type',
}
SOURCE_FIELDS = {
    'checked_id', 'corpus_claim', 'exact_cited_url', 'source_access', 'verdict',
    'source_supported', 'not_established_or_conflicting',
    'source_vs_compiler_derived_modifications', 'date_verification', 'evidence', 'confidence',
}


def safe_research_view(value):
    """Redact transport secrets and machine-local paths in the HTTP projection.

    Exact imported bytes and hashes stay in the private artifact store; only
    this presentation is sanitized, never the retained evidence itself.
    """
    from quantgraph.graph.personal_research import safe_metadata
    def paths(item):
        if isinstance(item, dict):
            return {key: paths(child) for key, child in item.items()
                    if not re.search(r'(?:^|_)(?:path|directory|local_file)(?:$|_)', key.casefold())}
        if isinstance(item, list):
            return [paths(child) for child in item]
        if isinstance(item, str):
            return re.sub(r'(?<![A-Za-z0-9:/])(?:/(?:home|Users|tmp|workspace|root|private|var|opt|mnt|Volumes)/|[A-Za-z]:\\)[^\s<>"\']+',
                          '[local path omitted]', item)
        return item
    return paths(safe_metadata(value))


def _fail(message):
    raise ValueError(message)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _loads(data):
    def constant(value):
        _fail('Non-finite JSON number: ' + value)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(data, parse_constant=constant, object_pairs_hook=pairs)


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        _fail('All numeric values must be finite')
    if isinstance(value, dict):
        for child in value.values():
            _finite(child)
    elif isinstance(value, list):
        for child in value:
            _finite(child)


def _identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        _fail('Invalid record, variant or run identity')
    return value


def _sha(value):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        _fail('Invalid SHA-256 digest')
    return value


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        _fail('Invalid daily observation date')
    date.fromisoformat(value)
    return value


def _integer(value):
    if type(value) is not int or value < 0:
        _fail('Counts must be nonnegative integers')
    return value


def _read_file(path, limit=MAX_ARTIFACT_BYTES):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        _fail('Input must be a regular non-symlink file: ' + path.name)
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        _fail('Artifact exceeds private import size limit: ' + path.name)
    return data


def _read_inputs(results_dir, audit_dir, artifacts=None):
    roots = {'results': Path(results_dir), 'audit': Path(audit_dir)}
    for root in roots.values():
        if root.is_symlink() or not root.is_dir():
            _fail('Explicit artifact directories must be non-symlink directories')
    # Names and directories come from code, never from the manifest or payload.
    return {name: _read_file(roots[group] / name) for name, group in (artifacts or ARTIFACTS).items()}


def build_manifest(results_dir, audit_dir, output):
    """Pin byte hashes; does not import or certify research correctness."""
    from quantgraph.graph.corpus_export import SCHEMA_V2, V2_ARTIFACTS, SCHEMA_V3, V3_ARTIFACTS
    version3=(Path(results_dir)/'origin-attachments.json').is_file()
    version2 = (Path(results_dir) / 'origin__run_manifest.json').is_file()
    blobs = _read_inputs(results_dir, audit_dir, V3_ARTIFACTS if version3 else V2_ARTIFACTS if version2 else ARTIFACTS)
    run = _loads(blobs['run_manifest.json'])
    manifest = dict(schema_version=SCHEMA_V3 if version3 else SCHEMA_V2 if version2 else SCHEMA, collection_type='RETAINED_STANDARDIZED_SCREEN',
                    run_id=_identifier(run['run_id']), execute_new_trials=False,
                    artifacts={name: {'sha256': _digest(blob), 'bytes': len(blob)}
                               for name, blob in blobs.items()})
    payload = (_json(manifest) + '\n').encode('utf-8')
    # No overwrite: the reviewed pin remains an immutable operator artifact.
    fd = os.open(Path(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(payload)
    return dict(run_id=run['run_id'], manifest_sha256=_digest(payload),
                artifact_count=len(blobs), status='PREPARED_REVIEW_DIGEST_BEFORE_IMPORT')


def _index(values, key, label):
    if not isinstance(values, list):
        _fail(label + ' must be an array')
    result = {}
    for value in values:
        if not isinstance(value, dict):
            _fail(label + ' entries must be objects')
        identity = _identifier(key(value))
        if identity in result:
            _fail('Duplicate ' + label + ' identity: ' + identity)
        result[identity] = value
    return result


def _csv(blob):
    reader = csv.DictReader(io.StringIO(blob.decode('utf-8-sig'), newline=''))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        _fail('Missing or duplicate CSV columns')
    rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        _fail('Malformed CSV row')
    return rows


def fidelity_view(metric, run_id):
    """Legacy absence means standardized screening, never source-exact replication."""
    return dict(origin_run_id=metric.get('origin_run_id', run_id),
                fidelity_class=metric.get('fidelity_class', 'STANDARDIZED'),
                fidelity_reason=metric.get('fidelity_reason', ''),
                origin_binding='EXPLICIT' if 'origin_run_id' in metric else 'CONTAINING_RUN_LEGACY')


def fidelity_counts(results):
    """Record class sets overlap; implementation identities are (origin run, variant)."""
    output = {}
    for category in FIDELITY_CLASSES:
        matching = [r for r in results if r['fidelity_class'] == category]
        output[category] = dict(records=len({r['id'] for r in matching}),
            implementations=len({(r['origin_run_id'], r['variant_id']) for r in matching}))
    return output


def _prepare(blobs, manifest):
    values = {name: _loads(blob) for name, blob in blobs.items() if name.endswith('.json')}
    for value in values.values():
        _finite(value)
    run = values['run_manifest.json']
    summary = values['run_summary.json']
    run_id = manifest['run_id']
    native_projection='origin-attachments.json' in blobs and run.get('projection_contract')=='native-retained-projection/v3'
    if run.get('projection_contract') and not native_projection:_fail('Native projection marker requires verifiedv3 artifacts')
    virtual_cash=run.get('virtual_cash_assets',[]) if native_projection else []
    if run.get('run_id') != run_id or summary.get('run_id') != run_id:
        _fail('Run identity does not reconcile')
    created = datetime.fromisoformat(run['created_at_utc'].replace('Z', '+00:00'))
    if created.tzinfo is None:
        _fail('Run creation time must include a timezone')
    main_end = _day(run['main_end'])
    latest_end = _day(run.get('observation_end', run.get('descriptive_2026_end')))
    if main_end > latest_end:
        _fail('Observation end cannot precede the main period')
    required_hashes = ['corpus_sha256', 'protocol_sha256', 'implementation_specs_sha256']
    if 'origin__run_manifest.json' not in blobs:
        required_hashes += ['protocol_amendments_sha256', 'market_data_manifest_sha256', 'data_acquisition_status_sha256']
    for key in required_hashes:
        _sha(run.get(key))
    for key in ['engine_code_sha256', 'normalized_data_sha256']:
        if not isinstance(run.get(key), dict) or not run[key]:
            _fail('Missing declared lineage hashes: ' + key)
        for filename, digest in run[key].items():
            if not isinstance(filename, str) or '/' in filename or '\\' in filename or filename in {'.', '..'}:
                _fail('Declared lineage files must use basenames only')
            _sha(digest)
    if run['implementation_specs_sha256'] != _digest(blobs['implemented_specs.json']):
        _fail('Implementation specification digest does not reconcile')
    coverage = _index(_csv(blobs['all_record_coverage.csv']), lambda x: x['id'], 'coverage')
    audit = _index([_loads(line) for line in blobs['record_audit.jsonl'].splitlines() if line.strip()],
                   lambda x: x['id'], 'audit')
    metrics = _index(values['strategy_metrics.json'], lambda x: x['variant_id'], 'metrics')
    specs = _index(values['implemented_specs.json'], lambda x: x.get('variant_id', x['id']), 'specification')
    deep = _index(values['deep_validation.json'], lambda x: x['variant_id'], 'deep validation')
    if not metrics or not specs:
        _fail('Completed screen imports require nonempty results and specifications')
    verification = values['source_verification.json']
    source = _index(verification['records'], lambda x: x['checked_id'], 'source verification')
    _finite(audit)
    if set(audit) != set(coverage) or not set(source) <= set(coverage):
        _fail('Audit and source IDs do not reconcile with corpus coverage')
    if not set(metrics) <= set(specs) or not set(deep) <= set(metrics):
        _fail('Tested and deep-validation IDs must reference retained specifications/results')
    if verification['input']['sha256'] != run['corpus_sha256']:
        _fail('Audit corpus digest does not reconcile')
    if _integer(verification['input']['row_count']) != len(coverage):
        _fail('Audit corpus row count does not reconcile')
    if _integer(verification['sample_summary']['sample_size']) != len(source):
        _fail('Source verification sample count does not reconcile')
    for spec in specs.values():
        if spec['id'] not in coverage:
            _fail('Specification references an unknown source-native record')
        if not isinstance(spec.get('family'), str) or not spec['family']:
            _fail('Specification family is required')
    by_record = defaultdict(list)
    for variant_id, metric in metrics.items():
        spec = specs[variant_id]
        if (metric.get('run_id') != run_id or metric.get('id') != spec['id']
                or metric.get('family') != spec['family']
                or metric.get('protocol_sha256') != run['protocol_sha256']
                or metric.get('implementation_specs_sha256') != run['implementation_specs_sha256']):
            _fail('Result identity or lineage does not reconcile: ' + variant_id)
        if metric['id'] not in coverage or metric.get('name') != coverage[metric['id']]['name']:
            _fail('Result source-native record does not reconcile')
        # Metric assets describe universe membership; the engine may emit a
        # sorted frame order. Keep both ORIGINAL arrays and parameter/weight
        # bindings intact; membership agreement is not implementation equivalence.
        if (not isinstance(metric.get('assets'), list) or not isinstance(spec.get('assets'), list)
                or not all(isinstance(x, str) for x in [*metric['assets'], *spec['assets']])
                or set(metric['assets']) != set(spec.get('price_assets',spec['assets']))
                or ('price_assets' in spec and (set(spec['assets']) != set(spec['price_assets']) | set(spec.get('signal_only_assets',[]))))
                or metric.get('cash_asset') != spec.get('cash_asset')):
            _fail('Result universe does not reconcile with specification')
        # Every collection represents one actual execution protocol. A cumulative
        # export must not relabel inherited results as a new run.
        for value in [metric, spec]:
            if 'origin_run_id' in value and value['origin_run_id'] != run_id:
                _fail('Result origin_run_id must equal its independent containing run')
            if 'origin_protocol_sha256' in value and value['origin_protocol_sha256'] != run['protocol_sha256']:
                _fail('Result origin protocol does not reconcile')
        category = metric.get('fidelity_class', 'STANDARDIZED')
        if category not in FIDELITY_CLASSES or category != spec.get('fidelity_class', 'STANDARDIZED'):
            _fail('Result and specification fidelity classes must agree')
        if ('fidelity_class' in metric) != ('fidelity_class' in spec):
            _fail('Explicit fidelity class must be present on both result and specification')
        proxy_declared = any(bool(value.get('asset_proxy')) for value in [metric, spec])
        hypothesis_declared = any(bool(value.get('parameter_hypothesis')) for value in [metric, spec])
        if ((proxy_declared and category not in {'PROXY', 'PROXY_HYPOTHESIS'})
                or (hypothesis_declared and category not in {'HYPOTHESIS', 'PROXY_HYPOTHESIS'})):
            _fail('Fidelity class cannot downgrade a positive proxy/hypothesis declaration')
        if category != 'STANDARDIZED':
            reason = metric.get('fidelity_reason')
            if not isinstance(reason, str) or not reason.strip() or reason != spec.get('fidelity_reason'):
                _fail('Proxy and hypothesis results require matching explicit fidelity reasons')
        by_record[metric['id']].append(dict(variant_id=variant_id, family=metric['family'],
                                            **fidelity_view(metric, run_id)))
    for identity, record in coverage.items():
        if record.get('run_id') != run_id or not record.get('status') or not record.get('name'):
            _fail('Coverage identity, name and status are required')
        count = record.get('tested_variants', '')
        if not re.fullmatch(r'0|[1-9]\d*', count):
            _fail('Invalid coverage tested-variant count')
        classes = {value['fidelity_class'] for value in by_record[identity]}
        expected_status = ('tested_mixed' if len(classes) > 1 else FIDELITY_STATUS[next(iter(classes))]) if classes else None
        if (int(count) != len(by_record[identity])
                or (bool(classes) and record['status'] != expected_status)
                or (not classes and record['status'] in RESULT_STATUSES)):
            _fail('Coverage tested status/count/fidelity does not reconcile')
        if audit[identity].get('名称') != record['name'] or audit[identity].get('source_url') != record.get('source_url'):
            _fail('Coverage and audit source identities do not reconcile')
        for key in ['source_verification_status', 'source_rule_attribution_status']:
            if not isinstance(audit[identity].get(key), str) or not audit[identity][key]:
                _fail('Per-record audit status is required')
    families = Counter(metric['family'] for metric in metrics.values())
    coverage_counts = dict(Counter(record['status'] for record in coverage.values()))
    series = set()
    for metric in metrics.values():
        if not isinstance(metric.get('assets'), list) or not all(isinstance(x, str) for x in metric['assets']):
            _fail('Result assets must be a string array')
        series.update(metric['assets'])
        if metric.get('cash_asset') not in {'CASH',*virtual_cash}:
            series.add(metric['cash_asset'])
    if native_projection:
        bindings=run.get('series_data_bindings',{})
        for asset in series:
            refs=bindings.get(asset)
            if not isinstance(refs,list) or not refs or any(ref not in run['normalized_data_sha256'] for ref in refs):_fail('Used data series lacks retained typed lineage')
    elif any(asset + '.csv' not in run['normalized_data_sha256'] for asset in series):
        _fail('Used data series lacks a retained lineage digest')
    expected_counts = dict(corpus_records=len(coverage), spec_variants=len(specs),
        tested_variants=len(metrics), tested_records=len({v['id'] for v in metrics.values()}),
        families=len(families), used_data_series=len(series),
        data_files=len(run['normalized_data_sha256']), deep_selected=len(deep))
    if any(_integer(summary.get(key)) != value for key, value in expected_counts.items()):
        _fail('Summary counts do not reconcile with retained artifacts')
    if _integer(run.get('corpus_records')) != len(coverage) or summary.get('coverage_counts') != coverage_counts:
        _fail('Corpus and coverage counts do not reconcile')
    # Bound decompression and retain missing observations as missing, never zero-fill.
    with gzip.GzipFile(fileobj=io.BytesIO(blobs['daily_returns.csv.gz'])) as stream:
        decompressed = stream.read(MAX_RETURN_BYTES + 1)
    if len(decompressed) > MAX_RETURN_BYTES:
        _fail('Daily return data exceeds decompression limit')
    reader = csv.reader(io.StringIO(decompressed.decode('utf-8-sig'), newline=''))
    header = next(reader, [])
    if not header or header[0] != 'date' or len(set(header)) != len(header) or set(header[1:]) != set(metrics):
        _fail('Daily return columns must match tested variant IDs exactly')
    returns = {variant_id: [] for variant_id in metrics}
    previous = ''
    for row in reader:
        if len(row) != len(header):
            _fail('Malformed daily return row')
        day = _day(row[0])
        if day <= previous or day > latest_end:
            _fail('Daily return dates must be unique, increasing and within the declared end date')
        previous = day
        for variant_id, value in zip(header[1:], row[1:]):
            if value == '':
                continue
            number = float(value)
            if not math.isfinite(number) or number < -1:
                _fail('Daily returns must be finite and at least -1')
            returns[variant_id].append([day, number])
    for variant_id, observations in returns.items():
        if not observations:
            _fail('Every tested variant must have daily returns')
        periods = metrics[variant_id].get('periods')
        if not isinstance(periods, dict) or not periods.get('full'):
            _fail('Tested variants require full-period metrics')
        for name, period in periods.items():
            if not isinstance(period, dict):
                _fail('Period metrics must be objects')
            count=_integer(period.get('observations'))
            if native_projection and count==0:_empty_period(period)
            if native_projection and (count==0 or (count<2 and not {'start','end','total_return'}<=set(period))):
                if count>0 and set(period)-{'observations','n','status','reason'}:_fail('Incomplete short-sample metrics contain unbound statistics')
                if 'n' in period and period['n']!=count:_fail('Short-sample counts disagree')
                bounds=run.get('periods',{}).get(name)
                if not bounds or len(bounds)!=2:_fail('Short-sampleperiod requires explicitdeclaredscope')
                if len([(d,v) for d,v in observations if _day(bounds[0])<=d<=_day(bounds[1])])!=count:
                    _fail('Short-sample observation count does not reconcile')
                continue
            start, end = _day(period['start']), _day(period['end'])
            if start > end or end > latest_end or (name == 'full' and end > main_end):
                _fail('Metric period dates exceed declared scope')
            selected = [(day, value) for day, value in observations if start <= day <= end]
            if (not selected or len(selected) != _integer(period['observations'])
                    or selected[0][0] != start or selected[-1][0] != end):
                _fail('Metric observations do not reconcile with daily returns')
            total = math.prod(1 + value for _, value in selected) - 1
            if not math.isfinite(total) or not math.isclose(total, period['total_return'], rel_tol=1e-7, abs_tol=1e-8):
                _fail('Metric total return does not reconcile with daily returns')
        equity = 1.0
        for _, number in observations:
            equity *= 1 + number
            if not math.isfinite(equity):
                _fail('Compounded equity must remain finite')
    for identity, checked in source.items():
        if checked.get('source_access', {}).get('status') != audit[identity]['source_verification_status']:
            _fail('Selected source verification status does not reconcile with audit')
        if checked.get('exact_cited_url', coverage[identity]['source_url']) != coverage[identity]['source_url']:
            _fail('Selected source verification URL does not reconcile with audit')
    records = []
    for identity, record in coverage.items():
        detail_audit = {key: value for key, value in audit[identity].items() if key in AUDIT_FIELDS}
        if identity in source:
            detail_audit['source_verification'] = {key: value for key, value in source[identity].items() if key in SOURCE_FIELDS}
        implementations = sorted(by_record[identity], key=lambda x: x['variant_id'])
        records.append(dict(id=identity, name=record['name'], status=record['status'], reason=record.get('reason', ''),
            source_url=record.get('source_url', ''), tested_variants=len(implementations),
            families=sorted({v['family'] for v in implementations}), audit=detail_audit, implementations=implementations))
    summary = dict(summary, standardized_implementations=sum(v.get('fidelity_class', 'STANDARDIZED') == 'STANDARDIZED' for v in metrics.values()),
        supplemental_defaults_implementations=sum(v.get('supplemental_defaults_flag') is True for v in metrics.values()))
    return dict(run=run, summary=summary, records=records, metrics=metrics, specs=specs, deep=deep,
                returns=returns, families=families, verification=verification)


TABLES = [
    '''CREATE TABLE IF NOT EXISTS corpus_runs (
        run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, imported_at TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL, manifest TEXT NOT NULL, summary TEXT NOT NULL, lineage TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS corpus_artifacts (
        run_id TEXT NOT NULL REFERENCES corpus_runs(run_id), name TEXT NOT NULL,
        sha256 TEXT NOT NULL, content BLOB NOT NULL, PRIMARY KEY(run_id,name))''',
    '''CREATE TABLE IF NOT EXISTS corpus_records (
        run_id TEXT NOT NULL REFERENCES corpus_runs(run_id), id TEXT NOT NULL, name TEXT NOT NULL,
        status TEXT NOT NULL, search_text TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,id))''',
    '''CREATE TABLE IF NOT EXISTS corpus_implementations (
        run_id TEXT NOT NULL, variant_id TEXT NOT NULL, record_id TEXT NOT NULL, family TEXT NOT NULL,
        metrics TEXT NOT NULL, spec TEXT NOT NULL, deep_validation TEXT, returns BLOB NOT NULL,
        PRIMARY KEY(run_id,variant_id), FOREIGN KEY(run_id,record_id) REFERENCES corpus_records(run_id,id))''',
    'CREATE INDEX IF NOT EXISTS corpus_records_status ON corpus_records(run_id,status,id)',
    'CREATE INDEX IF NOT EXISTS corpus_implementation_family ON corpus_implementations(run_id,family,record_id)',
]


def import_manifest(runtime, manifest_path, expected_sha256, results_dir, audit_dir):
    """Verify pin, all bytes and reconciliation before the first filesystem write."""
    _sha(expected_sha256)
    payload = _read_file(manifest_path, 1024 * 1024)
    if _digest(payload) != expected_sha256:
        _fail('Manifest digest mismatch')
    manifest = _loads(payload)
    from quantgraph.graph.corpus_export import SCHEMA_V2, V2_ARTIFACTS, SCHEMA_V3, V3_ARTIFACTS, verify_derived
    version3=manifest.get('schema_version')==SCHEMA_V3
    version2 = manifest.get('schema_version') == SCHEMA_V2
    expected_artifacts = V3_ARTIFACTS if version3 else V2_ARTIFACTS if version2 else ARTIFACTS
    if (manifest.get('schema_version') not in {SCHEMA, SCHEMA_V2, SCHEMA_V3}
            or manifest.get('collection_type') != 'RETAINED_STANDARDIZED_SCREEN'
            or manifest.get('execute_new_trials') is not False):
        _fail('Unsupported retained collection contract')
    _identifier(manifest.get('run_id'))
    refs = manifest.get('artifacts')
    if not isinstance(refs, dict) or set(refs) != set(expected_artifacts):
        _fail('Manifest must pin every fixed-name artifact and no extra files')
    blobs = _read_inputs(results_dir, audit_dir, expected_artifacts)
    for name, blob in blobs.items():
        ref = refs[name]
        if not isinstance(ref, dict) or set(ref) != {'sha256', 'bytes'}:
            _fail('Artifact references support only digest and byte count')
        if _sha(ref['sha256']) != _digest(blob) or _integer(ref['bytes']) != len(blob):
            _fail('Artifact digest or byte count mismatch: ' + name)
    if version2 or version3:
        verify_derived(blobs)
    prepared = _prepare(blobs, manifest)
    runtime = Path(runtime)
    if runtime.is_symlink() or (runtime / DATABASE).is_symlink():
        _fail('Runtime database cannot be a symlink')
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = runtime / DATABASE
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    with sqlite3.connect(path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('BEGIN IMMEDIATE')
        for statement in TABLES:
            con.execute(statement)
        for table in ['corpus_runs', 'corpus_artifacts', 'corpus_records', 'corpus_implementations']:
            for action in ['UPDATE', 'DELETE']:
                con.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} "
                            "BEGIN SELECT RAISE(ABORT,'Retained corpus collections are append-only'); END")
        # The declared corpus digest is an aggregation boundary. Reject a
        # contradictory ID universe before appending an otherwise valid run.
        new_ids = {row['id'] for row in prepared['records']}
        for prior_run_id, prior_lineage in con.execute('SELECT run_id,lineage FROM corpus_runs'):
            if _loads(prior_lineage)['declared_lineage']['corpus_sha256'] == prepared['run']['corpus_sha256']:
                prior_ids = {row[0] for row in con.execute('SELECT id FROM corpus_records WHERE run_id=?', (prior_run_id,))}
                if prior_ids != new_ids:
                    _fail('Same-corpus run record identities are inconsistent')
        previous = con.execute('SELECT manifest_sha256 FROM corpus_runs WHERE run_id=?', (manifest['run_id'],)).fetchone()
        if previous:
            if previous[0] != expected_sha256:
                _fail('Conflicting retained run ID; existing run is immutable')
            return dict(run_id=manifest['run_id'], manifest_sha256=expected_sha256, duplicate=True,
                        counts=prepared['summary'], new_trials=0)
        run_id = manifest['run_id']
        lineage = dict(source_native_namespace='GrokBot corpus record ID', definition_revision_bound=False,
            verification='Imported artifact bytes verified against operator-supplied manifest digest',
            declared_lineage=prepared['run'], artifacts=refs)
        con.execute('INSERT INTO corpus_runs VALUES(?,?,?,?,?,?,?)', (run_id, datetime.fromisoformat(prepared['run']['created_at_utc'].replace('Z', '+00:00')).astimezone(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(), expected_sha256, _json(manifest), _json(prepared['summary']), _json(lineage)))
        con.executemany('INSERT INTO corpus_artifacts VALUES(?,?,?,?)',
            ((run_id, name, _digest(blob), zlib.compress(blob)) for name, blob in blobs.items()))
        con.executemany('INSERT INTO corpus_records VALUES(?,?,?,?,?,?)',
            ((run_id, record['id'], record['name'], record['status'],
              ' '.join([record['id'], record['name'], record['reason'], *record['families']]).casefold(), _json(record))
             for record in prepared['records']))
        con.executemany('INSERT INTO corpus_implementations VALUES(?,?,?,?,?,?,?,?)',
            ((run_id, variant_id, metric['id'], metric['family'], _json(metric), _json(prepared['specs'][variant_id]),
              _json(prepared['deep'][variant_id]) if variant_id in prepared['deep'] else None,
              zlib.compress(_json(prepared['returns'][variant_id]).encode('utf-8')))
             for variant_id, metric in prepared['metrics'].items()))
    return dict(run_id=run_id, manifest_sha256=expected_sha256, duplicate=False, counts=prepared['summary'], new_trials=0)


def import_source_portfolio(runtime, origin_dir, expected_manifest_sha256):
    """Install authored portfolio evidence in a separate append-only table."""
    from quantgraph.graph.corpus_export import validate_source_portfolio
    prepared=validate_source_portfolio(origin_dir,expected_manifest_sha256)
    raw={name:_read_file(Path(origin_dir)/name) for name in prepared['artifacts']}
    raw['evaluation_manifest.json']=_read_file(Path(origin_dir)/'evaluation_manifest.json')
    if _digest(raw['evaluation_manifest.json'])!=expected_manifest_sha256:_fail('Source manifestchanged before import')
    for name,ref in prepared['artifacts'].items():
        if _digest(raw[name])!=ref['sha256'] or len(raw[name])!=ref['bytes']:_fail('Source artifactchanged before import')
    runtime=Path(runtime);path=runtime/DATABASE
    if runtime.is_symlink() or path.is_symlink() or not path.is_file():_fail('Import corpus runs before binding source evidence')
    with sqlite3.connect(path) as con:
        con.execute('BEGIN IMMEDIATE')
        for record in prepared['records']:
            names={r[0] for r in con.execute('SELECT name FROM corpus_records WHERE id=?',(record['id'],))}
            if names!={record['name']}:_fail('Source evidence does not bind existing corpus record/name')
        con.execute('CREATE TABLE IF NOT EXISTS corpus_source_evaluations (evaluation_id TEXT PRIMARY KEY,manifest_sha256 TEXT NOT NULL,payload TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS corpus_source_artifacts (evaluation_id TEXT NOT NULL REFERENCES corpus_source_evaluations(evaluation_id), name TEXT NOT NULL,sha256 TEXT NOT NULL,content BLOB NOT NULL,PRIMARY KEY(evaluation_id,name))')
        for action in ['UPDATE','DELETE']:
            con.execute(f"CREATE TRIGGER IF NOT EXISTS corpus_source_artifacts_no_{action.lower()} BEFORE {action} ON corpus_source_artifacts BEGIN SELECT RAISE(ABORT,'Source artifacts are append-only'); END")
            con.execute(f"CREATE TRIGGER IF NOT EXISTS corpus_source_evaluations_no_{action.lower()} BEFORE {action} ON corpus_source_evaluations BEGIN SELECT RAISE(ABORT,'Source evaluations are append-only'); END")
        old=con.execute('SELECT manifest_sha256 FROM corpus_source_evaluations WHERE evaluation_id=?',(prepared['evaluation_id'],)).fetchone()
        if old and old[0]!=expected_manifest_sha256:_fail('Conflicting immutable source evaluation ID')
        if not old:
            con.execute('INSERT INTO corpus_source_evaluations VALUES(?,?,?)',(prepared['evaluation_id'],expected_manifest_sha256,_json(prepared)))
            con.executemany('INSERT INTO corpus_source_artifacts VALUES(?,?,?,?)',[(prepared['evaluation_id'],name,_digest(blob),zlib.compress(blob)) for name,blob in raw.items()])
    return dict(evaluation_id=prepared['evaluation_id'],manifest_sha256=expected_manifest_sha256,duplicate=bool(old),source_evidence_records=len(prepared['records']),new_execution_records=0,new_trials=0)


class CorpusResearch:
    """Read-only, bounded personal projection over an operator-managed database."""
    def __init__(self, runtime):
        self.path = Path(runtime) / DATABASE

    @contextmanager
    def connect(self):
        # A missing read never initializes an empty database.
        if self.path.is_symlink() or not self.path.is_file():
            raise KeyError('Retained collection is not available')
        con = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    def source_portfolios(self, record_id=None):
        """Read authored factor evidence separately from every execution count."""
        with self.connect() as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='corpus_source_evaluations'").fetchone() is None:return []
            output=[]
            for row in con.execute('SELECT payload FROM corpus_source_evaluations ORDER BY evaluation_id'):
                value=_loads(row[0]);records=[r for r in value['records'] if record_id is None or r['id']==record_id]
                if records:output.append(dict(evaluation_id=value['evaluation_id'],evidence_class='PUBLISHED_SOURCE_PORTFOLIO',manifest_sha256=value['manifest_sha256'],records=records,new_execution_records=0))
            return output

    def _run(self, con, run_id):
        row = (con.execute('SELECT * FROM corpus_runs WHERE run_id=?', (run_id,)).fetchone() if run_id
               else con.execute('SELECT * FROM corpus_runs ORDER BY created_at DESC,run_id DESC LIMIT 1').fetchone())
        if row is None:
            raise KeyError('Unknown retained run')
        return row

    def _results(self, con, runs):
        results = []
        for run in runs:
            protocol = _loads(run['lineage'])['declared_lineage']['protocol_sha256']
            for row in con.execute('SELECT variant_id,record_id,metrics FROM corpus_implementations WHERE run_id=? ORDER BY variant_id', (run['run_id'],)):
                metric = _loads(row['metrics'])
                results.append(dict(id=row['record_id'], variant_id=row['variant_id'],
                    manifest_sha256=run['manifest_sha256'], protocol_sha256=protocol,
                    **fidelity_view(metric, run['run_id'])))
        return results

    def _compatible_runs(self, con, selected):
        corpus = _loads(selected['lineage'])['declared_lineage']['corpus_sha256']
        ids = {row[0] for row in con.execute('SELECT id FROM corpus_records WHERE run_id=?', (selected['run_id'],))}
        runs = []
        for run in con.execute('SELECT * FROM corpus_runs ORDER BY created_at DESC,run_id DESC'):
            if _loads(run['lineage'])['declared_lineage']['corpus_sha256'] != corpus:
                continue
            candidate_ids = {row[0] for row in con.execute('SELECT id FROM corpus_records WHERE run_id=?', (run['run_id'],))}
            if candidate_ids != ids:
                _fail('Same-corpus run record identities are inconsistent')
            runs.append(run)
        return corpus, ids, runs

    def _aggregate(self, con, selected):
        corpus, ids, runs = self._compatible_runs(con, selected)
        results = self._results(con, runs)
        tested_ids = {row['id'] for row in results}
        return dict(corpus_sha256=corpus, run_ids=[run['run_id'] for run in runs], run_count=len(runs),
            corpus_records=len(ids), tested_records=len(tested_ids), untested_records=len(ids - tested_ids),
            fidelity_counts=fidelity_counts(results),
            counting_note='Distinct source records across same-corpus runs; fidelity record sets overlap. Protocols and results remain separate.')

    def summary(self, run_id=None):
        if not self.path.exists():
            if run_id:
                raise KeyError(run_id)
            return dict(available=False, run_id=None, runs=[], counts={}, coverage_counts={}, families=[],
                        limitations=LIMITATIONS, manifest_sha256=None)
        with self.connect() as con:
            run = self._run(con, run_id)
            summary = _loads(run['summary'])
            families = con.execute('SELECT family,COUNT(*) AS n FROM corpus_implementations WHERE run_id=? GROUP BY family ORDER BY family', (run['run_id'],)).fetchall()
            return dict(available=True, run_id=run['run_id'],
                runs=[dict(row) for row in con.execute('SELECT run_id,created_at FROM corpus_runs ORDER BY created_at DESC,run_id DESC')],
                counts={key: summary[key] for key in ['corpus_records', 'tested_records', 'tested_variants', 'used_data_series', 'data_files', 'standardized_implementations', 'supplemental_defaults_implementations']},
                coverage_counts=summary['coverage_counts'], families=[dict(value=row['family'], count=row['n']) for row in families],
                limitations=LIMITATIONS, manifest_sha256=run['manifest_sha256'],
                fidelity_counts=fidelity_counts(self._results(con, [run])),
                aggregate=self._aggregate(con, run))

    def records(self, *, run_id=None, q='', status='', family='', page=1, page_size=20):
        if not 1 <= page_size <= 100 or page < 1 or len(q) > 2000:
            _fail('Invalid pagination or query length')
        with self.connect() as con:
            run = self._run(con, run_id)
            clauses, args = ['r.run_id=?'], [run['run_id']]
            if q.strip():
                clauses.append('instr(r.search_text,?)>0')
                args.append(q.strip().casefold())
            if status:
                clauses.append('r.status=?')
                args.append(status)
            if family:
                clauses.append('EXISTS(SELECT 1 FROM corpus_implementations i WHERE i.run_id=r.run_id AND i.record_id=r.id AND i.family=?)')
                args.append(family)
            where = ' AND '.join(clauses)
            total = con.execute('SELECT COUNT(*) FROM corpus_records r WHERE ' + where, args).fetchone()[0]
            rows = con.execute('SELECT r.payload FROM corpus_records r WHERE ' + where + ' ORDER BY r.id LIMIT ? OFFSET ?',
                               [*args, page_size, (page - 1) * page_size])
            items = []
            for row in rows:
                item = _loads(row['payload'])
                item.pop('source_url', None)
                item['audit'] = {key: item['audit'][key] for key in ['source_verification_status', 'source_rule_attribution_status']}
                # Legacy database payloads lack fidelity labels. Derive only from
                # the immutable per-run metric; never rewrite retained payloads.
                for implementation in item['implementations']:
                    metric_row = con.execute('SELECT metrics FROM corpus_implementations WHERE run_id=? AND variant_id=?',
                        (run['run_id'], implementation['variant_id'])).fetchone()
                    implementation.update(fidelity_view(_loads(metric_row[0]), run['run_id']))
                items.append(item)
            return dict(run_id=run['run_id'], items=items, total=total, page=page, page_size=page_size)

    def record(self, record_id, *, run_id=None):
        """Read one source record including untested/failed coverage and audit."""
        with self.connect() as con:
            run = self._run(con, run_id)
            row = con.execute('SELECT payload FROM corpus_records WHERE run_id=? AND id=?',
                              (run['run_id'], record_id)).fetchone()
            if row is None:
                raise KeyError(record_id)
            record = _loads(row['payload'])
            record['run_id'] = run['run_id']
            record['lineage'] = dict(run_id=run['run_id'], source_native_id=record['id'],
                source_native_namespace='GrokBot corpus record ID', definition_revision_bound=False,
                manifest_sha256=run['manifest_sha256'], artifacts=_loads(run['manifest'])['artifacts'])
            _, _, compatible = self._compatible_runs(con, run)
            record['related_results'] = [result for result in self._results(con, compatible) if result['id'] == record_id]
            record['limitations'] = LIMITATIONS
            return record

    def implementation(self, variant_id, *, run_id=None):
        with self.connect() as con:
            run = self._run(con, run_id)
            row = con.execute('SELECT * FROM corpus_implementations WHERE run_id=? AND variant_id=?', (run['run_id'], variant_id)).fetchone()
            if row is None:
                raise KeyError(variant_id)
            record = _loads(con.execute('SELECT payload FROM corpus_records WHERE run_id=? AND id=?', (run['run_id'], row['record_id'])).fetchone()[0])
            observations = _loads(zlib.decompress(row['returns']))
            equity = peak = 1.0
            curve = []
            for day, number in observations:
                equity *= 1 + number
                peak = max(peak, equity)
                curve.append(dict(date=day, equity=equity, drawdown=equity / peak - 1))
            count = len(curve)
            if count > MAX_CURVE_POINTS:
                # Preserve global extrema as well as both endpoints; the exact
                # drawdown was calculated on every original observation.
                indices = {0, count - 1,
                    min(range(count), key=lambda i: curve[i]['equity']),
                    max(range(count), key=lambda i: curve[i]['equity']),
                    min(range(count), key=lambda i: curve[i]['drawdown'])}
                for index in (i * (count - 1) // (MAX_CURVE_POINTS - 1) for i in range(MAX_CURVE_POINTS)):
                    if len(indices) == MAX_CURVE_POINTS:
                        break
                    indices.add(index)
                curve = [curve[i] for i in sorted(indices)]
            lineage = _loads(run['lineage'])
            lineage.update(run_id=run['run_id'], manifest_sha256=run['manifest_sha256'], source_native_id=record['id'],
                           implementation_variant_id=variant_id)
            return dict(run_id=run['run_id'], id=record['id'], variant_id=variant_id, name=record['name'],
                family=row['family'], metrics=_loads(row['metrics']), spec=_loads(row['spec']), audit=record['audit'],
                **fidelity_view(_loads(row['metrics']), run['run_id']),
                deep_validation=_loads(row['deep_validation']) if row['deep_validation'] else None,
                curve=curve, curve_meta=dict(method='daily_compounded', initial_equity=1,
                    total_observations=count, returned_points=len(curve), sampling='uniform_index_with_endpoints_and_global_extrema' if count > MAX_CURVE_POINTS else 'none',
                    start=observations[0][0], end=observations[-1][0], scope='all_retained_daily_observations',
                    drawdown_computed_before_sampling=True, benchmark_curve_available=False),
                lineage=lineage, limitations=LIMITATIONS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('build-manifest', help='Pin fixed-name private artifacts; review digest before import')
    prepare.add_argument('--output', type=Path, required=True)
    ingest = commands.add_parser('import', help='Import already-reviewed pinned artifacts into a personal runtime')
    ingest.add_argument('--runtime', type=Path, required=True)
    ingest.add_argument('--manifest', type=Path, required=True)
    ingest.add_argument('--sha256', required=True)
    for command in [prepare, ingest]:
        command.add_argument('--results-dir', type=Path, required=True)
        command.add_argument('--audit-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'build-manifest':
            result = build_manifest(args.results_dir, args.audit_dir, args.output)
        else:
            result = import_manifest(args.runtime, args.manifest, args.sha256, args.results_dir, args.audit_dir)
        print(_json(result))
    except (ValueError, KeyError, OSError, csv.Error, sqlite3.Error) as error:
        parser.exit(2, 'Private collection import rejected: ' + str(error) + '\n')


if __name__ == '__main__':
    main()

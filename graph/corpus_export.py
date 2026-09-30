"""Deterministic metadata-only projection of one immutable delta screen run.

No source files, market data, strategy engine or inherited result is modified.
The origin protocol and every producer output are pinned independently.
"""
import argparse
from collections import Counter, defaultdict
import csv
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile

from quantgraph.graph.corpus_research import (
    ARTIFACTS, _csv, _digest, _fail, _index, _json, _loads, _read_file,
    _sha, _identifier, _prepare, build_manifest, FIDELITY_STATUS,
)

SCHEMA_V2 = 'private-strategy-screen-collection/v2'
ORIGIN_NAMES = (
    'run_manifest.json', 'run_summary.json', 'strategy_metrics.json',
    'implemented_specs.json', 'implementation_status.json', 'daily_returns.csv.gz',
    'all_record_coverage.csv', 'strategy_metrics.csv', 'target_hashes.json',
)
ORIGIN_ARTIFACTS = {'origin__' + name: 'results' for name in ORIGIN_NAMES}
ORIGIN_ARTIFACTS['origin__protocol.json'] = 'results'
ANNOTATION_FILE = 'operator-annotations.json'
V2_ARTIFACTS = ARTIFACTS | ORIGIN_ARTIFACTS | {ANNOTATION_FILE: 'results'}


def _encoded(value):
    return (_json(value) + '\n').encode('utf-8')


def _csv_bytes(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


def _fidelity(value, annotation=None):
    proxy, hypothesis = value.get('asset_proxy'), value.get('parameter_hypothesis')
    extra = (annotation or {}).get('additional_hypothesis_reason')
    if extra:
        hypothesis = '\n'.join(v for v in [hypothesis, extra] if v)
    for reason in [proxy, hypothesis]:
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            _fail('Declared proxy/hypothesis must include an explicit nonempty reason')
    category = 'PROXY_HYPOTHESIS' if proxy and hypothesis else 'PROXY' if proxy else 'HYPOTHESIS' if hypothesis else 'STANDARDIZED'
    reason = '\n'.join(v for v in [proxy, hypothesis] if v)
    return dict(fidelity_class=category, fidelity_reason=reason)


def _merged_fidelity_declarations(metric, spec):
    """Missing/null metadata can never erase a positive deviation declaration."""
    output = {}
    for key in ['asset_proxy', 'parameter_hypothesis']:
        values = [value[key] for value in [spec, metric] if key in value and value[key] is not None]
        if any(not isinstance(v, str) or not v.strip() for v in values):
            _fail('Malformed fidelity declaration')
        unique = list(dict.fromkeys(values))
        if len(unique) > 1:
            _fail('Conflicting nonempty metric/spec fidelity reasons')
        output[key] = unique[0] if unique else None
    return output


def derive(blobs):
    """Derive only declared metadata; verify origin manifests before projection."""
    source = {name: blobs['origin__' + name] for name in ORIGIN_NAMES}
    origin = _loads(source['run_manifest.json'])
    run_id = _identifier(origin['run_id'])
    results = origin.get('result_hashes')
    if not isinstance(results, dict) or set(results) != set(ORIGIN_NAMES) - {'run_manifest.json'}:
        _fail('Origin manifest must pin exactly the supported producer outputs')
    for name, digest in results.items():
        if _sha(digest) != _digest(source[name]):
            _fail('Origin artifact digest mismatch: ' + name)
    protocol_blob = blobs['origin__protocol.json']
    if _sha(origin['protocol_sha256']) != _digest(protocol_blob):
        _fail('Origin protocol digest mismatch')
    protocol = _loads(protocol_blob)
    original_summary = _loads(source['run_summary.json'])
    if original_summary.get('run_id') != run_id:
        _fail('Origin summary belongs to another run')
    original_metrics = _index(_loads(source['strategy_metrics.json']), lambda x:x['variant_id'], 'origin metrics')
    original_specs = _index(_loads(source['implemented_specs.json']), lambda x:x.get('variant_id', x['id']), 'origin specifications')
    statuses = _index(_loads(source['implementation_status.json']), lambda x:x['variant_id'], 'origin implementation statuses')
    if not original_metrics or not original_specs:
        _fail('Empty origin execution cannot be imported as completed evidence')
    if not set(original_metrics) <= set(original_specs) or not set(original_metrics) <= set(statuses):
        _fail('Origin execution identities do not reconcile')
    annotations = _loads(blobs[ANNOTATION_FILE])
    if (not {'schema_version', 'run_id', 'implementations'} <= set(annotations)
            or not set(annotations) <= {'schema_version', 'run_id', 'implementations', 'description'}
            or annotations['schema_version'] != 'strategy-screen-annotations/v1'
            or annotations['run_id'] != run_id or not isinstance(annotations['implementations'], dict)
            or not set(annotations['implementations']) <= set(original_specs)):
        _fail('Operator annotations must bind known implementations of this origin run')
    for note in annotations['implementations'].values():
        if not isinstance(note, dict) or not note or not set(note) <= {'additional_hypothesis_reason', 'deep_validation_scope'}:
            _fail('Unsupported operator annotation')
        if 'additional_hypothesis_reason' in note and (not isinstance(note['additional_hypothesis_reason'], str) or not note['additional_hypothesis_reason'].strip()):
            _fail('Hypothesis annotation requires an explicit reason')
        if 'deep_validation_scope' in note and note['deep_validation_scope'] != 'FIXED_ORDER_PATH_DELAY':
            _fail('Unknown deep-validation annotation scope')
    verification = _loads(blobs['source_verification.json'])
    audit = _index([_loads(line) for line in blobs['record_audit.jsonl'].splitlines() if line.strip()], lambda x:x['id'], 'audit')
    if len(audit) != verification['input']['row_count']:
        _fail('Origin export audit corpus count does not reconcile')
    inherited = _index(_csv(source['all_record_coverage.csv']), lambda x:x['id'], 'origin cumulative coverage')
    if set(inherited) != set(audit):
        _fail('Origin coverage and requested audit corpus identities differ')
    for identity, record in inherited.items():
        if record['name'] != audit[identity]['名称'] or record['source_url'] != audit[identity]['source_url']:
            _fail('Origin source record does not match requested audit corpus')
    specs = []
    for variant_id, original in original_specs.items():
        spec = deepcopy(original)
        if original.get('origin_run_id', run_id) != run_id or original['id'] not in audit:
            _fail('Origin specification belongs to another run or corpus')
        declared = _merged_fidelity_declarations(original_metrics.get(variant_id, {}), original)
        enriched = dict(origin_run_id=run_id, origin_protocol_sha256=origin['protocol_sha256'], **_fidelity(declared, annotations['implementations'].get(variant_id)))
        for key, value in enriched.items():
            if key in original and original[key] != value:
                _fail('Conflicting producer fidelity/origin declaration')
        spec.update(enriched)
        specs.append(spec)
    specs_blob = _encoded(specs)
    metrics, deep = [], []
    by_record = defaultdict(list)
    for variant_id, original in original_metrics.items():
        if original.get('run_id') != run_id or original.get('origin_run_id', run_id) != run_id:
            _fail('Mixed-origin results cannot be relabeled into a single run')
        spec = original_specs[variant_id]
        if original['id'] != spec['id']:
            _fail('Origin metric/spec identity differs')
        if statuses[variant_id]['id'] != original['id'] or not statuses[variant_id]['status'].startswith('tested'):
            _fail('Origin result is not supported by an executed status')
        declared = _merged_fidelity_declarations(original, spec)
        annotation = annotations['implementations'].get(variant_id, {})
        metadata = dict(origin_run_id=run_id, origin_protocol_sha256=origin['protocol_sha256'],
            protocol_sha256=origin['protocol_sha256'], implementation_specs_sha256=_digest(specs_blob), **_fidelity(declared, annotation))
        executed_status = statuses[variant_id]['status']
        status_classes = {
            'tested': set(FIDELITY_STATUS),
            'tested_proxy': {'PROXY', 'PROXY_HYPOTHESIS'},
            'tested_hypothesis': {'HYPOTHESIS', 'PROXY_HYPOTHESIS'},
            'tested_proxy_hypothesis': {'PROXY_HYPOTHESIS'},
        }
        if executed_status not in status_classes or metadata['fidelity_class'] not in status_classes[executed_status]:
            _fail('Origin executed status requires explicit matching fidelity reasons')
        for key, value in metadata.items():
            if key in original and original[key] != value:
                _fail('Conflicting origin metric metadata')
        metric = dict(deepcopy(original), **metadata)
        metrics.append(metric)
        by_record[metric['id']].append(metric)
        if original.get('additional_day_lag') is not None:
            deep.append(dict(variant_id=variant_id, origin_run_id=run_id,
                selection='retained_origin_additional_day_lag', additional_day_lag=original['additional_day_lag'],
                interpretation=original.get('additional_day_lag_interpretation'),
                scope=annotation.get('deep_validation_scope', 'ORIGIN_REPORTED_SENSITIVITY_NOT_INDEPENDENTLY_VERIFIED')))
    status_by_record = defaultdict(list)
    for status in statuses.values():
        if status['id'] not in audit:
            _fail('Origin status references an unknown source record')
        status_by_record[status['id']].append(status)
    coverage = []
    for identity, record in audit.items():
        evidence = by_record[identity]
        classes = {r['fidelity_class'] for r in evidence}
        if classes:
            status = 'tested_mixed' if len(classes) > 1 or 'PROXY_HYPOTHESIS' in classes else FIDELITY_STATUS[next(iter(classes))]
            reason = '\n'.join(sorted({r['fidelity_reason'] for r in evidence if r['fidelity_reason']}))
        else:
            own = status_by_record[identity]
            states = {x['status'] for x in own}
            if any(state.startswith('tested') for state in states):
                _fail('Executed origin status has no retained result')
            status = next(iter(states)) if len(states) == 1 else 'multiple_unresolved_dependencies' if states else 'not_evaluated_in_this_run'
            reason = '\n'.join(sorted({str(x.get('reason', '')) for x in own if x.get('reason')})) or 'No retained experiment for this source record in this origin run.'
        coverage.append(dict(run_id=run_id, id=identity, name=record['名称'], status=status, reason=reason,
            tested_variants=len(evidence), source_url=record['source_url']))
    data = origin['input_files']
    normalized = {ticker + '.csv': _sha(value['sha256']) for ticker, value in data.items()}
    code = {}
    for path, digest in origin['code_hashes'].items():
        basename = Path(path).name
        if basename in code:
            _fail('Ambiguous origin engine code basename')
        code[basename] = _sha(digest)
    if not data or not code:
        _fail('Origin run lacks declared data/code lineage')
    periods = origin['periods']
    main_end = periods['full'][1]
    observation_end = max(bounds[1] for bounds in periods.values())
    origin_refs = {name: dict(sha256=_digest(blobs[name]), bytes=len(blobs[name])) for name in ORIGIN_ARTIFACTS}
    run = dict(run_id=run_id, origin_run_id=run_id, created_at_utc=origin['created_at_utc'],
        corpus_sha256=verification['input']['sha256'], corpus_records=len(audit),
        protocol_sha256=origin['protocol_sha256'], implementation_specs_sha256=_digest(specs_blob),
        engine_code_sha256=code, normalized_data_sha256=normalized, main_end=main_end, observation_end=observation_end,
        periods=periods, base_cost_bps=protocol.get('base_cost_bps'), origin_artifacts=origin_refs,
        source_run_manifest_sha256=_digest(source['run_manifest.json']), source_implementation_specs_sha256=_digest(source['implemented_specs.json']),
        metadata_enrichment=dict(adapter='quantgraph-delta-export/v1', recomputed=False,
            operator_annotations_sha256=_digest(blobs[ANNOTATION_FILE]),
            description='Metadata-only independent-run projection. Original producer files and protocol retained byte-for-byte. Cumulative source coverage is not imported as evidence. Corpus binding uses audited matching source IDs; market/code hashes remain producer declarations.'))
    series = {asset for metric in metrics for asset in metric['assets']}
    series.update(metric['cash_asset'] for metric in metrics if metric['cash_asset'] != 'CASH')
    summary = dict(run_id=run_id, corpus_records=len(audit), spec_variants=len(specs), tested_variants=len(metrics),
        tested_records=len(by_record.keys() & {m['id'] for m in metrics}), families=len({m['family'] for m in metrics}),
        used_data_series=len(series), data_files=len(data), deep_selected=len(deep), coverage_counts=dict(Counter(r['status'] for r in coverage)))
    return {'run_manifest.json':_encoded(run), 'run_summary.json':_encoded(summary),
        'implemented_specs.json':specs_blob, 'strategy_metrics.json':_encoded(metrics),
        'all_record_coverage.csv':_csv_bytes(coverage), 'daily_returns.csv.gz':source['daily_returns.csv.gz'],
        'deep_validation.json':_encoded(deep)}


def verify_derived(blobs):
    for name, expected in derive(blobs).items():
        if blobs[name] != expected:
            _fail('Derived projection differs from retained origin bytes: ' + name)


def export_delta(origin_dir, protocol_path, audit_dir, destination, annotations_path=None):
    """Write only a NEW private directory after origin and projection validation."""
    origin_dir, destination, audit_dir = Path(origin_dir), Path(destination), Path(audit_dir)
    if origin_dir.is_symlink() or not origin_dir.is_dir() or audit_dir.is_symlink() or not audit_dir.is_dir():
        _fail('Origin and audit directories must be explicit non-symlink directories')
    if destination.exists():
        _fail('Choose a new private export directory; no overwrite')
    blobs = {'origin__'+name:_read_file(origin_dir/name) for name in ORIGIN_NAMES}
    blobs['origin__protocol.json'] = _read_file(protocol_path)
    blobs[ANNOTATION_FILE] = (_read_file(annotations_path) if annotations_path else _encoded(dict(
        schema_version='strategy-screen-annotations/v1', run_id=_loads(blobs['origin__run_manifest.json'])['run_id'], implementations={})))
    for name in ['record_audit.jsonl', 'source_verification.json']:
        blobs[name] = _read_file(audit_dir/name)
    blobs.update(derive(blobs))
    _prepare(blobs, {'run_id':_loads(blobs['run_manifest.json'])['run_id']})
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.corpus-export-', dir=destination.parent))
    try:
        for name, data in blobs.items():
            target = temporary/name
            target.write_bytes(data)
            target.chmod(0o600)
        receipt = build_manifest(temporary, temporary, temporary/'import-manifest.json')
        os.rename(temporary, destination)
    except Exception:
        shutil.rmtree(temporary)
        raise
    return dict(receipt, origin_run_id=_loads(blobs['run_manifest.json'])['run_id'], recomputed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin-dir', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--annotations', type=Path, help='Reviewed metadata annotations for missing fidelity/deep-validation declarations')
    args = parser.parse_args()
    print(json.dumps(export_delta(args.origin_dir,args.protocol,args.audit_dir,args.destination,args.annotations)))


if __name__ == '__main__':
    main()

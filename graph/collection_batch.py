"""Verify a versioned source collection without executing upstream code.

Collection review is independent of formula execution, economic validation and
commercial rights. Public-clone validation cannot re-fetch private raw evidence.
"""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from quantgraph.graph.collection_dedup import collection_source_keys
from quantgraph.graph.metadata_pilot import digest, encoded, read_below, validate


FORMAT = 'quantgraph-source-collection/v1'
SOURCE_FORMAT = 'quantgraph-source-collection-lock/v1'
REVIEW_FORMAT = 'quantgraph-source-collection-reviews/v1'
CORE = {'strategy': ('signal', 'entry', 'exit', 'position'),
        'factor': ('formula', 'inputs', 'calculation')}
CONTENT_ROLES = {'source_code', 'author_document', 'published_definition'}
NO_CREDIT = {'EXISTING_DEFINITION', 'EXACT_DUPLICATE', 'MIRROR_OR_PORT',
             'PARAMETER_ONLY_VARIANT', 'AMBIGUOUS', 'INCOMPLETE'}


def _pin(root, path, pin):
    raw = read_below(root, path)
    if digest(raw) != pin['sha256'] or len(raw) != pin['bytes']:
        raise ValueError('Collection byte pin mismatch: ' + path)
    return raw


def _relative(path):
    return isinstance(path, str) and path and not path.startswith('/') and '\\' not in path and all(
        part not in {'', '.', '..'} for part in path.split('/'))


def _date(value):
    if not isinstance(value, str) or not datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo:
        raise ValueError('Collection evidence requires a timezone-aware timestamp')


def _identity(record):
    return tuple(record[key] for key in ('identity_namespace', 'entity_type', 'record_id'))


def source_text(raw, extraction):
    """Decode explicitly declared representations; never evaluate source code."""
    if extraction == 'utf8':
        return raw.decode('utf-8-sig')
    if extraction == 'json.source':
        value = json.loads(raw)['source']
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Published source response has no source text')
        return value
    raise ValueError('Unsupported source-text extraction')


def record_schema(root):
    """Extend the frozen metadata contract only with document-review status.

    Earlier code-only collections retain their original schema bytes. This
    collection accepts reviewed provider definitions without claiming code review.
    """
    schema = json.loads(read_below(root, 'metadata/schema.json'))
    for group in ('strategy_fields', 'factor_fields'):
        for field in schema['properties'][group]['properties'].values():
            statuses = field['properties']['status']['enum']
            if 'SOURCE_DESCRIPTION_REVIEWED' not in statuses:
                statuses.insert(1, 'SOURCE_DESCRIPTION_REVIEWED')
    return encoded(schema)


def _baseline_review(root, review, baseline_commit):
    """Bind compared definitions to local metadata bytes, not review prose.

    Pins are flat {native_id, path, sha256, row_sha256?} objects. Multiple
    paths may represent one native ID, but every compared ID needs a pin.
    This verifies the retained comparison inputs, not semantic equivalence or
    whether an arbitrary Git commit actually contains those paths.
    """
    if not isinstance(review, dict) or review.get('baseline_commit') != baseline_commit:
        raise ValueError('Collection duplicate review baseline commit mismatch')
    ids, pins = review.get('compared_native_ids'), review.get('compared_rule_pins')
    if (not isinstance(ids, list) or not all(isinstance(i, str) and i.strip() for i in ids)
            or len(set(ids)) != len(ids) or not isinstance(pins, list)):
        raise ValueError('Invalid collection baseline comparison membership')
    scope, terms = review.get('scope'), review.get('search_terms')
    if not ((isinstance(scope, str) and scope.strip()) or
            (isinstance(terms, list) and terms and all(isinstance(t, str) and t.strip() for t in terms))):
        raise ValueError('Collection baseline review needs its search scope')
    pinned_ids, paths = set(), set()
    for pin in pins:
        if not isinstance(pin, dict) or not {'native_id', 'path', 'sha256'} <= pin.keys():
            raise ValueError('Invalid collection baseline pin')
        native_id, path, checksum = pin['native_id'], pin['path'], pin['sha256']
        if (not isinstance(native_id, str) or native_id not in ids
                or not _relative(path) or not path.startswith('metadata/') or not path.endswith('.json')
                or path in paths or not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum)):
            raise ValueError('Invalid or repeated collection baseline pin')
        raw = read_below(root, path)
        if digest(raw) != checksum:
            raise ValueError('Collection baseline metadata byte pin mismatch')
        record = json.loads(raw)
        schema = record.get('schema_version')
        if schema in {'quantgraph-catalog-source-record/v1', 'quantgraph-knowledge-metadata/v1'}:
            known_ids = {record['record_id'], record['native_source_id']}
        elif schema == 'quantgraph-factor-metadata/v1':
            known_ids = {record['record_id'], *record['native_source_ids'], *record['identity']['source_record_ids']}
        else:
            raise ValueError('Collection baseline pin is not a supported metadata record')
        if native_id not in known_ids:
            raise ValueError('Collection baseline native identity mismatch')
        row_hash = record.get('provenance', {}).get('row_sha256')
        if schema == 'quantgraph-catalog-source-record/v1':
            values = {key: value['value'] for key, value in record['reported_fields'].items()}
            actual_row = digest(json.dumps(values, ensure_ascii=False, sort_keys=True,
                                           separators=(',', ':'), allow_nan=False).encode())
            if row_hash != actual_row or values['id'] != record['record_id']:
                raise ValueError('Collection baseline CSV row does not reconstruct')
        if schema == 'quantgraph-catalog-source-record/v1' or 'row_sha256' in pin:
            if (not isinstance(pin.get('row_sha256'), str)
                    or not re.fullmatch(r'[0-9a-f]{64}', pin['row_sha256']) or pin['row_sha256'] != row_hash):
                raise ValueError('Collection baseline CSV row pin mismatch')
        paths.add(path)
        pinned_ids.add(native_id)
    if pinned_ids != set(ids):
        raise ValueError('Collection baseline ID and pin membership mismatch')


def validate_collection(root, directory, *, verify_snapshots=False):
    """Return records and declared reviews after structural/evidence validation.

    This verifies review integrity, not whether an author's algorithm works or
    whether the reviewer's economic-equivalence judgment is mathematically true.
    """
    root, directory = Path(root), str(directory)
    if not _relative(directory):
        raise ValueError('Unsafe collection directory')
    base = root / directory
    manifest = json.loads(read_below(root, directory + '/manifest.json'))
    if manifest.get('schema_version') != FORMAT:
        raise ValueError('Unsupported collection manifest')
    if manifest['batch_id'] != Path(directory).name:
        raise ValueError('Collection batch identity mismatch')
    pins = manifest['files']
    if set(pins) != {'index.json', 'schema.json', 'source-lock.json', 'reviews.json', 'quality-contract.json'}:
        raise ValueError('Collection manifest must pin every control file')
    controls = {name: json.loads(_pin(base, name, pin)) for name, pin in pins.items()}
    # Only the explicit document-review status extension is accepted.
    if read_below(base, 'schema.json') != record_schema(root):
        raise ValueError('Collection record schema drift')
    records = validate(base)
    index = controls['index.json']
    contract = controls['quality-contract.json']
    if (contract['batch_id'] != manifest['batch_id'] or contract['execution_trials'] != 0
            or contract['economic_independence_claimed'] is not False):
        raise ValueError('Collection contract changed its research boundary')
    if not re.fullmatch(r'[0-9a-f]{40}', contract['baseline']['git_commit']):
        raise ValueError('Collection baseline must pin a repository commit')
    lock, reviews = controls['source-lock.json'], controls['reviews.json']
    if lock.get('schema_version') != SOURCE_FORMAT or reviews.get('schema_version') != REVIEW_FORMAT:
        raise ValueError('Unsupported collection evidence format')
    if lock['batch_id'] != manifest['batch_id'] or reviews['batch_id'] != manifest['batch_id']:
        raise ValueError('Collection control file identity mismatch')
    sources = {source['id']: source for source in lock['sources']}
    if len(sources) != len(lock['sources']):
        raise ValueError('Duplicate collection source ID')
    texts = {}
    for sid, source in sources.items():
        url = urlsplit(source['url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Invalid collection source URL')
        if source['http_status'] != 200 or not re.fullmatch(r'[0-9a-f]{64}', source['sha256']):
            raise ValueError('Collection source must be a successful pinned fetch')
        if type(source['bytes']) is not int or source['bytes'] <= 0:
            raise ValueError('Invalid source byte length')
        if source['role'] not in CONTENT_ROLES | {'license', 'attribution', 'source_index'}:
            raise ValueError('Unsupported collection source role')
        _date(source['retrieved_at'])
        snapshot = source['snapshot_path']
        if not _relative(snapshot) or not snapshot.startswith('datasets/raw/sources/'):
            raise ValueError('Unsafe collection snapshot path')
        if source['revision_kind'] == 'git_commit':
            revision = source['revision']
            if (url.hostname != 'github.com' or not re.fullmatch(r'[0-9a-f]{40}', revision)
                    or f'/blob/{revision}/' not in unquote(url.path)):
                raise ValueError('Git source must pin the same full commit in its URL')
        elif source['revision_kind'] != 'content_snapshot' or not source['revision']:
            raise ValueError('Unsupported collection source revision')
        if source['extraction'] not in {'utf8', 'json.source'}:
            raise ValueError('Unsupported source extraction')
        if verify_snapshots:
            raw = _pin(root, snapshot, source)
            texts[sid] = source_text(raw, source['extraction']).splitlines()
    refs = {_identity(ref): ref for ref in index['records']}
    decisions = {_identity(review): review for review in reviews['records']}
    if len(decisions) != len(reviews['records']) or set(decisions) != set(refs):
        raise ValueError('Collection review membership mismatch')
    accepted, seen_definitions, used_sources = Counter(), set(), set()
    source_keys, source_owners = {}, {}
    for record in records:
        key, kind = _identity(record), record['entity_type']
        review, ref = decisions[key], refs[key]
        if review['record_sha256'] != ref['sha256']:
            raise ValueError('Collection review targets another metadata version')
        _date(review['reviewed_at'])
        if not review['reviewer'] or review['method'] != 'PER_RECORD_SOURCE_REVIEW':
            raise ValueError('Collection needs an attributable per-record review')
        declared = {source['id']: source for source in record['sources']}
        if len(declared) != len(record['sources']) or not set(declared) <= set(sources):
            raise ValueError('Collection record source membership mismatch')
        used_sources.update(declared)
        for sid, source in declared.items():
            if any(source[field] != sources[sid][field] for field in ('url', 'revision', 'sha256')):
                raise ValueError('Collection source reference differs from its lock')
        if (record['lab'] is not None or record['rights']['source_fulltext_included'] is not False
                or record['rights']['raw_data_included'] is not False):
            raise ValueError('Collection cannot include source fulltext, data or Lab results')
        if review['states'] != dict(computation_semantics='NOT_EXECUTED', economic_validity='NOT_TESTED',
                                    commercial_use='REVIEW_REQUIRED'):
            raise ValueError('Collection review cannot promote execution or economic status')
        fields = record.get('strategy_fields') or record['factor_fields']
        spans = review['field_spans']
        if not set(spans) <= set(fields):
            raise ValueError('Review references an unknown metadata field')
        for field_name, locations in spans.items():
            for location in locations:
                sid = location['source_id']
                start, end = location['first_line'], location['last_line']
                if sid not in declared or sid not in fields[field_name]['evidence']:
                    raise ValueError('Review span is not field evidence')
                if sources[sid]['role'] not in CONTENT_ROLES:
                    raise ValueError('License or directory cannot establish a definition')
                if (fields[field_name]['status'] == 'SOURCE_CODE_REVIEWED'
                        and sources[sid]['role'] != 'source_code'):
                    raise ValueError('Code-reviewed field requires source-code evidence')
                if (type(start) is not int or type(end) is not int or not 1 <= start <= end
                        or not re.fullmatch(r'[0-9a-f]{64}', location['sha256'])):
                    raise ValueError('Invalid source line span')
                if verify_snapshots:
                    lines = texts[sid]
                    if end > len(lines) or digest('\n'.join(lines[start - 1:end]).encode()) != location['sha256']:
                        raise ValueError('Source span does not match saved bytes')
        outcome = review['dedup']['outcome']
        if outcome not in NO_CREDIT | {'REVIEWED_DISTINCT_CONSTRUCTION'}:
            raise ValueError('Unknown collection duplicate decision')
        if not review['dedup']['reason'] or not review['dedup']['baseline_review']:
            raise ValueError('Collection needs baseline duplicate-review evidence')
        _baseline_review(root, review['dedup']['baseline_review'], contract['baseline']['git_commit'])
        if review['dedup']['unresolved_candidates']:
            if outcome == 'REVIEWED_DISTINCT_CONSTRUCTION':
                raise ValueError('Unresolved similar definitions cannot count as new')
        if outcome == 'REVIEWED_DISTINCT_CONSTRUCTION':
            if review['core_rules_complete'] is not True:
                raise ValueError('Incomplete definition cannot count toward target')
            for field_name in CORE[kind]:
                if fields[field_name]['status'] not in {'SOURCE_CODE_REVIEWED', 'SOURCE_DESCRIPTION_REVIEWED'}:
                    raise ValueError('Core rule is not source reviewed')
                if not spans.get(field_name):
                    raise ValueError('Core rule needs precise source evidence')
            if (not isinstance(review['definition_signature'], str) or not review['definition_signature'].strip()
                    or review['definition_signature'] in seen_definitions):
                raise ValueError('Repeated definition cannot increase collection quota')
            keys = collection_source_keys(record, review, sources)
            for source_key in sorted(keys):
                if source_key in source_owners:
                    raise ValueError(f'Repeated collection source definition: {key} and '
                                     f'{source_owners[source_key]} share {source_key}')
            source_owners.update((source_key, key) for source_key in keys)
            source_keys[key] = keys
            seen_definitions.add(review['definition_signature'])
            accepted[kind] += 1
    if used_sources != set(sources):
        raise ValueError('Unreferenced source in collection lock')
    counts = dict(records=len(records), strategy=accepted['strategy'], factor=accepted['factor'], execution_trials=0)
    if manifest['counts'] != counts:
        raise ValueError('Collection counts differ from reviewed definitions')
    return dict(records=records, reviews=decisions, manifest=manifest, counts=counts, source_keys=source_keys,
                raw_evidence_verified=bool(verify_snapshots))


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--directory', required=True)
    parser.add_argument('--verify-snapshots', action='store_true')
    args = parser.parse_args()
    result = validate_collection(args.root, args.directory, verify_snapshots=args.verify_snapshots)
    print(json.dumps(dict(status='PASS', **result['counts'], raw_evidence_verified=result['raw_evidence_verified'])))


if __name__ == '__main__':
    main()

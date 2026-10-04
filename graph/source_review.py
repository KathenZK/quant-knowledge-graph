"""Validate source follow-ups while preserving the original catalog row and ID."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from quantgraph.graph.metadata_pilot import digest, read_below


FORMAT = 'quantgraph-source-review/v1'
INDEX_FORMAT = 'quantgraph-source-review-index/v1'
FIELDS = ('assets', 'universe', 'signal', 'entry', 'exit', 'position', 'risk', 'cost', 'execution_time', 'timeframe')


def schema():
    text = dict(type='string', minLength=1)
    sha = dict(type='string', pattern='^[0-9a-f]{64}$')
    strings = dict(type='array', uniqueItems=True, items=text)

    def obj(properties):
        return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)

    field = obj(dict(text=text, status=dict(enum=['SOURCE_CODE_REVIEWED', 'SOURCE_DESCRIPTION_REVIEWED',
        'CATALOG_REPORTED_UNVERIFIED', 'MISSING']), evidence=strings))
    result = obj(dict(
        schema_version=dict(const=FORMAT), record_id=dict(type='string', pattern='^M[0-9]{4}$'),
        name=text, reviewed_at=text,
        origin=obj(dict(path=text, sha256=sha, bytes=dict(type='integer', minimum=1), row_sha256=sha, rule_sha256=sha)),
        outcome=dict(enum=['SOURCE_CODE_REVIEWED', 'SOURCE_DESCRIPTION_REVIEWED', 'SOURCE_UNAVAILABLE']),
        identity_match=obj(dict(status=dict(enum=['EXACT_URL', 'OFFICIAL_SOURCE_CHAIN', 'UNRESOLVED']), reason=text, evidence=strings)),
        classification=obj(dict(kind=dict(enum=['strategy', 'factor', 'reference', 'unclassified']), subtype=text,
            reason=text, evidence=strings)),
        sources=dict(type='array', minItems=1, items=obj(dict(id=text, kind=dict(enum=[
            'github_code', 'public_code', 'source_page', 'license', 'availability_check']),
            url=dict(type='string', pattern='^https://'), revision=text, sha256=sha,
            bytes=dict(type='integer', minimum=1), http_status=dict(type='integer', minimum=100, maximum=599),
            retrieved_at=text, snapshot_path=text, locator=text, attribution=text, license=text))),
        fields=obj({name: field for name in FIELDS}),
        corrections=dict(type='array', items=text), missing_information=strings,
        computation_semantics=dict(const='NOT_EXECUTED'), economic_validity=dict(const='NOT_TESTED'),
        commercial_use=dict(const='REVIEW_REQUIRED'), source_fulltext_included=dict(const=False),
    ))
    result['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    return result


def _checked(root, relative, pin):
    raw = read_below(root, relative)
    if digest(raw) != pin['sha256'] or len(raw) != pin['bytes']:
        raise ValueError('Source review digest mismatch: ' + relative)
    return raw


def validate(root, relative_index, csv_rows, *, verify_snapshots=False):
    root = Path(root)
    index = json.loads(read_below(root, relative_index))
    parent = Path(relative_index).parent
    if set(index) != {'schema_version', 'schema', 'records'} or index['schema_version'] != INDEX_FORMAT:
        raise ValueError('Unsupported source review index')
    declared_schema = json.loads(_checked(root, str(parent / index['schema']['path']), index['schema']))
    if declared_schema != schema():
        raise ValueError('Source review schema drift')
    validator = Draft202012Validator(declared_schema)
    records, seen, paths = [], set(), set()
    for ref in index['records']:
        relative = str(parent / ref['path'])
        record = json.loads(_checked(root, relative, ref))
        validator.validate(record)
        rid = record['record_id']
        if ref['path'] != f'records/{rid}.json' or ref['record_id'] != rid or rid in seen or rid not in csv_rows:
            raise ValueError('Source review identity or membership mismatch')
        seen.add(rid); paths.add(relative)
        origin, expected = record['origin'], csv_rows[rid]
        if origin['path'] != expected['path']:
            raise ValueError('Source review origin path mismatch')
        original = json.loads(_checked(root, origin['path'], origin))
        if original != expected['record'] or any(origin[k] != original['provenance'][k] for k in ('row_sha256', 'rule_sha256')):
            raise ValueError('Source review origin version mismatch')
        sources = {s['id']: s for s in record['sources']}
        if len(sources) != len(record['sources']):
            raise ValueError('Duplicate source review evidence ID')
        evidence_groups = [record['classification'], record['identity_match'], *record['fields'].values()]
        for field in evidence_groups:
            if not set(field['evidence']) <= set(sources):
                raise ValueError('Unresolved source review evidence')
        fetched = {sid for sid, s in sources.items() if s['http_status'] == 200
                   and s['kind'] in {'github_code', 'public_code', 'source_page'}}
        code = {sid for sid in fetched if sources[sid]['kind'] in {'github_code', 'public_code'}}
        outcome = record['outcome']
        if outcome == 'SOURCE_UNAVAILABLE':
            if record['classification']['kind'] != 'unclassified' or record['identity_match']['status'] != 'UNRESOLVED':
                raise ValueError('Unavailable source cannot resolve classification or identity')
        else:
            needed = code if outcome == 'SOURCE_CODE_REVIEWED' else fetched
            if (record['classification']['kind'] == 'unclassified' or record['identity_match']['status'] == 'UNRESOLVED'
                    or not set(record['classification']['evidence']) & needed
                    or not set(record['identity_match']['evidence']) & fetched):
                raise ValueError('Reviewed classification needs successful matching source evidence')
        for field in record['fields'].values():
            status = field['status']
            if status in {'SOURCE_CODE_REVIEWED', 'SOURCE_DESCRIPTION_REVIEWED'}:
                needed = code if status == 'SOURCE_CODE_REVIEWED' else fetched
                if outcome == 'SOURCE_UNAVAILABLE' or not set(field['evidence']) & needed:
                    raise ValueError('Asserted field needs successful source evidence')
        for source in sources.values():
            parsed = urlsplit(source['url'])
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('Invalid source review URL')
            snapshot = source['snapshot_path']
            if (not snapshot.startswith('datasets/raw/sources/') or '\\' in snapshot
                    or any(p in {'', '.', '..'} for p in snapshot.split('/'))):
                raise ValueError('Unsafe source review snapshot path')
            if source['kind'] == 'github_code' and (parsed.hostname != 'github.com'
                    or not re.fullmatch(r'[0-9a-f]{40}', source['revision'])
                    or '/blob/' + source['revision'] + '/' not in source['url']):
                raise ValueError('GitHub source review must pin its commit')
            if source['kind'] in {'github_code', 'public_code'} and source['http_status'] != 200:
                raise ValueError('Code snapshot must be a successful fetch')
            if verify_snapshots:
                _checked(root, snapshot, source)
        records.append(record)
    actual = {str(p.relative_to(root)) for p in (root / parent / 'records').rglob('*.json')}
    if actual != paths:
        raise ValueError('Source review directory membership mismatch')
    return index, records


def main():
    from quantgraph.graph.classification_batch import source_rows
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--index', required=True)
    parser.add_argument('--verify-snapshots', action='store_true', help='Also check locally retained original HTTP bytes')
    args = parser.parse_args()
    _, records = validate(args.root, args.index, source_rows(args.root), verify_snapshots=args.verify_snapshots)
    print(json.dumps(dict(status='PASS', records=len(records), outcomes=dict(Counter(r['outcome'] for r in records)),
                          original_snapshots_checked=args.verify_snapshots), ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()

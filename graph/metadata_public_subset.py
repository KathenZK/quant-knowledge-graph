"""Derive a review-only public subset without altering a frozen private v2 batch."""
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator

from quantgraph.graph.corpus_research import _loads, _sha
from quantgraph.graph.metadata_catalog import (
    BATCH, _batch_counts, _immutable_write, _index_ref, _read_knowledge, read_checkpoint,
)
from quantgraph.graph.metadata_pilot import digest, encoded, publication_screen, read_below, validate

FORMAT = 'quantgraph-csv-public-subset/v1'
SCHEMAS = ('schema.json', 'source-record.schema.json')
INVENTORY_KEYS = {'record_id', 'native_source_id', 'csv_row_ordinal', 'row_sha256',
                  'rule_sha256', 'entity_type', 'type_status', 'publication',
                  'knowledge_record', 'review_record'}
MANIFEST_KEYS = {'schema_version', 'source_batch_sha256', 'source_plan_sha256',
    'source_batch_id', 'source_csv_sha256', 'source_batch_record_count', 'record_ids',
    'excluded_record_ids', 'counts', 'publication_status', 'all_fields_reviewed',
    'public_sync_ready', 'knowledge_values_complete_for_included_ids',
    'remote_persistence_verified', 'new_ids', 'new_execution_trials', 'files'}


def _ids(ids):
    if (not isinstance(ids, list) or any(not isinstance(x, str) or not re.fullmatch(r'M\d{4}', x) for x in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('Subset requires unique original Mdddd IDs')


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _screen_record(record):
    if publication_screen(dict(enumerate(_strings(record))))['status'] != 'FIELD_REVIEW_REQUIRED':
        raise ValueError('Subset candidate contains sensitive values')


def _schemas(root):
    # Do not publish arbitrary schema annotations from an input package. Only the
    # exact schemas reviewed with this tool version can be copied, byte for byte.
    approved = Path(__file__).resolve().parents[1] / 'metadata'
    blobs = {}
    for name in SCHEMAS:
        raw = read_below(root, 'metadata/' + name)
        if raw != read_below(approved, name):
            raise ValueError('Subset requires this tool version of the reviewed schemas')
        blobs['metadata/' + name] = raw
    return blobs


def _counts(inventory, refs, original_count, excluded):
    return dict(source_batch_original_ids=original_count, included_original_ids=len(inventory),
        excluded_original_ids=len(excluded), source_records=len(inventory), metadata_records=len(refs),
        strategies=sum(r['entity_type'] == 'strategy' for r in refs),
        factors=sum(r['entity_type'] == 'factor' for r in refs),
        unresolved=sum(r['entity_type'] is None for r in inventory))


def _batch_input(root, pin):
    manifest = read_checkpoint(root, pin, BATCH)
    _sha(manifest['plan_sha256']); _sha(manifest['source']['sha256'])
    if not re.fullmatch(r'batch-\d{4}', manifest['batch_id']):
        raise ValueError('Invalid batch identity')
    inventory = _loads(read_below(root, 'inventory.json', 64 * 1024**2))
    ids = [entry['record_id'] for entry in inventory]; _ids(ids)
    if ids != manifest['record_ids'] or not 1 <= len(ids) <= 250:
        raise ValueError('Batch inventory differs from original IDs')
    files = _schemas(root)
    validator = Draft202012Validator(_loads(files['metadata/source-record.schema.json']))
    records = validate(Path(root) / 'metadata')
    refs = _loads(read_below(root, 'metadata/index.json'))['records']
    expected_files = set(files) | {'inventory.json', 'metadata/index.json'}
    eligible, excluded = [], []
    for entry in inventory:
        _, raw = _read_knowledge(root, entry, manifest['source'], validator)
        record = _loads(raw)
        if (record['classification']['entity_type'] != entry['entity_type']
                or record['classification']['type_status'] != entry['type_status']):
            raise ValueError('Batch classification differs from complete source record')
        expected_files.add(entry['knowledge_record']['path'])
        if entry['publication']['status'] == 'PRIVATE_ONLY_BLOCKED':
            excluded.append(entry['record_id'])
        else:
            eligible.append(entry)
    identities = {(e['record_id'], 'source_record') for e in eligible}
    identities |= {(e['record_id'], e['entity_type']) for e in eligible if e['entity_type']}
    if {(r['record_id'], r['entity_type']) for r in records} != identities:
        raise ValueError('Batch metadata does not match eligible inventory')
    for ref in refs:
        expected_files.add('metadata/' + ref['path'])
    if set(manifest['files']) != expected_files:
        raise ValueError('Batch contains unknown member roles')
    expected_status = 'PRIVATE_ONLY_BLOCKED' if excluded else 'STAGED_REQUIRES_ALL_FIELD_REVIEW_AND_REMOTE_READBACK'
    if (manifest['counts'] != _batch_counts(inventory, refs)
            or manifest['private_only_record_ids'] != excluded
            or manifest['publication_status'] != expected_status or manifest['public_sync_ready'] is not False
            or manifest['knowledge_values_complete'] is not True
            or manifest['new_ids'] != 0 or manifest['new_execution_trials'] != 0):
        raise ValueError('Batch counts or publication flags differ from retained records')
    for record in records:
        _screen_record(record)
    return manifest, eligible, excluded, refs, files


def create_public_subset(batch_root, batch_sha256, output):
    """Read the full private batch, but export only safe original record bytes."""
    try:
        source, eligible, excluded, refs, files = _batch_input(batch_root, batch_sha256)
        by_identity = {(ref['record_id'], ref['entity_type']): ref for ref in refs}
        inventory = []; ordered_refs = []
        for entry in eligible:
            source_ref = by_identity[(entry['record_id'], 'source_record')]
            source_raw = read_below(batch_root, 'metadata/' + source_ref['path'])
            record = _loads(source_raw)
            row = {key: record[key] for key in ['record_id', 'native_source_id', 'publication']}
            row.update({key:record['provenance'][key] for key in ['csv_row_ordinal', 'row_sha256', 'rule_sha256']})
            row.update({key:record['classification'][key] for key in ['entity_type', 'type_status']})
            row['knowledge_record'] = dict(path='metadata/' + source_ref['path'], sha256=digest(source_raw), bytes=len(source_raw))
            row['review_record'] = by_identity.get((entry['record_id'], entry['entity_type']))
            inventory.append(row)
            ordered_refs.append(source_ref)
            if row['review_record'] is not None:
                ordered_refs.append(row['review_record'])
        refs = ordered_refs
        # Build an exact index; never copy the private manifest, complete inventory,
        # excluded record references or any unrelated file into the derived output.
        for ref in refs:
            name = 'metadata/' + ref['path']
            raw = read_below(batch_root, name)
            if ref != _index_ref(ref['path'], raw, ref['record_id'], ref['entity_type']):
                raise ValueError('Unexpected metadata reference fields')
            files[name] = raw
        files['metadata/index.json'] = encoded(dict(schema_version='quantgraph-metadata-index/v1', records=refs))
        files['inventory.json'] = encoded(inventory)
        manifest = dict(schema_version=FORMAT, source_batch_sha256=batch_sha256,
            source_plan_sha256=source['plan_sha256'], source_batch_id=source['batch_id'],
            source_csv_sha256=source['source']['sha256'], source_batch_record_count=len(source['record_ids']),
            record_ids=[e['record_id'] for e in inventory], excluded_record_ids=excluded,
            counts=_counts(inventory, refs, len(source['record_ids']), excluded),
            publication_status='FIELD_REVIEW_REQUIRED', all_fields_reviewed=False, public_sync_ready=False,
            knowledge_values_complete_for_included_ids=True, remote_persistence_verified=False,
            new_ids=0, new_execution_trials=0,
            files={name:dict(sha256=digest(raw), bytes=len(raw)) for name,raw in sorted(files.items())})
    except Exception as error:
        raise ValueError('Public subset source validation failed: ' + type(error).__name__) from None
    _immutable_write(output, files)
    validate(Path(output) / 'metadata')
    # As for v2 batches, publish the completion marker only after validation.
    with (Path(output) / 'manifest.json').open('xb') as stream:
        stream.write(encoded(manifest))
    pin = digest(encoded(manifest))
    check_public_subset(output, pin)
    return dict(subset_sha256=pin, source_batch_sha256=batch_sha256,
                source_batch_id=manifest['source_batch_id'], counts=manifest['counts'],
                excluded_record_ids=excluded, publication_status='FIELD_REVIEW_REQUIRED', public_sync_ready=False)


def _checked_subset(root, pin):
    manifest = read_checkpoint(root, pin, FORMAT)
    if set(manifest) != MANIFEST_KEYS:
        raise ValueError('Unexpected subset manifest fields')
    for key in ['source_batch_sha256', 'source_plan_sha256', 'source_csv_sha256']:
        _sha(manifest[key])
    _ids(manifest['record_ids']); _ids(manifest['excluded_record_ids'])
    if (set(manifest['record_ids']) & set(manifest['excluded_record_ids'])
            or not re.fullmatch(r'batch-\d{4}', manifest['source_batch_id'])
            or type(manifest['source_batch_record_count']) is not int
            or not 1 <= manifest['source_batch_record_count'] <= 250
            or manifest['source_batch_record_count'] != len(manifest['record_ids']) + len(manifest['excluded_record_ids'])):
        raise ValueError('Subset original IDs or excluded counts differ')
    if (manifest['publication_status'] != 'FIELD_REVIEW_REQUIRED'
            or any(manifest[key] is not False for key in ['all_fields_reviewed', 'public_sync_ready', 'remote_persistence_verified'])
            or manifest['knowledge_values_complete_for_included_ids'] is not True
            or manifest['new_ids'] != 0 or manifest['new_execution_trials'] != 0):
        raise ValueError('Subset must remain a review candidate without execution or publication claims')
    files = _schemas(root)
    validator = Draft202012Validator(_loads(files['metadata/source-record.schema.json']))
    inventory = _loads(read_below(root, 'inventory.json', 64 * 1024**2))
    if [e['record_id'] for e in inventory] != manifest['record_ids']:
        raise ValueError('Subset inventory differs from included IDs')
    records = validate(Path(root) / 'metadata')
    index = _loads(read_below(root, 'metadata/index.json'))
    if set(index) != {'schema_version', 'records'}:
        raise ValueError('Unexpected subset index fields')
    refs = index['records']; expected_refs = []; rows = []
    expected_files = set(files) | {'inventory.json', 'metadata/index.json'}
    for entry in inventory:
        if set(entry) != INVENTORY_KEYS or entry['publication']['status'] != 'FIELD_REVIEW_REQUIRED':
            raise ValueError('Subset inventory has unexpected fields or private rows')
        values, raw = _read_knowledge(root, entry, {'sha256':manifest['source_csv_sha256']}, validator)
        record = _loads(raw)
        if (entry['native_source_id'] != entry['record_id']
                or entry['rule_sha256'] != record['provenance']['rule_sha256']
                or entry['entity_type'] != record['classification']['entity_type']
                or entry['type_status'] != record['classification']['type_status']):
            raise ValueError('Subset classification or original identity differs')
        ref = _index_ref(entry['knowledge_record']['path'].removeprefix('metadata/'), raw, entry['record_id'], 'source_record')
        if entry['knowledge_record'] != dict(path='metadata/' + ref['path'], sha256=ref['sha256'], bytes=ref['bytes']):
            raise ValueError('Unexpected subset knowledge reference fields')
        expected_refs.append(ref); rows.append(values)
        if entry['entity_type']:
            review = entry['review_record']
            review_raw = read_below(root, 'metadata/' + review['path'])
            actual = _index_ref(review['path'], review_raw, entry['record_id'], entry['entity_type'])
            if review != actual:
                raise ValueError('Subset review reference differs')
            expected_refs.append(actual)
        elif entry['review_record'] is not None:
            raise ValueError('Unclassified subset record cannot imply a reviewed type')
    if refs != expected_refs:
        raise ValueError('Subset index does not exactly cover original IDs and review layers')
    expected_files |= {'metadata/' + r['path'] for r in refs}
    if set(manifest['files']) != expected_files:
        raise ValueError('Subset contains unknown member roles')
    if manifest['counts'] != _counts(inventory, refs, manifest['source_batch_record_count'], manifest['excluded_record_ids']):
        raise ValueError('Subset counts differ from included records')
    for record in records:
        _screen_record(record)
    return manifest, rows


def check_public_subset(root, pin):
    """Standalone verification; no private original batch is required."""
    try:
        manifest, _ = _checked_subset(root, pin)
    except Exception as error:
        # Schema failures can include complete instances. Never echo those values.
        raise ValueError('Public subset validation failed: ' + type(error).__name__) from None
    return dict(subset_sha256=pin, counts=manifest['counts'], excluded_record_ids=manifest['excluded_record_ids'],
                publication_status='FIELD_REVIEW_REQUIRED', public_sync_ready=False,
                knowledge_values_complete_for_included_ids=True, remote_persistence_verified=False)


def restore_public_subset(root, pin, output):
    try:
        manifest, rows = _checked_subset(root, pin)
    except Exception as error:
        raise ValueError('Public subset restore validation failed: ' + type(error).__name__) from None
    raw = b''.join((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode() for row in rows)
    receipt = dict(status='RESTORED_PRIVATE_ONLY', subset_sha256=pin, records=len(rows),
        excluded_records=len(manifest['excluded_record_ids']), all_eleven_field_values_preserved=True,
        original_batch_complete=not manifest['excluded_record_ids'], public_sync_ready=False,
        exact_original_csv_byte_format=False, sha256=digest(raw), bytes=len(raw), new_execution_trials=0)
    _immutable_write(output, {'private-only/restored-records.jsonl':raw, 'restore-receipt.json':encoded(receipt)})
    return receipt

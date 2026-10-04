"""Collection eligibility pins, evidence roles and honest status boundaries."""
from copy import deepcopy
import json
from pathlib import Path
from shutil import copyfile, copytree

import pytest

from quantgraph.graph.collection_batch import FORMAT, REVIEW_FORMAT, SOURCE_FORMAT, record_schema, validate_collection
from quantgraph.graph.metadata_pilot import digest, encoded


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = 'metadata/collections/test-batch'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else encoded(value)
    path.write_bytes(raw)
    return dict(bytes=len(raw), sha256=digest(raw))


def load(path):
    return json.loads(path.read_bytes())


def refresh(root, directory=DIRECTORY):
    base = root / directory
    index = load(base / 'index.json')
    for ref in index['records']:
        raw = (base / ref['path']).read_bytes()
        ref.update(bytes=len(raw), sha256=digest(raw))
    save(base / 'index.json', index)
    reviews = load(base / 'reviews.json')
    for review in reviews['records']:
        review['record_sha256'] = next(ref['sha256'] for ref in index['records'] if ref['record_id'] == review['record_id'])
    save(base / 'reviews.json', reviews)
    manifest = load(base / 'manifest.json')
    manifest['files'] = {name: dict(bytes=len((base / name).read_bytes()), sha256=digest((base / name).read_bytes()))
                         for name in manifest['files']}
    save(base / 'manifest.json', manifest)


@pytest.fixture
def collection(tmp_path):
    root = tmp_path / 'repository'
    base = root / DIRECTORY
    save(root / 'metadata/schema.json', (ROOT / 'metadata/schema.json').read_bytes())
    save(base / 'schema.json', record_schema(root))
    row = load(ROOT / 'metadata/public-web/20261004-v1/factors/AverageDollarVolume.json')
    row.update(identity_namespace='Synthetic/Library', record_id='SyntheticVolume', native_source_id='SyntheticVolume',
               name='Synthetic test volume', lab=None, relations=[])
    raw = b'inputs = close, volume\noutput = mean(close * volume)\n'
    source = dict(id='code', url='https://github.com/Synthetic/Library/blob/' + 'a' * 40 + '/volume.py',
                  revision='a' * 40, sha256=digest(raw), locator='L1-L2', supports=['Synthetic test definition'],
                  license='MIT', attribution='Synthetic author', verification='SOURCE_CODE_REVIEWED')
    row['sources'] = [source]
    for name, field in row['factor_fields'].items():
        field.update(evidence=['code'], status='SOURCE_CODE_REVIEWED', text='Synthetic ' + name)
    ref = dict(path='factors/SyntheticVolume.json', entity_type='factor', identity_namespace=row['identity_namespace'], record_id=row['record_id'],
               **save(base / 'factors/SyntheticVolume.json', row))
    save(base / 'index.json', dict(schema_version='quantgraph-metadata-index/v1', records=[ref]))
    snapshot = 'datasets/raw/sources/synthetic/volume.py'
    save(root / snapshot, raw)
    lock = dict(**{key: source[key] for key in ['id', 'url', 'revision', 'sha256']}, revision_kind='git_commit', bytes=len(raw),
                http_status=200, role='source_code', extraction='utf8', snapshot_path=snapshot, retrieved_at='2026-10-04T00:00:00Z')
    save(base / 'source-lock.json', dict(schema_version=SOURCE_FORMAT, batch_id='test-batch', sources=[lock]))
    baseline_path = 'metadata/baseline/M0001.json'
    original = ROOT / 'metadata/corpus-checkpoints/grokbot-6973-20261003/batches/batch-0001-v2/metadata/source-records/M0001.json'
    baseline = load(original)
    baseline_pin = save(root / baseline_path, baseline)
    review = dict(identity_namespace=row['identity_namespace'], entity_type='factor', record_id=row['record_id'],
                  record_sha256=ref['sha256'], reviewer='synthetic-reviewer', reviewed_at='2026-10-04T00:01:00Z',
                  method='PER_RECORD_SOURCE_REVIEW', core_rules_complete=True, definition_signature='synthetic-only-definition',
                  subtype='statistical_feature', markets=['SYNTHETIC'], frequencies=['BAR_SERIES'],
                  field_spans={name: [dict(source_id='code', first_line=1, last_line=2, sha256=digest(raw.rstrip(b'\n')))]
                               for name in ['formula', 'inputs', 'calculation']},
                  states=dict(computation_semantics='NOT_EXECUTED', economic_validity='NOT_TESTED', commercial_use='REVIEW_REQUIRED'),
                  dedup=dict(outcome='REVIEWED_DISTINCT_CONSTRUCTION', reason='Synthetic fixture only',
                             baseline_review=dict(baseline_commit='b' * 40, scope='Synthetic comparison fixture',
                                 compared_native_ids=['M0001'], compared_rule_pins=[dict(native_id='M0001',
                                     path=baseline_path, sha256=baseline_pin['sha256'],
                                     row_sha256=baseline['provenance']['row_sha256'])]), unresolved_candidates=[]))
    save(base / 'reviews.json', dict(schema_version=REVIEW_FORMAT, batch_id='test-batch', records=[review]))
    save(base / 'quality-contract.json', dict(batch_id='test-batch', execution_trials=0, economic_independence_claimed=False,
                                            baseline=dict(git_commit='b' * 40)))
    manifest = dict(schema_version=FORMAT, batch_id='test-batch', counts=dict(records=1, strategy=0, factor=1, execution_trials=0),
                    files={name: {} for name in ['index.json', 'schema.json', 'source-lock.json', 'reviews.json', 'quality-contract.json']})
    save(base / 'manifest.json', manifest)
    refresh(root)
    return root


def test_public_and_private_validation_have_distinct_evidence_claims(collection):
    public = validate_collection(collection, DIRECTORY)
    private = validate_collection(collection, DIRECTORY, verify_snapshots=True)
    assert public['counts'] == private['counts'] == dict(records=1, factor=1, strategy=0, execution_trials=0)
    assert public['raw_evidence_verified'] is False and private['raw_evidence_verified'] is True
    (collection / 'datasets/raw/sources/synthetic/volume.py').unlink()
    validate_collection(collection, DIRECTORY)
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_collection(collection, DIRECTORY, verify_snapshots=True)


def test_provider_document_is_reviewable_without_a_code_review_claim(collection):
    base = collection / DIRECTORY
    lock = load(base / 'source-lock.json')
    lock['sources'][0]['role'] = 'published_definition'
    save(base / 'source-lock.json', lock)
    path = base / 'factors/SyntheticVolume.json'
    record = load(path)
    for field in record['factor_fields'].values():
        field['status'] = 'SOURCE_DESCRIPTION_REVIEWED'
    save(path, record); refresh(collection)
    assert validate_collection(collection, DIRECTORY, verify_snapshots=True)['counts']['factor'] == 1
    record['factor_fields']['formula']['status'] = 'SOURCE_CODE_REVIEWED'
    save(path, record); refresh(collection)
    with pytest.raises(ValueError, match='requires source-code evidence'):
        validate_collection(collection, DIRECTORY)


@pytest.mark.parametrize(('field', 'value'), [('http_status', 404), ('http_status', 403), ('role', 'license'),
    ('role', 'source_index'), ('url', 'https://user:pass@example.test/code'), ('revision', 'main'),
    ('snapshot_path', 'datasets/raw/sources/../outside.py'), ('extraction', 'eval'), ('retrieved_at', '2026-10-04')])
def test_unsupported_or_nondefinition_evidence_is_rejected(collection, field, value):
    path = collection / DIRECTORY / 'source-lock.json'
    doc = load(path); doc['sources'][0][field] = value; save(path, doc); refresh(collection)
    with pytest.raises(ValueError):
        validate_collection(collection, DIRECTORY)


@pytest.mark.parametrize('mutation', ['missing_span', 'unknown_evidence', 'bad_line', 'unresolved_duplicate',
                                      'incomplete', 'promoted_economics', 'replay_claim', 'wrong_method'])
def test_incomplete_or_overstated_review_cannot_count(collection, mutation):
    path = collection / DIRECTORY / 'reviews.json'
    doc = load(path); review = doc['records'][0]
    if mutation == 'missing_span': review['field_spans']['formula'] = []
    elif mutation == 'unknown_evidence': review['field_spans']['formula'][0]['source_id'] = 'absent'
    elif mutation == 'bad_line': review['field_spans']['formula'][0]['first_line'] = 0
    elif mutation == 'unresolved_duplicate': review['dedup']['unresolved_candidates'] = ['other-definition']
    elif mutation == 'incomplete': review['core_rules_complete'] = False
    elif mutation == 'promoted_economics': review['states']['economic_validity'] = 'VALIDATED'
    elif mutation == 'replay_claim': review['states']['computation_semantics'] = 'EXECUTED'
    else: review['method'] = 'REGEX_EXTRACTION_ONLY'
    save(path, doc); refresh(collection)
    with pytest.raises(ValueError):
        validate_collection(collection, DIRECTORY)


def test_schema_cannot_be_weakened_even_when_all_pins_are_recomputed(collection):
    path = collection / DIRECTORY / 'schema.json'
    save(path, {}); refresh(collection)
    with pytest.raises(ValueError, match='schema drift'):
        validate_collection(collection, DIRECTORY)


def test_raw_and_span_tampering_are_detected_separately(collection):
    raw_path = collection / 'datasets/raw/sources/synthetic/volume.py'
    raw_path.write_bytes(raw_path.read_bytes() + b'# changed\n')
    with pytest.raises(ValueError, match='byte pin'):
        validate_collection(collection, DIRECTORY, verify_snapshots=True)
    raw_path.write_bytes(raw_path.read_bytes().removesuffix(b'# changed\n'))
    path = collection / DIRECTORY / 'reviews.json'
    doc = load(path); doc['records'][0]['field_spans']['formula'][0]['sha256'] = '0' * 64
    save(path, doc); refresh(collection)
    with pytest.raises(ValueError, match='span'):
        validate_collection(collection, DIRECTORY, verify_snapshots=True)


def test_deferred_definition_gets_no_quota(collection):
    base = collection / DIRECTORY
    doc = load(base / 'reviews.json'); doc['records'][0]['dedup']['outcome'] = 'AMBIGUOUS'
    doc['records'][0]['dedup']['unresolved_candidates'] = ['existing-definition']
    save(base / 'reviews.json', doc)
    manifest = load(base / 'manifest.json'); manifest['counts']['factor'] = 0
    save(base / 'manifest.json', manifest); refresh(collection)
    assert validate_collection(collection, DIRECTORY)['counts']['factor'] == 0


def test_renamed_native_id_does_not_make_identical_reviewed_definition_new(collection):
    base = collection / DIRECTORY
    row = load(base / 'factors/SyntheticVolume.json')
    row.update(record_id='Renamed', native_source_id='Renamed')
    ref = dict(path='factors/Renamed.json', identity_namespace=row['identity_namespace'], entity_type='factor', record_id='Renamed',
               **save(base / 'factors/Renamed.json', row))
    index = load(base / 'index.json'); index['records'].append(ref); save(base / 'index.json', index)
    doc = load(base / 'reviews.json'); new = deepcopy(doc['records'][0]); new['record_id'] = 'Renamed'; doc['records'].append(new)
    save(base / 'reviews.json', doc); refresh(collection)
    with pytest.raises(ValueError, match='Repeated definition'):
        validate_collection(collection, DIRECTORY)


def test_parent_directory_symlink_cannot_escape_repository(collection, tmp_path):
    base = collection / DIRECTORY
    escaped = tmp_path / 'escaped'; escaped.mkdir()
    for path in base.iterdir():
        if path.is_file(): copyfile(path, escaped / path.name)
    alias = collection / 'metadata/alias'; alias.symlink_to(escaped, target_is_directory=True)
    with pytest.raises(ValueError, match='symlinks'):
        validate_collection(collection, 'metadata/alias')


def test_catalog_projection_and_mirrored_registration_do_not_inflate_counts(collection):
    from quantgraph.graph.knowledge_catalog import KnowledgeCatalog
    registry = dict(schema_version='quantgraph-catalog-registry/v1', overlays=[],
                    collections=[dict(id='first', kind='source_collection', path=DIRECTORY)])
    save(collection / 'metadata/catalog.json', registry)
    catalog = KnowledgeCatalog(collection)
    assert catalog.stats()['source_collection_entries'] == 1
    assert catalog.stats()['collected_factor'] == 1
    assert catalog.search(source='Synthetic author', subtype='statistical_feature', status='NOT_TESTED')['total'] == 1
    assert catalog.search(status='VALIDATED')['total'] == 0
    row = catalog.get('Synthetic/Library:SyntheticVolume')
    assert row['kind'] == 'factor' and row['current_version'] is None
    assert row['versions'][0]['record']['review']['states']['economic_validity'] == 'NOT_TESTED'
    copytree(collection / DIRECTORY, collection / 'metadata/mirror/test-batch')
    registry['collections'].append(dict(id='mirror', kind='source_collection', path='metadata/mirror/test-batch'))
    save(collection / 'metadata/catalog.json', registry)
    mirrored = KnowledgeCatalog(collection)
    assert mirrored.stats() == catalog.stats()
    assert mirrored.get('Synthetic/Library:SyntheticVolume') == row


@pytest.mark.parametrize('mutation', ['commit', 'missing_pin', 'extra_id', 'duplicate_id', 'duplicate_path',
    'wrong_hash', 'wrong_row', 'missing_row', 'wrong_identity', 'unsafe_path', 'no_scope'])
def test_baseline_comparison_is_bound_to_real_metadata(collection, mutation):
    path = collection / DIRECTORY / 'reviews.json'
    doc = load(path)
    baseline = doc['records'][0]['dedup']['baseline_review']
    pin = baseline['compared_rule_pins'][0]
    if mutation == 'commit': baseline['baseline_commit'] = '0' * 40
    elif mutation == 'missing_pin': baseline['compared_rule_pins'] = []
    elif mutation == 'extra_id': baseline['compared_native_ids'].append('M999999')
    elif mutation == 'duplicate_id': baseline['compared_native_ids'].append('M0001')
    elif mutation == 'duplicate_path': baseline['compared_rule_pins'].append(deepcopy(pin))
    elif mutation == 'wrong_hash': pin['sha256'] = '0' * 64
    elif mutation == 'wrong_row': pin['row_sha256'] = '0' * 64
    elif mutation == 'missing_row': del pin['row_sha256']
    elif mutation == 'wrong_identity':
        pin['native_id'] = 'M999999'
        baseline['compared_native_ids'] = ['M999999']
    elif mutation == 'unsafe_path': pin['path'] = 'metadata/../baseline/M0001.json'
    else: baseline['scope'] = '  '
    save(path, doc); refresh(collection)
    with pytest.raises(ValueError, match='baseline'):
        validate_collection(collection, DIRECTORY)


def test_baseline_row_must_reconstruct_even_with_refreshed_file_pin(collection):
    path = collection / DIRECTORY / 'reviews.json'
    doc = load(path)
    pin = doc['records'][0]['dedup']['baseline_review']['compared_rule_pins'][0]
    record_path = collection / pin['path']
    record = load(record_path)
    record['reported_fields']['规则']['value'] = 'Changed comparison input'
    pin['sha256'] = save(record_path, record)['sha256']
    save(path, doc); refresh(collection)
    with pytest.raises(ValueError, match='baseline CSV row does not reconstruct'):
        validate_collection(collection, DIRECTORY)


def test_no_baseline_neighbor_still_requires_a_scoped_matching_baseline(collection):
    path = collection / DIRECTORY / 'reviews.json'
    doc = load(path)
    baseline = doc['records'][0]['dedup']['baseline_review']
    baseline.update(compared_native_ids=[], compared_rule_pins=[], scope='', search_terms=['Synthetic volume'])
    save(path, doc); refresh(collection)
    assert validate_collection(collection, DIRECTORY)['counts']['factor'] == 1


def test_baseline_metadata_pin_is_checked_without_private_snapshots(collection):
    path = collection / 'metadata/baseline/M0001.json'
    path.unlink()
    with pytest.raises(ValueError, match='regular non-symlink file'):
        validate_collection(collection, DIRECTORY)


def test_factor_baseline_alias_uses_its_real_source_identity(collection):
    factor = load(next((ROOT / 'metadata/factor-sources/records').glob('*.json')))
    native_id = factor['native_source_ids'][0]
    relative = 'metadata/baseline/factor.json'
    checksum = save(collection / relative, factor)['sha256']
    path = collection / DIRECTORY / 'reviews.json'
    doc = load(path)
    doc['records'][0]['dedup']['baseline_review'].update(compared_native_ids=[native_id],
        compared_rule_pins=[dict(native_id=native_id, path=relative, sha256=checksum)])
    save(path, doc); refresh(collection)
    assert validate_collection(collection, DIRECTORY)['counts']['factor'] == 1


@pytest.mark.parametrize('new_namespace', ['Synthetic/Library', 'Another/Mirror'])
def test_same_definition_cannot_gain_quota_through_a_second_batch(collection, new_namespace):
    second = 'metadata/collections/second-batch'
    base = collection / second
    copytree(collection / DIRECTORY, base)
    row = load(base / 'factors/SyntheticVolume.json')
    row.update(identity_namespace=new_namespace, record_id='Renamed', native_source_id='Renamed')
    (base / 'factors/SyntheticVolume.json').unlink()
    pin = save(base / 'factors/Renamed.json', row)
    index = load(base / 'index.json')
    index['records'][0].update(path='factors/Renamed.json', identity_namespace=new_namespace, record_id='Renamed', **pin)
    save(base / 'index.json', index)
    for name in ['source-lock.json', 'reviews.json', 'quality-contract.json', 'manifest.json']:
        doc = load(base / name); doc['batch_id'] = 'second-batch'
        if name == 'reviews.json':
            doc['records'][0].update(identity_namespace=new_namespace, record_id='Renamed')
        save(base / name, doc)
    refresh(collection, second)
    assert validate_collection(collection, second)['counts']['factor'] == 1
    save(collection / 'metadata/catalog.json', dict(schema_version='quantgraph-catalog-registry/v1', overlays=[],
        collections=[dict(id='first', kind='source_collection', path=DIRECTORY),
                     dict(id='second', kind='source_collection', path=second)]))
    from quantgraph.graph.knowledge_catalog import KnowledgeCatalog
    with pytest.raises(ValueError, match='Repeated collection definition across batches'):
        KnowledgeCatalog(collection)

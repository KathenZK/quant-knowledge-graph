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


@pytest.fixture
def pdf_collection(collection, monkeypatch):
    from quantgraph.graph import collection_batch as module

    base = collection / DIRECTORY
    original = b'%PDF-1.4\nsynthetic PDF input for mocked converter\n'
    text = b'inputs = close, volume\noutput = mean(close * volume)\n'
    pdf_path = 'datasets/raw/sources/synthetic/definition.pdf'
    text_path = 'datasets/raw/sources/synthetic/definition.layout.txt'
    save(collection / pdf_path, original)
    save(collection / text_path, text)
    lock = load(base / 'source-lock.json')
    source = lock['sources'][0]
    source.update(url='https://example.test/definition.pdf', revision='document-v1',
                  revision_kind='content_snapshot', sha256=digest(original), bytes=len(original),
                  snapshot_path=pdf_path, role='author_document', extraction=module.PDF_EXTRACTION,
                  derived_text=dict(parent_pdf_sha256=digest(original), sha256=digest(text),
                      bytes=len(text), snapshot_path=text_path,
                      generator=dict(name='pdftotext', version='pdftotext version 24.04.0',
                                     arguments=module.PDF_ARGUMENTS.copy())))
    save(base / 'source-lock.json', lock)
    path = base / 'factors/SyntheticVolume.json'
    record = load(path)
    record['sources'][0].update({key: source[key] for key in ['url', 'revision', 'sha256']})
    record['sources'][0]['verification'] = 'PINNED_DOCUMENT_REVIEWED'
    for field in record['factor_fields'].values():
        field['status'] = 'SOURCE_DESCRIPTION_REVIEWED'
    save(path, record); refresh(collection)

    def rebuild(raw, version):
        assert raw == original and version == 'pdftotext version 24.04.0'
        return text

    monkeypatch.setattr(module, '_pdf_layout_bytes', rebuild)
    return collection


def test_pdf_parent_and_text_are_separate_verified_objects(pdf_collection, monkeypatch):
    from quantgraph.graph import collection_batch as module

    assert validate_collection(pdf_collection, DIRECTORY, verify_snapshots=True)['raw_evidence_verified']
    # Public clones need neither the private originals nor the converter.
    def forbidden(*args):
        raise AssertionError('Public validation must not run a PDF converter')

    monkeypatch.setattr(module, '_pdf_layout_bytes', forbidden)
    for path in (pdf_collection / 'datasets/raw/sources/synthetic').iterdir():
        path.unlink()
    assert validate_collection(pdf_collection, DIRECTORY)['raw_evidence_verified'] is False


@pytest.mark.parametrize('mutation', ['parent_hash', 'derived_path', 'same_path', 'generator',
                                      'null_generator', 'list_generator', 'arguments',
                                      'version', 'code_role', 'extraction'])
def test_pdf_derivation_contract_cannot_mislabel_evidence(pdf_collection, mutation):
    base = pdf_collection / DIRECTORY
    lock = load(base / 'source-lock.json'); source = lock['sources'][0]
    derived = source['derived_text']
    if mutation == 'parent_hash': derived['parent_pdf_sha256'] = '0' * 64
    elif mutation == 'derived_path': derived['snapshot_path'] = 'datasets/raw/sources/../outside.txt'
    elif mutation == 'same_path': derived['snapshot_path'] = source['snapshot_path']
    elif mutation == 'generator': derived['generator']['name'] = 'python'
    elif mutation == 'null_generator': derived['generator'] = None
    elif mutation == 'list_generator': derived['generator'] = []
    elif mutation == 'arguments': derived['generator']['arguments'] = ['-raw', '-', '-']
    elif mutation == 'version': derived['generator']['version'] = 'unknown'
    elif mutation == 'code_role': source['role'] = 'source_code'
    else: source['extraction'] = 'utf8'
    save(base / 'source-lock.json', lock); refresh(pdf_collection)
    with pytest.raises(ValueError):
        validate_collection(pdf_collection, DIRECTORY)


@pytest.mark.parametrize('object_name', ['definition.pdf', 'definition.layout.txt'])
def test_pdf_original_and_derivative_tampering_are_detected(pdf_collection, object_name):
    path = pdf_collection / 'datasets/raw/sources/synthetic' / object_name
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='byte pin mismatch'):
        validate_collection(pdf_collection, DIRECTORY, verify_snapshots=True)


def test_repinning_forged_pdf_text_still_requires_reconstruction(pdf_collection):
    base = pdf_collection / DIRECTORY
    lock = load(base / 'source-lock.json'); derived = lock['sources'][0]['derived_text']
    raw = b'inputs = forged\noutput = forged\n'
    derived.update(save(pdf_collection / derived['snapshot_path'], raw))
    save(base / 'source-lock.json', lock)
    review = load(base / 'reviews.json')
    for spans in review['records'][0]['field_spans'].values():
        spans[0]['sha256'] = digest(raw.rstrip(b'\n'))
    save(base / 'reviews.json', review); refresh(pdf_collection)
    with pytest.raises(ValueError, match='does not reconstruct'):
        validate_collection(pdf_collection, DIRECTORY, verify_snapshots=True)


def test_pdf_conversion_uses_fixed_arguments_and_checks_version(monkeypatch):
    from types import SimpleNamespace
    from quantgraph.graph import collection_batch as module

    calls = []
    raw = b'%PDF-1.4\nsynthetic'

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command == ['pdftotext', '-v']:
            return SimpleNamespace(stderr=b'pdftotext version 24.04.0\nCopyright\n', stdout=b'')
        assert command == ['pdftotext', '-layout', '-enc', 'UTF-8', '-', '-']
        assert kwargs['input'] == raw
        return SimpleNamespace(stdout=b'reviewed text\n', stderr=b'')

    monkeypatch.setattr(module.subprocess, 'run', run)
    assert module.source_text(raw, module.PDF_EXTRACTION,
                              extractor_version='pdftotext version 24.04.0') == 'reviewed text\n'
    assert all(k['check'] and k['timeout'] == 30 and not k.get('shell') for _, k in calls)
    calls.clear()
    with pytest.raises(ValueError, match='version differs'):
        module.source_text(raw, module.PDF_EXTRACTION, extractor_version='pdftotext version 25.0.0')
    assert len(calls) == 1
    with pytest.raises(ValueError, match='original PDF bytes'):
        module.source_text(b'not a PDF', module.PDF_EXTRACTION,
                           extractor_version='pdftotext version 24.04.0')
    with pytest.raises(ValueError, match='pinned extractor version'):
        module.source_text(raw, module.PDF_EXTRACTION)


def test_missing_pdf_converter_does_not_claim_source_verification(monkeypatch):
    from quantgraph.graph import collection_batch as module

    def unavailable(*args, **kwargs):
        raise FileNotFoundError('pdftotext')

    monkeypatch.setattr(module.subprocess, 'run', unavailable)
    with pytest.raises(ValueError, match='requires the recorded pdftotext'):
        module.source_text(b'%PDF-1.4\n', module.PDF_EXTRACTION,
                           extractor_version='pdftotext version 24.04.0')


def test_empty_pdf_version_output_fails_with_a_useful_diagnostic(monkeypatch):
    from types import SimpleNamespace
    from quantgraph.graph import collection_batch as module

    def empty(command, **kwargs):
        assert command == ['pdftotext', '-v']
        return SimpleNamespace(stderr=b'', stdout=b'')

    monkeypatch.setattr(module.subprocess, 'run', empty)
    with pytest.raises(ValueError, match='version differs'):
        module.source_text(b'%PDF-1.4\n', module.PDF_EXTRACTION,
                           extractor_version='pdftotext version 24.04.0')


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


def add_library_algorithm(root, *, different_spans):
    """Two algorithms in one file, or an editorially renamed copy of one."""
    base = root / DIRECTORY
    row = load(base / 'factors/SyntheticVolume.json')
    row.update(identity_namespace='Another/Library', record_id='OtherAlgorithm', native_source_id='OtherAlgorithm')
    ref = dict(path='factors/OtherAlgorithm.json', entity_type='factor', identity_namespace=row['identity_namespace'],
               record_id=row['record_id'], **save(base / 'factors/OtherAlgorithm.json', row))
    index = load(base / 'index.json'); index['records'].append(ref); save(base / 'index.json', index)
    reviews = load(base / 'reviews.json'); other = deepcopy(reviews['records'][0])
    other.update(identity_namespace=row['identity_namespace'], record_id=row['record_id'], definition_signature='different-signature')
    if different_spans:
        # Same source bytes/input; the second formula occupies a distinct line.
        for name in ('formula', 'calculation'):
            other['field_spans'][name][0].update(first_line=2, last_line=2,
                                               sha256=digest(b'output = mean(close * volume)'))
    reviews['records'].append(other); save(base / 'reviews.json', reviews)
    manifest = load(base / 'manifest.json'); manifest['counts'].update(records=2, factor=2)
    save(base / 'manifest.json', manifest); refresh(root)


def test_renamed_signature_and_namespace_cannot_repeat_same_core_code_in_one_batch(collection):
    add_library_algorithm(collection, different_spans=False)
    with pytest.raises(ValueError, match='Repeated collection source definition'):
        validate_collection(collection, DIRECTORY)


def test_different_algorithms_in_same_source_file_keep_separate_quota(collection):
    add_library_algorithm(collection, different_spans=True)
    result = validate_collection(collection, DIRECTORY, verify_snapshots=True)
    assert result['counts']['factor'] == 2
    from quantgraph.graph.knowledge_catalog import KnowledgeCatalog
    save(collection / 'metadata/catalog.json', dict(schema_version='quantgraph-catalog-registry/v1', overlays=[],
        collections=[dict(id='first', kind='source_collection', path=DIRECTORY)]))
    assert KnowledgeCatalog(collection).stats()['collected_factor'] == 2


def make_tradingview_collection(root):
    """Synthetic Pine bytes with the real duplicate's public/native identities."""
    base = root / DIRECTORY
    row = load(base / 'factors/SyntheticVolume.json')
    row.update(identity_namespace='tradingview/public-script', record_id='9KcWvaBf', native_source_id='9KcWvaBf')
    code = '//@version=6\nindicator("Synthetic review fixture")\nplot(close)\n'
    raw = encoded(dict(source=code, version='1.0'))
    url = 'https://pine-facade.tradingview.com/pine-facade/get/PUB%3B9410078a82ee4673b180a5633bcb016b/1'
    source = row['sources'][0]
    source.update(url=url, revision='PUB;9410078a82ee4673b180a5633bcb016b@1.0', sha256=digest(raw))
    row['rights']['terms_url'] = 'https://www.tradingview.com/script/9KcWvaBf-Original-title/'
    (base / 'factors/SyntheticVolume.json').unlink()
    save(base / 'factors/9KcWvaBf.json', row)
    index = load(base / 'index.json')
    index['records'][0].update(path='factors/9KcWvaBf.json', identity_namespace=row['identity_namespace'], record_id=row['record_id'])
    save(base / 'index.json', index)
    locks = load(base / 'source-lock.json'); lock = locks['sources'][0]
    lock.update(url=url, revision=source['revision'], sha256=source['sha256'], revision_kind='content_snapshot',
                extraction='json.source', bytes=len(raw), snapshot_path='datasets/raw/sources/synthetic/script.json')
    save(root / lock['snapshot_path'], raw); save(base / 'source-lock.json', locks)
    reviews = load(base / 'reviews.json'); review = reviews['records'][0]
    review.update(identity_namespace=row['identity_namespace'], record_id=row['record_id'])
    for spans in review['field_spans'].values():
        spans[0]['sha256'] = digest('\n'.join(code.splitlines()[:2]).encode())
    save(base / 'reviews.json', reviews); refresh(root)


@pytest.mark.parametrize('same_review_mirror', [False, True])
def test_tradingview_duplicate_across_batches_ignores_namespace_and_changed_summary(collection, same_review_mirror):
    from quantgraph.graph.knowledge_catalog import KnowledgeCatalog
    make_tradingview_collection(collection)
    second = 'metadata/mirror/test-batch'
    base = collection / second
    copytree(collection / DIRECTORY, base)
    if not same_review_mirror:
        row = load(base / 'factors/9KcWvaBf.json')
        row.update(identity_namespace='TradingView', name='A newly worded summary')
        row['factor_fields']['formula']['text'] = 'Another description of precisely the same script'
        row['rights']['terms_url'] = 'https://cn.tradingview.com/script/9KcWvaBf-New-slug/'
        save(base / 'factors/9KcWvaBf.json', row)
        index = load(base / 'index.json'); index['records'][0]['identity_namespace'] = 'TradingView'
        save(base / 'index.json', index)
        reviews = load(base / 'reviews.json'); review = reviews['records'][0]
        review.update(identity_namespace='TradingView', definition_signature='renamed-signature-not-proof')
        # Different editorial ranges defeat an exact span-set comparison, but
        # not the same native PUB/version and code identity.
        for spans in review['field_spans'].values():
            spans[0].update(first_line=2, last_line=3,
                           sha256=digest(b'indicator("Synthetic review fixture")\nplot(close)'))
        save(base / 'reviews.json', reviews); refresh(collection, second)
    assert validate_collection(collection, second, verify_snapshots=True)['counts']['factor'] == 1
    save(collection / 'metadata/catalog.json', dict(schema_version='quantgraph-catalog-registry/v1', overlays=[],
        collections=[dict(id='first', kind='source_collection', path=DIRECTORY),
                     dict(id='second', kind='source_collection', path=second)]))
    if same_review_mirror:
        assert KnowledgeCatalog(collection).stats()['collected_factor'] == 1
    else:
        with pytest.raises(ValueError, match='Repeated collection source definition across batches'):
            KnowledgeCatalog(collection)

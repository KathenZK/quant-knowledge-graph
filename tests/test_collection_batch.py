"""Collection eligibility pins, evidence roles and honest status boundaries."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from shutil import copyfile, copytree
import tarfile

import pytest

from quantgraph.graph.collection_batch import FORMAT, REVIEW_FORMAT, SOURCE_FORMAT, TAR_EXTRACTION, _git_commit_url, record_schema, source_text, validate_collection
from quantgraph.graph.metadata_pilot import digest, encoded


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = 'metadata/collections/test-batch'


def html_code_fixture(root):
    from quantgraph.graph.collection_batch import HTML_PRE_DECODER, HTML_PRE_EXTRACTION
    base = root / DIRECTORY
    raw = b'<div id="other"><pre>ignore()</pre></div><div id="file_py"><pre>x = 1\nx + 2\n</pre></div>'
    decoded = b'x = 1\nx + 2\n'
    lock = load(base / 'source-lock.json')
    source = lock['sources'][0]
    source.update(url='https://example.org/published-code.html', revision='snapshot-one',
                  revision_kind='content_snapshot', extraction=HTML_PRE_EXTRACTION,
                  selector='div#file_py pre', sha256=digest(raw), bytes=len(raw),
                  snapshot_path='datasets/raw/sources/synthetic/source.html',
                  derived_text=dict(parent_html_sha256=digest(raw), sha256=digest(decoded), bytes=len(decoded),
                                    snapshot_path='datasets/raw/sources/synthetic/decoded.py', decoder=HTML_PRE_DECODER))
    save(root / source['snapshot_path'], raw)
    save(root / source['derived_text']['snapshot_path'], decoded)
    save(base / 'source-lock.json', lock)
    row = load(base / 'factors/SyntheticVolume.json')
    row['sources'][0].update({key: source[key] for key in ['url', 'revision', 'sha256']})
    save(base / 'factors/SyntheticVolume.json', row)
    reviews = load(base / 'reviews.json')
    for spans in reviews['records'][0]['field_spans'].values():
        spans[0]['sha256'] = digest(decoded.rstrip(b'\n'))
    save(base / 'reviews.json', reviews)
    refresh(root)
    return source


def test_html_code_preserves_entities_unicode_and_original_newlines():
    from quantgraph.graph.collection_batch import HTML_PRE_EXTRACTION
    raw = ('<pre>outside</pre><div id="code"><div><pre>\r\n'
           '<span>值 = &quot;&lt;&amp;&gt;&quot;</span>\r\nx = &#49;\n'
           '</pre></div></div><script>do_not_run()</script>').encode()
    assert source_text(raw, HTML_PRE_EXTRACTION, selector='div#code pre') == '\r\n值 = "<&>"\r\nx = 1\n'


@pytest.mark.parametrize('raw', [
    b'<div id="other"><pre>x</pre></div>',
    b'<div id="code"><pre>x</pre></div><div id="code"><pre>y</pre></div>',
    b'<div id="code" id="other"><pre>x</pre></div>',
    b'<span id="code"><pre>x</pre></span>',
    b'<div id="code"><pre>x</pre><pre>y</pre></div>',
    b'<div id="code"><pre><pre>x</pre></pre></div>',
    b'<div id="code"><pre>x</div></pre>',
    b'<div id="code"><pre>x</pre>',
    b'<div id="code"></div><pre>x</pre>',
    b'<div id="code"><pre> </pre></div>',
    b'<div id="code"><pre><script>x</script></pre></div>',
    b'<template><div id="code"><pre>x</pre></div></template>',
    b'<noscript><div id="code"><pre>x</pre></div></noscript>',
    b'<div id="code"><template><pre>x</pre></template></div>',
    b'<div id="code"><noscript><pre>x</pre></noscript></div>',
    b'<div id="code"><pre>actual()<template>unselected()</template></pre></div>',
    b'<div id="code"><pre>actual()<noscript>conditional()</noscript></pre></div>',
    b'<script/><div id="code"><pre>x</pre></div>',
    b'<template/><div id="code"><pre>x</pre></div>',
    b'<textarea/><div id="code"><pre>x</pre></div>',
    b'<xmp><div id="code"><pre>x</pre></div></xmp>',
    b'<textarea><div id="code"><pre>x</pre></div></textarea>',
    b'<div id="code"><iframe><pre>x</pre></iframe></div>',
    b'<div id="code"><pre>\xff</pre></div>',
])
def test_html_code_rejects_missing_ambiguous_or_incomplete_blocks(raw):
    from quantgraph.graph.collection_batch import HTML_PRE_EXTRACTION
    with pytest.raises((ValueError, UnicodeError)):
        source_text(raw, HTML_PRE_EXTRACTION, selector='div#code pre')


def test_html_code_private_validation_rebuilds_pinned_parent(collection):
    source = html_code_fixture(collection)
    validate_collection(collection, DIRECTORY)
    validate_collection(collection, DIRECTORY, verify_snapshots=True)
    # A separately pinned derivative cannot silently substitute different code.
    base = collection / DIRECTORY
    lock = load(base / 'source-lock.json')
    other = b'other = 1\nother + 2\n'
    lock['sources'][0]['derived_text'].update(save(collection / source['derived_text']['snapshot_path'], other))
    save(base / 'source-lock.json', lock)
    refresh(collection)
    with pytest.raises(ValueError, match='does not reconstruct'):
        validate_collection(collection, DIRECTORY, verify_snapshots=True)


@pytest.mark.parametrize('mutation', ['selector', 'parent', 'same_path', 'unsafe_path', 'decoder',
                                      'bytes_bool', 'raw_limit', 'text_limit', 'role', 'wrong_extraction'])
def test_html_code_public_contract_rejects_invalid_derivation(collection, mutation):
    from quantgraph.graph.collection_batch import CODEC_MAX_RAW, CODEC_MAX_TEXT
    html_code_fixture(collection)
    base = collection / DIRECTORY
    lock = load(base / 'source-lock.json')
    source = lock['sources'][0]
    derivative = source['derived_text']
    if mutation == 'selector': source['selector'] = 'div pre'
    elif mutation == 'parent': derivative['parent_html_sha256'] = '0' * 64
    elif mutation == 'same_path': derivative['snapshot_path'] = source['snapshot_path']
    elif mutation == 'unsafe_path': derivative['snapshot_path'] = 'datasets/raw/sources/../x'
    elif mutation == 'decoder': derivative['decoder'] = 'eval'
    elif mutation == 'bytes_bool': derivative['bytes'] = True
    elif mutation == 'raw_limit': source['bytes'] = CODEC_MAX_RAW + 1
    elif mutation == 'text_limit': derivative['bytes'] = CODEC_MAX_TEXT + 1
    elif mutation == 'role': source['role'] = 'license'
    else: source['extraction'] = 'utf8'
    save(base / 'source-lock.json', lock)
    refresh(collection)
    with pytest.raises(ValueError):
        validate_collection(collection, DIRECTORY)


def tar_source(entries):
    """Synthetic source bytes only; no source programs are executed."""
    output = BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, content, kind in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.size = len(content) if kind == tarfile.REGTYPE else 0
            if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
                info.linkname = 'package/definition.txt'
            archive.addfile(info, BytesIO(content) if kind == tarfile.REGTYPE else None)
    return output.getvalue()


def member_pin(name, content):
    return dict(member=name, sha256=digest(content), bytes=len(content))


def test_archive_text_uses_declared_order_original_bytes_and_member_headers():
    a, b = b'first\r\nsecond\r\n', '第三行'.encode()
    raw = tar_source([('package/b.txt', b, tarfile.REGTYPE),
                      ('package/a.txt', a, tarfile.REGTYPE)])
    members = [member_pin('package/a.txt', a), member_pin('package/b.txt', b)]
    assert source_text(raw, TAR_EXTRACTION, archive_members=members) == (
        '@@ archive member package/a.txt\nfirst\r\nsecond\r\n'
        '@@ archive member package/b.txt\n第三行\n')


@pytest.mark.parametrize('kind', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE])
def test_archive_rejects_selected_links_and_nonfiles(kind):
    raw = tar_source([('package/definition.txt', b'', kind)])
    with pytest.raises(ValueError, match='unique regular file'):
        source_text(raw, TAR_EXTRACTION,
                    archive_members=[member_pin('package/definition.txt', b'')])


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'a/../b', 'a\\b',
                                  'a\nb', 'a\rb', 'a\x00b', 'a//b'])
def test_archive_rejects_unsafe_member_contracts_without_raw_files(name):
    with pytest.raises(ValueError, match='member pin'):
        source_text(b'', TAR_EXTRACTION, archive_members=[member_pin(name, b'')])


@pytest.mark.parametrize('mutation', ['missing', 'duplicate_archive', 'duplicate_pin',
                                      'wrong_hash', 'wrong_size', 'invalid_utf8', 'invalid_tar'])
def test_archive_requires_unambiguous_exact_member_bytes(mutation):
    content = b'formula\n'
    entries = [('package/definition.txt', content, tarfile.REGTYPE)]
    pins = [member_pin('package/definition.txt', content)]
    if mutation == 'missing':
        entries = []
    elif mutation == 'duplicate_archive':
        entries *= 2
    elif mutation == 'duplicate_pin':
        pins *= 2
    elif mutation == 'wrong_hash':
        pins[0]['sha256'] = '0' * 64
    elif mutation == 'wrong_size':
        pins[0]['bytes'] += 1
    elif mutation == 'invalid_utf8':
        entries[0] = ('package/definition.txt', b'\xff', tarfile.REGTYPE)
        pins[0] = member_pin('package/definition.txt', b'\xff')
    raw = b'not a gzip archive' if mutation == 'invalid_tar' else tar_source(entries)
    with pytest.raises(ValueError):
        source_text(raw, TAR_EXTRACTION, archive_members=pins)


def test_archive_collection_keeps_http_parent_and_member_evidence(collection):
    base = collection / DIRECTORY
    content = b'input\r\nformula\r\n'
    raw = tar_source([('package/definition.txt', content, tarfile.REGTYPE)])
    lock = load(base / 'source-lock.json')
    source = lock['sources'][0]
    source.update(url='https://example.org/package.tar.gz', revision='archive-snapshot',
                  revision_kind='content_snapshot', sha256=digest(raw), bytes=len(raw),
                  extraction=TAR_EXTRACTION,
                  archive_members=[member_pin('package/definition.txt', content)],
                  snapshot_path='datasets/raw/sources/synthetic/package.tar.gz')
    save(collection / source['snapshot_path'], raw)
    save(base / 'source-lock.json', lock)
    record = load(base / 'factors/SyntheticVolume.json')
    record['sources'][0].update({key: source[key] for key in ['url', 'revision', 'sha256']})
    save(base / 'factors/SyntheticVolume.json', record)
    review = load(base / 'reviews.json')
    for locations in review['records'][0]['field_spans'].values():
        locations[0].update(first_line=2, last_line=3, sha256=digest(b'input\nformula'))
    save(base / 'reviews.json', review)
    refresh(collection)
    assert validate_collection(collection, DIRECTORY, verify_snapshots=True)['raw_evidence_verified']
    (collection / source['snapshot_path']).unlink()
    assert not validate_collection(collection, DIRECTORY)['raw_evidence_verified']
    # Public verification must still reject corrupt member declarations.
    source['archive_members'][0]['member'] = '../outside'
    save(base / 'source-lock.json', lock)
    refresh(collection)
    with pytest.raises(ValueError, match='member pin'):
        validate_collection(collection, DIRECTORY)


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


@pytest.mark.parametrize('route', [
    'https://github.com/Owner/Repo/blob/{commit}/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/file.py',
])
@pytest.mark.parametrize('suffix', ['', '#L1', '#L2-L20'])
def test_git_commit_routes_keep_source_code_and_original_url(collection, route, suffix):
    base = collection / DIRECTORY
    lock = load(base / 'source-lock.json')
    source = lock['sources'][0]
    url = route.format(commit=source['revision']) + suffix
    source['url'] = url
    save(base / 'source-lock.json', lock)
    record_path = base / 'factors/SyntheticVolume.json'
    record = load(record_path)
    record['sources'][0]['url'] = url
    save(record_path, record)
    refresh(collection)
    assert validate_collection(collection, DIRECTORY, verify_snapshots=True)['raw_evidence_verified']
    assert load(base / 'source-lock.json')['sources'][0] == source
    assert source['revision_kind'] == 'git_commit' and source['role'] == 'source_code'
    assert all(field['status'] == 'SOURCE_CODE_REVIEWED' for field in record['factor_fields'].values())
    (collection / source['snapshot_path']).unlink()
    assert not validate_collection(collection, DIRECTORY)['raw_evidence_verified']


@pytest.mark.parametrize('url', [
    'https://github.com/Owner/Repo_1.0/blob/{commit}/%E7%AD%96%E7%95%A5.py#L1-L1',
    'https://raw.githubusercontent.com/Owner/Repo_1.0/{commit}/dir/a%20b.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/LICENSE',
    'https://github.com/Owner/Repo/blob/{commit}/a%23b%3Fc.py',
    'https://GITHUB.COM/Owner/Repo/blob/{commit}/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/blob/main/file.py',
])
def test_git_commit_routes_preserve_encoded_filenames_and_line_locations(url):
    _git_commit_url(url.format(commit='a' * 40), 'a' * 40)


@pytest.mark.parametrize('url', [
    'https://github.com/Owner/Repo/blob/main/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/main/file.py',
    'https://github.com/Owner/Repo/blob/aaaaaaa/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/aaaaaaa/file.py',
    'https://github.com/Owner/Repo/blob/{other}/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/{other}/file.py',
    'https://github.com/Owner/Repo/tree/{commit}/file.py',
    'https://github.com/Owner/Repo/prefix/blob/{commit}/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/blob/{commit}/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/prefix/{commit}/file.py',
    'https://github.com//Repo/blob/{commit}/file.py',
    'https://raw.githubusercontent.com//Repo/{commit}/file.py',
    'https://github.com/Owner//blob/{commit}/file.py',
    'https://raw.githubusercontent.com/Owner//{commit}/file.py',
    'https://github.com/Owner/Repo/blob/{commit}',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}',
    'https://github.com/Owner/Repo/blob/{commit}/',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/',
    'https://github.com/Owner/Repo/blob/{commit}/dir//file.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/dir/../file.py',
    'https://github.com/Owner/Repo/blob/{commit}/./file.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/%2e%2e/file.py',
    'https://github.com/Owner/Repo/blob/{commit}/%252e%252e/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/dir%2ffile.py',
    'https://github.com/Owner/Repo/blob/{commit}/dir%5cfile.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/dir\\file.py',
    'https://github.com/Owner%2fOther/Repo/blob/{commit}/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/bad%ZZ.py',
    'https://github.com/Owner/Repo/blob/{commit}/bad%ff.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/bad%00.py',
    'https://github.com/Owner/Repo/blob/{commit}/bad%0a.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/bad%C2%85.py',
    'https://github.com/Owner/Repo/blob/{commit}/file.py?ref=main',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/file.py?raw=1',
    'https://github.com/Owner/Repo/blob/{commit}/file.py#L0',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/file.py#L5-L2',
    'https://github.com/Owner/Repo/blob/{commit}/file.py#blob/{commit}/fake',
    'https://github.com.evil.example/Owner/Repo/blob/{commit}/file.py',
    'https://raw.githubusercontent.com.evil.example/Owner/Repo/{commit}/file.py',
    'https://evil.example/Owner/Repo/blob/{commit}/file.py',
    'http://github.com/Owner/Repo/blob/{commit}/file.py',
    'http://raw.githubusercontent.com/Owner/Repo/{commit}/file.py',
    'https://user@github.com/Owner/Repo/blob/{commit}/file.py',
    'https://raw.githubusercontent.com:443/Owner/Repo/{commit}/file.py',
    'https://github.com:444/Owner/Repo/blob/{commit}/file.py',
    '\nhttps://github.com/Owner/Repo/blob/{commit}/file.py',
    'https://raw.githubuser\tcontent.com/Owner/Repo/{commit}/file.py',
    'https://github.com/Owner/Repo/blob/{commit}/fi\rle.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/file.py#L1\n',
    ' https://github.com/Owner/Repo/blob/{commit}/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/file\x7f.py',
])
def test_git_commit_routes_reject_wrong_identity_and_ambiguous_paths(url):
    with pytest.raises(ValueError):
        _git_commit_url(url.format(commit='a' * 40, other='b' * 40), 'a' * 40)


@pytest.mark.parametrize('revision', ['main', 'a' * 7, 'a' * 39, 'a' * 41, 'A' * 40, None])
def test_git_commit_revision_requires_full_lowercase_commit(revision):
    with pytest.raises(ValueError):
        _git_commit_url('https://raw.githubusercontent.com/O/R/' + 'a' * 40 + '/x', revision)


@pytest.mark.parametrize('url', [
    'https://github.com/Owner/Repo/prefix/blob/{commit}/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/main/blob/{commit}/file.py',
    'https://git\thub.com/Owner/Repo/blob/{commit}/file.py',
    'https://raw.githubusercontent.com/Owner/Repo/{commit}/file%0a.py',
])
def test_git_commit_validation_rejects_after_all_pins_are_refreshed(collection, url):
    base = collection / DIRECTORY
    lock = load(base / 'source-lock.json')
    source = lock['sources'][0]
    source['url'] = url.format(commit=source['revision'])
    save(base / 'source-lock.json', lock)
    record_path = base / 'factors/SyntheticVolume.json'
    record = load(record_path)
    record['sources'][0]['url'] = source['url']
    save(record_path, record)
    refresh(collection)
    with pytest.raises(ValueError):
        validate_collection(collection, DIRECTORY)


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


def visual_png(width=2, height=2, value=0):
    """A real tiny RGB PNG made without an image dependency."""
    import struct
    import zlib

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data)))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + bytes([value]) * width * 3) * height))
            + chunk(b'IEND', b''))


@pytest.fixture
def visual_collection(collection, monkeypatch):
    from types import SimpleNamespace
    from quantgraph.graph import collection_batch as module

    base = collection / DIRECTORY
    original = b'%PDF-1.4\nsynthetic PDF for the mocked Poppler tools\n'
    snapshots = {1: visual_png(), 2: visual_png(value=255)}
    lock = load(base / 'source-lock.json')
    source = lock['sources'][0]
    source.update(url='https://example.test/scanned.pdf', revision='document-v1',
                  revision_kind='content_snapshot', sha256=digest(original), bytes=len(original),
                  snapshot_path='datasets/raw/sources/synthetic/scanned.pdf',
                  role='author_document', extraction=module.PDF_VISUAL_EXTRACTION)
    source['visual_pages'] = dict(page_count=2,
        inspector=dict(name='pdfinfo', version='pdfinfo version 24.04.0'),
        generator=dict(name='pdftoppm', version='pdftoppm version 24.04.0', dpi=125,
                       arguments=['-singlefile', '-png']), pages=[])
    save(collection / source['snapshot_path'], original)
    for number, raw in snapshots.items():
        path = f'datasets/raw/sources/synthetic/scan-{number}.png'
        pin = save(collection / path, raw)
        source['visual_pages']['pages'].append(dict(physical_page=number,
            parent_pdf_sha256=source['sha256'], snapshot_path=path, **pin))
    save(base / 'source-lock.json', lock)
    path = base / 'factors/SyntheticVolume.json'
    record = load(path)
    record['sources'][0].update({key: source[key] for key in ['url', 'revision', 'sha256']})
    record['sources'][0].update(locator='physical pages 1-2', verification='PINNED_DOCUMENT_REVIEWED')
    for field in record['factor_fields'].values():
        field['status'] = 'SOURCE_DESCRIPTION_REVIEWED'
    save(path, record)
    reviews = load(base / 'reviews.json')
    review = reviews['records'][0]
    review['field_spans'] = {}
    review['field_pages'] = {name: [dict(source_id='code', physical_page=n, sha256=digest(snapshots[n]))
                                  for n in [1, 2]] for name in ['formula', 'inputs', 'calculation']}
    save(base / 'reviews.json', reviews); refresh(collection)

    def run(command, **kwargs):
        assert kwargs.get('shell') is None
        assert kwargs['check'] is True and kwargs['timeout'] in {30, 60}
        assert kwargs['env']['LC_ALL'] == 'C'
        if command in [['pdfinfo', '-v'], ['pdftoppm', '-v']]:
            return SimpleNamespace(stderr=(command[0] + ' version 24.04.0\n').encode(), stdout=b'')
        assert kwargs['input'] == original
        number = int(command[2])
        if command[0] == 'pdfinfo':
            assert command == ['pdfinfo', '-f', str(number), '-l', str(number), '-box', '-']
            return SimpleNamespace(stdout=(f'Pages: 2\nPage {number} rot: 0\n'
                f'Page {number} MediaBox: 0 0 1.152 1.152\n').encode(), stderr=b'')
        assert command == ['pdftoppm', '-f', str(number), '-l', str(number), '-r', '125', '-singlefile', '-png', '-']
        kwargs['stdout'].write(snapshots[number])
        return SimpleNamespace(stderr=b'')

    monkeypatch.setattr(module.subprocess, 'run', run)
    return collection


def test_visual_pages_verify_real_image_bytes_and_need_no_tools_or_raw_publicly(visual_collection, monkeypatch):
    from quantgraph.graph import collection_batch as module
    assert validate_collection(visual_collection, DIRECTORY, verify_snapshots=True)['counts']['factor'] == 1

    def forbidden(*args, **kwargs):
        raise AssertionError('Public-clone validation must not run external tools')

    monkeypatch.setattr(module.subprocess, 'run', forbidden)
    for path in (visual_collection / 'datasets/raw/sources/synthetic').iterdir():
        path.unlink()
    assert validate_collection(visual_collection, DIRECTORY)['raw_evidence_verified'] is False


@pytest.mark.parametrize('mutation', [
    'page_bool', 'page_zero', 'page_overflow', 'count_bool', 'count_overflow', 'duplicate_page',
    'duplicate_path', 'unsafe_path', 'control_path', 'wrong_extension', 'parent_path', 'parent_hash',
    'missing_page', 'too_many_pages', 'bytes_bool', 'huge_png', 'huge_pdf', 'empty_pages',
    'bad_hash', 'bad_dpi', 'dpi_bool', 'bad_args', 'renderer', 'version', 'inspector', 'text_mix',
    'source_code', 'license', 'attribution', 'source_index', 'text_extraction'])
def test_visual_lock_rejects_invalid_provenance_and_resource_contracts_publicly(visual_collection, mutation):
    root = visual_collection
    path = root / DIRECTORY / 'source-lock.json'
    doc = load(path)
    source = doc['sources'][0]
    visual = source['visual_pages']
    page = visual['pages'][0]
    if mutation == 'page_bool': page['physical_page'] = True
    elif mutation == 'page_zero': page['physical_page'] = 0
    elif mutation == 'page_overflow': page['physical_page'] = 3
    elif mutation == 'count_bool': visual['page_count'] = True
    elif mutation == 'count_overflow': visual['page_count'] = 1025
    elif mutation == 'duplicate_page': visual['pages'].append(deepcopy(page))
    elif mutation == 'duplicate_path': visual['pages'][1]['snapshot_path'] = page['snapshot_path']
    elif mutation == 'unsafe_path': page['snapshot_path'] = 'datasets/raw/sources/../outside.png'
    elif mutation == 'control_path': page['snapshot_path'] = 'datasets/raw/sources/a\nb.png'
    elif mutation == 'wrong_extension': page['snapshot_path'] = 'datasets/raw/sources/pretend.txt'
    elif mutation == 'parent_path': page['snapshot_path'] = source['snapshot_path']
    elif mutation == 'parent_hash': page['parent_pdf_sha256'] = '0' * 64
    elif mutation == 'missing_page': del page['physical_page']
    elif mutation == 'too_many_pages': visual['pages'] *= 33
    elif mutation == 'bytes_bool': page['bytes'] = True
    elif mutation == 'huge_png': page['bytes'] = 8 * 1024 * 1024 + 1
    elif mutation == 'huge_pdf': source['bytes'] = 8 * 1024 * 1024 + 1
    elif mutation == 'empty_pages': visual['pages'] = []
    elif mutation == 'bad_hash': page['sha256'] = 'not a hash'
    elif mutation == 'bad_dpi': visual['generator']['dpi'] = 201
    elif mutation == 'dpi_bool': visual['generator']['dpi'] = True
    elif mutation == 'bad_args': visual['generator']['arguments'].append('-cropbox')
    elif mutation == 'renderer': visual['generator']['name'] = 'sh'
    elif mutation == 'version': visual['generator']['version'] = ''
    elif mutation == 'inspector': visual['inspector']['name'] = 'pdftotext'
    elif mutation == 'text_mix': source['derived_text'] = {}
    elif mutation == 'text_extraction': source['extraction'] = 'utf8'
    else: source['role'] = mutation
    save(path, doc); refresh(root)
    with pytest.raises(ValueError):
        validate_collection(root, DIRECTORY)


@pytest.mark.parametrize('mutation', ['unknown_field', 'duplicate', 'unknown_source', 'unselected_page',
                                      'page_bool', 'wrong_hash', 'extra_line_span', 'empty', 'non_list'])
def test_visual_field_references_are_exact_and_unique(visual_collection, mutation):
    root = visual_collection
    path = root / DIRECTORY / 'reviews.json'
    doc = load(path); review = doc['records'][0]
    refs = review['field_pages']['formula']
    if mutation == 'unknown_field': review['field_pages']['not_a_field'] = deepcopy(refs)
    elif mutation == 'duplicate': refs.append(deepcopy(refs[0]))
    elif mutation == 'unknown_source': refs[0]['source_id'] = 'unknown'
    elif mutation == 'unselected_page': refs[0]['physical_page'] = 3
    elif mutation == 'page_bool': refs[0]['physical_page'] = True
    elif mutation == 'wrong_hash': refs[0]['sha256'] = '0' * 64
    elif mutation == 'extra_line_span': refs[0]['first_line'] = 1
    elif mutation == 'empty': review['field_pages']['formula'] = []
    else: review['field_pages']['formula'] = refs[0]
    save(path, doc); refresh(root)
    with pytest.raises(ValueError):
        validate_collection(root, DIRECTORY)


def test_visual_core_needs_declared_field_evidence_and_cannot_claim_code_review(visual_collection):
    root = visual_collection
    path = root / DIRECTORY / 'factors/SyntheticVolume.json'
    doc = load(path)
    doc['factor_fields']['formula']['status'] = 'SOURCE_CODE_REVIEWED'
    save(path, doc); refresh(root)
    with pytest.raises(ValueError, match='cannot establish a code-reviewed'):
        validate_collection(root, DIRECTORY)
    doc['factor_fields']['formula']['status'] = 'SOURCE_DESCRIPTION_REVIEWED'
    doc['factor_fields']['formula']['evidence'] = []
    save(path, doc); refresh(root)
    with pytest.raises(ValueError, match='requires evidence|not declared'):
        validate_collection(root, DIRECTORY)


def test_visual_core_cannot_omit_both_evidence_types_or_fake_text_lines(visual_collection):
    root = visual_collection
    path = root / DIRECTORY / 'reviews.json'
    doc = load(path); review = doc['records'][0]
    del review['field_pages']['formula']
    save(path, doc); refresh(root)
    with pytest.raises(ValueError, match='precise source evidence'):
        validate_collection(root, DIRECTORY)
    review['field_spans']['formula'] = [dict(source_id='code', first_line=1, last_line=1,
                                           sha256=digest(b'\f'))]
    save(path, doc); refresh(root)
    with pytest.raises(ValueError, match='masquerade'):
        validate_collection(root, DIRECTORY)


def test_text_source_cannot_substitute_for_visual_page_evidence(collection):
    path = collection / DIRECTORY / 'reviews.json'
    doc = load(path)
    doc['records'][0]['field_pages'] = dict(formula=[dict(source_id='code', physical_page=1, sha256='0' * 64)])
    save(path, doc); refresh(collection)
    with pytest.raises(ValueError, match='not declared'):
        validate_collection(collection, DIRECTORY)


@pytest.mark.parametrize('alias_kind', ['visual', 'original', 'derived_text'])
def test_visual_snapshot_paths_do_not_collide_across_sources(visual_collection, alias_kind):
    root = visual_collection
    path = root / DIRECTORY / 'source-lock.json'
    doc = load(path); original = doc['sources'][0]
    other = deepcopy(original); other['id'] = 'second'
    if alias_kind != 'visual':
        other.pop('visual_pages')
        if alias_kind == 'original':
            other.update(extraction='utf8', snapshot_path=original['visual_pages']['pages'][0]['snapshot_path'])
        else:
            other.update(extraction='pdf.pdftotext-layout', derived_text=dict(
                snapshot_path=original['visual_pages']['pages'][0]['snapshot_path']))
    doc['sources'].append(other)
    save(path, doc); refresh(root)
    with pytest.raises(ValueError, match='paths must be unique'):
        validate_collection(root, DIRECTORY)


@pytest.mark.parametrize('mutation', ['png_bytes', 'pdf_bytes', 're_pinned_png', 'fake_png', 'huge_dimensions'])
def test_visual_private_validation_rejects_forged_snapshots_even_if_repinned(visual_collection, mutation):
    root = visual_collection; base = root / DIRECTORY
    lock = load(base / 'source-lock.json'); source = lock['sources'][0]
    page = source['visual_pages']['pages'][0]
    if mutation == 'pdf_bytes':
        (root / source['snapshot_path']).write_bytes(b'%PDF-forged')
    elif mutation == 'png_bytes':
        (root / page['snapshot_path']).write_bytes(b'forged')
    else:
        raw = (visual_png(value=128) if mutation == 're_pinned_png' else
               b'pretend PNG' if mutation == 'fake_png' else visual_png(width=10001, height=1))
        page.update(save(root / page['snapshot_path'], raw))
        if len(raw) < 67:  # A textual forgery can still claim a plausible PNG byte length.
            raw += b' ' * (67 - len(raw)); page.update(save(root / page['snapshot_path'], raw))
        review = load(base / 'reviews.json')
        for refs in review['records'][0]['field_pages'].values():
            refs[0]['sha256'] = page['sha256']
        save(base / 'reviews.json', review); save(base / 'source-lock.json', lock); refresh(root)
    with pytest.raises(ValueError):
        validate_collection(root, DIRECTORY, verify_snapshots=True)


@pytest.mark.parametrize('mutation', ['page_count', 'geometry', 'rotation', 'huge_page', 'version', 'missing_tool', 'timeout'])
def test_visual_tools_fail_closed_before_rendering(visual_collection, monkeypatch, mutation):
    from types import SimpleNamespace
    from quantgraph.graph import collection_batch as module
    original_run = module.subprocess.run

    def run(command, **kwargs):
        if command[0] == 'pdftoppm' and '-v' not in command:
            raise AssertionError('Invalid contract must fail before rendering')
        if mutation == 'missing_tool': raise FileNotFoundError('tool unavailable')
        if mutation == 'timeout': raise module.subprocess.TimeoutExpired(command, 30)
        if mutation == 'version' and '-v' in command:
            return SimpleNamespace(stderr=b'', stdout=b'')
        result = original_run(command, **kwargs)
        if command[0] == 'pdfinfo' and '-v' not in command:
            if mutation == 'page_count': result.stdout = result.stdout.replace(b'Pages: 2', b'Pages: 3')
            elif mutation == 'geometry': result.stdout = result.stdout.replace(b'MediaBox:', b'UnknownBox:')
            elif mutation == 'rotation': result.stdout = result.stdout.replace(b'rot: 0', b'rot: 17')
            elif mutation == 'huge_page': result.stdout = result.stdout.replace(b'1.152 1.152', b'14000 14000')
        return result

    monkeypatch.setattr(module.subprocess, 'run', run)
    with pytest.raises(ValueError):
        validate_collection(visual_collection, DIRECTORY, verify_snapshots=True)


def test_visual_png_symlink_escape_is_rejected(visual_collection, tmp_path):
    root = visual_collection
    page = load(root / DIRECTORY / 'source-lock.json')['sources'][0]['visual_pages']['pages'][0]
    path = root / page['snapshot_path']
    outside = tmp_path / 'external.png'; outside.write_bytes(path.read_bytes())
    path.unlink(); path.symlink_to(outside)
    with pytest.raises(ValueError, match='symlink'):
        validate_collection(root, DIRECTORY, verify_snapshots=True)


def test_scanned_pdf_still_cannot_satisfy_old_text_extraction(monkeypatch):
    from types import SimpleNamespace
    from quantgraph.graph import collection_batch as module

    def run(command, **kwargs):
        if '-v' in command:
            return SimpleNamespace(stderr=b'pdftotext version 24.04.0\n', stdout=b'')
        return SimpleNamespace(stdout=b'\f' * 36, stderr=b'')

    monkeypatch.setattr(module.subprocess, 'run', run)
    with pytest.raises(ValueError, match='returned no text'):
        module.source_text(b'%PDF-1.4\n', module.PDF_EXTRACTION, extractor_version='pdftotext version 24.04.0')


@pytest.mark.parametrize('status', ['RESEARCH_ASSUMPTION', 'MISSING'])
def test_visual_background_reference_does_not_promote_unreviewed_fields(visual_collection, status):
    root = visual_collection; base = root / DIRECTORY
    path = base / 'factors/SyntheticVolume.json'
    doc = load(path)
    doc['factor_fields']['economic_meaning']['status'] = status
    save(path, doc); refresh(root)
    result = validate_collection(root, DIRECTORY)
    assert result['records'][0]['factor_fields']['economic_meaning']['status'] == status
    # It can cite the paper as context, but cannot claim a verified visual page.
    path = base / 'reviews.json'; review = load(path)
    review['records'][0]['field_pages']['economic_meaning'] = deepcopy(
        review['records'][0]['field_pages']['formula'])
    save(path, review); refresh(root)
    with pytest.raises(ValueError, match='not declared description-reviewed'):
        validate_collection(root, DIRECTORY)


def test_all_visual_page_geometry_is_inspected_before_any_render(visual_collection, monkeypatch):
    from quantgraph.graph import collection_batch as module
    old_run = module.subprocess.run
    inspected, rendered = [], []

    def run(command, **kwargs):
        if '-v' not in command:
            if command[0] == 'pdfinfo': inspected.append(int(command[2]))
            else:
                assert inspected == [1, 2]
                rendered.append(int(command[2]))
        return old_run(command, **kwargs)

    monkeypatch.setattr(module.subprocess, 'run', run)
    validate_collection(visual_collection, DIRECTORY, verify_snapshots=True)
    assert rendered == [1, 2]


def test_visual_png_dimensions_are_checked_before_render(visual_collection, monkeypatch):
    from quantgraph.graph import collection_batch as module
    root = visual_collection; base = root / DIRECTORY
    lock = load(base / 'source-lock.json'); pin = lock['sources'][0]['visual_pages']['pages'][0]
    pin.update(save(root / pin['snapshot_path'], visual_png(width=8, height=8)))
    save(base / 'source-lock.json', lock); refresh(root)
    old_run = module.subprocess.run

    def run(command, **kwargs):
        assert command[0] != 'pdftoppm' or '-v' in command
        return old_run(command, **kwargs)

    monkeypatch.setattr(module.subprocess, 'run', run)
    with pytest.raises(ValueError, match='dimensions differ'):
        validate_collection(root, DIRECTORY, verify_snapshots=True)


@pytest.mark.parametrize('corruption', ['signature', 'crc', 'truncated', 'trailing'])
def test_png_is_more_than_an_extension_or_header(corruption):
    from quantgraph.graph import collection_batch as module
    raw = visual_png()
    if corruption == 'signature': raw = b'x' + raw[1:]
    elif corruption == 'crc': raw = raw[:50] + bytes([raw[50] ^ 1]) + raw[51:]
    elif corruption == 'truncated': raw = raw[:-12]
    else: raw += b'not part of the image'
    with pytest.raises(ValueError):
        module._png_dimensions(raw)


def two_page_pdf():
    """Two self-authored vector pages; no external documents or source programs."""
    bodies = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] /Contents 5 0 R >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] /Contents 6 0 R >>']
    for content in [b'0 g 0 0 36 36 re f\n', b'0.5 g 20 20 30 30 re f\n']:
        bodies.append(b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'endstream')
    raw, offsets = b'%PDF-1.4\n', []
    for number, body in enumerate(bodies, 1):
        offsets.append(len(raw))
        raw += f'{number} 0 obj\n'.encode() + body + b'\nendobj\n'
    start = len(raw)
    raw += f'xref\n0 {len(bodies) + 1}\n0000000000 65535 f \n'.encode()
    raw += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)
    raw += f'trailer\n<< /Size {len(bodies) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
    return raw


def test_real_poppler_visual_collection_rebuilds_two_physical_pages(visual_collection, monkeypatch):
    from shutil import which
    import subprocess
    if not which('pdfinfo') or not which('pdftoppm'):
        pytest.skip('Optional real Poppler integration; mocked boundary tests always run')
    monkeypatch.undo()  # Replace the fixture's mock with installed trusted PDF tools.
    root = visual_collection; base = root / DIRECTORY
    lock = load(base / 'source-lock.json'); source = lock['sources'][0]
    raw = two_page_pdf()
    source.update(save(root / source['snapshot_path'], raw))
    visual = source['visual_pages']
    for tool in [visual['inspector'], visual['generator']]:
        out = subprocess.run([tool['name'], '-v'], capture_output=True, check=True, timeout=30)
        tool['version'] = (out.stderr or out.stdout).decode().splitlines()[0]
    for page in visual['pages']:
        n = str(page['physical_page'])
        out = subprocess.run(['pdftoppm', '-f', n, '-l', n, '-r', '125', '-singlefile', '-png', '-'],
                             input=raw, capture_output=True, check=True, timeout=30)
        page.update(save(root / page['snapshot_path'], out.stdout), parent_pdf_sha256=source['sha256'])
    save(base / 'source-lock.json', lock)
    path = base / 'factors/SyntheticVolume.json'; doc = load(path)
    doc['sources'][0]['sha256'] = source['sha256']; save(path, doc)
    path = base / 'reviews.json'; doc = load(path)
    for refs in doc['records'][0]['field_pages'].values():
        for ref in refs:
            ref['sha256'] = visual['pages'][ref['physical_page'] - 1]['sha256']
    save(path, doc); refresh(root)
    assert validate_collection(root, DIRECTORY, verify_snapshots=True)['raw_evidence_verified'] is True


def test_visual_review_remains_a_read_only_catalog_definition(visual_collection):
    from quantgraph.graph.knowledge_catalog import KnowledgeCatalog
    root = visual_collection
    save(root / 'metadata/catalog.json', dict(schema_version='quantgraph-catalog-registry/v1', overlays=[],
        collections=[dict(id='visual', kind='source_collection', path=DIRECTORY)]))
    catalog = KnowledgeCatalog(root)
    assert catalog.stats()['collected_factor'] == 1
    assert catalog.search(status='NOT_TESTED')['total'] == 1
    assert catalog.search(status='VALIDATED')['total'] == 0
    record = catalog.get('Synthetic/Library:SyntheticVolume')['versions'][0]['record']
    assert record['review']['field_spans'] == {}
    assert record['review']['field_pages']['formula'][0]['physical_page'] == 1
    assert record['review']['states']['computation_semantics'] == 'NOT_EXECUTED'


def gray_png(*, width=3, height=2, pixels=None, compressed=None, chunks=None, header=None):
    """Synthetic gray4 image bytes; no executable source or external renderer."""
    import struct
    import zlib
    if header is None:
        header = struct.pack('>IIBBBBB', width, height, 4, 0, 0, 0, 0)
    if pixels is None:
        pixels = (b'\0' + b'\x12' * ((width + 1) // 2)) * height
    if compressed is None:
        compressed = zlib.compress(pixels)
    if chunks is None:
        chunks = [(b'IHDR', header), (b'IDAT', compressed), (b'IEND', b'')]
    return b'\x89PNG\r\n\x1a\n' + b''.join(
        struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        for kind, data in chunks)


IMAGE_TAG = '<img src="https://example.test/page.png" alt="1732" width="3" height="2">'


def sync_image_fixture(root):
    base = root / DIRECTORY
    lock = load(base / 'source-lock.json')
    sources = {s['id']: s for s in lock['sources']}
    record_path = base / 'factors/SyntheticVolume.json'
    record = load(record_path)
    for source in record['sources']:
        source.update({key: sources[source['id']][key] for key in ['url', 'revision', 'sha256']})
    save(record_path, record)
    refresh(root)


def replace_image_html(root, html, *, first=2, last=2):
    base = root / DIRECTORY
    lock = load(base / 'source-lock.json')
    image, parent = lock['sources'][:2]
    parent.update(save(root / parent['snapshot_path'], html.encode()))
    image['original_image']['identity_link'].update(source_sha256=parent['sha256'],
        first_line=first, last_line=last, sha256=digest('\n'.join(html.splitlines()[first - 1:last]).encode()))
    save(base / 'source-lock.json', lock)
    sync_image_fixture(root)


@pytest.fixture
def image_collection(collection):
    from quantgraph.graph import collection_batch as module
    base = collection / DIRECTORY
    lock = load(base / 'source-lock.json')
    image = lock['sources'][0]
    image.update(id='page', url='https://example.test/page.png', revision='image-content',
                 revision_kind='content_snapshot', snapshot_path='datasets/raw/sources/synthetic/page.png',
                 role='published_definition', extraction=module.IMAGE_EXTRACTION)
    image.update(save(collection / image['snapshot_path'], gray_png()))
    parent = dict(image, id='html', url='https://example.test/article/', role='source_index',
                  extraction='utf8', snapshot_path='datasets/raw/sources/synthetic/article.html')
    parent.update(save(collection / parent['snapshot_path'], ('<!doctype html>\n' + IMAGE_TAG + '\n').encode()))
    image['original_image'] = dict(format='PNG', width=3, height=2, bit_depth=4, color_type=0,
        printed_page='1732', identity_link=dict(source_id='html', source_sha256=parent['sha256'],
            first_line=2, last_line=2, sha256=digest(IMAGE_TAG.encode()), tag='img', attribute='src',
            url=image['url'], attributes=dict(alt='1732', width='3', height='2')))
    lock['sources'] = [image, parent]
    save(base / 'source-lock.json', lock)
    path = base / 'factors/SyntheticVolume.json'
    record = load(path)
    template = record['sources'][0]
    record['sources'] = [dict(template, **{key: s[key] for key in ['id', 'url', 'revision', 'sha256']},
                             verification='PINNED_DOCUMENT_REVIEWED') for s in lock['sources']]
    for field in record['factor_fields'].values():
        field.update(status='SOURCE_DESCRIPTION_REVIEWED', evidence=['page'])
    save(path, record)
    reviews = load(base / 'reviews.json')
    reviews['records'][0].update(field_spans={}, field_images={name: [dict(source_id='page',
        sha256=image['sha256'], printed_page='1732')] for name in ['formula', 'inputs', 'calculation']})
    save(base / 'reviews.json', reviews)
    refresh(collection)
    return collection


def test_original_image_is_verified_without_tools_and_public_clone_only_claims_structure(image_collection, monkeypatch):
    from quantgraph.graph import collection_batch as module
    def forbidden(*args, **kwargs):
        raise AssertionError('Original PNG validation must not execute tools')
    monkeypatch.setattr(module.subprocess, 'run', forbidden)
    private = validate_collection(image_collection, DIRECTORY, verify_snapshots=True)
    assert private['counts']['factor'] == 1 and private['raw_evidence_verified'] is True
    assert private['source_keys'][('Synthetic/Library', 'factor', 'SyntheticVolume')] == set()
    for source in load(image_collection / DIRECTORY / 'source-lock.json')['sources']:
        (image_collection / source['snapshot_path']).unlink()
    assert validate_collection(image_collection, DIRECTORY)['raw_evidence_verified'] is False
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_collection(image_collection, DIRECTORY, verify_snapshots=True)


@pytest.mark.parametrize('mutation', [
    'role_code', 'role_license', 'role_index', 'role_attribution', 'git', 'missing_image',
    'extra_key', 'pdf_parent', 'renderer', 'derived_text', 'visual_pages', 'archive_members',
    'wrong_extraction', 'width_bool', 'height_zero', 'dimensions', 'pixels', 'depth', 'color_bool',
    'format', 'printed_page', 'huge_bytes', 'unsafe_path', 'control_path', 'extension',
    'parent_missing', 'parent_hash', 'parent_role', 'parent_extraction', 'parent_bytes',
    'line_bool', 'line_zero', 'reversed_lines', 'line_hash', 'tag', 'attribute', 'url', 'attrs'])
def test_original_image_public_contract_fails_closed(image_collection, mutation):
    root = image_collection; base = root / DIRECTORY
    lock = load(base / 'source-lock.json'); source, parent = lock['sources']
    image = source['original_image']; link = image['identity_link']
    if mutation.startswith('role_'):
        source['role'] = {'code': 'source_code', 'license': 'license', 'index': 'source_index',
                          'attribution': 'attribution'}[mutation[5:]]
    elif mutation == 'git':
        source.update(revision_kind='git_commit', revision='a' * 40,
                      url='https://github.com/a/b/blob/' + 'a' * 40 + '/p.png')
        link['url'] = source['url']
    elif mutation == 'missing_image': source.pop('original_image')
    elif mutation == 'extra_key': image['renderer'] = 'not an original'
    elif mutation == 'pdf_parent': source['parent_pdf_sha256'] = 'a' * 64
    elif mutation in {'renderer', 'derived_text', 'visual_pages', 'archive_members'}: source[mutation] = {}
    elif mutation == 'wrong_extraction': source['extraction'] = 'utf8'
    elif mutation == 'width_bool': image['width'] = True
    elif mutation == 'height_zero': image['height'] = 0
    elif mutation == 'dimensions': image['width'] = 10_001
    elif mutation == 'pixels': image.update(width=5000, height=5000)
    elif mutation == 'depth': image['bit_depth'] = 8
    elif mutation == 'color_bool': image['color_type'] = False
    elif mutation == 'format': image['format'] = 'JPEG'
    elif mutation == 'printed_page': image['printed_page'] = '1732\n1733'
    elif mutation == 'huge_bytes': source['bytes'] = 8 * 1024 * 1024 + 1
    elif mutation == 'unsafe_path': source['snapshot_path'] = 'datasets/raw/sources/../page.png'
    elif mutation == 'control_path': source['snapshot_path'] = 'datasets/raw/sources/pa\nge.png'
    elif mutation == 'extension': source['snapshot_path'] = 'datasets/raw/sources/page.pdf'
    elif mutation == 'parent_missing': link['source_id'] = 'absent'
    elif mutation == 'parent_hash': link['source_sha256'] = 'f' * 64
    elif mutation == 'parent_role': parent['role'] = 'license'
    elif mutation == 'parent_extraction': parent['extraction'] = 'json.source'
    elif mutation == 'parent_bytes': parent['bytes'] = 8 * 1024 * 1024 + 1
    elif mutation == 'line_bool': link['first_line'] = True
    elif mutation == 'line_zero': link['first_line'] = 0
    elif mutation == 'reversed_lines': link.update(first_line=3, last_line=2)
    elif mutation == 'line_hash': link['sha256'] = 'unknown'
    elif mutation == 'tag': link['tag'] = 'a'
    elif mutation == 'attribute': link['attribute'] = 'href'
    elif mutation == 'url': link['url'] = 'https://example.test/other.png'
    elif mutation == 'attrs': link['attributes']['alt'] = '1733'
    save(base / 'source-lock.json', lock); sync_image_fixture(root)
    with pytest.raises(ValueError):
        validate_collection(root, DIRECTORY)


@pytest.mark.parametrize('before,after', [
    ('<!--\n', '\n-->'), ('<script>\nconst x = "', '";\n</script>'),
    ('<style>\n', '\n</style>'), ('<textarea>\n', '\n</textarea>'),
    ('<title>\n', '\n</title>'), ('<xmp>\n', '\n</xmp>'),
    ('<iframe>\n', '\n</iframe>'), ('<noembed>\n', '\n</noembed>'),
    ('<noframes>\n', '\n</noframes>'), ('<noscript>\n', '\n</noscript>'),
    ('<template>\n', '\n</template>'), ('<template><template>\n', '\n</template></template>'),
    ('<plaintext>\n', '\n</plaintext>'), ('<svg>\n', '\n</svg>'), ('<math>\n', '\n</math>'),
    ('<textarea>\n</template>', '\n</textarea>'),
])
def test_original_image_full_html_context_excludes_inert_content(image_collection, before, after):
    html = before + IMAGE_TAG + after
    replace_image_html(image_collection, html)
    # Correct pins and a selected line that looks like an img still cannot make
    # an element in a previous-line raw-text/comment/template context active.
    validate_collection(image_collection, DIRECTORY)
    with pytest.raises(ValueError, match='one real complete HTML img'):
        validate_collection(image_collection, DIRECTORY, verify_snapshots=True)


@pytest.mark.parametrize('html', [
    '&lt;img src="https://example.test/page.png" alt="1732" width="3" height="2"&gt;',
    IMAGE_TAG.replace('src=', 'src="https://wrong.test/p" src='),
    IMAGE_TAG.replace('src=', 'SRC="https://wrong.test/p" src='),
    IMAGE_TAG.replace('alt="1732"', 'alt="1733"'),
    IMAGE_TAG.replace('width="3"', 'width="4"'),
    IMAGE_TAG.replace('src=', 'data-src='),
    IMAGE_TAG + IMAGE_TAG,
    '<base href="https://other.test/">' + IMAGE_TAG,
    '<textarea/>' + IMAGE_TAG,
    '<template/>' + IMAGE_TAG,
    '<plaintext></plaintext>' + IMAGE_TAG,
])
def test_original_image_rejects_escaped_ambiguous_or_nonmatching_html(image_collection, html):
    replace_image_html(image_collection, '<!doctype html>\n' + html)
    with pytest.raises(ValueError):
        validate_collection(image_collection, DIRECTORY, verify_snapshots=True)


def test_original_image_tag_must_be_wholly_inside_pinned_lines(image_collection):
    html = '<!-- harmless -->\n' + IMAGE_TAG.replace(' alt=', '\n alt=') + '\n'
    replace_image_html(image_collection, html, first=2, last=2)
    with pytest.raises(ValueError, match='one real complete HTML img'):
        validate_collection(image_collection, DIRECTORY, verify_snapshots=True)
    replace_image_html(image_collection, html, first=2, last=3)
    assert validate_collection(image_collection, DIRECTORY, verify_snapshots=True)['raw_evidence_verified']


@pytest.mark.parametrize('prefix', ['<script>ignored</script>\n', '<textarea>ignored</textarea>\r\n',
                                    '<template>ignored</template>\r', '<!-- ignored -->\f'])
def test_original_image_links_after_closed_inert_context_and_line_endings(image_collection, prefix):
    replace_image_html(image_collection, prefix + IMAGE_TAG.replace('https://example.test/page.png', '/page.png'))
    assert validate_collection(image_collection, DIRECTORY, verify_snapshots=True)['raw_evidence_verified']


def test_original_image_private_html_hash_and_whole_source_pin_are_both_required(image_collection):
    root = image_collection; base = root / DIRECTORY
    lock = load(base / 'source-lock.json')
    lock['sources'][0]['original_image']['identity_link']['sha256'] = '0' * 64
    save(base / 'source-lock.json', lock); refresh(root)
    with pytest.raises(ValueError, match='HTML line pin mismatch'):
        validate_collection(root, DIRECTORY, verify_snapshots=True)
    replace_image_html(root, '<!doctype html>\n' + IMAGE_TAG)
    parent = load(base / 'source-lock.json')['sources'][1]
    (root / parent['snapshot_path']).write_text('<!doctype html>\n' + IMAGE_TAG + ' changed')
    with pytest.raises(ValueError, match='byte pin mismatch'):
        validate_collection(root, DIRECTORY, verify_snapshots=True)


@pytest.mark.parametrize('mutation', ['bad_hash', 'page', 'extra', 'unknown_source', 'empty', 'duplicate',
    'no_evidence', 'not_declared', 'parent_not_declared', 'code', 'assumption', 'missing',
    'unknown_field', 'no_core_evidence', 'text_mix', 'pdf_mix', 'html_is_formula'])
def test_original_image_field_evidence_membership_and_states(image_collection, mutation):
    root = image_collection; base = root / DIRECTORY
    reviews = load(base / 'reviews.json'); review = reviews['records'][0]
    record = load(base / 'factors/SyntheticVolume.json')
    ref = review['field_images']['formula'][0]
    if mutation == 'bad_hash': ref['sha256'] = '0' * 64
    elif mutation == 'page': ref['printed_page'] = '1733'
    elif mutation == 'extra': ref['physical_page'] = 1
    elif mutation == 'unknown_source': ref['source_id'] = 'absent'
    elif mutation == 'empty': review['field_images']['formula'] = []
    elif mutation == 'duplicate': review['field_images']['formula'].append(deepcopy(ref))
    elif mutation == 'no_evidence': record['factor_fields']['formula']['evidence'] = []
    elif mutation == 'not_declared': record['sources'] = record['sources'][1:]
    elif mutation == 'parent_not_declared': record['sources'] = record['sources'][:1]
    elif mutation in {'code', 'assumption', 'missing'}:
        record['factor_fields']['formula']['status'] = {'code': 'SOURCE_CODE_REVIEWED',
            'assumption': 'RESEARCH_ASSUMPTION', 'missing': 'MISSING'}[mutation]
    elif mutation == 'unknown_field': review['field_images']['unknown'] = [ref]
    elif mutation == 'no_core_evidence': review['field_images'].pop('formula')
    elif mutation == 'text_mix': review['field_spans']['formula'] = [dict(source_id='page', first_line=1,
        last_line=1, sha256='a' * 64)]
    elif mutation == 'pdf_mix': review['field_pages'] = dict(formula=[dict(source_id='page', physical_page=1,
        sha256=ref['sha256'])])
    elif mutation == 'html_is_formula':
        review['field_images']['formula'] = [dict(ref, source_id='html')]
        record['factor_fields']['formula']['evidence'] = ['html']
    save(base / 'reviews.json', reviews); save(base / 'factors/SyntheticVolume.json', record); refresh(root)
    with pytest.raises(ValueError):
        validate_collection(root, DIRECTORY)


@pytest.mark.parametrize('status', ['MISSING', 'RESEARCH_ASSUMPTION'])
def test_original_image_can_be_background_without_promoting_unreviewed_field(image_collection, status):
    root = image_collection; base = root / DIRECTORY
    path = base / 'factors/SyntheticVolume.json'; record = load(path)
    record['factor_fields']['economic_meaning']['status'] = status
    save(path, record); refresh(root)
    assert validate_collection(root, DIRECTORY, verify_snapshots=True)['counts']['factor'] == 1


@pytest.mark.parametrize('mutation', ['raw', 'derived', 'alias_ref'])
def test_original_image_paths_and_same_content_field_aliases_cannot_inflate_evidence(image_collection, mutation):
    root = image_collection; base = root / DIRECTORY
    lock = load(base / 'source-lock.json'); image = lock['sources'][0]
    other = deepcopy(image); other['id'] = 'alias'
    if mutation == 'derived':
        other.pop('original_image')
        other.update(extraction='pdf.pdftotext-layout', snapshot_path='datasets/raw/sources/synthetic/other.pdf',
            derived_text=dict(parent_pdf_sha256=other['sha256'], sha256='c' * 64, bytes=1,
                snapshot_path=image['snapshot_path'], generator=dict(name='pdftotext',
                    version='pdftotext version 24.04.0', arguments=['-layout', '-enc', 'UTF-8', '-', '-'])))
    elif mutation == 'alias_ref': other['snapshot_path'] = 'datasets/raw/sources/synthetic/alias.png'
    lock['sources'].append(other); save(base / 'source-lock.json', lock)
    record = load(base / 'factors/SyntheticVolume.json')
    record['sources'].append(dict(record['sources'][0], id='alias'))
    record['factor_fields']['formula']['evidence'].append('alias')
    save(base / 'factors/SyntheticVolume.json', record)
    review = load(base / 'reviews.json')
    review['records'][0]['field_images']['formula'].append(dict(source_id='alias',
        sha256=other['sha256'], printed_page='1732'))
    save(base / 'reviews.json', review); sync_image_fixture(root)
    with pytest.raises(ValueError, match='snapshot paths|Repeated original image'):
        validate_collection(root, DIRECTORY)


@pytest.mark.parametrize('target', ['page', 'html'])
def test_original_image_private_read_rejects_symlinks(image_collection, tmp_path, target):
    source = next(s for s in load(image_collection / DIRECTORY / 'source-lock.json')['sources'] if s['id'] == target)
    path = image_collection / source['snapshot_path']
    outside = tmp_path / 'outside'; outside.write_bytes(path.read_bytes())
    path.unlink(); path.symlink_to(outside)
    with pytest.raises(ValueError, match='symlink'):
        validate_collection(image_collection, DIRECTORY, verify_snapshots=True)


@pytest.mark.parametrize('corruption', ['crc', 'truncated', 'trailing', 'ihdr_repeat', 'iend_repeat',
    'ihdr_not_first', 'iend_data', 'no_idat', 'nonconsecutive_idat', 'unknown_chunk', 'apng',
    'rgba', 'depth', 'interlace', 'compression', 'filter_method', 'dimensions', 'huge_dimensions',
    'invalid_zlib', 'truncated_zlib', 'concatenated_zlib', 'too_long', 'too_short', 'bomb',
    'filter_byte', 'ancillary_size', 'ancillary_repeat', 'compressed_text'])
def test_original_png_rejects_repinned_malformed_or_unbounded_bytes(image_collection, corruption):
    import struct
    import zlib
    root = image_collection; base = root / DIRECTORY
    header = struct.pack('>IIBBBBB', 3, 2, 4, 0, 0, 0, 0)
    pixels = b'\0\x12\x30' * 2; compressed = zlib.compress(pixels)
    chunks = [(b'IHDR', header), (b'IDAT', compressed), (b'IEND', b'')]
    if corruption == 'ihdr_repeat': chunks.insert(1, chunks[0])
    elif corruption == 'iend_repeat': chunks.append(chunks[-1])
    elif corruption == 'ihdr_not_first': chunks.insert(0, (b'tEXt', b'key\0value'))
    elif corruption == 'iend_data': chunks[-1] = (b'IEND', b'x')
    elif corruption == 'no_idat': chunks[1] = (b'tEXt', b'Title\0Malformed image without IDAT')
    elif corruption == 'nonconsecutive_idat': chunks[1:2] = [(b'IDAT', compressed[:3]),
        (b'tEXt', b'key\0value'), (b'IDAT', compressed[3:])]
    elif corruption in {'unknown_chunk', 'apng', 'compressed_text'}:
        chunks.insert(1, ({'unknown_chunk': b'abCD', 'apng': b'acTL', 'compressed_text': b'zTXt'}[corruption], b'\0'))
    elif corruption in {'rgba', 'depth', 'interlace', 'compression', 'filter_method', 'dimensions', 'huge_dimensions'}:
        h = [3, 2, 4, 0, 0, 0, 0]
        key, value = {'rgba': (3, 6), 'depth': (2, 8), 'interlace': (6, 1), 'compression': (4, 1),
            'filter_method': (5, 1), 'dimensions': (0, 4), 'huge_dimensions': (0, 100_000)}[corruption]
        h[key] = value; chunks[0] = (b'IHDR', struct.pack('>IIBBBBB', *h))
    elif corruption in {'invalid_zlib', 'truncated_zlib', 'concatenated_zlib'}:
        chunks[1] = (b'IDAT', {'invalid_zlib': b'not-zlib', 'truncated_zlib': compressed[:-1],
            'concatenated_zlib': compressed + compressed}[corruption])
        chunks.insert(1, (b'tEXt', b'Title\0Malformed compressed image'))
    elif corruption in {'too_long', 'too_short', 'bomb', 'filter_byte'}:
        p = {'too_long': pixels + b'\0', 'too_short': pixels[:-1], 'bomb': b'\0' * 1_000_000,
             'filter_byte': b'\x05' + pixels[1:]}[corruption]
        chunks[1] = (b'IDAT', zlib.compress(p))
    elif corruption == 'ancillary_size': chunks.insert(1, (b'gAMA', b'\0'))
    elif corruption == 'ancillary_repeat': chunks[1:1] = [(b'gAMA', struct.pack('>I', 45455))] * 2
    raw = gray_png(chunks=chunks)
    if corruption == 'crc': raw = raw[:-1] + bytes([raw[-1] ^ 1])
    elif corruption == 'truncated': raw = raw[:-3]
    elif corruption == 'trailing': raw += b'extra'
    lock = load(base / 'source-lock.json'); image = lock['sources'][0]
    image.update(save(root / image['snapshot_path'], raw)); save(base / 'source-lock.json', lock)
    reviews = load(base / 'reviews.json')
    for refs in reviews['records'][0]['field_images'].values(): refs[0]['sha256'] = image['sha256']
    save(base / 'reviews.json', reviews); sync_image_fixture(root)
    # The attacker has repinned both metadata and review: structure alone is not
    # a claim that bytes decode. The private check must still reject them.
    validate_collection(root, DIRECTORY)
    with pytest.raises(ValueError):
        validate_collection(root, DIRECTORY, verify_snapshots=True)


def test_original_png_accepts_all_filters_and_observed_ancillary_chunks():
    import struct
    import zlib
    from quantgraph.graph import collection_batch as module
    pixels = b''.join(bytes([i, 0x12, 0x30]) for i in range(5))
    stream = zlib.compress(pixels)
    raw = gray_png(chunks=[(b'IHDR', struct.pack('>IIBBBBB', 3, 5, 4, 0, 0, 0, 0)),
        (b'gAMA', struct.pack('>I', 45455)), (b'bKGD', b'\0\x0f'),
        (b'pHYs', struct.pack('>IIB', 100, 100, 1)), (b'tIME', struct.pack('>HBBBBB', 2020, 1, 2, 3, 4, 5)),
        (b'IDAT', stream[:3]), (b'IDAT', stream[3:]), (b'tEXt', b'Title\0Scan'),
        (b'tEXt', b'Author\0Source author'), (b'IEND', b'')])
    module._verify_original_png(raw, dict(width=3, height=5))


@pytest.mark.parametrize('limit', ['images', 'bytes', 'pixels'])
def test_original_image_batch_limits_precede_any_inflation(image_collection, monkeypatch, limit):
    from quantgraph.graph import collection_batch as module
    root = image_collection; base = root / DIRECTORY
    lock = load(base / 'source-lock.json'); image, parent = lock['sources']
    count = 65 if limit == 'images' else 17
    copies = []
    for number in range(count):
        copy = deepcopy(image)
        copy.update(id=f'image-{number}', snapshot_path=f'datasets/raw/sources/synthetic/{number}.png')
        if limit == 'bytes': copy['bytes'] = 8 * 1024 * 1024
        if limit == 'pixels':
            copy['original_image'].update(width=4000, height=4000)
            copy['original_image']['identity_link']['attributes'].update(width='4000', height='4000')
        copies.append(copy)
    lock['sources'] = copies + [parent]
    save(base / 'source-lock.json', lock); refresh(root)
    def forbidden(*args, **kwargs):
        raise AssertionError('Batch limits must be checked before image inflation')
    monkeypatch.setattr(module, '_verify_original_png', forbidden)
    with pytest.raises(ValueError, match='collection exceeds its resource limits'):
        validate_collection(root, DIRECTORY, verify_snapshots=True)


def test_original_image_cannot_alias_a_pdf_rendered_snapshot(image_collection):
    from quantgraph.graph import collection_batch as module
    root = image_collection; base = root / DIRECTORY
    lock = load(base / 'source-lock.json'); image = lock['sources'][0]
    pdf = dict(image, id='pdf', url='https://example.test/document.pdf',
               snapshot_path='datasets/raw/sources/synthetic/document.pdf',
               extraction=module.PDF_VISUAL_EXTRACTION)
    pdf.pop('original_image')
    pdf['visual_pages'] = dict(page_count=1,
        inspector=dict(name='pdfinfo', version='pdfinfo version 24.04.0'),
        generator=dict(name='pdftoppm', version='pdftoppm version 24.04.0', dpi=125,
                       arguments=['-singlefile', '-png']),
        pages=[dict(physical_page=1, parent_pdf_sha256=pdf['sha256'], sha256=image['sha256'],
                    bytes=image['bytes'], snapshot_path=image['snapshot_path'])])
    lock['sources'].append(pdf); save(base / 'source-lock.json', lock); refresh(root)
    with pytest.raises(ValueError, match='snapshot paths must be unique'):
        validate_collection(root, DIRECTORY)


def test_original_image_oversize_ihdr_is_rejected_before_zlib_allocation(monkeypatch):
    from quantgraph.graph import collection_batch as module
    raw = gray_png(width=10001, height=1)
    def forbidden(*args, **kwargs):
        raise AssertionError('Invalid IHDR must be checked before creating the inflater')
    monkeypatch.setattr(module.zlib, 'decompressobj', forbidden)
    with pytest.raises(ValueError, match='IHDR'):
        module._verify_original_png(raw, dict(width=10001, height=1))


def test_original_image_bounded_html_and_utf8_are_required():
    from quantgraph.graph import collection_batch as module
    with pytest.raises(ValueError, match='byte limit'):
        module._image_html(b' ' * (8 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match='UTF-8'):
        module._image_html(b'<html>\xff</html>')


def test_original_image_evidence_retains_missing_background_and_catalog_readonly(image_collection):
    from quantgraph.graph.knowledge_catalog import KnowledgeCatalog
    root = image_collection
    save(root / 'metadata/catalog.json', dict(schema_version='quantgraph-catalog-registry/v1', overlays=[],
        collections=[dict(id='image', kind='source_collection', path=DIRECTORY)]))
    before = {str(p.relative_to(root)): digest(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
    assert KnowledgeCatalog(root).stats()['collected_factor'] == 1
    after = {str(p.relative_to(root)): digest(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
    assert before == after


@pytest.mark.parametrize('kind,data', [
    (b'gAMA', b'\0\0\0\0'), (b'bKGD', b'\0\x10'), (b'pHYs', b'\0' * 8 + b'\x02'),
    (b'tIME', b'\x07\xe8\x02\x1e\0\0\0'), (b'tEXt', b' bad\0text'),
    (b'tEXt', b'bad  key\0text'), (b'tEXt', b'key\0text\0extra'),
])
def test_original_png_rejects_invalid_observed_ancillary_values(kind, data):
    import struct
    import zlib
    from quantgraph.graph import collection_batch as module
    raw = gray_png(chunks=[(b'IHDR', struct.pack('>IIBBBBB', 3, 2, 4, 0, 0, 0, 0)),
        (kind, data), (b'IDAT', zlib.compress(b'\0\x12\x30' * 2)), (b'IEND', b'')])
    with pytest.raises(ValueError, match='Malformed original PNG ancillary'):
        module._verify_original_png(raw, dict(width=3, height=2))


def test_original_image_identity_parent_order_is_irrelevant(image_collection):
    root = image_collection; base = root / DIRECTORY
    lock = load(base / 'source-lock.json'); lock['sources'].reverse()
    save(base / 'source-lock.json', lock); refresh(root)
    assert validate_collection(root, DIRECTORY, verify_snapshots=True)['counts']['factor'] == 1


# Codec fixtures retain raw evidence, independently construct original LF ranges,
# and then adapt only the evidence coordinates used by the existing collection.
def codec_source_fixture(root, raw=None, *, utf8=False, first=2, last=3):
    import platform
    from quantgraph.graph.collection_batch import CODEC_EXTRACTION
    base = root / DIRECTORY
    raw = raw if raw is not None else '注释\f保留\r\nresult=1;\r\nresult=2'.encode('gb18030')
    codec = 'utf-8' if utf8 else 'gb18030'
    text = raw.decode(codec)
    formal = raw.decode('utf-8-sig') if utf8 else text
    lock = load(base / 'source-lock.json')
    source = lock['sources'][0]
    source.update(sha256=digest(raw), bytes=len(raw), extraction='utf8' if utf8 else CODEC_EXTRACTION)
    save(root / source['snapshot_path'], raw)
    if not utf8:
        path = 'datasets/raw/sources/synthetic/volume.decoded-utf8.txt'
        source['derived_text'] = dict(parent_source_sha256=digest(raw), **save(root / path, text.encode()),
            snapshot_path=path,
            generator=dict(name='python-codec', profile='cpython-gb18030-strict-roundtrip/v1', codec='gb18030',
                errors='strict', output_encoding='utf-8', newline_transformation='none',
                unicode_normalization='none', bom_transformation='none', producer_implementation='CPython',
                producer_version=platform.python_version()),
            native_line_basis='LF_BYTES_PRESERVE_ENDINGS/v1', native_line_count=len(raw.split(b'\n'))-int(raw.endswith(b'\n')),
            unicode_line_basis='PYTHON_UNICODE_SPLITLINES/v1', unicode_line_count=len(text.splitlines()))
    save(base / 'source-lock.json', lock)
    record_path = base / 'factors/SyntheticVolume.json'
    record = load(record_path)
    record['sources'][0]['sha256'] = source['sha256']
    save(record_path, record)
    chunks = raw.split(b'\n')
    chunks = [x+b'\n' for x in chunks[:-1]] + ([chunks[-1]] if chunks[-1] else [])
    selected = b''.join(chunks[first-1:last])
    # Full-file Unicode positions, including context before the selected span.
    positions, physical = [], 1
    for i, part in enumerate(formal.splitlines(keepends=True), 1):
        if first <= physical <= last:
            positions.append(i)
        physical += part.count('\n')
    start, end = positions[0], positions[-1]
    canonical = '\n'.join(formal.splitlines()[start-1:end]).encode()
    native_lines = []
    for part in chunks[first-1:last]:
        ending = 2 if part.endswith(b'\r\n') else int(part.endswith(b'\n'))
        native_lines.append((part[:-ending] if ending else part).decode(codec))
    candidate_canonical = ('\n'.join(native_lines)+'\n').encode()
    native = dict(mapping_profile='native-lf-to-unicode-splitlines/v1', parent_source_sha256=digest(raw),
        derived_text_sha256=digest(formal.encode()), first_line=first, last_line=last,
        byte_start=sum(map(len, chunks[:first-1])), byte_end_exclusive=sum(map(len, chunks[:last])),
        raw_sha256=digest(selected), raw_bytes=len(selected), decoded_utf8_sha256=digest(selected.decode(codec).encode()),
        decoded_utf8_bytes=len(selected.decode(codec).encode()), unicode_first_line=start, unicode_last_line=end,
        candidate_sha256=digest(candidate_canonical), candidate_hash_scope='LF_JOIN_PLUS_ONE_TERMINAL_LF')
    span = dict(source_id='code', first_line=start, last_line=end, sha256=digest(canonical), native_lf_span=native)
    reviews = load(base / 'reviews.json')
    reviews['records'][0]['field_spans'] = {name: [deepcopy(span)] for name in ['formula', 'inputs', 'calculation']}
    save(base / 'reviews.json', reviews)
    refresh(root)
    return source, span


def test_gb18030_original_bytes_and_two_line_coordinates(collection):
    source, span = codec_source_fixture(collection)
    assert (span['native_lf_span']['first_line'], span['first_line']) == (2, 3)
    assert span['native_lf_span']['decoded_utf8_sha256'] != span['sha256']
    assert validate_collection(collection, DIRECTORY, verify_snapshots=True)['raw_evidence_verified']
    assert load(collection / DIRECTORY / 'source-lock.json')['sources'][0] == source
    (collection / source['snapshot_path']).unlink()
    (collection / source['derived_text']['snapshot_path']).unlink()
    assert not validate_collection(collection, DIRECTORY)['raw_evidence_verified']


@pytest.mark.parametrize('text', [
    '中文\r\n\U0001f600\f末行', '\ufeff注释\n返回', 'a\n\n',
    'a\r\nb\n', 'a\rb\n', 'a\v', 'a\f', 'a\x85', 'a\r',
    'a\f\f\n', '\r\n', 'a\x1cb\x1dc\x1ed\u2028e\u2029f\n',
])
def test_codec_preserves_controls_and_full_file_mapping(collection, text):
    from quantgraph.graph.collection_batch import CODEC_EXTRACTION
    raw = text.encode('gb18030')
    last = len(raw.split(b'\n')) - int(raw.endswith(b'\n'))
    codec_source_fixture(collection, raw, first=1, last=last)
    assert source_text(raw, CODEC_EXTRACTION) == text
    assert validate_collection(collection, DIRECTORY, verify_snapshots=True)['raw_evidence_verified']


@pytest.mark.parametrize('raw', [b'\x81', b'\xff', b'\x81\x30\x81', b'\x81\x30\x20\x30', b''])
def test_codec_does_not_fallback_or_replace_invalid_sequences(raw):
    from quantgraph.graph.collection_batch import CODEC_EXTRACTION
    with pytest.raises(ValueError):
        source_text(raw, CODEC_EXTRACTION)


def test_reversible_codec_is_not_an_encoding_detector():
    from quantgraph.graph.collection_batch import CODEC_EXTRACTION
    raw = b'\xc2\xa9'
    assert source_text(raw, 'utf8') != source_text(raw, CODEC_EXTRACTION)
    assert source_text(raw, CODEC_EXTRACTION).encode('gb18030') == raw


@pytest.mark.parametrize('mutation', [
    'role', 'content_snapshot', 'short_commit', 'wrong_commit_url', 'raw_bool', 'raw_limit',
    'missing_derivative', 'wrong_parent', 'bad_sha', 'derived_bool', 'derived_empty', 'derived_limit',
    'absolute', 'traversal', 'control_path', 'parent_path', 'missing_generator', 'codec', 'errors',
    'newline', 'normalize', 'bom', 'output', 'producer', 'version', 'generator_extra', 'derived_extra',
    'native_basis', 'unicode_basis', 'native_bool', 'unicode_bool', 'line_limit', 'reversed_counts',
])
def test_codec_public_contract_rejects_unsafe_declarations(collection, mutation):
    from quantgraph.graph.collection_batch import CODEC_MAX_RAW, CODEC_MAX_TEXT, CODEC_MAX_LINES
    codec_source_fixture(collection)
    base = collection / DIRECTORY
    lock = load(base / 'source-lock.json'); s = lock['sources'][0]; d = s['derived_text']; g = d['generator']
    if mutation == 'role': s['role'] = 'author_document'
    elif mutation == 'content_snapshot': s['revision_kind'] = 'content_snapshot'
    elif mutation == 'short_commit': s['revision'] = 'a'*7
    elif mutation == 'wrong_commit_url': s['url'] = s['url'].replace('a'*40, 'b'*40)
    elif mutation == 'raw_bool': s['bytes'] = True
    elif mutation == 'raw_limit': s['bytes'] = CODEC_MAX_RAW+1
    elif mutation == 'missing_derivative': del s['derived_text']
    elif mutation == 'wrong_parent': d['parent_source_sha256'] = 'b'*64
    elif mutation == 'bad_sha': d['sha256'] = 'not-a-sha'
    elif mutation == 'derived_bool': d['bytes'] = True
    elif mutation == 'derived_empty': d['bytes'] = 0
    elif mutation == 'derived_limit': d['bytes'] = CODEC_MAX_TEXT+1
    elif mutation == 'absolute': d['snapshot_path'] = '/tmp/code.txt'
    elif mutation == 'traversal': d['snapshot_path'] = 'datasets/raw/sources/../escape.txt'
    elif mutation == 'control_path': d['snapshot_path'] = 'datasets/raw/sources/with\ttab.txt'
    elif mutation == 'parent_path': d['snapshot_path'] = s['snapshot_path']
    elif mutation == 'missing_generator': del d['generator']
    elif mutation == 'codec': g['codec'] = 'gbk'
    elif mutation == 'errors': g['errors'] = 'replace'
    elif mutation == 'newline': g['newline_transformation'] = 'universal-newlines'
    elif mutation == 'normalize': g['unicode_normalization'] = 'NFC'
    elif mutation == 'bom': g['bom_transformation'] = 'strip'
    elif mutation == 'output': g['output_encoding'] = 'utf-8-sig'
    elif mutation == 'producer': g['producer_implementation'] = 'unrecorded'
    elif mutation == 'version': g['producer_version'] = 'Python3'
    elif mutation == 'generator_extra': g['command'] = 'python -c malicious'
    elif mutation == 'derived_extra': d['parent_pdf_sha256'] = s['sha256']
    elif mutation == 'native_basis': d['native_line_basis'] = 'splitlines'
    elif mutation == 'unicode_basis': d['unicode_line_basis'] = 'LF'
    elif mutation == 'native_bool': d['native_line_count'] = True
    elif mutation == 'unicode_bool': d['unicode_line_count'] = True
    elif mutation == 'line_limit': d['unicode_line_count'] = CODEC_MAX_LINES+1
    elif mutation == 'reversed_counts': d['native_line_count'] = d['unicode_line_count']+1
    save(base / 'source-lock.json', lock); refresh(collection)
    with pytest.raises(ValueError):
        validate_collection(collection, DIRECTORY)


@pytest.mark.parametrize('mutation', ['newline', 'ff', 'wrong_codec', 'wrong_hash', 'wrong_count'])
def test_codec_private_rebuild_rejects_repinned_derivative_drift(collection, mutation):
    codec_source_fixture(collection)
    base = collection / DIRECTORY
    lock = load(base / 'source-lock.json'); s = lock['sources'][0]; d = s['derived_text']
    p = collection / d['snapshot_path']; original = p.read_bytes()
    if mutation == 'newline': changed = original.replace(b'\r\n', b'\n')
    elif mutation == 'ff': changed = original.replace(b'\f', b'\n')
    elif mutation == 'wrong_codec': changed = (collection / s['snapshot_path']).read_bytes().decode('latin1').encode()
    else: changed = original
    d.update(save(p, changed))
    if mutation == 'wrong_hash': d['sha256'] = 'b'*64
    elif mutation == 'wrong_count': d['unicode_line_count'] += 1
    save(base / 'source-lock.json', lock)
    reviews = load(base / 'reviews.json')
    for spans in reviews['records'][0]['field_spans'].values():
        spans[0]['native_lf_span']['derived_text_sha256'] = d['sha256']
    save(base / 'reviews.json', reviews); refresh(collection)
    validate_collection(collection, DIRECTORY)
    with pytest.raises(ValueError, match='does not reconstruct'):
        validate_collection(collection, DIRECTORY, verify_snapshots=True)


@pytest.mark.parametrize('mutation', [
    'missing', 'parent', 'derivative', 'offset', 'raw_bytes', 'raw_hash', 'decoded_hash', 'decoded_bytes',
    'candidate_hash', 'candidate_scope', 'first_bool', 'last_bool', 'offset_bool', 'raw_bool',
    'unicode_bool', 'negative', 'end_outside', 'wrong_line', 'wrong_unicode', 'phantom_last', 'extra',
])
def test_native_lf_span_cannot_be_forged_after_control_repins(collection, mutation):
    codec_source_fixture(collection)
    base = collection / DIRECTORY
    reviews = load(base / 'reviews.json'); span = reviews['records'][0]['field_spans']['formula'][0]; n = span['native_lf_span']
    if mutation == 'missing': del span['native_lf_span']
    elif mutation == 'parent': n['parent_source_sha256'] = 'b'*64
    elif mutation == 'derivative': n['derived_text_sha256'] = 'b'*64
    elif mutation == 'offset': n['byte_start'] += 1; n['raw_bytes'] -= 1
    elif mutation == 'raw_bytes': n['raw_bytes'] += 1
    elif mutation == 'raw_hash': n['raw_sha256'] = 'b'*64
    elif mutation == 'decoded_hash': n['decoded_utf8_sha256'] = 'b'*64
    elif mutation == 'decoded_bytes': n['decoded_utf8_bytes'] += 1
    elif mutation == 'candidate_hash': n['candidate_sha256'] = 'b'*64
    elif mutation == 'candidate_scope': n['candidate_hash_scope'] = 'WITHOUT_LF'
    elif mutation == 'first_bool': n['first_line'] = True
    elif mutation == 'last_bool': n['last_line'] = True
    elif mutation == 'offset_bool': n['byte_start'] = False
    elif mutation == 'raw_bool': n['raw_bytes'] = True
    elif mutation == 'unicode_bool': n['unicode_first_line'] = True
    elif mutation == 'negative': n['byte_start'] = -1
    elif mutation == 'end_outside': n['byte_end_exclusive'] += 1000; n['raw_bytes'] += 1000
    elif mutation == 'wrong_line': n['first_line'] = 1
    elif mutation == 'wrong_unicode': n['unicode_first_line'] -= 1
    elif mutation == 'phantom_last': n['last_line'] += 1
    elif mutation == 'extra': n['unverified'] = True
    save(base / 'reviews.json', reviews); refresh(collection)
    with pytest.raises(ValueError):
        validate_collection(collection, DIRECTORY, verify_snapshots=True)


@pytest.mark.parametrize('text', ['\ufeff中文\f尾\r\n代码', '\ufeff\r\n代码\n', 'a\f\n\n'])
def test_utf8_optional_native_span_preserves_bom_while_legacy_text_strips_it(collection, text):
    raw = text.encode()
    codec_source_fixture(collection, raw, utf8=True, first=1, last=len(raw.split(b'\n'))-int(raw.endswith(b'\n')))
    assert source_text(raw, 'utf8') == text.removeprefix('\ufeff')
    assert validate_collection(collection, DIRECTORY, verify_snapshots=True)['raw_evidence_verified']


def test_utf8_optional_native_locator_is_actually_verified(collection):
    codec_source_fixture(collection, b'a\fb\nc', utf8=True, first=2, last=2)
    base = collection / DIRECTORY
    reviews = load(base / 'reviews.json')
    reviews['records'][0]['field_spans']['formula'][0]['native_lf_span']['raw_sha256'] = 'b'*64
    save(base / 'reviews.json', reviews); refresh(collection)
    with pytest.raises(ValueError, match='Native LF span does not reconstruct'):
        validate_collection(collection, DIRECTORY, verify_snapshots=True)


@pytest.mark.parametrize('mutation', ['original_alias', 'derivative_alias', 'symlink', 'parent_as_derivative'])
def test_code_derivative_paths_do_not_alias_other_evidence(collection, mutation):
    codec_source_fixture(collection)
    base = collection / DIRECTORY
    lock = load(base / 'source-lock.json'); source = lock['sources'][0]
    if mutation == 'symlink':
        p = collection / source['derived_text']['snapshot_path']; raw = p.read_bytes(); p.unlink()
        target = p.with_name('other.txt'); target.write_bytes(raw); p.symlink_to(target)
    else:
        other = deepcopy(source); other['id'] = 'other'
        if mutation == 'original_alias':
            other['extraction'] = 'utf8'; other.pop('derived_text'); other['snapshot_path'] = source['derived_text']['snapshot_path']
        elif mutation == 'derivative_alias': other['snapshot_path'] = 'datasets/raw/sources/synthetic/other.py'
        else:
            other['snapshot_path'] = 'datasets/raw/sources/synthetic/other.py'
            other['derived_text']['snapshot_path'] = source['snapshot_path']
        lock['sources'].append(other)
    save(base / 'source-lock.json', lock); refresh(collection)
    with pytest.raises(ValueError):
        validate_collection(collection, DIRECTORY, verify_snapshots=True)


def test_codec_line_and_byte_limits_precede_splitting(monkeypatch):
    import quantgraph.graph.collection_batch as module
    monkeypatch.setattr(module, 'CODEC_MAX_LINES', 2)
    with pytest.raises(ValueError, match='line bounds'):
        module.source_text(b'a\fa\fa', module.CODEC_EXTRACTION)
    monkeypatch.setattr(module, 'CODEC_MAX_RAW', 2)
    with pytest.raises(ValueError, match='byte limit'):
        module.source_text(b'abc', module.CODEC_EXTRACTION)
    monkeypatch.setattr(module, 'CODEC_MAX_TEXT', 1)
    with pytest.raises(ValueError, match='byte limit'):
        module.source_text('字'.encode('gb18030'), module.CODEC_EXTRACTION)


def test_codec_total_limit_is_structural(collection, monkeypatch):
    import quantgraph.graph.collection_batch as module
    codec_source_fixture(collection)
    monkeypatch.setattr(module, 'CODEC_MAX_TOTAL', 1)
    with pytest.raises(ValueError, match='collection exceeds'):
        validate_collection(collection, DIRECTORY)


def test_native_locator_cannot_make_license_content_into_code(collection):
    codec_source_fixture(collection, b'license\ntext', utf8=True, first=1, last=2)
    base = collection / DIRECTORY
    lock = load(base / 'source-lock.json'); lock['sources'][0]['role'] = 'license'
    save(base / 'source-lock.json', lock); refresh(collection)
    with pytest.raises(ValueError, match='License or directory'):
        validate_collection(collection, DIRECTORY)

"""Classification artifacts remain source-bound and independently replayable."""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import ValidationError
import pytest

from quantgraph.graph import classification_batch as batch
from quantgraph.graph.metadata_catalog import canonical_hash
from quantgraph.graph.metadata_pilot import digest, encoded


ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else encoded(value)
    path.write_bytes(raw)
    return dict(sha256=digest(raw), bytes=len(raw))


def read(path):
    return json.loads(path.read_bytes())


def make_repository(root, rules):
    folder = root / 'metadata/corpus/first/metadata'
    for name in ('schema.json', 'source-record.schema.json'):
        write(folder / name, (ROOT / 'metadata' / name).read_bytes())
    template = read(ROOT / 'metadata/corpus-checkpoints/grokbot-6973-20261003/batches/batch-0001-v2/metadata/source-records/M0050.json')
    refs = []
    for number, (rid, name, rule) in enumerate(rules, 1):
        row = deepcopy(template)
        values = {key: '' for key in row['reported_fields']}
        values.update(id=rid, 名称=name, 规则=rule, 市场='Synthetic', 可回测='高')
        row.update(record_id=rid, native_source_id=rid)
        for key, value in values.items():
            row['reported_fields'][key]['value'] = value
        row['provenance'].update(csv_row_ordinal=number, row_sha256=canonical_hash(values),
                                 rule_sha256=digest(rule.encode()))
        path = f'source-records/{rid}.json'
        refs.append(dict(path=path, **write(folder / path, row), **{
            key: row[key] for key in ('record_id', 'identity_namespace', 'entity_type')}))
    write(folder / 'index.json', dict(schema_version='quantgraph-metadata-index/v1', records=refs))
    frozen = {str(p.relative_to(folder.parent)): dict(sha256=digest(p.read_bytes()), bytes=p.stat().st_size)
              for p in folder.rglob('*.json')}
    pin = write(folder.parent / 'manifest.json', dict(record_ids=[r[0] for r in rules], files=frozen))
    write(root / 'metadata/corpus-index.json', dict(batches=[dict(path='corpus/first', record_count=len(rules),
        manifest_sha256=pin['sha256'])], counts=dict(public_source_records=len(rules))))
    return root


@pytest.fixture
def repository(tmp_path):
    root = make_repository(tmp_path / 'repository', [
        ('M9901', 'Synthetic policy', '收盘高于SMA20买入SPY，否则持有BIL。手续费未写明。'),
        ('M9902', 'Synthetic characteristic', '信号（Signal Browser Definition）：盈利除以市值。组合规则：按信号持有。'),
        ('M9903', '买入做多Alpha因子策略', '模型主题，规则未明确。'),
        ('M9904', 'Synthetic protocol', '单因子测试：测试设置为统一回测约束。'),
        ('M9905', 'Synthetic renderer', '用于绘制图形。'),
    ])
    return root


def override():
    return dict(record_id='M9905', kind='reference', subtype='visualization_tool',
                reason='正文明确用途为图形绘制。', evidence=[dict(field='规则', quote='用于绘制图形。')])


@pytest.fixture
def built(repository):
    destination = repository / 'metadata/classification/test'
    targets = list(batch.source_rows(repository))
    batch.build(repository, destination, targets, [override()])
    return repository, destination, targets


def validate(root, destination):
    return batch.validate_batch(root, str((destination / 'index.json').relative_to(root)), batch.source_rows(root))


def change_decisions(destination, change):
    rows = [json.loads(line) for line in (destination / 'decisions.jsonl').read_bytes().splitlines()]
    change(rows)
    raw = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n' for r in rows).encode()
    repin(destination, 'decisions.jsonl', raw)


def repin(destination, filename, value):
    index = read(destination / 'index.json')
    index['files'][filename] = write(destination / filename, value)
    write(destination / 'index.json', index)


def test_round_trip_keeps_original_sources_and_never_promotes_definitions(built):
    root, destination, targets = built
    sources = {p: p.read_bytes() for p in (root / 'metadata/corpus').rglob('*') if p.is_file()}
    index, decisions = validate(root, destination)
    assert index['target_ids'] == sorted(targets)
    assert index['counts']['kinds'] == dict(strategy=1, factor=1, reference=2, unclassified=1)
    assert index['counts']['manual_overrides'] == 1
    assert index['counts']['new_native_definitions'] == index['counts']['new_execution_trials'] == 0
    assert all(r['classification_status'] == 'CONTENT_INFERRED' and r['definition_status'] == 'UNVERIFIED'
               for r in decisions)
    assert decisions[2]['kind'] == 'unclassified'  # Trading/factor words only occur in its title.
    assert decisions[4]['rule_id'] == 'INDIVIDUAL_CONTENT_REVIEW' and decisions[4]['confidence'] == 'MEDIUM'
    assert 'DEFINITION_DETAILS_MISSING' in decisions[0]['quality_flags']
    reviewed = read(destination / 'overrides.json')[0]
    assert reviewed['row_sha256'] == decisions[4]['row_sha256']
    assert reviewed['rule_sha256'] == decisions[4]['rule_sha256']
    assert [r['record_id'] for r in read(destination / 'unclassified-queue.json')] == ['M9903']
    assert all(p.read_bytes() == raw for p, raw in sources.items())


def test_rebuild_is_location_independent_and_existing_destination_is_immutable(built, tmp_path):
    root, destination, targets = built
    other = tmp_path / 'another-output'
    batch.build(root, other, list(reversed(targets)), [override()])
    files = lambda folder: {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
    assert files(destination) == files(other)
    with pytest.raises(ValueError, match='exists'):
        batch.build(root, destination, targets, [override()])


@pytest.mark.parametrize('change, message', [
    (lambda rs: rs[0]['evidence'][0].update(quote='伪造的正文买入证据'), 'exact original rule'),
    (lambda rs: rs[0].update(row_sha256='0' * 64), 'row or rule hash'),
    (lambda rs: rs[0].update(rule_sha256='0' * 64), 'row or rule hash'),
    (lambda rs: rs[0]['source'].update(sha256='0' * 64), 'digest mismatch'),
    (lambda rs: rs[0]['source'].update(path=rs[1]['source']['path']), 'source path'),
    (lambda rs: rs.append(deepcopy(rs[0])), 'target coverage'),
    (lambda rs: rs.pop(), 'target coverage'),
    (lambda rs: rs[0].update(reason='手工改写且重新计算文件哈希'), 'differ from replay'),
])
def test_rehashed_tampering_cannot_bypass_source_or_replay_checks(built, change, message):
    root, destination, _ = built
    change_decisions(destination, change)
    with pytest.raises(ValueError, match=message):
        validate(root, destination)


def test_promoted_status_and_invalid_kind_fail_schema_even_after_rehash(built):
    root, destination, _ = built
    original = (destination / 'decisions.jsonl').read_bytes()
    for field, value in [('definition_status', 'VERIFIED'), ('kind', 'live_strategy')]:
        repin(destination, 'decisions.jsonl', original)
        change_decisions(destination, lambda rs: rs[0].update({field: value}))
        with pytest.raises(ValidationError):
            validate(root, destination)


@pytest.mark.parametrize('artifact', ['README.md', 'unclassified-queue.json', 'strategy/page-0001.md'])
def test_rehashed_directory_views_must_rebuild_exactly(built, artifact):
    root, destination, _ = built
    repin(destination, artifact, (destination / artifact).read_bytes() + b'\nchanged\n')
    with pytest.raises(ValueError, match='differ from replay|rebuilt artifact'):
        validate(root, destination)


def test_extra_file_and_changed_algorithm_are_rejected(built, monkeypatch):
    root, destination, _ = built
    extra = destination / 'unlisted.md'
    extra.write_text('unlisted')
    with pytest.raises(ValueError, match='directory drift'):
        validate(root, destination)
    extra.unlink()
    monkeypatch.setattr(batch.classifier, 'VERSION', 'changed-policy-version')
    with pytest.raises(ValueError, match='algorithm version'):
        validate(root, destination)


def test_counts_schema_and_overrides_are_bound_to_the_replayed_batch(built):
    root, destination, _ = built
    original_index = read(destination / 'index.json')
    changed = deepcopy(original_index)
    changed['counts']['kinds']['strategy'] += 1
    write(destination / 'index.json', changed)
    with pytest.raises(ValueError, match='differ from replay'):
        validate(root, destination)
    write(destination / 'index.json', original_index)
    schema = read(destination / 'schema.json')
    repin(destination, 'schema.json', dict(schema, additionalProperties=True))
    with pytest.raises(ValueError, match='schema drift'):
        validate(root, destination)
    repin(destination, 'schema.json', schema)
    overrides = read(destination / 'overrides.json')
    overrides[0]['kind'] = 'factor'
    repin(destination, 'overrides.json', overrides)
    with pytest.raises(ValueError, match='differ from replay'):
        validate(root, destination)


def test_manual_review_preserves_inferred_quality_flags_and_rejects_stale_source_pins(repository, tmp_path):
    row = dict(record_id='M9901', kind='strategy', subtype='reviewed_outline',
               reason='正文明确买入与持有用途。', evidence=[dict(field='规则', quote='收盘高于SMA20买入SPY')])
    destination = tmp_path / 'reviewed'
    batch.build(repository, destination, ['M9901'], [row])
    decisions = [json.loads(line) for line in (destination / 'decisions.jsonl').read_bytes().splitlines()]
    assert 'DEFINITION_DETAILS_MISSING' in decisions[0]['quality_flags']
    frozen = read(destination / 'overrides.json')
    frozen[0]['row_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='different source version'):
        batch.build(repository, tmp_path / 'stale-review', ['M9901'], frozen)
    assert not (tmp_path / 'stale-review').exists()


@pytest.mark.parametrize('mutation', ['duplicate-target', 'unknown-target', 'duplicate-override', 'outside-override', 'false-quote'])
def test_invalid_explicit_inputs_fail_before_writing(repository, tmp_path, mutation):
    targets, overrides = list(batch.source_rows(repository)), [override()]
    if mutation == 'duplicate-target':
        targets.append(targets[0])
    elif mutation == 'unknown-target':
        targets.append('M0000')
    elif mutation == 'duplicate-override':
        overrides.append(override())
    elif mutation == 'outside-override':
        overrides[0]['record_id'] = 'M0000'
    else:
        overrides[0]['evidence'][0]['quote'] = '不是原文'
    destination = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        batch.build(repository, destination, targets, overrides)
    assert not destination.exists()


def test_rehashing_source_index_does_not_break_frozen_corpus_binding(repository, tmp_path):
    folder = repository / 'metadata/corpus/first/metadata'
    index = read(folder / 'index.json')
    row = read(folder / index['records'][0]['path'])
    row['reported_fields']['名称']['value'] = 'modified'
    row['provenance']['row_sha256'] = canonical_hash({k: v['value'] for k, v in row['reported_fields'].items()})
    index['records'][0].update(write(folder / index['records'][0]['path'], row))
    write(folder / 'index.json', index)
    with pytest.raises(ValueError, match='digest mismatch'):
        batch.build(repository, tmp_path / 'invalid', ['M9901'], [])


def test_page_boundaries_cover_every_target_once(tmp_path):
    root = make_repository(tmp_path / 'repository', [(f'M{9000 + n}', f'Policy {n}', '买入SPY。') for n in range(101)])
    destination = root / 'metadata/classification/paginated'
    batch.build(root, destination, list(batch.source_rows(root)), [])
    index, decisions = validate(root, destination)
    assert len(decisions) == index['counts']['target_records'] == 101
    assert (destination / 'strategy/page-0001.md').read_text().count('\n\n## ') == 100
    assert (destination / 'strategy/page-0002.md').read_text().count('\n\n## ') == 1


def test_check_and_validate_cli_do_not_write(built, monkeypatch, capsys):
    root, destination, _ = built
    original = {p: p.read_bytes() for p in destination.rglob('*') if p.is_file()}
    monkeypatch.setattr('sys.argv', ['classification_batch', '--root', str(root), '--output', str(destination), '--check'])
    batch.main()
    assert json.loads(capsys.readouterr().out)['target_records'] == 5
    monkeypatch.setattr('sys.argv', ['classification_batch', '--root', str(root), '--validate',
                                   str((destination / 'index.json').relative_to(root))])
    batch.main()
    assert json.loads(capsys.readouterr().out)['manual_overrides'] == 1
    assert all(p.read_bytes() == raw for p, raw in original.items())

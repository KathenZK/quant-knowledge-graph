"""The committed catalog must account for every original ID without promoting it."""
import json
from pathlib import Path

from quantgraph.graph.metadata_catalog import BATCH, SOURCE
from quantgraph.graph.metadata_pilot import digest
from quantgraph.graph.metadata_public_subset import FORMAT, _batch_input, _checked_subset

ROOT = Path(__file__).resolve().parents[1] / 'metadata'


def test_committed_corpus_covers_original_ids_and_retains_all_field_evidence():
    index = json.loads((ROOT / 'corpus-index.json').read_bytes())
    assert index['schema_version'] == 'quantgraph-catalog-corpus-index/v1'
    assert index['source'] == SOURCE
    assert index['excluded_record_ids'] == ['M2535', 'M2709']
    assert index['counts'] == dict(
        source_original_ids=6973, public_source_records=6971, excluded_original_ids=2,
        batches=70, previously_committed_source_records=500, added_source_records=6471,
        classified_reading_views=200, reviewed_native_records=2,
        new_native_definitions=0, new_execution_trials=0,
    )
    assert index['all_source_fields_preserved_for_included_ids'] is True
    assert index['full_corpus_publicly_available'] is False
    assert index['classification_complete'] is False
    assert index['publication_status'] == 'FIELD_REVIEW_REQUIRED'
    assert index['source_verification_status'] == 'CATALOG_REPORTED_UNVERIFIED'
    assert index['commercial_use'] == 'REVIEW_REQUIRED'

    sources = {}
    excluded = []
    ordinals = set()
    paths = []
    for number, ref in enumerate(index['batches'], 1):
        bid = f'batch-{number:04d}'
        assert ref['batch_id'] == bid
        assert ref['csv_row_start'] == (number - 1) * 100 + 1
        assert ref['csv_row_end'] == min(number * 100, SOURCE['rows'])
        suffix = '-public-subset-v1' if ref['excluded_record_ids'] else '-v2'
        assert ref['path'] == f'corpus-checkpoints/grokbot-6973-20261003/batches/{bid}{suffix}'
        path = ROOT / ref['path']
        paths.append(path.name)
        if ref['schema_version'] == BATCH:
            manifest, inventory, blocked, _, _ = _batch_input(path, ref['manifest_sha256'])
            assert manifest['source'] == SOURCE
            assert manifest['batch_id'] == bid
            assert not blocked
        else:
            assert ref['schema_version'] == FORMAT
            manifest, _ = _checked_subset(path, ref['manifest_sha256'])
            assert manifest['source_csv_sha256'] == SOURCE['sha256']
            assert manifest['source_batch_id'] == bid
            assert manifest['excluded_record_ids'] == ref['excluded_record_ids']
            inventory = json.loads((path / 'inventory.json').read_bytes())
        ids = [entry['record_id'] for entry in inventory]
        assert ids == manifest['record_ids']
        assert len(ids) == ref['record_count']
        assert len(ids) + len(ref['excluded_record_ids']) == ref['csv_row_end'] - ref['csv_row_start'] + 1
        for entry in inventory:
            rid = entry['record_id']
            ordinal = entry['csv_row_ordinal']
            assert rid not in sources and ordinal not in ordinals
            assert ref['csv_row_start'] <= ordinal <= ref['csv_row_end']
            raw = (path / entry['knowledge_record']['path']).read_bytes()
            record = json.loads(raw)
            assert record['provenance']['csv_sha256'] == SOURCE['sha256']
            assert record['provenance']['csv_row_ordinal'] == ordinal
            assert record['source_webpage_fulltext_fetched'] is False
            assert record['execution_permission_granted'] is False
            assert record['new_execution_trials'] == 0
            assert all(field['status'] == 'CATALOG_REPORTED_UNVERIFIED'
                       for field in record['reported_fields'].values())
            classification = record['classification']
            if rid in {'M0256', 'M0259'}:
                assert classification['type_status'] == 'EXISTING_REVIEWED_METADATA'
            else:
                assert classification['entity_type'] is None
                assert classification['type_status'] == 'UNREVIEWED'
            sources[rid] = digest(raw)
            ordinals.add(ordinal)
        excluded.extend(ref['excluded_record_ids'])

    assert len(sources) == 6971
    assert excluded == index['excluded_record_ids']
    assert not set(excluded) & sources.keys()
    all_ids = {f'M{i:04d}' for i in range(SOURCE['min_id'], SOURCE['max_id'] + 1)}
    assert sorted(all_ids - sources.keys() - set(excluded)) == index['stable_id_gaps']
    assert len(index['stable_id_gaps']) == SOURCE['gaps']
    batch_root = ROOT / 'corpus-checkpoints/grokbot-6973-20261003/batches'
    assert sorted(p.name for p in batch_root.iterdir()) == sorted(paths)
    assert not any(batch_root.rglob('private-only'))

    reading = json.loads((ROOT / 'directory-index.json').read_bytes())
    assert len(reading['records']) == index['counts']['classified_reading_views']
    for entry in reading['records']:
        assert sources[entry['record_id']] == entry['source']['sha256']
    native = json.loads((ROOT / 'index.json').read_bytes())
    assert [r['record_id'] for r in native['records']] == ['M0256', 'M0259']

"""Restrictive overlays use synthetic pinned evidence and never alter results."""
from copy import deepcopy
import sqlite3

import pytest

from quantgraph.graph.research_data_quality import import_quality_overlay, data_quality_annotations
from test_research_interpretations import retained, origin, collection, encoded, digest


def quality_row(state):
    lineage = state['lineage']
    names = lineage['series_data_bindings']['S']
    return dict(
        record_id='R1', origin_run_id=state['run_id'], variant_id='R1@A',
        origin_manifest_sha256=state['binding']['manifest_sha256'],
        origin_metrics_file_sha256=state['binding']['metrics_file_sha256'],
        asset='S', actual_series_ref={'sha256': lineage['normalized_data_sha256'][names[0]]},
        strict_comparability_eligible=False, original_metrics_unchanged=True,
        data_quality_status='REQUIRES_REVIEW', priority='high',
        series_first_observation='2024-01-01', current_vehicle_inception='2024-01-02',
        historical_scope_requiring_review='Synthetic pre-inception observation',
        warning_zh='合成数据需复核；不是认证', official_sources=['https://example.org/synthetic'],
    )


def pin_overlay(state, rows=None, version='synthetic-quality-v1', **updates):
    body = encoded(dict(schema_version='quant-research-data-quality-overlay/v1', overlay_id=version,
                        new_execution_trials=0, records=rows if rows is not None else [quality_row(state)]) | updates)
    path = state['root'] / 'quality-overlay.json'
    path.write_bytes(body)
    return path, digest(body)


def ingest_overlay(state, rows=None, **kwargs):
    path, pin = pin_overlay(state, rows, **kwargs)
    return import_quality_overlay(state['catalog'], state['research'], path, pin)


def test_quality_is_restrictive_projection_with_exact_evidence_identity(retained):
    before = retained['research'].path.read_bytes()
    original_metrics = deepcopy(retained['research'].implementation('R1@A')['metrics'])
    row = quality_row(retained)
    row.update(metrics={'periods': {'full': {'total_return': 999}}},
               strict_validation_status='CERTIFIED', private_path='/private/do-not-project')
    path, pin = pin_overlay(retained, [row])
    result = import_quality_overlay(retained['catalog'], retained['research'], path, pin)
    assert result == dict(overlay_id='synthetic-quality-v1', attached=1, not_in_snapshot=[], new_execution_trials=0)
    saved = data_quality_annotations(retained['catalog'])[0]
    assert saved['strict_comparability_eligible'] is False
    assert saved['origin_manifest_sha256'] == retained['binding']['manifest_sha256']
    assert saved['collection_manifest_sha256'] == retained['collection_sha']
    assert saved['origin_manifest_sha256'] != saved['collection_manifest_sha256']
    assert saved['series_sha256'] == row['actual_series_ref']['sha256']
    assert saved['overlay_sha256'] == pin
    assert not {'metrics', 'strict_validation_status', 'private_path'} & saved.keys()
    assert retained['research'].implementation('R1@A')['metrics'] == original_metrics
    assert retained['research'].path.read_bytes() == before


@pytest.mark.parametrize('violation', ['pin', 'bytes'])
def test_quality_overlay_requires_exact_pinned_bytes(retained, violation):
    path, pin = pin_overlay(retained)
    if violation == 'pin':
        pin = '0' * 64
    else:
        path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='digest differs'):
        import_quality_overlay(retained['catalog'], retained['research'], path, pin)
    assert data_quality_annotations(retained['catalog']) == []


@pytest.mark.parametrize('field,value', [
    ('strict_comparability_eligible', True), ('strict_comparability_eligible', 0),
    ('strict_comparability_eligible', None), ('original_metrics_unchanged', False),
    ('original_metrics_unchanged', 1), ('original_metrics_unchanged', None),
])
def test_quality_cannot_certify_data_or_request_changed_returns(retained, field, value):
    before = retained['research'].path.read_bytes()
    row = quality_row(retained)
    row[field] = value
    with pytest.raises(ValueError, match='cannot certify data or change returns'):
        ingest_overlay(retained, [row])
    assert data_quality_annotations(retained['catalog']) == []
    assert retained['research'].path.read_bytes() == before


@pytest.mark.parametrize('field,value,message', [
    ('record_id', 'R2', 'execution identity'),
    ('variant_id', 'unknown-variant', 'execution identity'),
    ('origin_manifest_sha256', 'COLLECTION', 'origin manifest'),
    ('origin_metrics_file_sha256', '9' * 64, 'metric artifact'),
    ('asset', 'OTHER_INSTRUMENT', 'declared instrument'),
    ('actual_series_ref', {'sha256': '9' * 64}, 'declared instrument'),
])
def test_quality_rejects_wrong_manifest_metric_or_instrument_binding(retained, field, value, message):
    row = quality_row(retained)
    row[field] = retained['collection_sha'] if value == 'COLLECTION' else value
    with pytest.raises(ValueError, match=message):
        ingest_overlay(retained, [row])
    assert data_quality_annotations(retained['catalog']) == []


def test_later_invalid_overlay_binding_prevents_all_catalog_writes(retained):
    first = quality_row(retained)
    wrong = deepcopy(first)
    wrong.update(variant_id='R1@B', asset='OTHER_INSTRUMENT')
    with pytest.raises(ValueError, match='declared instrument'):
        ingest_overlay(retained, [first, wrong])
    assert data_quality_annotations(retained['catalog']) == []
    with pytest.raises(ValueError, match='Duplicate data-quality binding'):
        ingest_overlay(retained, [first, first])
    assert data_quality_annotations(retained['catalog']) == []


def test_out_of_snapshot_overlay_remains_unattached_and_does_not_invent_execution(retained):
    before = retained['research'].path.read_bytes()
    row = quality_row(retained)
    row['origin_run_id'] = 'absent-run'
    result = ingest_overlay(retained, [row])
    assert result['attached'] == 0
    assert result['not_in_snapshot'] == [dict(record_id='R1', run_id='absent-run', variant_id='R1@A',
                                              reason='ORIGIN_NOT_IN_THIS_SNAPSHOT')]
    assert data_quality_annotations(retained['catalog']) == []
    assert retained['research'].path.read_bytes() == before


def test_overlay_replay_is_idempotent_and_versions_are_append_only(retained):
    before = retained['research'].path.read_bytes()
    assert ingest_overlay(retained)['attached'] == 1
    assert ingest_overlay(retained)['attached'] == 1
    with retained['catalog'].connect() as con:
        assert con.execute('SELECT COUNT(*) FROM research_data_quality').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM research_data_quality_bindings').fetchone()[0] == 1
    row = quality_row(retained)
    row['warning_zh'] = 'Changed warning'
    with pytest.raises(ValueError, match='overlay is immutable'):
        ingest_overlay(retained, [row])
    assert len(data_quality_annotations(retained['catalog'])) == 1
    assert ingest_overlay(retained, [row], version='synthetic-quality-v2')['attached'] == 1
    assert [row['overlay_id'] for row in data_quality_annotations(retained['catalog'])] == [
        'synthetic-quality-v1', 'synthetic-quality-v2']
    with retained['catalog'].connect() as con:
        for table, field in [('research_data_quality', 'source_payload'), ('research_data_quality_bindings', 'payload')]:
            for sql in [f'DELETE FROM {table}', f"UPDATE {table} SET {field}='{{}}'"]:
                with pytest.raises(sqlite3.IntegrityError, match='immutable'):
                    con.execute(sql)
    assert retained['research'].path.read_bytes() == before


@pytest.mark.parametrize('updates', [{'schema_version': 'unknown'}, {'new_execution_trials': 1}])
def test_overlay_cannot_change_schema_or_create_execution_trials(retained, updates):
    with pytest.raises(ValueError, match='Unsupported restrictive'):
        ingest_overlay(retained, **updates)
    assert data_quality_annotations(retained['catalog']) == []


def test_duplicate_json_properties_are_rejected_before_overlay_import(retained):
    path, _ = pin_overlay(retained)
    raw = path.read_bytes().replace(b'"new_execution_trials": 0', b'"new_execution_trials": 0, "new_execution_trials": 1')
    path.write_bytes(raw)
    with pytest.raises(ValueError, match='Duplicate JSON key'):
        import_quality_overlay(retained['catalog'], retained['research'], path, digest(raw))
    assert data_quality_annotations(retained['catalog']) == []


def test_failed_quality_binding_rolls_back_overlay_and_preserves_history(retained):
    ingest_overlay(retained)
    before = data_quality_annotations(retained['catalog'])
    with retained['catalog'].connect() as con:
        con.execute("""CREATE TRIGGER synthetic_reject_quality BEFORE INSERT ON research_data_quality_bindings
                    WHEN NEW.overlay_id='synthetic-quality-v2'
                    BEGIN SELECT RAISE(ABORT,'Synthetic storage failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='Synthetic storage failure'):
        ingest_overlay(retained, version='synthetic-quality-v2')
    assert data_quality_annotations(retained['catalog']) == before
    with retained['catalog'].connect() as con:
        assert con.execute('SELECT COUNT(*) FROM research_data_quality').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM research_data_quality_bindings').fetchone()[0] == 1

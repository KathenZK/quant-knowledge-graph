"""Synthetic release tests over real retained collections; no private inputs."""
from copy import deepcopy
import gzip
import json
import sqlite3
import zlib

import pytest

from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.catalog_projection import item
from quantgraph.graph.corpus_export import export_delta
from quantgraph.graph.corpus_research import CorpusResearch
from quantgraph.graph.research_interpretations import import_interpretations, interpretations
from quantgraph.graph.research_universe import import_universe
from test_corpus_export import origin, import_export
from test_corpus_research import collection, encoded, digest


def pin_universe(state, version='synthetic-worklist-v1', rule='Synthetic rule'):
    cat = state['catalog']
    value = item('strategy', 'synthetic:one', 'Synthetic', 'StrategyVariant',
                 'definition-' + version, source_native_ids=['R1'])
    raw = {'raw_record': {'规则': rule, '市场': 'Synthetic market'},
           'variant': {'original_rule_text': rule, 'source_native_id': 'R1'}}
    with cat.connect() as con:
        cat._put(con, value, 'synthetic', raw)
    row = dict(record_id='R1', identity_namespace='grok_final_6973',
               entity_type='legacy_pending_review', definition_text=rule,
               definition_sha256=digest(rule.encode()), raw_record=raw['raw_record'])
    folder = state['root'] / version
    folder.mkdir()
    blobs = {'universe.jsonl.gz': gzip.compress(encoded(row), mtime=0),
             'summary.json': encoded({'total_research_objects_in_scope': 1})}
    for name, body in blobs.items():
        (folder / name).write_bytes(body)
    manifest = encoded(dict(schema_version='quant-research-universe-manifest/v1',
                            version=version, files={name: digest(body) for name, body in blobs.items()}))
    (folder / 'manifest.json').write_bytes(manifest)
    import_universe(cat, folder, digest(manifest))
    return digest(manifest), row['definition_sha256']


@pytest.fixture
def retained(origin, request):
    annotations = getattr(request, 'param', None)
    annotation_path = None
    if annotations is not None:
        annotation_path = origin['root'] / 'synthetic-annotations.json'
        annotation_path.write_bytes(encoded(dict(schema_version='strategy-screen-annotations/v1',
                                                run_id='synthetic-screen-v1', implementations=annotations)))
    receipt = export_delta(origin['origin'], origin['protocol'], origin['audit'], origin['export'],
                           annotation_path, format_version=3)
    import_export(origin, receipt)
    state = dict(origin, catalog=CatalogRepository(origin['root'] / 'catalog.sqlite'),
                 research=CorpusResearch(origin['runtime']))
    with state['research'].connect() as con:
        run = con.execute('SELECT * FROM corpus_runs').fetchone()
        state.update(run_id=run['run_id'], collection_sha=run['manifest_sha256'],
                     lineage=json.loads(run['lineage'])['declared_lineage'])
    state['universe_sha'], state['definition_sha'] = pin_universe(state)
    state['metrics'] = json.loads((origin['origin'] / 'strategy_metrics.json').read_bytes())
    state['binding'] = dict(
        origin_run_id=state['run_id'], variant_id='R1@A',
        manifest_sha256=state['lineage']['source_run_manifest_sha256'],
        metrics_file_sha256=digest((origin['origin'] / 'strategy_metrics.json').read_bytes()),
        spec_file_sha256=digest((origin['origin'] / 'implemented_specs.json').read_bytes()),
        active_annotation_sha256=None, metric_json_pointer='/0',
    )
    return state


def interpretation_row(state, version='synthetic-interpretation-v1'):
    binding = deepcopy(state['binding'])
    reference = {key: binding[key] for key in ['origin_run_id', 'variant_id', 'manifest_sha256']}
    return dict(record_id='R1', definition_sha256=state['definition_sha'],
                interpretation_version=version, new_execution_trials=0,
                evidence_bindings=[binding], observed_findings=[{'finding': 'Synthetic only', 'bindings': [reference]}],
                quantitative_evidence=[dict(variant_id='R1@A', metric_reference=reference,
                                           periods=deepcopy(state['metrics'][0]['periods']),
                                           windows_count=0, capital_state=None)])


def pin_interpretations(state, rows=None, *, version='synthetic-interpretation-v1', **updates):
    folder = state['root'] / 'interpretation-release'
    folder.mkdir(exist_ok=True)
    body = encoded(rows if rows is not None else [interpretation_row(state, version)])
    (folder / 'interpretations.json').write_bytes(body)
    manifest = encoded(dict(schema_version='quant-research-interpretation-release/v1', id=version,
                            new_execution_trials=0, source_universe_manifest_sha256=state['universe_sha'],
                            files={'interpretations.json': digest(body)}) | updates)
    (folder / 'manifest.json').write_bytes(manifest)
    return folder, digest(manifest)


def ingest_interpretations(state, rows=None, **kwargs):
    folder, pin = pin_interpretations(state, rows, **kwargs)
    return import_interpretations(state['catalog'], state['research'], folder, pin)


def test_pinned_interpretation_preserves_origin_collection_and_empty_annotation_distinction(retained):
    before = retained['research'].path.read_bytes()
    receipt = ingest_interpretations(retained)
    assert receipt['new_execution_trials'] == 0 and receipt['replayed'] is False
    saved = interpretations(retained['catalog'], 'R1')[0]
    binding = saved['evidence_bindings'][0]
    assert binding['origin_manifest_sha256'] == retained['binding']['manifest_sha256']
    assert binding['collection_manifest_sha256'] == retained['collection_sha']
    assert binding['origin_manifest_sha256'] != binding['collection_manifest_sha256']
    assert binding['graph_annotation_artifact_sha256'] == retained['lineage']['metadata_enrichment']['operator_annotations_sha256']
    assert binding['source_annotation_sha256'] is None
    assert binding['graph_annotation_artifact_sha256'] is not None
    assert saved['catalog_entity_id'] == 'synthetic:one'
    assert saved['catalog_definition_revision'] == 'definition-synthetic-worklist-v1'
    assert saved['binding_status'] == 'SOURCE_DEFINITION_AND_ORIGINAL_EVIDENCE_BOUND'
    assert saved['quantitative_evidence'][0]['periods'] == retained['metrics'][0]['periods']
    assert interpretations(retained['catalog'], 'absent') == []
    assert retained['research'].path.read_bytes() == before


@pytest.mark.parametrize('violation', ['manifest', 'file', 'stored_metric'])
def test_interpretation_pins_are_verified_before_catalog_write(retained, violation):
    folder, pin = pin_interpretations(retained)
    if violation == 'manifest':
        pin = '0' * 64
    elif violation == 'file':
        (folder / 'interpretations.json').write_bytes(b'[]')
    else:
        with sqlite3.connect(retained['research'].path) as con:
            # Model disk-level corruption only inside this disposable synthetic DB.
            con.execute('DROP TRIGGER corpus_artifacts_no_update')
            con.execute("UPDATE corpus_artifacts SET content=? WHERE name='origin__strategy_metrics.json'",
                        (zlib.compress(b'[]'),))
    with pytest.raises(ValueError):
        import_interpretations(retained['catalog'], retained['research'], folder, pin)
    assert interpretations(retained['catalog']) == []


@pytest.mark.parametrize('field,value,message', [
    ('definition_sha256', '9' * 64, 'definition'),
    ('new_execution_trials', 1, 'version/trial'),
    ('interpretation_version', 'another-version', 'version/trial'),
])
def test_interpretation_cannot_relabel_definition_or_trials(retained, field, value, message):
    row = interpretation_row(retained)
    row[field] = value
    with pytest.raises(ValueError, match=message):
        ingest_interpretations(retained, [row])
    assert interpretations(retained['catalog']) == []


@pytest.mark.parametrize('field,value,message', [
    ('manifest_sha256', 'COLLECTION', 'Origin manifest'),
    ('metrics_file_sha256', '9' * 64, 'metric artifact'),
    ('spec_file_sha256', '9' * 64, 'specification artifact'),
    ('active_annotation_sha256', '9' * 64, 'assessment revision'),
    ('metric_json_pointer', '/1', 'pointer identity'),
    ('metric_json_pointer', '/99', 'does not resolve'),
    ('metric_json_pointer', '/0/periods', 'direct original'),
    ('origin_run_id', 'unknown-run', 'execution identity'),
])
def test_interpretation_binding_mismatches_fail_atomically(retained, field, value, message):
    row = interpretation_row(retained)
    row['evidence_bindings'][0][field] = retained['collection_sha'] if value == 'COLLECTION' else value
    with pytest.raises(ValueError, match=message):
        ingest_interpretations(retained, [row])
    assert interpretations(retained['catalog']) == []


@pytest.mark.parametrize('retained', [{'R1@A': {'additional_hypothesis_reason': 'Synthetic unresolved source interpretation'}}], indirect=True)
def test_nonempty_annotations_must_be_bound_explicitly(retained):
    with pytest.raises(ValueError, match='cannot ignore active annotations'):
        ingest_interpretations(retained)
    assert interpretations(retained['catalog']) == []
    row = interpretation_row(retained)
    annotation = retained['lineage']['metadata_enrichment']['operator_annotations_sha256']
    row['evidence_bindings'][0]['active_annotation_sha256'] = annotation
    assert ingest_interpretations(retained, [row])['replayed'] is False
    assert interpretations(retained['catalog'])[0]['evidence_bindings'][0]['source_annotation_sha256'] == annotation


@pytest.mark.parametrize('field', ['periods', 'cost_sensitivity', 'additional_execution_delay',
                                  'additional_execution_delay_interpretation', 'primary_window_id',
                                  'window_selection', 'windows_count', 'capital_state'])
def test_quantitative_fields_cannot_disagree_with_original_metrics(retained, field):
    row = interpretation_row(retained)
    row['quantitative_evidence'][0][field] = {'forged': 999}
    with pytest.raises(ValueError, match='differs from original metric'):
        ingest_interpretations(retained, [row])
    assert interpretations(retained['catalog']) == []


@pytest.mark.parametrize('field,value', [('origin_run_id', 'unknown-run'), ('variant_id', 'R1@B'),
                                        ('manifest_sha256', '9' * 64)])
def test_metric_reference_must_resolve_to_the_bound_implementation(retained, field, value):
    row = interpretation_row(retained)
    row['quantitative_evidence'][0]['metric_reference'][field] = value
    row['observed_findings'] = []
    with pytest.raises(ValueError, match='variant|pinned implementation'):
        ingest_interpretations(retained, [row])
    assert interpretations(retained['catalog']) == []


def test_duplicate_bindings_and_findings_outside_interpretation_are_rejected(retained):
    row = interpretation_row(retained)
    row['evidence_bindings'].append(deepcopy(row['evidence_bindings'][0]))
    with pytest.raises(ValueError, match='Duplicate interpretation binding'):
        ingest_interpretations(retained, [row])
    row = interpretation_row(retained)
    row['observed_findings'][0]['bindings'][0]['manifest_sha256'] = '9' * 64
    with pytest.raises(ValueError, match='outside this interpretation'):
        ingest_interpretations(retained, [row])
    assert interpretations(retained['catalog']) == []


def test_replay_is_idempotent_versions_append_and_history_cannot_change(retained):
    assert not ingest_interpretations(retained)['replayed']
    assert ingest_interpretations(retained)['replayed']
    row = interpretation_row(retained)
    row['conclusion'] = 'Changed authored conclusion'
    with pytest.raises(ValueError, match='release is immutable'):
        ingest_interpretations(retained, [row])
    assert len(interpretations(retained['catalog'])) == 1
    assert not ingest_interpretations(retained, version='synthetic-interpretation-v2')['replayed']
    assert [row['interpretation_version'] for row in interpretations(retained['catalog'])] == [
        'synthetic-interpretation-v2', 'synthetic-interpretation-v1']
    with retained['catalog'].connect() as con:
        assert con.execute('SELECT COUNT(*) FROM research_interpretation_releases').fetchone()[0] == 2
        for table, column in [('research_interpretation_releases', 'manifest_json'), ('research_interpretations', 'payload')]:
            for sql in [f'DELETE FROM {table}', f"UPDATE {table} SET {column}='{{}}'"]:
                with pytest.raises(sqlite3.IntegrityError, match='immutable'):
                    con.execute(sql)


def test_declared_worklist_pin_cannot_be_substituted_with_latest_definition(retained):
    old_pin = retained['universe_sha']
    _, new_definition = pin_universe(retained, 'synthetic-worklist-v2', 'Changed synthetic rule')
    row = interpretation_row(retained)
    row['definition_sha256'] = new_definition
    with pytest.raises(ValueError, match='definition|worklist'):
        ingest_interpretations(retained, [row], source_universe_manifest_sha256=old_pin)
    assert interpretations(retained['catalog']) == []


def test_historical_interpretation_keeps_its_pinned_worklist_definition(retained):
    old_row = interpretation_row(retained)
    pin_universe(retained, 'synthetic-worklist-v2', 'Changed synthetic rule')
    assert ingest_interpretations(retained, [old_row])['records'] == 1
    saved = interpretations(retained['catalog'])[0]
    assert saved['catalog_definition_revision'] == 'definition-synthetic-worklist-v1'
    assert saved['definition_sha256'] == old_row['definition_sha256']


def test_failed_interpretation_write_rolls_back_release_and_preserves_history(retained):
    ingest_interpretations(retained)
    before = interpretations(retained['catalog'])
    with retained['catalog'].connect() as con:
        con.execute("""CREATE TRIGGER synthetic_reject_interpretation BEFORE INSERT ON research_interpretations
                    WHEN NEW.version='synthetic-interpretation-v2'
                    BEGIN SELECT RAISE(ABORT,'Synthetic storage failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='Synthetic storage failure'):
        ingest_interpretations(retained, version='synthetic-interpretation-v2')
    assert interpretations(retained['catalog']) == before
    with retained['catalog'].connect() as con:
        assert con.execute('SELECT COUNT(*) FROM research_interpretation_releases').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM research_interpretations').fetchone()[0] == 1

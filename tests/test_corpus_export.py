"""Metadata-only v2 export keeps origin protocols/bytes and rejects forged projections."""
import json
from pathlib import Path

import pytest

from quantgraph.graph.corpus_export import ORIGIN_NAMES, SCHEMA_V2, export_delta
from quantgraph.graph.corpus_research import CorpusResearch, build_manifest, import_manifest
from test_corpus_research import collection, encoded, digest


@pytest.fixture
def origin(collection):
    root=collection['root']/'origin';root.mkdir()
    source=collection['results']
    for name in ['implemented_specs.json','daily_returns.csv.gz','all_record_coverage.csv','run_summary.json']:
        (root/name).write_bytes((source/name).read_bytes())
    metrics=json.loads((source/'strategy_metrics.json').read_bytes())
    for row in metrics:
        row.pop('protocol_sha256');row.pop('implementation_specs_sha256')
    (root/'strategy_metrics.json').write_bytes(encoded(metrics))
    (root/'implementation_status.json').write_bytes(encoded([
        dict(id='R1',variant_id='R1@A',status='tested'),dict(id='R1',variant_id='R1@B',status='tested'),
        dict(id='R4',variant_id='R4',status='market_data_unavailable',reason='missing specified input')]))
    (root/'strategy_metrics.csv').write_text('id,variant_id\nR1,R1@A\nR1,R1@B\n')
    (root/'target_hashes.json').write_bytes(encoded({'R1@A':'b'*64,'R1@B':'c'*64}))
    protocol=collection['root']/'protocol.json';protocol.write_bytes(encoded({'base_cost_bps':5}))
    manifest=dict(run_id='synthetic-screen-v1',created_at_utc='2026-01-01T00:00:00Z',
        protocol_sha256=digest(protocol.read_bytes()),input_files={'S':{'path':'/private/source/S.csv','sha256':'7'*64}},
        code_hashes={'/private/code/engine.py':'6'*64},
        periods={'full':['2024-01-01','2024-01-02'],'later':['2024-01-03','2024-01-03']},
        result_hashes={name:digest((root/name).read_bytes()) for name in ORIGIN_NAMES if name!='run_manifest.json'})
    (root/'run_manifest.json').write_bytes(encoded(manifest))
    return collection|dict(origin=root,protocol=protocol,export=collection['root']/'export')


def do_export(data):
    return export_delta(data['origin'],data['protocol'],data['audit'],data['export'])


def import_export(data,receipt):
    return import_manifest(data['runtime'],data['export']/'import-manifest.json',receipt['manifest_sha256'],data['export'],data['export'])


def test_export_keeps_all_origin_bytes_and_rebuilds_only_own_coverage(origin):
    hashes={name:digest((origin['origin']/name).read_bytes()) for name in ORIGIN_NAMES}
    receipt=do_export(origin)
    assert receipt['recomputed'] is False and receipt['artifact_count']==20
    assert json.loads((origin['export']/'import-manifest.json').read_bytes())['schema_version']==SCHEMA_V2
    for name,expected in hashes.items():
        assert digest((origin['origin']/name).read_bytes())==expected
        assert digest((origin['export']/('origin__'+name)).read_bytes())==expected
    import_export(origin,receipt)
    reader=CorpusResearch(origin['runtime'])
    assert reader.record('R3')['status']=='not_evaluated_in_this_run'
    detail=reader.implementation('R1@A')
    assert detail['origin_run_id']=='synthetic-screen-v1'
    declared=detail['lineage']['declared_lineage']
    assert declared['protocol_sha256']==digest(origin['protocol'].read_bytes())
    assert declared['source_run_manifest_sha256']==hashes['run_manifest.json']
    assert declared['metadata_enrichment']['recomputed'] is False
    assert 'protocol_amendments_sha256' not in declared  # Never fabricate nonexistent origin manifests.
    with pytest.raises(ValueError,match='no overwrite'):
        do_export(origin)


def test_repinning_changed_projection_cannot_change_original_metrics(origin):
    do_export(origin)
    path=origin['export']/'strategy_metrics.json';rows=json.loads(path.read_bytes())
    rows[0]['periods']['full']['total_return']=999;path.write_bytes(encoded(rows))
    pinned=origin['root']/'repinned.json'
    receipt=build_manifest(origin['export'],origin['export'],pinned)
    with pytest.raises(ValueError,match='differs from retained origin bytes'):
        import_manifest(origin['runtime'],pinned,receipt['manifest_sha256'],origin['export'],origin['export'])
    assert not origin['runtime'].exists()


@pytest.mark.parametrize('filename',['strategy_metrics.json','daily_returns.csv.gz','run_summary.json','implemented_specs.json'])
def test_origin_hash_mismatch_rejected_before_export(origin,filename):
    path=origin['origin']/filename;path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='Origin artifact digest mismatch'):
        do_export(origin)
    assert not origin['export'].exists()


def test_wrong_protocol_rejected(origin):
    origin['protocol'].write_bytes(encoded({'base_cost_bps':25}))
    with pytest.raises(ValueError,match='Origin protocol digest mismatch'):
        do_export(origin)


def test_mixed_origin_cannot_be_projected_as_new_run(origin):
    path=origin['origin']/'strategy_metrics.json';rows=json.loads(path.read_bytes());rows[0]['run_id']='previous-run';path.write_bytes(encoded(rows))
    manifest=origin['origin']/'run_manifest.json';v=json.loads(manifest.read_bytes());v['result_hashes'][path.name]=digest(path.read_bytes());manifest.write_bytes(encoded(v))
    with pytest.raises(ValueError,match='Mixed-origin'):
        do_export(origin)


def test_proxy_and_hypothesis_overlap_keeps_both_deviations(origin):
    for name in ['strategy_metrics.json','implemented_specs.json']:
        p=origin['origin']/name;rows=json.loads(p.read_bytes())
        rows[0].update(asset_proxy='ETF replaces index',parameter_hypothesis='Full capital replaces fixed shares')
        p.write_bytes(encoded(rows))
    p=origin['origin']/'run_manifest.json';manifest=json.loads(p.read_bytes())
    for name in ['strategy_metrics.json','implemented_specs.json']:
        manifest['result_hashes'][name]=digest((origin['origin']/name).read_bytes())
    p.write_bytes(encoded(manifest))
    receipt=do_export(origin);import_export(origin,receipt)
    detail=CorpusResearch(origin['runtime']).implementation('R1@A')
    assert detail['fidelity_class']=='PROXY_HYPOTHESIS'
    assert 'ETF replaces index' in detail['fidelity_reason'] and 'fixed shares' in detail['fidelity_reason']


def test_reviewed_annotations_are_separate_evidence_and_limit_delay_claim(origin):
    p=origin['origin']/'strategy_metrics.json';values=json.loads(p.read_bytes())
    values[0]['additional_day_lag']={'full':{'total_return':0.01}};p.write_bytes(encoded(values))
    p=origin['origin']/'run_manifest.json';v=json.loads(p.read_bytes());v['result_hashes']['strategy_metrics.json']=digest((origin['origin']/'strategy_metrics.json').read_bytes());p.write_bytes(encoded(v))
    annotations=origin['root']/'annotations.json';annotations.write_bytes(encoded(dict(schema_version='strategy-screen-annotations/v1',run_id='synthetic-screen-v1',implementations={'R1@A':{'additional_hypothesis_reason':'Endpoint interpretation is unresolved','deep_validation_scope':'FIXED_ORDER_PATH_DELAY'}})))
    receipt=export_delta(origin['origin'],origin['protocol'],origin['audit'],origin['export'],annotations)
    import_export(origin,receipt)
    detail=CorpusResearch(origin['runtime']).implementation('R1@A')
    assert detail['fidelity_class']=='HYPOTHESIS'
    assert detail['deep_validation']['scope']=='FIXED_ORDER_PATH_DELAY'
    assert detail['lineage']['declared_lineage']['metadata_enrichment']['operator_annotations_sha256']==digest(annotations.read_bytes())
    assert 'parameter_hypothesis' not in json.loads((origin['origin']/'strategy_metrics.json').read_bytes())[0]


def test_annotation_cannot_bind_another_run_or_unknown_implementation(origin):
    annotations=origin['root']/'annotations.json'
    annotations.write_bytes(encoded(dict(schema_version='strategy-screen-annotations/v1',run_id='other-run',implementations={})))
    with pytest.raises(ValueError,match='annotations must bind'):
        export_delta(origin['origin'],origin['protocol'],origin['audit'],origin['export'],annotations)
    assert not origin['export'].exists()


@pytest.mark.parametrize('field,expected',[('asset_proxy','PROXY'),('parameter_hypothesis','HYPOTHESIS')])
def test_null_metric_cannot_erase_positive_spec_fidelity(origin,field,expected):
    for name in ['strategy_metrics.json','implemented_specs.json']:
        path=origin['origin']/name;rows=json.loads(path.read_bytes())
        rows[0][field]=None if name=='strategy_metrics.json' else 'Positive spec deviation'
        path.write_bytes(encoded(rows))
    path=origin['origin']/'run_manifest.json';manifest=json.loads(path.read_bytes())
    for name in ['strategy_metrics.json','implemented_specs.json']:
        manifest['result_hashes'][name]=digest((origin['origin']/name).read_bytes())
    path.write_bytes(encoded(manifest))
    receipt=do_export(origin);import_export(origin,receipt)
    detail=CorpusResearch(origin['runtime']).implementation('R1@A')
    assert detail['fidelity_class']==expected and detail['fidelity_reason']=='Positive spec deviation'
    assert detail['metrics'][field] is None  # Original declaration preserved, not silently rewritten.


def test_conflicting_positive_fidelity_reasons_require_review(origin):
    for name in ['strategy_metrics.json','implemented_specs.json']:
        path=origin['origin']/name;rows=json.loads(path.read_bytes());rows[0]['asset_proxy']=name+' contradictory reason';path.write_bytes(encoded(rows))
    path=origin['origin']/'run_manifest.json';manifest=json.loads(path.read_bytes())
    for name in ['strategy_metrics.json','implemented_specs.json']:
        manifest['result_hashes'][name]=digest((origin['origin']/name).read_bytes())
    path.write_bytes(encoded(manifest))
    with pytest.raises(ValueError,match='Conflicting nonempty'):
        do_export(origin)
    assert not origin['export'].exists()

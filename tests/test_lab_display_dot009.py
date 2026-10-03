"""Synthetic dot009 contracts; no Lab checkout, private data or actual metrics."""
import calendar
from copy import deepcopy
import gzip
import json

import pytest

from quantgraph.graph import lab_display_dot009 as dot
from quantgraph.graph.lab_display_projection import digest, encoded, merge_snapshot, prepare, project, verified_source
from test_lab_display_projection import active


def fixture(tmp_path, monkeypatch, rid='M1346'):
    root = tmp_path/'source'; root.mkdir()
    e = dict(id=rid, group='synthetic', lab_commit='b'*40, origin_lab_commit=dot.ORIGIN_PIN,
             run_id='synthetic-'+rid, variant_id=rid+'-base', fidelity_class='HYPOTHESIS',
             source_contract=dot.CONTRACTS[rid], projection_profile=dot.PROFILE, manifest_kind=dot.KIND)
    configs = [dict(name=n, fee_bps_each_side=f, slippage_bps_each_side=2, delay_bars=l)
               for n, f, l in [('base', 8, 1), ('fee0', 0, 1), ('fee20', 20, 1), ('delay2', 8, 2)]]
    metric = dict(total_return=0.0, cagr=0.0, max_drawdown=0.0, sharpe_zero_cash=None,
                  observations=731, final_equity=100000.0)
    view = dict(metric, sharpe=None, start='2023-01-01', end='2024-12-31', annualization=365)
    cases = [dict(metric, case=x['name'], kind='STRATEGY', fee_bps=x['fee_bps_each_side'],
                  slippage_bps=2, delay_bars=x['delay_bars'], fills=0) for x in configs]
    stats = dict(basis='synthetic daily convention, not real research values')
    rules = dict(id=rid, input={'sha256': 'c'*64}, economic_hypothesis='Synthetic unverified hypothesis',
                 **{k: 'Synthetic '+k for k in dot.RULE_KEYS+dot.SPECIAL[rid]})
    rules.update(capital=dict(fraction='1', initial_cash='100000', entry_fee_inclusive=True, Decimal_precision=50),
                 cost_cases=configs, statistics=stats)
    control = dict(id='M1258', input_sha256='c'*64, initial_cash='100000', allocation='100% fee-inclusive',
                   fee_bps_each_side=8, slippage_bps_each_side=2, bars=731, trusted=False, window_OOS=False, statistics=stats)
    control_sha = digest(encoded(control)); monkeypatch.setattr(dot, 'CONTROL_SHA', control_sha)
    projection = dict(reference_sha256=control_sha, new_controls=0, trusted=False, window_OOS=False, metrics=metric)
    summary = dict(id=rid, classification=dot.FIDELITY, execution_class=dot.EXECUTION, strict_reproductions=0,
                   trusted=False, window_OOS=False, strategy_configurations=4, new_controls=0,
                   cases=cases, input_sha256='c'*64, benchmark_reuse=projection)
    if rid == 'M1349': summary['execution_policy'] = {'max_completed_closes': 25}
    fields = {'id': rid, **{k: 'Synthetic '+k for k in ['名称', '市场', '规则', '作者或机构', '标题',
                                                     'source_url', '页码或文件', '可回测', '别名来源', '提出日期']}}
    dates = ['2023-01-01'] + [f'{y}-{m:02d}-{calendar.monthrange(y, m)[1]}' for y in [2023, 2024] for m in range(1, 13)]
    curve = [dict(date=date, equity=1.0, drawdown=0.0) for date in dates]
    meta = dict(point_count=25, source_observations=731, normalized_to_initial=100000, returned_points=25,
                observations=731, total_observations=731, equity_unit='initial_capital_multiple', drawdown_unit='fraction',
                denominator=100000, first_point_rebased=False, full_daily_curve_published=False,
                interpolation_claim=False, private_daily_nav_used=False)
    metrics = dict(periods={'2023-2024': deepcopy(view)}, same_instrument_benchmark={'2023-2024': deepcopy(view)},
                   additional_native_bar_lag={'2023-2024': deepcopy(view)},
                   cost_sensitivity={k: {'2023-2024': deepcopy(view)} for k in ['fee0', 'fee20']})
    original = dict(id=rid, run_id=e['run_id'], origin_run_id=e['run_id'], variant_id=e['variant_id'], family='synthetic',
                    name='Synthetic '+rid, fidelity_class='HYPOTHESIS', execution_class=dot.EXECUTION,
                    audit=dict(original_runtime_equivalence=False, trusted=False), lineage={}, metrics=metrics,
                    curve=curve, curve_meta=deepcopy(meta), limitations=['Synthetic original limit'])
    d = deepcopy(original)
    d.update(projection_profile=dot.PROFILE, source_contract=e['source_contract'], research_fidelity=dot.FIDELITY,
             implementation_fidelity=dot.EXECUTION, manifest_kind=dot.KIND, projection_status='STAGED_NOT_IMPORTED',
             lab_counts=dict(strategy_ids=1, strategy_configurations=4, new_control_configurations=0, reused_control_configurations=1, strict_reproductions=0),
             projection_activity=dict(new_strategy_trials=0, new_controls=0),
             spec=dict(params={'rules': {k: rules[k] for k in dot.RULE_KEYS+dot.SPECIAL[rid]}, 'metric_conventions': stats}, assumptions=[]))
    d['metrics']['cost_sensitivity'] = {str(f): d['metrics']['cost_sensitivity'][n] for f, n in [(0, 'fee0'), (20, 'fee20')]}
    for container in [d['metrics']['periods'], d['metrics']['same_instrument_benchmark'], d['metrics']['additional_native_bar_lag'], *d['metrics']['cost_sensitivity'].values()]:
        container['full'] = deepcopy(container['2023-2024'])
    d['metrics'].update(source_period_aliases={'2023-2024': 'full'}, source_cost_key_aliases={'fee0': '0', 'fee20': '20'}, additional_lag_unit='day')
    r = dict(id=rid, name='Synthetic '+rid, status='tested_hypothesis_only', reason='Synthetic result',
             audit=deepcopy(fields), catalog_fields=deepcopy(fields),
             fidelity_class='HYPOTHESIS', research_fidelity=dot.FIDELITY, execution_class=dot.EXECUTION,
             source_contract=e['source_contract'], projection_profile=dot.PROFILE, manifest_kind=dot.KIND,
             projection_status='STAGED_NOT_IMPORTED', definition_revision_bound=False,
             configuration_runs=4, strategy_configurations=4, new_control_runs=0, control_configurations=0,
             reused_control_configurations=1, rules=deepcopy(d['spec']['params']['rules']),
             economic_basis=dict(hypothesis=rules['economic_hypothesis'], author_verified=False),
             monthly=None, monthly_status='STRATEGY_MONTHLY_VALUES_NOT_IN_SELECTED_PUBLIC_SUMMARY',
             results={x['case']: x for x in cases}, benchmark_reference=dict(kind='REUSED_ACCEPTED_M1258_BASE_CONTROL',
                id='M1258', reference_sha256=control_sha, projection=projection, matched_cost_controls_available=False))
    values = dict(record=r, detail=d, summary=summary, rules=rules, catalog={'fields': fields}, original_detail=original,
                  original_record={'id': rid, 'audit': deepcopy(fields)}, original_curve=curve, curve=deepcopy(curve),
                  control_reference=control, control_projection=projection, statistics=stats, cases=configs,
                  C0=dict(strategy_ids=[rid], classification=dot.FIDELITY, execution_class=dot.EXECUTION, new_controls=0, input_sha256='c'*64))
    blobs = {k: encoded(v) for k, v in values.items()}
    seal(root, e, blobs, monkeypatch)
    return root, e, blobs


def seal(root, entry, blobs, monkeypatch):
    """Re-pin synthetic bytes, leaving business values untouched for negatives."""
    rid = entry['id']; paths = dot.artifact_paths(rid)
    c0 = json.loads(blobs['C0'])
    c0['pins'] = [dict(path='frozen/'+name, **dot.fingerprint(blobs[role])) for role, name in
                  dict(rules=rid+'-root-frozen-rules.json', catalog=rid+'-catalog-original-fields.json', **dot.SHARED_FILES).items()]
    blobs['C0'] = encoded(c0)
    summary = json.loads(blobs['summary']); summary['C0_sha256'] = digest(blobs['C0']); blobs['summary'] = encoded(summary)
    original = json.loads(blobs['original_detail']); original['lineage']['C0_sha256'] = digest(blobs['C0']); blobs['original_detail'] = encoded(original)
    def ref(path, raw, pin):
        return dict(path=path, **dot.fingerprint(raw), url=f'https://github.com/KathenZK/quant-research-lab/blob/{pin}/{path}')
    refs = {('curve' if role == 'original_curve' else role): ref(path, blobs[role], dot.ORIGIN_PIN)
            for role, path in dot.source_paths(rid).items()}
    lock = dict(schema='selected-approved-git-source-lock/v1', commit=dot.ORIGIN_PIN,
                not_original_publication_manifest=True, records={x: (refs if x == rid else {}) for x in dot.CONTRACTS})
    blobs['selected_source_lock'] = encoded(lock); monkeypatch.setattr(dot, 'LOCK_SHA', digest(blobs['selected_source_lock']))
    r, d = (json.loads(blobs[k]) for k in ['record', 'detail'])
    manifest = dict(schema_version=dot.SCHEMA, manifest_kind=dot.KIND, projection_profile=dot.PROFILE,
                    source_contract=entry['source_contract'], id=rid, origin_run_id=entry['run_id'], variant_id=entry['variant_id'],
                    origin_lab_commit=dot.ORIGIN_PIN, original_private_result_manifest=False, original_results_modified=False,
                    source_lock_kind=dot.LOCK_KIND, source_lock_sha256=dot.LOCK_SHA, source_artifacts=refs,
                    files={**refs, 'base-nav-sampled.json': dot.fingerprint(blobs['curve'])}, curve_contract=d['curve_meta'],
                    excluded_from_self_hash=['public-display-manifest.json', 'graph-record.json', 'graph-detail.json'])
    blobs['result_manifest'] = encoded(manifest)
    binding = dict(origin_run_id=entry['run_id'], variant_id=entry['variant_id'], fidelity_class='HYPOTHESIS',
                   execution_class=dot.EXECUTION, protocol_sha256=digest(blobs['rules']), manifest_sha256=digest(blobs['result_manifest']))
    rr = dict(binding, manifest_kind=dot.KIND)
    r.update(source_artifacts=refs, related_results=[rr], implementations=[dict(rr, family='synthetic')])
    d.update(transport_binding=binding, lineage=dict(manifest_kind=dot.KIND, manifest_sha256=digest(blobs['result_manifest']),
        source_display_manifest_sha256=digest(blobs['result_manifest']), protocol_sha256=digest(blobs['rules']), protocol_hash_role=dot.RULE_KIND,
        C0_sha256=digest(blobs['C0']), lab_commit=dot.ORIGIN_PIN, source_artifacts=refs, source_lineage=original['lineage'], definition_revision_bound=False))
    blobs.update(record=encoded(r), detail=encoded(d))
    repin(root, entry, blobs, refs)


def repin(root, entry, blobs, refs=None):
    rid = entry['id']; paths = dot.artifact_paths(rid)
    refs = refs or json.loads(blobs['selected_source_lock'])['records'][rid]
    by_path = {paths[k]: dot.fingerprint(v) for k, v in blobs.items() if k != 'publication_manifest'}
    for path in dot.publication_paths(rid): by_path.setdefault(path, dot.fingerprint(b'synthetic unused public file'))
    pub = dict(schema='dot009-additive-public-display-publication/v1', manifest_kind=dot.PUBLICATION_KIND, id=rid, revision=1,
        source_commit=dot.ORIGIN_PIN, source_contract=entry['source_contract'], not_original_publication_manifest=True,
        historical_publication_manifest_existed=False, previous_publication_manifest=None, self_excluded=True,
        actual_strategy_configurations=4, projection_new_trials=0, projection_new_controls=0, strict_reproductions=0,
        public_curve_points=25, original_metric_observations=731, matched_cost_controls_available=False, reused_control_id='M1258',
        files=[dict(path=p, **v) for p, v in sorted(by_path.items())], payload_count=len(by_path), payload_bytes=sum(x['bytes'] for x in by_path.values()),
        source_lock_kind=dot.LOCK_KIND, source_lock=dict(path=paths['selected_source_lock'], **dot.fingerprint(blobs['selected_source_lock'])), source_artifacts=refs)
    blobs['publication_manifest'] = encoded(pub)
    entry['artifacts'] = {k: dict(path=paths[k], **dot.fingerprint(v),
        url=f'https://github.com/KathenZK/quant-research-lab/blob/{entry["lab_commit"]}/{paths[k]}') for k, v in blobs.items()}
    for role, body in blobs.items():
        p = root/paths[role]; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(body)


@pytest.mark.parametrize('rid', list(dot.CONTRACTS))
def test_dot009_positive_and_deterministic(tmp_path, monkeypatch, rid):
    root, e, b = fixture(tmp_path, monkeypatch, rid)
    r, d = project(e, verified_source(root, e))
    assert d['curve'] == json.loads(b['original_curve']) and len(d['curve']) == 25
    assert len(r['catalog_fields']) == 11 and d['metrics']['periods']['full']['observations'] == 731
    assert d['metrics']['additional_native_bar_lag']['full']['sharpe'] is None
    assert r['benchmark_reference']['id'] == 'M1258' and r['control_configurations'] == 0
    assert d['lineage']['publication_manifest_kind'] == dot.PUBLICATION_KIND
    registry = dict(schema_version='quantgraph-approved-lab-display-sources/v1', records=[e])
    first, second = tmp_path/'first', tmp_path/'second'
    status = prepare({'synthetic': root}, first, registry=registry)
    prepare({'synthetic': root}, second, registry=registry)
    assert status['active_merge_status'].startswith('BLOCKED_') and status['new_execution_trials'] == 0
    assert not (first/'site-sync-candidate.json').exists()
    assert {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()} == {p.relative_to(second): p.read_bytes() for p in second.rglob('*') if p.is_file()}
    with pytest.raises(ValueError): prepare({'synthetic': root}, first, registry=registry)


@pytest.mark.parametrize('rid', list(dot.CONTRACTS))
@pytest.mark.parametrize('change', ['unknown_contract', 'swapped_contract', 'missing_contract', 'origin_pin', 'source_hash',
    'shared_id', 'shared_role', 'shared_pin', 'traversal', 'symlink', 'lock_hash', 'lock_shared_path', 'extra_private_role',
    'inventory_kind', 'inventory_historical', 'inventory_duplicate', 'manifest_kind', 'cycle', 'protocol_forgery'])
def test_dot009_source_boundaries(tmp_path, monkeypatch, rid, change):
    root, e, b = fixture(tmp_path, monkeypatch, rid)
    if change == 'unknown_contract': e['source_contract'] = 'UNKNOWN'
    elif change == 'swapped_contract': e['source_contract'] = next(v for k, v in dot.CONTRACTS.items() if k != rid)
    elif change == 'missing_contract': e.pop('source_contract')
    elif change == 'origin_pin': e['origin_lab_commit'] = 'c'*40
    elif change == 'source_hash': (root/e['artifacts']['summary']['path']).write_bytes(b['summary']+b' ')
    elif change == 'shared_id': e['artifacts']['control_reference']['path'] = dot.source_paths('M9999')['summary']
    elif change == 'shared_role': e['artifacts']['statistics'] = deepcopy(e['artifacts']['cases'])
    elif change == 'shared_pin': e['artifacts']['control_reference']['url'] = e['artifacts']['control_reference']['url'].replace('b'*40, 'c'*40)
    elif change == 'traversal': e['artifacts']['summary']['path'] = '../outside'
    elif change == 'symlink':
        p = root/e['artifacts']['summary']['path']; target = tmp_path/'other'; target.write_bytes(b['summary']); p.unlink(); p.symlink_to(target)
    elif change == 'extra_private_role': e['artifacts']['private_output_inventory'] = deepcopy(e['artifacts']['summary'])
    else:
        role = ('selected_source_lock' if change.startswith('lock_') else 'publication_manifest' if change.startswith('inventory_') else
                'detail' if change == 'protocol_forgery' else 'result_manifest')
        value = json.loads(b[role])
        if change == 'lock_hash': value['not_original_publication_manifest'] = False
        elif change == 'lock_shared_path':
            value['records'][rid]['control_reference']['path'] = dot.SHARED+'unapproved.json'
        elif change == 'inventory_kind': value['manifest_kind'] = 'HISTORICAL_RUN_MANIFEST'
        elif change == 'inventory_historical': value['previous_publication_manifest'] = {'path': 'invented.json'}
        elif change == 'inventory_duplicate': value['files'].append(deepcopy(value['files'][0]))
        elif change == 'manifest_kind': value['manifest_kind'] = 'LAB_ORIGIN_RESULT_MANIFEST_NOT_GRAPH_COLLECTION'
        elif change == 'cycle': value['files']['graph-detail.json'] = dot.fingerprint(b['detail'])
        elif change == 'protocol_forgery': value['lineage']['protocol_hash_role'] = 'ORIGINAL_PROTOCOL'
        b[role] = encoded(value)
        if role != 'publication_manifest':
            if change == 'lock_shared_path': monkeypatch.setattr(dot, 'LOCK_SHA', digest(b[role]))
            repin(root, e, b)
        else:
            e['artifacts'][role].update(dot.fingerprint(b[role])); (root/e['artifacts'][role]['path']).write_bytes(b[role])
    with pytest.raises(ValueError): project(e, verified_source(root, e))


@pytest.mark.parametrize('rid', list(dot.CONTRACTS))
@pytest.mark.parametrize('change', ['full_conflict', 'full_bool_zero', 'null_to_zero', 'double_normalize', '731_points', 'USDT_unit',
    'fidelity', 'author_verified', 'new_control', 'projection_run', 'matched_cost', 'fee', 'lag', 'slippage', 'rules',
    'catalog', 'monthly', 'private', 'active_identity', 'capital', 'case_declaration', 'statistics', 'control_cost', 'control_bool', 'fee_bool'])
def test_dot009_semantic_rejections(tmp_path, monkeypatch, rid, change):
    root, e, b = fixture(tmp_path, monkeypatch, rid)
    obj = {k: json.loads(v) for k, v in b.items()}
    r, d, s, w = (obj[k] for k in ['record', 'detail', 'summary', 'rules'])
    if change == 'full_conflict': d['metrics']['periods']['full']['cagr'] = .5
    elif change == 'full_bool_zero': d['metrics']['periods']['full']['total_return'] = False
    elif change == 'null_to_zero': d['metrics']['additional_native_bar_lag']['full']['sharpe'] = 0
    elif change == 'double_normalize':
        for point in d['curve']: point['equity'] /= 100000
    elif change == '731_points': d['curve_meta']['returned_points'] = 731
    elif change == 'USDT_unit': d['curve_meta']['equity_unit'] = 'USDT'
    elif change == 'fidelity': r['research_fidelity'] = 'STRICT'
    elif change == 'author_verified': r['economic_basis']['author_verified'] = True
    elif change == 'new_control': r['control_configurations'] = 1
    elif change == 'control_bool': r['control_configurations'] = False
    elif change == 'fee_bool':
        s['cases'][1]['fee_bps'] = False; r['results'] = {v['case']: v for v in s['cases']}
    elif change == 'projection_run': d['projection_activity']['new_strategy_trials'] = 1
    elif change == 'matched_cost': r['benchmark_reference']['matched_cost_controls_available'] = True
    elif change in ['fee', 'lag', 'slippage']:
        key = {'fee': 'fee_bps', 'lag': 'delay_bars', 'slippage': 'slippage_bps'}[change]
        s['cases'][0][key] = 99; r['results'] = {v['case']: v for v in s['cases']}
    elif change == 'rules': r['rules']['entry'] = 'Invented'
    elif change == 'catalog': r['catalog_fields'].pop('规则')
    elif change == 'monthly': r['monthly'] = [0]
    elif change == 'private': r['note'] = 'libfile_synthetic_private'
    elif change == 'active_identity': r['entity_id'] = 'invented'
    elif change == 'capital': w['capital']['fraction'] = '0.95'
    elif change == 'case_declaration': obj['cases'][0]['fee_bps_each_side'] = 99
    elif change == 'statistics': obj['statistics']['basis'] = 'changed'
    elif change == 'control_cost': obj['control_reference']['fee_bps_each_side'] = 0
    b.update({k: encoded(v) for k, v in obj.items()})
    seal(root, e, b, monkeypatch)
    with pytest.raises(ValueError): project(e, verified_source(root, e))


def test_m1349_completed_closes_and_m1270_zero_null(tmp_path, monkeypatch):
    for rid, field, value in [('M1349', 'execution_policy', {'max_completed_closes': 24}),
                              ('M1270', 'cases', None)]:
        p = tmp_path/rid; p.mkdir(); root, e, b = fixture(p, monkeypatch, rid)
        s = json.loads(b['summary'])
        if field == 'cases': s['cases'][-1]['fills'] = 1
        else: s[field] = value
        b['summary'] = encoded(s); seal(root, e, b, monkeypatch)
        with pytest.raises(ValueError): project(e, verified_source(root, e))


def test_dot009_merge_is_additive_and_transport_unchanged(tmp_path, monkeypatch):
    source, e, b = fixture(tmp_path, monkeypatch)
    r, d = project(e, verified_source(source, e))
    root, receipt, shard = active(tmp_path, r, d)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assets, envelope = merge_snapshot([r], [d], root, digest(encoded(receipt)), receipt['active_batch'])
    row = json.loads(gzip.decompress(assets[shard]))[e['id']]
    assert row['audit'] == {'retained': 'original'} and row['note_marker'] == 'unchanged' and len(row['related_results']) == 3
    assert set(envelope['results'][0]) == {'origin_run_id', 'variant_id', 'manifest_sha256', 'record_id', 'detail_path', 'detail_sha256'}
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    for path, raw in assets.items():
        p = root/'assets'/path[1:]; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)
        receipt['files'][path] = dot.fingerprint(raw)
    (root/'active-snapshot.json').write_bytes(encoded(receipt))
    assert merge_snapshot([r], [d], root, digest(encoded(receipt)), receipt['active_batch'])[0] == {}
    changed = deepcopy(d); changed['name'] = 'different frozen result'
    with pytest.raises(ValueError, match='different bytes'):
        merge_snapshot([r], [changed], root, digest(encoded(receipt)), receipt['active_batch'])

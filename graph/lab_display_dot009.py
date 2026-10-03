"""Three explicit catalog display contracts backed by a selected source lock.

The current public inventory is new; it is not a historical run publication.
Only four exact shared public paths may cross the stable-ID directory boundary.
"""
import calendar
from copy import deepcopy
import math
import re

from quantgraph.graph.corpus_research import _finite, _loads
from quantgraph.graph.metadata_pilot import digest, encoded, read_below

CONTRACTS = {
    'M1346': 'CATALOG_CLOSE25_LEVEL_FULLCASH_REUSED_CONTROL_V1',
    'M1349': 'CATALOG_ROC25_NEG10_HOLD25_FULLCASH_REUSED_CONTROL_V1',
    'M1270': 'CATALOG_UTC_SUNDAY_MONDAY_RAW_CANCEL_FULLCASH_REUSED_CONTROL_V1',
}
ORIGIN_PIN = '08e6ab4a49a808f53f06e509f06cb2c453f007d5'
LOCK_SHA = '4379e8c4897b9ae8d3eeaaf3a467549a71abd79600026b2da463a7f682b3d9f1'
CONTROL_SHA = 'ea4fb4687cffe69b7ee877312e19ec49b263bf5d21705d0dcfa2e791c24be00a'
SHARED = 'research/public-strategies/catalog-hypothesis-batch017-execution-20261003/payload/frozen/'
SHARED_FILES = {'control_reference': 'buyhold-reference-v1.json',
                'control_projection': 'reused-buyhold-projection-v1.json',
                'statistics': 'statistics-v1.json', 'cases': 'cases-v1.json'}
KIND = 'PUBLIC_DERIVED_DISPLAY_MANIFEST'
PROFILE = 'DAILY_SAMPLED_APPROVED_DETAIL_V1'
SCHEMA = 'quantgraph-public-derived-display-manifest/v2'
PUBLICATION_KIND = 'APPROVED_PUBLIC_DISPLAY_SOURCE_INVENTORY'
LOCK_KIND = 'SELECTED_APPROVED_GIT_SOURCE_LOCK_NOT_PUBLICATION_MANIFEST'
RULE_KIND = 'FROZEN_RULE_CONTRACT_NOT_INVENTED_PROTOCOL_FILE'
FIDELITY = 'HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED'
EXECUTION = 'ADAPTED_EXECUTION_PROXY'
RULE_KEYS = ['indicator', 'entry', 'exit', 'capital', 'execution', 'cold_start',
             'cost_cases', 'valuation', 'statistics', 'stop_or_roi', 'known_halt']
SPECIAL = {'M1346': [], 'M1349': ['holding_counter', 'source_warning'],
           'M1270': ['calendar_execution']}


def require(ok, reason):
    if not ok:
        raise ValueError('dot009: ' + reason)


def same(value, expected, reason):
    # Deep JSON comparison preserves null, bool/int and int/float distinctions.
    require(encoded(value) == encoded(expected), reason)


def fingerprint(raw):
    return dict(bytes=len(raw), sha256=digest(raw))


def selected(entry):
    return entry.get('id') in CONTRACTS or entry.get('source_contract') in CONTRACTS.values()


def identity(entry):
    rid = entry['id']
    require(rid in CONTRACTS and entry.get('source_contract') == CONTRACTS[rid], 'ID/contract mismatch')
    require(entry.get('projection_profile') == PROFILE and entry.get('manifest_kind') == KIND
            and entry.get('fidelity_class') == 'HYPOTHESIS', 'Explicit profile/type/fidelity required')
    require(re.fullmatch(r'[a-f0-9]{40}', entry.get('lab_commit', ''))
            and entry.get('origin_lab_commit') == ORIGIN_PIN, 'Exact current and origin pins required')
    return rid


def source_paths(rid):
    prefix = f'research/public-strategies/{rid}/'
    old = prefix + 'artifacts/20261003-batch017-v1/'
    return dict(summary=old+'summary.json', original_detail=old+'graph-detail.json',
                original_record=old+'graph-record.json', original_curve=old+'light-curve.json',
                rules=prefix+'source/root-frozen-rules.json', catalog=prefix+'source/catalog-original-fields.json',
                C0=prefix+'specs/C0.json', **{k: SHARED+v for k, v in SHARED_FILES.items()})


def artifact_paths(rid):
    prefix = f'research/public-strategies/{rid}/'
    display = prefix+'artifacts/20261003-public-display-prep/'
    return dict(publication_manifest=prefix+'publication-manifest.display-v1.json',
                selected_source_lock=prefix+'scripts/public-display-v2/selected-public-source-lock.json',
                record=display+'graph-record.json', detail=display+'graph-detail.json',
                curve=display+'base-nav-sampled.json', result_manifest=display+'public-display-manifest.json',
                **source_paths(rid))


def publication_paths(rid):
    prefix = f'research/public-strategies/{rid}/'
    paths = set(artifact_paths(rid).values()) - {prefix+'publication-manifest.display-v1.json'}
    paths.update(prefix+'scripts/public-display-v2/'+name for name in
                 ['export_dot009.py', 'verify_dot009.py', 'common_public_display.py', 'frozen_export.py'])
    paths.update(prefix+'artifacts/20261003-public-display-review/'+name for name in
                 ['review.safe.json', 'DELIVERY-MANIFEST.json', 'EXACT-12-FILES.json'])
    paths.update(prefix+name for name in ['README-display-v1.md', 'decision-log-display-v1.md'])
    return paths


def source_binding(entry, blobs):
    rid = identity(entry)
    paths = artifact_paths(rid)
    require(set(entry['artifacts']) == set(blobs) == set(paths), 'Exact17 approved artifact roles required')
    for role, path in paths.items():
        ref = entry['artifacts'][role]
        require(ref['path'] == path and ref['url'] ==
                f'https://github.com/KathenZK/quant-research-lab/blob/{entry["lab_commit"]}/{path}',
                'Role path or current commit URL mismatch: '+role)
        same({k: ref[k] for k in ['bytes', 'sha256']}, fingerprint(blobs[role]), 'Source hash/bytes mismatch: '+role)
    pub, lock = (_loads(blobs[k]) for k in ['publication_manifest', 'selected_source_lock'])
    _finite([pub, lock])
    require(pub['schema'] == 'dot009-additive-public-display-publication/v1'
            and pub['manifest_kind'] == PUBLICATION_KIND and pub['id'] == rid and pub['revision'] == 1
            and pub['source_commit'] == ORIGIN_PIN and pub['source_contract'] == CONTRACTS[rid]
            and pub['not_original_publication_manifest'] is True and pub['historical_publication_manifest_existed'] is False
            and pub['previous_publication_manifest'] is None and pub['self_excluded'] is True,
            'Current selective inventory is not a historical publication')
    require(pub['actual_strategy_configurations'] == 4 and pub['projection_new_trials'] == pub['projection_new_controls'] == 0
            and pub['strict_reproductions'] == 0 and pub['public_curve_points'] == 25
            and pub['original_metric_observations'] == 731 and pub['matched_cost_controls_available'] is False
            and pub['reused_control_id'] == 'M1258', 'Publication scope/count/control conflict')
    same([pub[k] for k in ['actual_strategy_configurations', 'projection_new_trials', 'projection_new_controls', 'strict_reproductions']],
         [4, 0, 0, 0], 'Publication count types changed')
    allowed = {}
    for ref in pub['files']:
        path = ref['path']
        require(path not in allowed, 'Duplicate publication path')
        allowed[path] = {k: ref[k] for k in ['bytes', 'sha256']}
    require(set(allowed) == publication_paths(rid) and len(allowed) == pub['payload_count'] == 25
            and pub['payload_bytes'] == sum(x['bytes'] for x in allowed.values()), 'Selective publication scope changed')
    for role, path in paths.items():
        if role != 'publication_manifest':
            same(allowed[path], fingerprint(blobs[role]), 'Artifact outside exact publication allowlist: '+role)
    require(digest(blobs['selected_source_lock']) == LOCK_SHA and lock['schema'] == 'selected-approved-git-source-lock/v1'
            and lock['commit'] == ORIGIN_PIN and lock['not_original_publication_manifest'] is True
            and set(lock['records']) == set(CONTRACTS) and pub['source_lock_kind'] == LOCK_KIND,
            'Approved selected source lock/type/pin mismatch')
    same(pub['source_lock'], dict(path=paths['selected_source_lock'], **fingerprint(blobs['selected_source_lock'])), 'Publication lock binding mismatch')
    refs = lock['records'][rid]
    same(pub['source_artifacts'], refs, 'Publication selected source roles conflict')
    require(set(refs) == (set(source_paths(rid)) - {'original_curve'}) | {'curve'}, 'Exactly11 origin roles required')
    for role, ref in refs.items():
        selected_role = 'original_curve' if role == 'curve' else role
        path = paths[selected_role]
        require(ref['path'] == path and ref['url'] ==
                f'https://github.com/KathenZK/quant-research-lab/blob/{ORIGIN_PIN}/{path}', 'Origin role/ID/shared path/pin mismatch')
        same({k: ref[k] for k in ['bytes', 'sha256']}, fingerprint(blobs[selected_role]), 'Origin role hash mismatch')
    return refs


def verified_source(root, entry):
    rid = identity(entry)
    paths = artifact_paths(rid)
    require(set(entry['artifacts']) == set(paths), 'Exact17 approved artifact roles required')
    blobs = {}
    # Validate exact role paths before any read; there is no shared-prefix scan.
    for role, path in paths.items():
        ref = entry['artifacts'][role]
        require(ref['path'] == path and ref['url'] ==
                f'https://github.com/KathenZK/quant-research-lab/blob/{entry["lab_commit"]}/{path}', 'Unapproved role path/pin')
        raw = read_below(root, path)
        same(fingerprint(raw), {k: ref[k] for k in ['bytes', 'sha256']}, 'Source hash/bytes mismatch: '+role)
        blobs[role] = raw
    source_binding(entry, blobs)
    return blobs


def validate(entry, blobs):
    refs = source_binding(entry, blobs)
    rid = entry['id']
    v = {k: _loads(raw) for k, raw in blobs.items()}
    _finite(v)
    r, d, manifest, s, w, c0, catalog, original, old_record, control, projection = (
        v[k] for k in ['record', 'detail', 'result_manifest', 'summary', 'rules', 'C0', 'catalog',
                       'original_detail', 'original_record', 'control_reference', 'control_projection'])
    require(all(x['id'] == rid for x in [r, d, manifest, s, w, original, old_record])
            and catalog['fields']['id'] == rid and rid in c0['strategy_ids'], 'Stable source identity mismatch')
    require(d['run_id'] == d['origin_run_id'] == original['run_id'] == manifest['origin_run_id'] == entry['run_id']
            and d['variant_id'] == original['variant_id'] == manifest['variant_id'] == entry['variant_id'], 'Immutable execution identity mismatch')
    require(manifest['schema_version'] == SCHEMA and manifest['manifest_kind'] == KIND
            and manifest['projection_profile'] == PROFILE and manifest['source_contract'] == CONTRACTS[rid]
            and manifest['origin_lab_commit'] == ORIGIN_PIN and manifest['original_private_result_manifest'] is False
            and manifest['original_results_modified'] is False and manifest['source_lock_kind'] == LOCK_KIND
            and manifest['source_lock_sha256'] == LOCK_SHA, 'Derived manifest type/profile/source lock conflict')
    same(manifest['source_artifacts'], refs, 'Derived selected sources conflict')
    same(manifest['files'], {**refs, 'base-nav-sampled.json': fingerprint(blobs['curve'])}, 'Derived evidence binding mismatch')
    require(set(manifest['excluded_from_self_hash']) == {'public-display-manifest.json', 'graph-record.json', 'graph-detail.json'}, 'Cyclic/extra display evidence')
    same(r['source_artifacts'], refs, 'Record source roles conflict')
    same(d['lineage']['source_artifacts'], refs, 'Detail source roles conflict')
    require(r['source_contract'] == d['source_contract'] == CONTRACTS[rid]
            and r['projection_profile'] == d['projection_profile'] == PROFILE
            and r['manifest_kind'] == d['manifest_kind'] == d['lineage']['manifest_kind'] == KIND,
            'Record/detail contract or manifest type conflict')
    binding = dict(origin_run_id=entry['run_id'], variant_id=entry['variant_id'], fidelity_class='HYPOTHESIS',
                   execution_class=EXECUTION, protocol_sha256=digest(blobs['rules']), manifest_sha256=digest(blobs['result_manifest']))
    same(d['transport_binding'], binding, 'Six-field source binding conflict')
    require(len(r['related_results']) == len(r['implementations']) == 1, 'Result identity set changed')
    for ref in r['related_results'] + r['implementations']:
        same({k: ref[k] for k in binding}, binding, 'Result identity/hash binding conflict')
        require(ref['manifest_kind'] == KIND, 'Result reference kind conflict')
    lineage = d['lineage']
    require(lineage['manifest_sha256'] == lineage['source_display_manifest_sha256'] == digest(blobs['result_manifest'])
            and lineage['protocol_sha256'] == digest(blobs['rules']) and lineage['protocol_hash_role'] == RULE_KIND
            and lineage['C0_sha256'] == s['C0_sha256'] == original['lineage']['C0_sha256'] == digest(blobs['C0'])
            and lineage['lab_commit'] == ORIGIN_PIN and 'source_run_manifest_sha256' not in lineage,
            'Frozen rule/C0/display lineage conflict')
    same(lineage['source_lineage'], original['lineage'], 'Original source lineage changed')
    require(s['classification'] == c0['classification'] == r['research_fidelity'] == d['research_fidelity'] == FIDELITY
            and s['execution_class'] == c0['execution_class'] == r['execution_class'] == d['execution_class'] == d['implementation_fidelity'] == EXECUTION
            and r['fidelity_class'] == d['fidelity_class'] == original['fidelity_class'] == 'HYPOTHESIS'
            and s['strict_reproductions'] == 0 and s['trusted'] is False and s['window_OOS'] is False
            and original['audit']['original_runtime_equivalence'] is False and original['audit']['trusted'] is False,
            'Catalog research/execution must not be promoted')
    require(r['projection_status'] == d['projection_status'] == 'STAGED_NOT_IMPORTED'
            and r['definition_revision_bound'] is False and lineage['definition_revision_bound'] is False
            and all('entity_id' not in x and 'definition_revision' not in x for x in [r, d]), 'Cannot invent active identity')
    require(s['strategy_configurations'] == r['configuration_runs'] == r['strategy_configurations'] == 4
            and s['new_controls'] == c0['new_controls'] == r['new_control_runs'] == r['control_configurations'] == 0
            and r['reused_control_configurations'] == 1, 'Original/projection control or configuration count conflict')
    same([s['new_controls'], c0['new_controls'], r['new_control_runs'], r['control_configurations']],
         [0, 0, 0, 0], 'Zero control counts must remain integers')
    same(d['lab_counts'], dict(strategy_ids=1, strategy_configurations=4, new_control_configurations=0,
                              reused_control_configurations=1, strict_reproductions=0), 'Lab counts conflict')
    same(d['projection_activity'], dict(new_strategy_trials=0, new_controls=0), 'Projection must not add trials')
    require(len(catalog['fields']) == 11, 'Exactly11 approved fields required')
    same(r['catalog_fields'], catalog['fields'], 'Catalog fields changed')
    same(old_record['audit'], catalog['fields'], 'Original catalog fields conflict')
    same(r['audit'], old_record['audit'], 'Original record audit changed')
    pins = {}
    for ref in c0['pins']:
        require(ref['path'] not in pins, 'Duplicate C0 path')
        pins[ref['path']] = {k: ref[k] for k in ['bytes', 'sha256']}
    for role, name in dict(rules=rid+'-root-frozen-rules.json', catalog=rid+'-catalog-original-fields.json', **SHARED_FILES).items():
        same(pins['frozen/'+name], fingerprint(blobs[role]), 'Selected source differs from C0')
    require(s['input_sha256'] == c0['input_sha256'] == w['input']['sha256'] == control['input_sha256'], 'Input identity conflict')
    require(w['capital']['fraction'] == '1' and w['capital']['entry_fee_inclusive'] is True
            and w['capital']['initial_cash'] == '100000' and w['capital']['Decimal_precision'] == 50,
            'Fullcash fee-inclusive allocation changed')
    rules = {k: w[k] for k in RULE_KEYS+SPECIAL[rid]}
    same(w['statistics'], v['statistics'], 'Frozen statistics role conflict')
    same(w['cost_cases'], v['cases'], 'Frozen cost cases role conflict')
    same(r['rules'], rules, 'Display rules changed')
    same(d['spec']['params'], dict(rules=rules, metric_conventions=w['statistics']), 'Detail rules/statistics changed')
    same(r['economic_basis'], dict(hypothesis=w['economic_hypothesis'], author_verified=False), 'Economic provenance changed')
    require(r['monthly'] is None and r['monthly_status'] == 'STRATEGY_MONTHLY_VALUES_NOT_IN_SELECTED_PUBLIC_SUMMARY', 'Unpublished strategy monthly values invented')
    require(digest(blobs['control_reference']) == CONTROL_SHA and control['id'] == 'M1258'
            and control['allocation'] == '100% fee-inclusive' and control['initial_cash'] == '100000'
            and control['fee_bps_each_side'] == 8 and control['slippage_bps_each_side'] == 2 and control['bars'] == 731
            and control['trusted'] is False and control['window_OOS'] is False,
            'Same accepted M1258 base control required')
    require(projection['reference_sha256'] == CONTROL_SHA and projection['new_controls'] == 0
            and projection['trusted'] is False and projection['window_OOS'] is False, 'Reused control projection conflict')
    same(s['benchmark_reuse'], projection, 'Summary control projection changed')
    same(control['statistics'], v['statistics'], 'Control statistics conflict')
    same(r['benchmark_reference'], dict(kind='REUSED_ACCEPTED_M1258_BASE_CONTROL', id='M1258',
        reference_sha256=CONTROL_SHA, projection=projection, matched_cost_controls_available=False), 'Matched fee0/20 controls cannot be invented')
    cases = {case['case']: case for case in s['cases']}
    require(len(cases) == len(s['cases']) == 4 and set(cases) == {'base', 'fee0', 'fee20', 'delay2'}, 'Four original cases required')
    same(r['results'], cases, 'Original result values changed')
    expected_metrics = deepcopy(original['metrics'])
    expected_metrics['cost_sensitivity'] = {str(fee): expected_metrics['cost_sensitivity'][name]
                                           for fee, name in [(0, 'fee0'), (20, 'fee20')]}
    containers = [expected_metrics['periods'], expected_metrics['same_instrument_benchmark'],
                  expected_metrics['additional_native_bar_lag'], *expected_metrics['cost_sensitivity'].values()]
    for container in containers:
        require(set(container) == {'2023-2024'} and isinstance(container['2023-2024'], dict), 'Original metric period scope changed')
        container['full'] = deepcopy(container['2023-2024'])
    expected_metrics.update(source_period_aliases={'2023-2024': 'full'}, source_cost_key_aliases={'fee0': '0', 'fee20': '20'}, additional_lag_unit='day')
    same(d['metrics'], expected_metrics, 'Deep full alias/source metrics conflict')
    def match(view, metric):
        for key in ['total_return', 'cagr', 'max_drawdown', 'sharpe_zero_cash', 'observations', 'final_equity']:
            same(view[key], metric[key], 'Original metric/type changed: '+key)
        same(view['sharpe'], metric['sharpe_zero_cash'], 'Sharpe/null changed')
        require(view['observations'] == 731 and view['start'] == '2023-01-01' and view['end'] == '2024-12-31'
                and view['annualization'] == 365, 'Metric window/observation count changed')
    for name, fee, lag in [('base', 8, 1), ('fee0', 0, 1), ('fee20', 20, 1), ('delay2', 8, 2)]:
        case = cases[name]
        same({k: case[k] for k in ['fee_bps', 'slippage_bps', 'delay_bars', 'observations']},
             dict(fee_bps=fee, slippage_bps=2, delay_bars=lag, observations=731), 'Frozen fee/day lag types changed')
        require(dict(name=name, fee_bps_each_side=fee, slippage_bps_each_side=2, delay_bars=lag) in v['cases'],
                'Frozen case declaration conflict')
        require(case['kind'] == 'STRATEGY' and case['fee_bps'] == fee and case['slippage_bps'] == 2
                and case['delay_bars'] == lag and case['observations'] == 731, 'Frozen fee/day lag conflict')
        container = (d['metrics']['periods'] if name == 'base' else d['metrics']['additional_native_bar_lag']
                     if name == 'delay2' else d['metrics']['cost_sensitivity'][str(fee)])
        match(container['full'], case)
    match(d['metrics']['same_instrument_benchmark']['full'], projection['metrics'])
    if rid == 'M1270':
        case = cases['delay2']
        require(case['fills'] == 0 and case['sharpe_zero_cash'] is None, 'M1270 delay2 cash/null changed')
        same(case['final_equity'], 100000.0, 'M1270 delay2 cash changed')
        same(case['total_return'], 0.0, 'M1270 delay2 zero changed')
    if rid == 'M1349':
        same(s['execution_policy'], {'max_completed_closes': 25}, 'M1349 completed-close policy changed')
    curve = v['curve']
    same(curve, v['original_curve'], 'Original curve changed')
    same(curve, original['curve'], 'Original detail curve changed')
    same(curve, d['curve'], 'Display curve changed')
    dates = ['2023-01-01'] + [f'{y}-{m:02d}-{calendar.monthrange(y, m)[1]}' for y in [2023, 2024] for m in range(1, 13)]
    require([p['date'] for p in curve] == dates, 'Exactly25 approved sampled dates required')
    for point in curve:
        require(type(point['equity']) in [float, int] and math.isfinite(point['equity']) and point['equity'] >= 0
                and type(point['drawdown']) in [float, int] and math.isfinite(point['drawdown']) and -1 <= point['drawdown'] <= 0,
                'Invalid sampled units/type')
    require(curve[0]['equity'] == 1 and math.isclose(curve[-1]['equity'], cases['base']['final_equity']/100000, abs_tol=1e-14), 'No repeated normalization or rebasing')
    meta = d['curve_meta']
    same(meta, manifest['curve_contract'], 'Derived curve contract conflict')
    require(meta['returned_points'] == meta['point_count'] == 25
            and meta['observations'] == meta['source_observations'] == meta['total_observations'] == 731
            and meta['equity_unit'] == 'initial_capital_multiple' and meta['drawdown_unit'] == 'fraction'
            and meta['denominator'] == meta['normalized_to_initial'] == 100000
            and all(meta[k] is False for k in ['first_point_rebased', 'full_daily_curve_published', 'interpolation_claim', 'private_daily_nav_used']),
            '25-point/731-observation distinction changed')
    return r, d


def project(entry, blobs):
    record, detail = validate(entry, blobs)
    projected, result = deepcopy(record), deepcopy(detail)
    result['lineage'].update(lab_commit=entry['lab_commit'], origin_lab_commit=ORIGIN_PIN,
        source_artifacts=entry['artifacts'], publication_manifest_sha256=digest(blobs['publication_manifest']),
        source_display_detail_sha256=digest(blobs['detail']), projection_profile=PROFILE,
        source_contract=entry['source_contract'], publication_manifest_kind=PUBLICATION_KIND,
        source_lock_kind=LOCK_KIND, source_lock_sha256=LOCK_SHA)
    result['spec']['params']['rules'] = deepcopy(record['rules'])
    result['spec']['economic_basis'] = deepcopy(record['economic_basis'])
    result['curve_meta']['public_curve_available'] = True
    return projected, result

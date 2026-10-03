"""Explicit, public-only display v2 profiles; no execution or source discovery."""
import calendar
from copy import deepcopy
import csv
from datetime import date, timedelta
import io
import math
from pathlib import PurePosixPath
import re

from quantgraph.graph.corpus_research import _finite, _loads
from quantgraph.graph.metadata_pilot import digest
from quantgraph.graph.lab_display_catalog_daily import CONTRACT as CATALOG_DAILY, validate as catalog_daily

SCHEMA = 'quantgraph-public-derived-display-manifest/v2'
KIND = 'PUBLIC_DERIVED_DISPLAY_MANIFEST'
NATIVE = 'NATIVE_5M_RULE_CARD_V2'
DAILY = 'DAILY_SAMPLED_APPROVED_DETAIL_V1'
PROFILES = {NATIVE, DAILY}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def fingerprint(raw):
    return dict(sha256=digest(raw), bytes=len(raw))


def bindings(entry, blobs, origin, record, detail):
    rid = entry['id']
    profile = entry.get('projection_profile')
    contract = entry.get('source_contract')
    require(contract is None or (contract == CATALOG_DAILY and profile == DAILY and rid == 'M1258'),
            'Unknown or incompatible explicit source contract')
    require(profile in PROFILES and origin.get('projection_profile') == profile,
            'Unsupported or conflicting explicit v2 profile')
    require(origin.get('schema_version') == SCHEMA
            and entry.get('manifest_kind') == origin.get('manifest_kind') == KIND,
            'Explicit v2 manifest schema/type required')
    require(origin.get('id') == record.get('id') == detail.get('id') == rid
            and origin.get('origin_run_id') == detail.get('run_id') == detail.get('origin_run_id') == entry['run_id']
            and origin.get('variant_id') == detail.get('variant_id') == entry['variant_id'],
            'V2 immutable execution identity mismatch')
    require(origin.get('original_private_result_manifest') is False
            and origin.get('original_results_modified') is False,
            'V2 display cannot claim original private results')
    pin = origin.get('origin_lab_commit', '')
    require(re.fullmatch(r'[a-f0-9]{40}', pin) and pin == entry.get('origin_lab_commit'),
            'V2 origin commit must be explicit and pinned')
    prefix = f'research/public-strategies/{rid}/'
    prior = _loads(blobs['origin_publication_manifest'])
    require((prior.get('id') or prior.get('record_id')) == rid, 'Historical publication identity mismatch')
    allowed = {}
    for item in prior['files']:
        path = item['path'] if item['path'].startswith(prefix) else prefix + item['path']
        require(path not in allowed, 'Duplicate historical publication path')
        allowed[path] = {k: item[k] for k in ['sha256', 'bytes']}
    refs = origin['source_artifacts']
    private_role = 'private_output_inventory_reference_only'
    expected_roles = ({'publication_manifest', 'summary', 'protocol', 'C0', 'source_rule_card',
                       'readme', 'attribution', 'validation_summary', 'base_daily', 'fee0_daily',
                       'fee20_daily', 'delay2_daily'} if profile == NATIVE else
                      {'publication_manifest', 'summary', 'protocol', 'C0', 'source_rule_card',
                       'readme', 'report', 'original_record', 'original_detail', 'numerics', private_role})
    if contract == CATALOG_DAILY:
        expected_roles = {'publication_manifest', 'summary', 'protocol', 'C0', 'rules',
                          'source_card', 'catalog_fields', 'original_record', 'original_detail'}
        require(record.get('projection_profile') == detail.get('projection_profile') == DAILY,
                'Catalog source record/detail profile conflict')
    require(set(refs) == expected_roles, 'Unexpected v2 source role set')
    for role, ref in refs.items():
        path = ref['path']
        require(path.startswith(prefix) and PurePosixPath(path).as_posix() == path
                and '..' not in PurePosixPath(path).parts and '\\' not in path
                and ref['url'] == f'https://github.com/KathenZK/quant-research-lab/blob/{pin}/{path}',
                'V2 source URL/path must bind same ID and origin commit')
        expected = (fingerprint(blobs['origin_publication_manifest'])
                    if role == 'publication_manifest' and path == prefix + 'publication-manifest.json'
                    else allowed.get(path))
        require(expected == {k: ref[k] for k in ['sha256', 'bytes']},
                'V2 source outside historical publication allowlist')
        if role == private_role:
            # Hash-only provenance for an already-public inventory; never read
            # that inventory's content or any of its private output paths.
            require(role not in blobs, 'Private output inventory is reference-only')
            continue
        selected = 'origin_publication_manifest' if role == 'publication_manifest' else role
        require(fingerprint(blobs[selected]) == expected, 'V2 selected source hash mismatch: ' + role)
        if role not in {'publication_manifest', 'readme'}:
            require(entry['artifacts'][selected]['path'] == path, 'Unexpected v2 source path remapping')
    curve_name = 'base-nav-light.csv' if profile == NATIVE else 'base-nav-sampled.json'
    expected_files = {role: ref for role, ref in refs.items() if role != private_role}
    expected_files[curve_name] = fingerprint(blobs['curve'])
    require(origin['files'] == expected_files and set(origin.get('excluded_from_self_hash', [])) ==
            {'public-display-manifest.json', 'graph-record.json', 'graph-detail.json'},
            'V2 evidence binding mismatch or cyclic display references')
    require(record.get('source_artifacts') == detail['lineage'].get('source_artifacts') == refs,
            'V2 record/detail source lineage conflict')
    manifest_sha = digest(blobs['result_manifest'])
    for ref in record['related_results'] + record['implementations']:
        require(ref.get('origin_run_id') == entry['run_id'] and ref.get('variant_id') == entry['variant_id']
                and ref.get('manifest_kind') == KIND and ref.get('manifest_sha256') == manifest_sha
                and ref.get('protocol_sha256') == digest(blobs['protocol'])
                and ref.get('fidelity_class') == entry['fidelity_class']
                and ref.get('execution_class') == 'ADAPTED_EXECUTION_PROXY',
                'V2 result reference identity/type/fidelity conflict')
    require(len(record['related_results']) == len(record['implementations']) == 1
            and record.get('manifest_kind') == detail.get('manifest_kind') == detail['lineage'].get('manifest_kind') == KIND
            and detail['lineage'].get('manifest_sha256') == detail['lineage'].get('source_display_manifest_sha256') == manifest_sha
            and detail['lineage'].get('protocol_sha256') == digest(blobs['protocol'])
            and detail['lineage'].get('C0_sha256') == digest(blobs['C0'])
            and detail['lineage'].get('lab_commit') == pin
            and 'source_run_manifest_sha256' not in detail['lineage'],
            'V2 manifest/detail lineage conflict')
    require(record.get('fidelity_class') == detail.get('fidelity_class') == entry['fidelity_class']
            and record.get('execution_class') == 'ADAPTED_EXECUTION_PROXY'
            and record.get('projection_status') == detail.get('projection_status') == 'STAGED_NOT_IMPORTED'
            and record.get('definition_revision_bound') is False
            and detail['lineage'].get('definition_revision_bound') is False,
            'V2 fidelity or staging status conflict')
    require(detail['curve_meta'] == origin['curve_contract'], 'V2 curve contract conflict')
    controls = 1 if contract == CATALOG_DAILY else 0
    require(detail['lab_counts'] == dict(strategy_ids=1, strategy_configurations=4,
            new_control_configurations=controls, reused_control_configurations=1-controls, strict_reproductions=0)
            and record['strategy_configurations'] == 4 and record['control_configurations'] == controls
            and record['reused_control_configurations'] == 1-controls,
            'V2 frozen count mismatch')
    return profile


def native_period(metric):
    return dict(start=metric['start'][:10], end='2024-12-31',
                observations=metric['daily_observations'], native_observations=metric['observations'],
                total_return=metric['total_return'], cagr=metric['annualized_return'],
                sharpe=metric['sharpe'], max_drawdown=-abs(metric['max_drawdown']),
                annualization=365, oos_claim=False)


def native(entry, blobs, record, detail, summary, protocol, c0, card):
    rid = entry['id']
    require(summary.get('id') == protocol.get('record_id') == c0.get('record_id') == card.get('id') == rid
            and summary.get('origin_run_id') == protocol.get('run_id') == entry['run_id']
            and summary.get('variant_id') == protocol.get('variant_id') == entry['variant_id'],
            'Native v2 source identity mismatch')
    require(entry['fidelity_class'] == summary.get('fidelity_class') == protocol.get('fidelity_class') == 'ADAPTED'
            and summary['protocol_sha256'] == c0['protocol_sha256'] == digest(blobs['protocol'])
            and c0['source_sha256'] == card['source']['sha256'] == protocol['source']['sha256'],
            'Native v2 C0/fidelity mismatch')
    rules = dict(source_signal_rules=card['rules'], source_specific_requirements=protocol['source_specific_requirements'],
                 execution=protocol['execution'], risk=protocol['risk'], parameters=protocol['parameters'],
                 catalog_omissions=card['catalog_omissions'])
    require(record['rules'] == detail['spec']['params']['rules'] == rules, 'Native v2 rules differ from frozen source')
    require(summary['strategy_configurations'] == c0['strategy_configurations_frozen'] == 4
            and summary['new_control_configurations'] == c0['new_controls'] == 0
            and summary['reused_control_configurations'] == 1
            and protocol['execution']['initial_cash'] == 100000, 'Native v2 counts/initial cash mismatch')
    require(record['results'] == summary['results'] and record['signals'] == summary['signals']
            and record['benchmark_reference'] == summary['benchmark_reference'] == protocol['benchmark_reference'],
            'Native v2 metrics or benchmark changed')
    for case, fee, lag in [('base', 8, 1), ('fee0', 0, 1), ('fee20', 20, 1), ('delay2', 8, 2)]:
        result = summary['results'][case]
        require(result['configuration'] == dict(name=case, fee_bps=fee, delay_bars=lag)
                and result['configuration'] in protocol['cases'], 'Native v2 frozen cost/lag mismatch')
        metric = result['metrics']
        require(metric['daily_observations'] == 366 and metric['observations'] == 105408,
                'Native v2 supports frozen calendar 2024 only')
        if metric['trades'] == 0:
            require(metric['sharpe'] is None and metric['total_return'] == metric['max_drawdown'] == 0
                    and metric['final_equity'] == 100000, 'Zero-trade Sharpe must remain null')
    expected_metrics = dict(periods={'full': native_period(summary['results']['base']['metrics'])},
        same_instrument_benchmark={'full': native_period(summary['benchmark_reference']['metrics'])},
        cost_sensitivity={str(fee): {'full': native_period(summary['results'][case]['metrics'])}
                          for fee, case in [(0, 'fee0'), (20, 'fee20')]},
        additional_native_bar_lag={'full': native_period(summary['results']['delay2']['metrics'])})
    require(detail['metrics'] == expected_metrics, 'Native v2 display metrics differ from frozen summary')
    rows = list(csv.DictReader(io.StringIO(blobs['curve'].decode())))
    original = _loads(blobs['base_daily'])
    require(original['initial_equity'] == 100000 and original['observations'] == 105408
            and len(rows) == len(original['points']) == len(detail['curve']) == 366,
            'Native v2 curve count/units mismatch')
    peak = 1.0
    for n, (row, source, point) in enumerate(zip(rows, original['points'], detail['curve'], strict=True)):
        stamp = (date(2024, 1, 1) + timedelta(days=n)).isoformat()
        time = (date(2024, 1, 2) + timedelta(days=n)).isoformat() + 'T00:00:00Z'
        nav = source['equity'] / 100000
        peak = max(peak, nav)
        require(math.isfinite(nav) and nav >= 0 and -1 <= source['drawdown'] <= 0
                and row['date'] == source['date'] == stamp
                and row['valuation_time_utc'] == source['timestamp_utc'] == time
                and float(row['equity']) == source['equity'] and float(row['nav']) == nav
                and float(row['source_native_drawdown']) == source['drawdown']
                and point == dict(date=stamp, equity=nav, drawdown=nav / peak - 1,
                                  valuation_time_utc=time, source_native_drawdown=source['drawdown']),
                'Native v2 curve differs from original initial-capital units or UTC boundary')
    require(math.isclose(detail['curve'][-1]['equity'] - 1,
            summary['results']['base']['metrics']['total_return'], abs_tol=1e-11), 'Native v2 terminal return mismatch')
    meta = detail['curve_meta']
    require(meta['returned_points'] == meta['total_observations'] == 366 and meta['native_observations'] == 105408
            and meta['equity_unit'] == 'initial_capital_multiple' and meta['denominator'] == 100000
            and meta['first_point_rebased'] is False, 'Native v2 curve metadata mismatch')


def daily(entry, blobs, record, detail, summary, protocol, c0, card):
    rid = entry['id']
    require(summary.get('record_id') == c0.get('record_id') == card.get('record_id') == rid
            and protocol['exclusive_ids'] == [rid], 'Daily v2 source identity mismatch')
    require(summary['C0_sha256'] == digest(blobs['C0']) and c0['root_contract_sha256'] == digest(blobs['protocol'])
            and summary['fidelity'] == protocol['fidelity'] == c0['fidelity'] == 'ADAPTED'
            and entry['fidelity_class'] == 'HYPOTHESIS'
            and record['research_fidelity'] == detail['research_fidelity'] == 'ADAPTED'
            and detail['implementation_fidelity'] == 'ADAPTED_EXECUTION_PROXY', 'Daily v2 C0/fidelity mismatch')
    require(summary['configurations'] == protocol['strategy_configurations_expected'] == 4
            and summary['new_controls'] == protocol['new_control_configurations_expected'] == 0,
            'Daily v2 frozen count mismatch')
    require(record['results'] == summary['summary'] and record['benchmark_reference'] == protocol['benchmark_reference']
            and summary['existing_buyhold_reference'] == protocol['benchmark_reference']['result'],
            'Daily v2 metrics/benchmark source mismatch')
    require(record['rules'] == dict(source_signal_rules=protocol['source_signal_rules'], execution=protocol['execution'])
            and detail['spec']['params']['source_signal_rules'] == protocol['source_signal_rules']
            and detail['spec']['params']['execution'] == protocol['execution']
            and protocol['execution']['initial_cash'] == 100000
            and protocol['execution']['buy_fee_additional_in_USDT'] is True, 'Daily v2 rule/account mismatch')
    original = _loads(blobs['original_detail'])
    curve = _loads(blobs['curve'])
    dates = ['2023-01-01'] + [f'{y}-{m:02d}-{calendar.monthrange(y, m)[1]}'
                            for y in [2023, 2024] for m in range(1, 13)]
    require(original['id'] == rid and original['run_id'] == entry['run_id']
            and original['variant_id'] == entry['variant_id'] and original['fidelity_class'] == 'HYPOTHESIS'
            and curve == detail['curve'] == original['curve'] and [p['date'] for p in curve] == dates,
            'Daily v2 must retain exactly the approved 25 sampled objects')
    for point in curve:
        require(math.isfinite(point['equity']) and point['equity'] >= 0 and -1 <= point['drawdown'] <= 0,
                'Invalid daily sampled point')
    require(curve[0]['equity'] == 1 and math.isclose(curve[-1]['equity'],
            summary['summary']['base']['metrics']['final_equity'] / 100000, abs_tol=1e-14),
            'Daily sampled equity must not be normalized again')
    meta = detail['curve_meta']
    require(meta['returned_points'] == 25 and meta['observations'] == meta['total_observations'] == 731
            and meta['equity_unit'] == 'initial_capital_multiple'
            and all(meta[k] is False for k in ['full_daily_curve_published', 'interpolation_claim',
                                               'private_daily_nav_used', 'first_point_rebased']),
            'Daily sampled/full-observation semantics conflict')
    expected_metrics = deepcopy(original['metrics'])
    expected_metrics['cost_sensitivity'] = {str(fee): original['metrics']['cost_sensitivity'][case]
                                          for fee, case in [(0, 'fee0'), (20, 'fee20')]}
    expected_metrics['source_cost_key_aliases'] = {'fee0': '0', 'fee20': '20'}
    require(detail['metrics'] == expected_metrics, 'Daily v2 display metrics changed')
    def match(view, metric):
        require(all(view.get(k) == v for k, v in metric.items())
                and view['sharpe'] == metric['sharpe_zero_cash'], 'Daily v2 source metric alias mismatch')
    for case, fee, lag in [('base', 8, 1), ('fee0', 0, 1), ('fee20', 20, 1), ('lag2', 8, 2)]:
        cfg = summary['summary'][case]
        require(cfg['fee_bps'] == fee and cfg['lag_days'] == lag
                and dict(name=case, fee_bps=fee, lag_days=lag) in protocol['cases'], 'Daily v2 cost/day lag mismatch')
        view = (detail['metrics']['periods'] if case == 'base' else detail['metrics']['additional_native_bar_lag']
                if case == 'lag2' else detail['metrics']['cost_sensitivity'][str(fee)])
        match(view['2023-2024'], cfg['metrics'])
        require(cfg['metrics']['observations'] == 731, 'Daily full period must retain 731 observations')
        for year in ['2023', '2024']:
            match(view[year], cfg['periods'][year])
    benchmark = summary['existing_buyhold_reference']
    match(detail['metrics']['same_instrument_benchmark']['2023-2024'], benchmark['metrics'])
    for year in ['2023', '2024']:
        match(detail['metrics']['same_instrument_benchmark'][year], benchmark['periods'][year])


def project_v2(entry, blobs):
    values = {k: _loads(blobs[k]) for k in ['record', 'detail', 'result_manifest', 'summary', 'protocol', 'C0']}
    _finite(values)
    record, detail, origin = (values[k] for k in ['record', 'detail', 'result_manifest'])
    profile = bindings(entry, blobs, origin, record, detail)
    if entry.get('source_contract') == CATALOG_DAILY:
        catalog_daily(entry, blobs, values)
    else:
        card = _loads(blobs['source_rule_card'])
        _finite(card)
        (native if profile == NATIVE else daily)(entry, blobs, record, detail,
                values['summary'], values['protocol'], values['C0'], card)
    projected, result = deepcopy(record), deepcopy(detail)
    # These are approved display fields, not an entity definition or a claim
    # that a current active revision has been found.
    for value in [projected, result]:
        require(not any(k in value for k in ['entity_id', 'definition_revision']), 'Source must not invent active identity')
        value['projection_profile'] = profile
        value['projection_status'] = 'STAGED_NOT_IMPORTED'
    result['lineage'].update(lab_commit=entry['lab_commit'], origin_lab_commit=origin['origin_lab_commit'],
        source_artifacts=entry['artifacts'], publication_manifest_sha256=digest(blobs['publication_manifest']),
        source_display_detail_sha256=digest(blobs['detail']), projection_profile=profile)
    result['spec']['params']['rules'] = deepcopy(record['rules'])
    result['spec']['economic_basis'] = deepcopy(record['economic_basis'])
    result['curve_meta']['public_curve_available'] = True
    result['metrics']['additional_lag_unit'] = 'native_5m_bar' if profile == NATIVE else 'day'
    if entry.get('source_contract') == CATALOG_DAILY:
        projected['source_contract'] = result['lineage']['source_contract'] = CATALOG_DAILY
    if profile == DAILY:
        # Existing UI starts at "full". Alias original full-period statistics;
        # never compute them from the sampled curve or discard original keys.
        metrics = result['metrics']
        for periods in [metrics['periods'], metrics['same_instrument_benchmark'],
                        metrics['additional_native_bar_lag'], *metrics['cost_sensitivity'].values()]:
            require('full' not in periods, 'Unexpected existing daily full alias')
            periods['full'] = deepcopy(periods['2023-2024'])
        metrics['source_period_aliases'] = {'2023-2024': 'full'}
    return projected, result

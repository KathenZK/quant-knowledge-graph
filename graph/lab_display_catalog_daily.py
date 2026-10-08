"""Validate the explicitly selected M1258 catalog/fullcash display contract."""
import calendar
import math
from copy import deepcopy

from quantgraph.graph.corpus_research import _finite, _loads
from quantgraph.graph.metadata_pilot import digest

CONTRACT = 'CATALOG_RSI5_FULLCASH_V1'
FIDELITY = 'HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def same(value, expected, reason):
    # Python otherwise considers False == 0. Preserve source null/zero/type.
    require(type(value) is type(expected) and value == expected, reason)


def validate(entry, blobs, values):
    record, detail, summary, protocol, c0 = (values[k] for k in ['record', 'detail', 'summary', 'protocol', 'C0'])
    rules, card, catalog, original = (_loads(blobs[k]) for k in ['rules', 'source_card', 'catalog_fields', 'original_detail'])
    _finite([rules, card, catalog, original])
    rid = entry['id']
    require(rid == 'M1258' and all(v.get('id') == rid for v in [summary, protocol, c0, rules, card, original])
            and catalog['fields']['id'] == rid and len(catalog['fields']) == 11
            and protocol.get('schema') == 'M1258-catalog-hypothesis-protocol/v1',
            'Catalog daily contract identity/schema mismatch')
    require(summary['classification'] == protocol['classification'] == card['fidelity'] ==
            record['research_fidelity'] == detail['research_fidelity'] == FIDELITY
            and entry['fidelity_class'] == original['fidelity_class'] == 'HYPOTHESIS'
            and summary['execution'] == protocol['execution'] == detail['implementation_fidelity'] == 'ADAPTED_EXECUTION_PROXY'
            and card['source_verified'] is False and card['original_framework_verified'] is False
            and summary['strict_reproductions'] == protocol['strict_reproductions'] == c0['strict_reproductions'] == 0,
            'Catalog hypothesis must not be promoted to source-verified research')
    require(summary['C0_sha256'] == original['lineage']['C0_sha256'] == digest(blobs['C0'])
            and protocol['source_rules']['sha256'] == digest(blobs['rules']), 'Catalog C0/rule binding mismatch')
    frozen = {}
    for ref in c0['files']:
        require(ref['path'] not in frozen, 'Duplicate catalog C0 path')
        frozen[ref['path']] = ref
    prefix = f'research/public-strategies/{rid}/'
    for role in ['protocol', 'rules', 'source_card', 'catalog_fields']:
        path = entry['artifacts'][role]['path'].removeprefix(prefix)
        require(path in frozen and frozen[path]['sha256'] == digest(blobs[role])
                and frozen[path]['bytes'] == len(blobs[role]), 'Catalog selected source differs from frozen C0')
    require(protocol['input']['sha256'] == summary['input_sha256'] == original['lineage']['input_sha256'] == c0['canonical_sha256']
            and summary['source_commit'] == original['lineage']['source_commit'], 'Catalog execution provenance conflict')
    require(summary['strategy_configurations'] == c0['planned_strategy_configurations'] == record['configuration_runs'] == 4
            and summary['new_controls'] == c0['planned_new_controls'] == record['new_control_runs'] == 1
            and detail['projection_activity'] == {'new_strategy_trials': 0, 'new_controls': 0},
            'Original fullcash control and zero projection activity must remain separate')
    require(record['results'] == summary['cases'] and record['monthly'] == summary['monthly']
            and record['catalog_fields'] == catalog['fields'] and record['source'] == card,
            'Catalog results/monthly/original fields changed')
    capital = rules['capital']
    require(capital['fraction'] == '1' and capital['entry_fee_inclusive'] is True
            and capital['initial_cash'] == protocol['initial_cash'] == '100000'
            and capital['Decimal_precision'] == 50 and capital['rounding'] == 'ROUND_HALF_EVEN'
            and rules['benchmark']['allocation'] == capital
            and detail['metrics']['capital_state']['initial_cash_usdt'] == 100000,
            'Catalog fullcash fee-inclusive allocation mismatch')
    expected_rules = {k: deepcopy(rules[k]) for k in ['RSI5', 'entry', 'exit', 'capital', 'cold_start', 'stop_or_roi', 'known_halt']}
    expected_rules.update(raw_cross_cancellation=rules['execution']['raw_M1258'],
        same_side_pending='Retain original earliest due; no postponement. Opposite raw cross cancels before holding-eligible scheduling.',
        cost_cases=rules['cost_cases'])
    require(record['rules'] == expected_rules and record['metric_conventions'] == protocol['statistics'],
            'Catalog display rules differ from frozen research conventions')
    for key in ['capital', 'RSI5', 'entry', 'exit']:
        require(detail['spec']['params'][key] == rules[key], 'Catalog detail rule differs from frozen source')
    require(detail['spec']['params']['metric_conventions'] == protocol['statistics'], 'Catalog detail statistics conflict')
    require(set(summary['cases']) == {'base', 'fee0', 'fee20', 'delay2', 'buyhold'}, 'Catalog case set mismatch')

    def match(view, case):
        for key in ['total_return', 'cagr', 'max_drawdown', 'sharpe_zero_cash', 'observations', 'final_equity']:
            same(view[key], case[key], 'Catalog metric changed: ' + key)
        same(view['sharpe'], case['sharpe_zero_cash'], 'Catalog Sharpe alias or null changed')
        require(case['observations'] == 731 and view['annualization'] == 365
                and view['start'] == '2023-01-01' and view['end'] == '2024-12-31', 'Catalog metrics window mismatch')

    for name, fee, lag in [('base', 8, 1), ('fee0', 0, 1), ('fee20', 20, 1), ('delay2', 8, 2)]:
        case = summary['cases'][name]
        cfg = dict(name=name, fee_bps_each_side=fee, slippage_bps_each_side=2, delay_bars=lag)
        require(cfg in protocol['cases'] and cfg in rules['cost_cases'] and case['kind'] == 'STRATEGY'
                and case['fee_bps'] == fee and case['slippage_bps'] == 2 and case['delay_bars'] == lag,
                'Catalog frozen fee/daily lag mismatch')
        view = (detail['metrics']['periods'] if name == 'base' else detail['metrics']['additional_native_bar_lag']
                if name == 'delay2' else detail['metrics']['cost_sensitivity'][str(fee)])
        require(set(view) == {'2023-2024'}, 'Catalog periods must match the approved full-only source')
        match(view['2023-2024'], case)
    benchmark = summary['cases']['buyhold']
    bc = protocol['benchmark']
    require(benchmark['kind'] == 'CONTROL' and benchmark['fee_bps'] == bc['fee_bps_each_side'] == rules['benchmark']['fee_bps'] == 8
            and benchmark['slippage_bps'] == bc['slippage_bps_each_side'] == rules['benchmark']['slippage_bps'] == 2
            and benchmark['delay_bars'] == bc['delay_bars'] == 0 and bc['new_controls'] == rules['benchmark']['new_control_configurations'] == 1
            and benchmark['fills'] == 1 and benchmark['closed_roundtrips'] == 0 and benchmark['win_rate'] is None,
            'Catalog original new control parameters/null state mismatch')
    require(record['benchmark_reference'] == dict(kind='ACTUAL_ORIGINAL_NEW_CONTROL', name='buyhold',
            new_controls_at_original_run=1, allocation=capital, configuration=bc, result=benchmark, evidence_role='summary'),
            'Catalog benchmark cannot be replaced by a reused 95-percent control')
    match(detail['metrics']['same_instrument_benchmark']['2023-2024'], benchmark)
    expected_metrics = deepcopy(original['metrics'])
    expected_metrics['cost_sensitivity'] = {str(fee): original['metrics']['cost_sensitivity'][name]
                                          for name, fee in [('fee0', 0), ('fee20', 20)]}
    expected_metrics['source_cost_key_aliases'] = {'fee0': '0', 'fee20': '20'}
    require(detail['metrics'] == expected_metrics, 'Catalog metrics differ from approved original detail')
    curve = _loads(blobs['curve'])
    dates = ['2023-01-01'] + [f'{y}-{m:02d}-{calendar.monthrange(y, m)[1]}'
                            for y in [2023, 2024] for m in range(1, 13)]
    require(original['run_id'] == entry['run_id'] and original['variant_id'] == entry['variant_id']
            and curve == detail['curve'] == original['curve'] and [p['date'] for p in curve] == dates,
            'Catalog curve must retain exactly the approved 25 sampled objects')
    for point in curve:
        require(type(point['equity']) in [int, float] and math.isfinite(point['equity']) and point['equity'] >= 0
                and type(point['drawdown']) in [int, float] and math.isfinite(point['drawdown']) and -1 <= point['drawdown'] <= 0,
                'Invalid catalog sampled point')
    require(curve[0]['equity'] == 1 and math.isclose(curve[-1]['equity'],
            summary['cases']['base']['final_equity'] / 100000, abs_tol=1e-14), 'Catalog sampled equity was rescaled/rebased')
    meta = detail['curve_meta']
    require(meta['returned_points'] == 25 and meta['observations'] == meta['total_observations'] == 731
            and meta['equity_unit'] == 'initial_capital_multiple' and meta['drawdown_unit'] == 'fraction'
            and meta['denominator'] == 100000 and all(meta[k] is False for k in ['first_point_rebased',
                'full_daily_curve_published', 'interpolation_claim', 'private_daily_nav_used']),
            'Catalog sample/full-observation/unit semantics conflict')
    # Source transport_binding is execution provenance, not the Site/D1 envelope.
    binding = {k: detail[k] for k in ['origin_run_id', 'variant_id', 'fidelity_class', 'execution_class']}
    binding.update(protocol_sha256=digest(blobs['protocol']), manifest_sha256=digest(blobs['result_manifest']))
    require(detail['transport_binding'] == binding and all(isinstance(v, str) and v for v in binding.values()),
            'Catalog source transport binding conflict')

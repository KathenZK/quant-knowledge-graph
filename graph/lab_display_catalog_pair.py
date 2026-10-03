"""Two explicit catalog contracts with sampled public NAV and a reused control."""
import calendar
from copy import deepcopy
import math

from quantgraph.graph.corpus_research import _finite, _loads
from quantgraph.graph.lab_display_catalog_daily import FIDELITY, require, same
from quantgraph.graph.metadata_pilot import digest

CONTRACTS = {
    'M1396': 'CATALOG_WEEKDAY_HL2SMA4_FULLCASH_REUSED_CONTROL_V1',
    'M1463': 'CATALOG_BOLLINGER20X2_FULLCASH_REUSED_CONTROL_V1',
}
RULE_KEYS = ['entry', 'exit', 'capital', 'capital_provenance', 'cold_start', 'execution',
             'stop_or_roi', 'known_halt', 'cost_cases', 'valuation', 'timeframe']
SPECIFIC = {'M1396': ['hl2_SMA4', 'calendar_execution', 'date_filter_adaptation'],
            'M1463': ['bollinger', 'membership_scope', 'date_scope']}
CONTROL_PIN = '2a2e33e0de2b4897d6ccb460e72dcb5e73aa4153'


def validate(entry, blobs, values):
    rid = entry['id']
    record, detail, summary, protocol, c0 = (values[k] for k in ['record', 'detail', 'summary', 'protocol', 'C0'])
    sources = {k: _loads(blobs[k]) for k in ['rules', 'catalog_fields', 'original_detail',
        'original_record', 'control_reference', 'control_release', 'publication_manifest', 'origin_publication_manifest']}
    _finite(sources)
    require(all(isinstance(v, dict) for v in sources.values()), 'Catalog pair sources must be objects')
    rules, catalog, original, original_record, control, release, pub, prior = sources.values()
    require(rid in CONTRACTS and entry['source_contract'] == CONTRACTS[rid]
            and all(v.get('id') == rid for v in [summary, protocol, c0, rules, original, original_record, prior, pub]),
            'Catalog pair ID/contract mismatch')
    prior_ref = entry['artifacts']['origin_publication_manifest']
    require(prior['schema'] == 'batch016-fixed-publication/v1' and pub['schema'] == 'batch016-fixed-publication/v2'
            and pub['revision'] == 2 and pub['previous_publication_manifest'] == {k: prior_ref[k] for k in ['path', 'bytes', 'sha256']}
            and pub['original_C0_sha256'] == prior['original_C0_sha256'] == digest(blobs['C0'])
            and pub['actual_strategy_configurations'] == 4
            and pub['new_controls'] == pub['projection_new_trials'] == pub['projection_new_controls'] == 0,
            'Catalog pair publication version/count/C0 binding mismatch')
    require(summary['classification'] == record['research_fidelity'] == detail['research_fidelity'] == FIDELITY
            and summary['execution_class'] == detail['implementation_fidelity'] == 'ADAPTED_EXECUTION_PROXY'
            and protocol['classification'] == rules['classification'] == FIDELITY + ' / ADAPTED_EXECUTION_PROXY; strict0'
            and original['fidelity_class'] == entry['fidelity_class'] == 'HYPOTHESIS'
            and summary['strict_reproductions'] == c0['strict_reproductions'] == original['audit']['strict_reproductions'] == 0
            and original['audit']['original_runtime_equivalence'] is False and original['audit']['PIT'] == 'NOT_PROVEN',
            'Catalog pair hypothesis must not be promoted')
    require(summary['strategy_configurations'] == c0['planned_strategy_configurations'] == record['configuration_runs'] == 4
            and summary['new_controls'] == c0['planned_new_controls'] == record['new_control_runs'] == 0
            and detail['projection_activity'] == {'new_strategy_trials': 0, 'new_controls': 0},
            'Catalog pair reuse/projection count conflict')
    require(original['lineage']['C0_sha256'] == digest(blobs['C0']) and original['lineage']['input_sha256'] ==
            c0['canonical_sha256'] == protocol['input']['sha256'] == rules['input']['sha256'] == control['input_sha256'],
            'Catalog pair input/C0 provenance conflict')
    frozen = {}
    for item in c0['files']:
        require(item['path'] not in frozen, 'Duplicate catalog pair C0 path')
        frozen[item['path']] = item
    prefix = f'research/public-strategies/{rid}/'
    for role in ['protocol', 'rules', 'catalog_fields']:
        path = entry['artifacts'][role]['path'].removeprefix(prefix)
        require(frozen[path]['sha256'] == digest(blobs[role]) and frozen[path]['bytes'] == len(blobs[role]),
                'Catalog pair selected rule differs from C0')
    for key, value in rules.items():
        if key != 'input':
            same(protocol[key], value, 'Catalog pair protocol/rule conflict: ' + key)
    expected_rules = {k: deepcopy(rules[k]) for k in RULE_KEYS + SPECIFIC[rid]}
    require(('bollinger' not in rules) if rid == 'M1396' else ('hl2_SMA4' not in rules), 'Cross-strategy rule contamination')
    require(record['rules'] == expected_rules and record['metric_conventions'] == protocol['statistics'], 'Catalog pair display rules changed')
    for key in ['capital', 'entry', 'exit']:
        same(detail['spec']['params'][key], rules[key], 'Catalog pair detail rule changed')
    require(detail['spec']['params']['metric_conventions'] == protocol['statistics']
            and detail['spec']['params']['source_contract'] == CONTRACTS[rid], 'Catalog pair detail contract conflict')
    capital = rules['capital']
    require(capital['fraction'] == '1' and capital['entry_fee_inclusive'] is True and capital['initial_cash'] == '100000'
            and capital['Decimal_precision'] == 50 and capital['rounding'] == 'ROUND_HALF_EVEN'
            and detail['metrics']['capital_state']['initial_cash_usdt'] == 100000,
            'Catalog pair fullcash fee-inclusive allocation conflict')
    require(catalog['fields']['id'] == rid and catalog['original_field_count'] == 11
            and len(catalog['fields']) == (11 if rid == 'M1396' else 10)
            and set(catalog['redacted_fields']) == (set() if rid == 'M1396' else {'别名来源'})
            and record['catalog_fields'] == catalog['fields'], 'Catalog pair approved field scope changed')
    scope = dict(original_field_count=11, public_field_count=len(catalog['fields']),
        omitted_fields={key: {k: v for k, v in value.items() if k in ['reason', 'public_alias_url']}
                        for key, value in catalog['redacted_fields'].items()}, complete_original_fields_public=rid == 'M1396')
    require(record['catalog_public_scope'] == scope and (rid != 'M1463' or '别名来源' not in record['catalog_fields']),
            'Catalog pair redaction disclosure changed or private alias restored')
    require(record['economic_basis'] == dict(paper=None, hypothesis=rules['economic_hypothesis'], status='INFERRED_RESEARCH_RATIONALE_NOT_SOURCE_VERIFIED')
            and record['monthly'] is None and record['monthly_status'] == 'NOT_PUBLISHED_IN_SELECTED_LIGHT_SUMMARY'
            and record['benchmark_curve'] == [], 'Catalog pair invented economic/source/series evidence')
    require(control['id'] == release['source_id'] == 'M1258' and control['control_name'] == 'buyhold'
            and release['status'] == 'RELEASED_FOR_EXACT_IDENTITY_REUSE' and rid in release['consumers']
            and release['control_reference']['sha256'] == original['lineage']['control_reference_sha256'] == digest(blobs['control_reference'])
            and release['new_controls_authorized'] == protocol['benchmark']['new_control_configurations'] == 0
            and release['remote_public_core_commit'] == summary['control_remote_commit'] == original['lineage']['control_remote_commit'] == CONTROL_PIN,
            'Catalog pair accepted control identity/release conflict')
    require(control['initial_cash'] == '100000' and control['allocation'] == '100% fee-inclusive'
            and control['fee_bps_each_side'] == 8 and control['slippage_bps_each_side'] == 2
            and control['native_timeframe'] == '1d' and control['bars'] == 731
            and control['window_OOS'] is False and control['trusted'] is False and control['PIT'] == 'NOT_PROVEN'
            and control['statistics'] == protocol['statistics'], 'Catalog pair control capital/cost/quality changed')
    expected_benchmark = dict(kind='REUSED_ACCEPTED_M1258_CONTROL', id='M1258', name='buyhold', source_commit=CONTROL_PIN,
        evidence_role='control_reference', acceptance_role='control_release', new_controls_for_this_strategy=0,
        allocation='100% fee-inclusive', initial_cash='100000', fee_bps_each_side=8, slippage_bps_each_side=2,
        timeframe='1d', observations=731, evaluation_start=control['evaluation_start'],
        evaluation_end_exclusive=control['evaluation_end_exclusive'], metrics=control['metrics'], window_OOS=False)
    require(record['benchmark_reference'] == expected_benchmark, 'Catalog pair must reference the same existing M1258 control')
    require(protocol['evaluation_start_ms'] == 1672531200000 and protocol['evaluation_end_ms'] == 1735689600000
            and control['evaluation_start'] == '2023-01-01T00:00:00Z' and control['evaluation_end_exclusive'] == '2025-01-01T00:00:00Z',
            'Catalog pair window changed')
    cases = {case['case']: case for case in summary['cases']}
    require(len(summary['cases']) == len(cases) == 4 and set(cases) == {'base', 'fee0', 'fee20', 'delay2'}
            and record['results'] == cases, 'Catalog pair result/configurations changed')
    def match(view, metric):
        for key in ['total_return', 'cagr', 'max_drawdown', 'sharpe_zero_cash', 'observations', 'final_equity']:
            same(view[key], metric[key], 'Catalog pair source metric changed: ' + key)
        same(view['sharpe'], metric['sharpe_zero_cash'], 'Catalog pair Sharpe/null changed')
        require(metric['observations'] == 731 and view['annualization'] == 365
                and view['start'] == '2023-01-01' and view['end'] == '2024-12-31', 'Catalog pair metric observations/window changed')
    for name, fee, lag in [('base', 8, 1), ('fee0', 0, 1), ('fee20', 20, 1), ('delay2', 8, 2)]:
        case = cases[name]
        cfg = dict(name=name, fee_bps_each_side=fee, slippage_bps_each_side=2, delay_bars=lag)
        require(cfg in protocol['cases'] and cfg in rules['cost_cases'] and case['kind'] == 'STRATEGY'
                and case['fee_bps'] == fee and case['slippage_bps'] == 2 and case['delay_bars'] == lag
                and case['monthly_observations'] == 24, 'Catalog pair frozen cost/day lag changed')
        view = detail['metrics']['periods'] if name == 'base' else detail['metrics']['additional_native_bar_lag'] if name == 'delay2' else detail['metrics']['cost_sensitivity'][str(fee)]
        require(set(view) == ({'full', '2023-2024'} if name == 'base' else {'2023-2024'}), 'Catalog pair unexpected periods')
        match(view['2023-2024'], case)
    same(detail['metrics']['periods']['full'], detail['metrics']['periods']['2023-2024'], 'Catalog pair existing full alias conflicts')
    match(detail['metrics']['same_instrument_benchmark']['2023-2024'], control['metrics'])
    same(detail['metrics']['capital_state']['terminal_pending'], cases['base']['terminal_pending'], 'Catalog pair terminal null changed')
    metrics = deepcopy(original['metrics'])
    metrics['cost_sensitivity'] = {str(fee): original['metrics']['cost_sensitivity'][name] for name, fee in [('fee0', 0), ('fee20', 20)]}
    metrics['source_cost_key_aliases'] = {'fee0': '0', 'fee20': '20'}
    require(detail['metrics'] == metrics, 'Catalog pair metrics differ from approved original detail')
    curve = _loads(blobs['curve'])
    dates = ['2023-01-01'] + [f'{y}-{m:02d}-{calendar.monthrange(y, m)[1]}' for y in [2023, 2024] for m in range(1, 13)]
    require(original['run_id'] == entry['run_id'] and original['variant_id'] == entry['variant_id']
            and curve == original['curve'] == detail['curve'] and [p['date'] for p in curve] == dates,
            'Catalog pair must retain exactly25 original curve objects')
    for point in curve:
        require(type(point['equity']) in [int, float] and math.isfinite(point['equity']) and point['equity'] >= 0
                and type(point['drawdown']) in [int, float] and math.isfinite(point['drawdown']) and -1 <= point['drawdown'] <= 0,
                'Invalid catalog pair sampled point')
    require(curve[0]['equity'] == 1 and math.isclose(curve[-1]['equity'], cases['base']['final_equity']/100000, abs_tol=1e-14),
            'Catalog pair sampled equity was rescaled/rebased')
    meta = detail['curve_meta']
    require(meta['returned_points'] == 25 and meta['observations'] == meta['total_observations'] == 731
            and meta['equity_unit'] == 'initial_capital_multiple' and meta['drawdown_unit'] == 'fraction'
            and meta['denominator'] == 100000 and all(meta[k] is False for k in ['first_point_rebased',
                'full_daily_curve_published', 'interpolation_claim', 'private_daily_nav_used']), 'Catalog pair curve semantics conflict')
    binding = {k: detail[k] for k in ['origin_run_id', 'variant_id', 'fidelity_class', 'execution_class']}
    binding.update(protocol_sha256=digest(blobs['protocol']), manifest_sha256=digest(blobs['result_manifest']))
    require(detail['transport_binding'] == binding and all(isinstance(v, str) and v for v in binding.values()),
            'Catalog pair source transport conflict')

"""M1347's approved public graph projection, without replay or native identity.

This is a separate typed contract. Its Lab manifest hashes the immutable Lab
record/detail; the enriched Graph outputs reference that manifest, not themselves.
"""
import calendar
from copy import deepcopy
import math

from quantgraph.graph.corpus_research import _finite, _loads
from quantgraph.graph.metadata_pilot import digest, encoded

ID = 'M1347'
CONTRACT = 'CATALOG_UTC_MONTHTURN_FULLCASH_PUBLIC_GRAPH_V2'
PROFILE = 'APPROVED_M1347_GRAPH_PROJECTION_V2'
KIND = 'PUBLIC_DERIVED_GRAPH_PROJECTION'
SCHEMA = 'M1347-public-graph-projection/v2'
PIN = '475ee92d451b581b8565dc1ef487437cdc39b743'
ORIGIN = '5ccadf192dfc6381721058d28887cd9bc435a20c'
RUN = 'm1347-catalog-daily-20261003-v1'
VARIANT = 'M1347-catalog-daily-v1-base'
FIDELITY = 'HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED'
EXECUTION = 'ADAPTED_EXECUTION_PROXY'
PREFIX = 'research/public-strategies/M1347/'
V1 = 'artifacts/20261003-catalog-v1/'
V2 = 'artifacts/20261003-graph-projection-v2/'
PATHS = {
    'publication_manifest': 'publication-manifest.v1.json',
    'record': V2+'graph-record.json', 'detail': V2+'graph-detail.json',
    'result_manifest': V2+'public-display-manifest.json', 'curve': V2+'base-nav-sampled.json',
    'verification': V2+'verification.safe.json',
    'origin_record': V1+'graph-record.json', 'origin_detail': V1+'graph-detail.json',
    'origin_curve': V1+'base-nav-sampled.json', 'summary': V1+'summary.json',
    'license': V1+'LICENSE-results.md', 'projection_script': 'scripts/derive_graph_v2.py',
    'public_catalog': 'source/catalog-public-fields.json', 'root_rules': 'source/root-frozen-rules.json',
    'protocol': 'specs/protocol-v1.json', 'C0': 'specs/C0-v1.json',
    'control_reference': 'specs/control-reference.json', 'correction_note': 'M1347-display-correction-v2.md',
}
# Frozen semantic/permission anchors supplement the independently pinned registry.
# A re-signed display/publication cannot silently replace the research contract.
CORE_SHA = {
    'public_catalog': 'af1f54439cdde98b5ca32752b885e7bc0d1660c357bb1543a73cf58f080d6819',
    'root_rules': 'c84bc598eb11cc3649cf58caf069d69715574070ea192754bd9f97124c5a23b4',
    'protocol': 'b176b3412aca14a1f9c860937654f97b4d42c9448abb712583005f14996ab674',
    'C0': '95c1aaee84657d0d3639c94d282e6e4bfa9934ba9f3b4c6fa5aaed13355dfed3',
    'control_reference': 'ea4fb4687cffe69b7ee877312e19ec49b263bf5d21705d0dcfa2e791c24be00a',
    'license': '6109e7075c3c92e70759c667ef6d2bb43927fa0fb111b19c3a8599a11864dec8',
    'projection_script': '9d0dbdcebe5d57c013b7ca0bf4617694747da911bfacc34a26cd505ef06394ef',
}
FIELDS = {'id', '名称', '市场', '作者或机构', '标题', 'source_url', '页码或文件', '可回测', '别名来源', '提出日期'}
RULE_KEYS = ['indicator', 'entry', 'exit', 'calendar_execution', 'capital', 'execution',
             'cold_start', 'cost_cases', 'valuation', 'statistics', 'stop_or_roi', 'known_halt']
COSTS = [dict(name=n, fee_bps_each_side=f, slippage_bps_each_side=2, delay_bars=l)
         for n, f, l in [('base', 8, 1), ('fee0', 0, 1), ('fee20', 20, 1), ('delay2', 8, 2)]]


def require(ok, reason):
    if not ok:
        raise ValueError('M1347: ' + reason)


def same(value, expected, reason):
    require(encoded(value) == encoded(expected), reason)


def number(value, reason, *, nullable=False):
    if nullable and value is None:
        return
    try:
        valid = type(value) in [int, float] and math.isfinite(value)
    except OverflowError:
        valid = False
    require(valid, reason)


def match_metric(view, case):
    # Equal strings/booleans in two re-signed objects are still not metrics.
    for key in ['total_return', 'cagr', 'max_drawdown', 'sharpe_zero_cash', 'final_equity']:
        for value in [view[key], case[key]]:
            number(value, 'Financial metric must be a finite number: '+key, nullable=key == 'sharpe_zero_cash')
        same(view[key], case[key], 'Metric value/type/null changed: '+key)
    number(view['sharpe'], 'Sharpe must be a finite number or null', nullable=True)
    same(view['sharpe'], case['sharpe_zero_cash'], 'Sharpe alias/null changed')
    same(view['observations'], 731, 'Metrics retain 731 actual observations')
    same(case['observations'], 731, 'Source metric observation count must be integer')
    same(view['annualization'], 365, 'Daily annualization changed')
    require(view['start'] == '2023-01-01' and view['end'] == '2024-12-31', 'Metric window changed')
    require(view['total_return'] >= -1 and view['cagr'] >= -1 and -1 <= view['max_drawdown'] <= 0
            and view['final_equity'] >= 0, 'Financial metric outside defined range')


def selected(entry):
    return (entry.get('id') == ID or entry.get('source_contract') == CONTRACT
            or entry.get('manifest_kind') == KIND or entry.get('projection_profile') == PROFILE)


def check_entry(entry):
    require(entry.get('id') == ID and entry.get('source_contract') == CONTRACT
            and entry.get('projection_profile') == PROFILE and entry.get('manifest_kind') == KIND
            and entry.get('lab_commit') == PIN and entry.get('fidelity_class') == 'HYPOTHESIS'
            and entry.get('run_id') == RUN and entry.get('variant_id') == VARIANT,
            'Explicit frozen identity/contract/type/pin required')
    refs = entry['artifacts']
    require(set(refs) == set(PATHS), 'Only the 18 approved public roles may be read')
    for role, rel in PATHS.items():
        ref = refs[role]
        require(ref['path'] == PREFIX+rel
                and ref['url'] == f'https://github.com/KathenZK/quant-research-lab/blob/{PIN}/{PREFIX+rel}'
                and type(ref['bytes']) is int and ref['bytes'] > 0, 'Exact public path/pin/size required: '+role)


def source_bindings(entry, blobs, v):
    check_entry(entry)
    require(set(blobs) == set(PATHS), 'Unexpected source role')
    for role, raw in blobs.items():
        ref = entry['artifacts'][role]
        same(dict(bytes=len(raw), sha256=digest(raw)), {k: ref[k] for k in ['bytes', 'sha256']}, 'Source hash/size: '+role)
    for role, sha in CORE_SHA.items():
        require(digest(blobs[role]) == sha, 'Frozen semantic/permission source changed: '+role)
    pub, manifest, c0 = (v[k] for k in ['publication_manifest', 'result_manifest', 'C0'])
    require(pub.get('schema') == 'M1347-fixed-publication/v1' and pub.get('id') == ID
            and pub.get('first_publication_manifest') is True and pub.get('source_commit') == ORIGIN,
            'Publication schema/identity/provenance conflict')
    same(pub['delivery_revision'], 2, 'Publication revision must be integer 2')
    require(pub['active_graph_projection'] == PREFIX+V2.rstrip('/'), 'Wrong active source projection')
    allowed = {r['path']: r for r in pub['files']}
    require(len(allowed) == len(pub['files']), 'Duplicate publication path')
    for role, ref in entry['artifacts'].items():
        if role != 'publication_manifest':
            same(allowed.get(ref['path']), {k: ref[k] for k in ['path', 'bytes', 'sha256']}, 'Outside public allowlist: '+role)
    require(manifest.get('schema') == SCHEMA and manifest.get('manifest_kind') == KIND
            and manifest.get('id') == ID and manifest.get('fixed_original_source_C0_and_results_unchanged') is True,
            'Explicit public graph manifest schema/type required')
    for key, roles in [('files', ['curve', 'detail', 'record']),
                       ('source_files', ['origin_detail', 'origin_record', 'origin_curve', 'summary'])]:
        expected = [dict(path=PATHS[r].rsplit('/', 1)[-1], bytes=len(blobs[r]), sha256=digest(blobs[r])) for r in roles]
        same(manifest[key], expected, 'Noncyclic manifest file binding conflict: '+key)
    require(manifest['script_sha256'] == digest(blobs['projection_script']), 'Source projection script mismatch')
    for key, expected in [('returned_points', 25), ('metrics_observations', 731), ('normalization_operations', 0),
                          ('original_research_counts', dict(strategy_configurations=4, new_controls=0)),
                          ('this_projection_counts', dict(strategy_configurations=0, new_controls=0))]:
        same(manifest[key], expected, 'Manifest count/unit conflict: '+key)
    require(pub['C0_sha256'] == digest(blobs['C0']) and c0['id'] == ID
            and c0['schema'] == 'M1347-catalog-code-freeze/v1'
            and c0['source_rule_sha256'] == digest(blobs['root_rules']), 'Frozen C0 conflict')
    frozen = {r['path']: r for r in c0['files']}
    require(len(frozen) == len(c0['files']), 'Duplicate C0 path')
    for role in ['public_catalog', 'root_rules', 'protocol', 'control_reference']:
        same(frozen.get(PATHS[role]), dict(path=PATHS[role], bytes=len(blobs[role]), sha256=digest(blobs[role])), 'C0 source binding: '+role)


def validate(entry, blobs, v):
    source_bindings(entry, blobs, v)
    r, d, old, s, p, rules, cat, control = (v[k] for k in [
        'record', 'detail', 'origin_detail', 'summary', 'protocol', 'root_rules', 'public_catalog', 'control_reference'])
    require(all(x.get('id') == ID for x in [r, d, old, s, p, rules, v['origin_record']])
            and d['run_id'] == d['origin_run_id'] == RUN and d['variant_id'] == VARIANT,
            'Stable source execution identity mismatch')
    require(not any(k in x for x in [r, d, old, v['origin_record']] for k in ['entity_id', 'definition_revision']),
            'Do not invent native entity/revision')
    require(d['fidelity_class'] == 'HYPOTHESIS' and d['execution_class'] == s['execution_class'] == EXECUTION
            and d['research_classification'] == r['research_classification'] == s['classification'] == FIDELITY
            and p['classification'] == rules['classification'] == FIDELITY+' / '+EXECUTION+'; strict0'
            and r['status'] == 'tested_proxy_only', 'Research/source fidelity cannot be promoted')
    for obj, key, n in [(r, 'configuration_runs', 4), (r, 'tested_variants', 1), (r, 'new_control_runs', 0),
                        (s, 'strategy_configurations', 4), (s, 'new_controls', 0), (s, 'strict_reproductions', 0),
                        (r['audit'], 'strict_reproductions', 0), (v['C0'], 'new_controls', 0)]:
        same(obj[key], n, 'Exact integer research count required: '+key)
    require(r['audit']['source_verification_status'] == 'CATALOG_ONLY_ORIGINAL_WEBPAGE_UNVERIFIED'
            and r['audit']['original_runtime_equivalence'] is False and r['audit']['PIT'] == 'NOT_PROVEN',
            'Unverified source/PIT boundary changed')
    require(cat['schema'] == 'catalog-public-excerpt/v1' and set(cat['fields']) == FIELDS
            and cat['fields']['id'] == ID and cat['full_original_rule_public'] is False
            and cat['source_webpage_fulltext_verified'] is False, 'Only ten catalog fields plus permitted excerpt are public')
    require(d['spec']['rule_excerpt'] == cat['rule_original_operational_excerpt']
            and d['spec']['source_url'] == p['source_url'] == cat['fields']['source_url'], 'Rule excerpt/attribution conflict')
    for key in RULE_KEYS+['economic_hypothesis', 'benchmark']:
        same(p[key], rules[key], 'Frozen rule/protocol conflict: '+key)
    same(p['cases'], COSTS, 'Frozen cost/day-lag cases changed')
    same(rules['cost_cases'], COSTS, 'Rule cost cases changed')
    same(d['spec']['params'], dict(timeframe='1d', calendar='UTC_24_7', entry='day=month_length-2 at close',
         exit='day=3 at close', fraction='1', entry_fee_inclusive=True, fee_bps=8, slippage_bps=2, lag_bars=1), 'Display implementation params changed')
    capital = rules['capital']
    for k, value in dict(initial_cash='100000', fraction='1', entry_fee_inclusive=True, Decimal_precision=50).items():
        same(capital[k], value, 'Fullcash capital conflict: '+k)
    require(control['id'] == 'M1258' and p['benchmark']['reference_sha256'] == digest(blobs['control_reference'])
            and old['lineage']['control_reference_sha256'] == digest(blobs['control_reference'])
            and old['lineage']['C0_sha256'] == digest(blobs['C0'])
            and old['lineage']['input_sha256'] == v['C0']['input_sha256'] == control['input_sha256'],
            'One existing M1258 control/source chain required')
    same(p['benchmark']['new_control_configurations'], 0, 'No new control permitted')

    # Reconstruct only the public v1-to-v2 aliases; no execution, metric
    # computation or mutation of any source file takes place here.
    expected = deepcopy(old)
    m = expected['metrics']
    same(m['periods']['full'], m['periods']['2023-2024'], 'Conflicting original full alias')
    for name in ['same_instrument_benchmark', 'additional_native_bar_lag']:
        require(set(m[name]) == {'2023-2024'}, 'Unexpected original periods')
        m[name]['full'] = deepcopy(m[name]['2023-2024'])
    require(set(m['cost_sensitivity']) == {'fee0', 'fee20'}, 'Original fee labels changed')
    m['cost_sensitivity'] = {str(f): dict(deepcopy(m['cost_sensitivity'][n]),
        full=deepcopy(m['cost_sensitivity'][n]['2023-2024'])) for n, f in [('fee0', 0), ('fee20', 20)]}
    projection = dict(version=2, period_aliases={'full': '2023-2024'}, fee_labels_bps=['0', '20'],
        retained_slippage_bps_each_side=2, v1_detail_sha256=digest(blobs['origin_detail']), summary_sha256=digest(blobs['summary']),
        new_strategy_configurations=0, new_controls=0,
        explanation='Default full-period consumer and numeric bps labels; all values, nulls and25sourcepoints unchanged')
    expected['display_projection'] = projection
    same(d, expected, 'Public v2 detail changed beyond approved aliases')
    same(r, dict(v['origin_record'], display_projection=projection), 'Public v2 record changed beyond approved aliases')
    same(r['implementations'], [dict(variant_id=VARIANT, family=d['family'], origin_run_id=RUN, fidelity_class='HYPOTHESIS')], 'Origin implementation identity conflict')
    require(len(s['cases']) == 4, 'Exactly four original configurations required')
    metrics = d['metrics']
    for case, cfg in zip(s['cases'], COSTS, strict=True):
        same({k: case[k] for k in ['case', 'kind', 'fee_bps', 'slippage_bps', 'delay_bars']},
             dict(case=cfg['name'], kind='STRATEGY', fee_bps=cfg['fee_bps_each_side'], slippage_bps=2, delay_bars=cfg['delay_bars']),
             'Frozen source cost/day-lag mismatch')
        same(case['terminal_pending'], None, 'Original pending null must remain null')
        require(type(case['total_return']) in [float, int] and case['total_return'] < 0, 'Approved four losing results must remain explicit')
        name = cfg['name']
        view = (metrics['periods'] if name == 'base' else metrics['additional_native_bar_lag'] if name == 'delay2'
                else metrics['cost_sensitivity'][str(cfg['fee_bps_each_side'])])
        require(set(view) == {'full', '2023-2024'}, 'Exact display period set required')
        same(view['full'], view['2023-2024'], 'Full alias conflict')
        match_metric(view['full'], case)
    match_metric(metrics['same_instrument_benchmark']['full'], control['metrics'])
    same(metrics['same_instrument_benchmark']['full'], metrics['same_instrument_benchmark']['2023-2024'], 'Control alias conflict')
    same(metrics['capital_state'], dict(initial_cash_usdt=100000, final_equity_usdt=s['cases'][0]['final_equity'],
                                      final_position_open=True, terminal_pending=None), 'Capital/null state conflict')
    same(v['curve'], d['curve'], 'Detail sampled curve changed')
    require(blobs['curve'] == blobs['origin_curve'], 'Original curve bytes must remain unchanged')
    dates = ['2023-01-01']+[f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}' for y in [2023, 2024] for m in range(1, 13)]
    require([pt['date'] for pt in v['curve']] == dates, 'Only the 25 approved dates are allowed')
    for pt in v['curve']:
        require(set(pt) == {'date', 'equity', 'drawdown'} and type(pt['equity']) in [int, float]
                and type(pt['drawdown']) in [int, float] and pt['equity'] >= 0 and -1 <= pt['drawdown'] <= 0,
                'Invalid sampled curve point')
    require(v['curve'][0]['equity'] == 1 and math.isclose(v['curve'][-1]['equity'], s['cases'][0]['final_equity']/100000,
            rel_tol=0, abs_tol=1e-14), 'Do not rebase or renormalize approved units')
    for key, value in dict(observations=731, total_observations=731, returned_points=25,
                           equity_unit='initial_capital_multiple', drawdown_unit='fraction', benchmark_curve_available=False).items():
        same(d['curve_meta'][key], value, 'Curve semantics changed: '+key)
    return r, d, rules, cat, control


def project(entry, blobs):
    try:
        values = {role: _loads(raw) for role, raw in blobs.items() if PATHS[role].endswith('.json')}
        _finite(values)
        record, detail, rules, catalog, control = validate(entry, blobs, values)
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError('M1347: Missing or malformed typed source field') from exc
    record, detail = deepcopy(record), deepcopy(detail)
    manifest_sha = digest(blobs['result_manifest'])
    ref = dict(origin_run_id=RUN, variant_id=VARIANT, manifest_sha256=manifest_sha, manifest_kind=KIND,
               protocol_sha256=digest(blobs['protocol']), fidelity_class='HYPOTHESIS', execution_class=EXECUTION)
    record.update(related_results=[ref], implementations=[dict(ref, family=detail['family'])],
        fidelity_class='HYPOTHESIS', execution_class=EXECUTION, research_fidelity=FIDELITY,
        strategy_configurations=4, control_configurations=0, reused_control_configurations=1,
        catalog_fields=deepcopy(catalog['fields']), rule_original_operational_excerpt=catalog['rule_original_operational_excerpt'],
        full_original_rule_public=False, source_webpage_fulltext_verified=False,
        rules={k: deepcopy(rules[k]) for k in RULE_KEYS},
        economic_basis=dict(hypothesis=rules['economic_hypothesis'], paper=None, paper_status='MISSING_NOT_SOURCE_VERIFIED'),
        source_artifacts=deepcopy(entry['artifacts']), results=deepcopy(values['summary']['cases']),
        benchmark_reference=dict(id='M1258', kind='EXISTING_ACTUAL_CONTROL_REFERENCE_ONLY',
            source_sha256=digest(blobs['control_reference']), source_commit=control['source_commit'],
            metrics=deepcopy(control['metrics']), new_controls=0, unique_reused_controls=1,
            matched_cost_controls_available=False, limitation=rules['benchmark']['comparison']))
    for obj in [record, detail]:
        obj.update(manifest_kind=KIND, projection_profile=PROFILE, source_contract=CONTRACT,
                   projection_status='STAGED_NOT_IMPORTED', definition_revision_bound=False)
    original_lineage = deepcopy(detail['lineage'])
    detail['lineage'] = dict(original_lab_lineage=original_lineage, lab_commit=PIN, origin_lab_commit=ORIGIN,
        source_artifacts=deepcopy(entry['artifacts']), manifest_kind=KIND, manifest_sha256=manifest_sha,
        source_display_manifest_sha256=manifest_sha, publication_manifest_sha256=digest(blobs['publication_manifest']),
        source_display_detail_sha256=digest(blobs['detail']), protocol_sha256=digest(blobs['protocol']),
        C0_sha256=digest(blobs['C0']), source_contract=CONTRACT, projection_profile=PROFILE, definition_revision_bound=False)
    detail.update(lab_counts=dict(strategy_ids=1, strategy_configurations=4, new_control_configurations=0,
                                  reused_control_configurations=1, strict_reproductions=0),
                  projection_activity=dict(new_strategy_trials=0, new_controls=0))
    detail['spec']['params']['rules'] = deepcopy(record['rules'])
    detail['spec']['economic_basis'] = deepcopy(record['economic_basis'])
    detail['spec']['benchmark_reference'] = deepcopy(record['benchmark_reference'])
    detail['curve_meta'].update(public_curve_available=True, denominator=100000, first_point_rebased=False,
        full_daily_curve_published=False, private_daily_nav_used=False, interpolation_claim=False)
    detail['metrics']['additional_lag_unit'] = 'day'
    return record, detail


def check_merge_kind(record, detail):
    """The new kind is limited to this explicit contract, even in offline merge."""
    require(record.get('id') == detail.get('id') == ID and detail.get('run_id') == RUN
            and detail.get('variant_id') == VARIANT, 'Graph projection merge identity mismatch')
    for obj in [record, detail, detail['lineage']]:
        require(obj.get('manifest_kind') == KIND and obj.get('source_contract') == CONTRACT
                and obj.get('projection_profile') == PROFILE, 'Graph projection merge type/contract mismatch')
    refs = record['related_results']+record['implementations']
    require(len(refs) == 2 and all(r.get('origin_run_id') == RUN and r.get('variant_id') == VARIANT
            and r.get('manifest_kind') == KIND and r.get('manifest_sha256') == detail['lineage']['manifest_sha256']
            for r in refs), 'Graph projection merge reference mismatch')

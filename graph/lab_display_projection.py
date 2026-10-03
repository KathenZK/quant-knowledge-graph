"""Bounded, offline Lab display adapter; never a native corpus import or uploader.

Only explicitly selected, hash-pinned approved source inventories enter this
adapter; the committed default lists each approved record. There is no repository scan.
An optional externally pinned current snapshot permits an additive asset draft;
neither path activates, deploys, fetches data, or executes a strategy.
"""
import argparse
from copy import deepcopy
import csv
from datetime import date, timedelta
import gzip
import io
import json
import math
from pathlib import Path
import re
import shutil

from quantgraph.graph.corpus_research import _finite, _loads
from quantgraph.graph.metadata_pilot import (
    RESERVE, digest, encoded, merge_record, publication_screen, read_below,
)
from quantgraph.graph.site_feedback import canonical

REGISTRY = Path(__file__).resolve().parents[1] / 'metadata/lab-display-sources.json'
MANIFEST_KIND = 'LAB_ORIGIN_RESULT_MANIFEST_NOT_GRAPH_COLLECTION'
DERIVED_MANIFEST_KIND = 'PUBLIC_DERIVED_DISPLAY_MANIFEST'
COMMON_LIMITS = [
    '研究者按可用数据选定2024年BTCUSDT现货5分钟实例；不是样本外，也不是原作者完整运行环境。',
    'DIAGNOSTIC_ONLY；PIT、历史可交易性及数据最终性未获严格认证；0严格复现，不晋升。',
    '费用情景及额外一根原生K线延迟属于冻结诊断配置，不是新的策略ID。',
    '指标最大回撤保留原生5分钟口径；显示回撤仅由保留的每日单位净值计算，二者不可混同。',
]
EXECUTION_NOTES = {
    'batch009': 'ADAPTED_EXECUTION_PROXY：原GTC限价进出改为下一原生开盘保证全额成交，风险退出使用OHLC代理；没有限价排队、部分成交、超时验证。',
    'M0298': 'HYPOTHESIS：保留Simple信号；以信号收盘价为限价，下一可成交5分钟内开盘改善或触价全额成交，超时取消；止损改为市场代理，2bps作为现金摩擦。',
    'M0304': 'HYPOTHESIS：Strategy002限价GTC/300秒超时与O-L-H-C路径是假设执行；保留盈利门槛、ROI和止损，不能称原框架严格复现。',
}


def reviewed(value):
    _finite(value)
    if publication_screen({'display': json.dumps(value, ensure_ascii=False)})['status'] == 'PRIVATE_ONLY_BLOCKED':
        raise ValueError('Display contains a private or credential-like field; review required')
    return value


def verified_source(root, entry):
    rid = entry['id']
    if not re.fullmatch(r'M\d{4}', rid) or not re.fullmatch(r'[a-f0-9]{40}', entry['lab_commit']):
        raise ValueError('Invalid pinned source identity')
    prefix = f'research/public-strategies/{rid}/'
    blobs = {}
    for role, ref in entry['artifacts'].items():
        if not ref['path'].startswith(prefix):
            raise ValueError('Source artifact belongs to another stable ID')
        if ref['url'] != f'https://github.com/KathenZK/quant-research-lab/blob/{entry["lab_commit"]}/{ref["path"]}':
            raise ValueError('Source URL does not pin the same commit and path')
        raw = read_below(root, ref['path'])
        if digest(raw) != ref['sha256'] or len(raw) != ref['bytes']:
            raise ValueError('Source artifact hash/bytes mismatch: ' + role)
        blobs[role] = raw
    pub = _loads(blobs['publication_manifest'])
    if (pub.get('id') or pub.get('record_id')) != rid:
        raise ValueError('Publication identity mismatch')
    allowed = {}
    for ref in pub['files']:
        path = ref['path'] if ref['path'].startswith(prefix) else prefix + ref['path']
        if path in allowed:
            raise ValueError('Duplicate publication path')
        allowed[path] = {'sha256': ref['sha256'], 'bytes': ref['bytes']}
    for role, ref in entry['artifacts'].items():
        if role != 'publication_manifest' and allowed.get(ref['path']) != {'sha256': ref['sha256'], 'bytes': ref['bytes']}:
            raise ValueError('Source artifact is outside publication allowlist')
    return blobs


def period(metric, start, end):
    _finite(metric)
    return dict(start=start, end=end, observations=metric['daily_observations'],
                native_observations=metric['observations'], total_return=metric['total_return'],
                cagr=metric['annualized_return'], sharpe=metric.get('sharpe_daily', metric.get('sharpe')),
                max_drawdown=-abs(metric['max_drawdown']), annualization=365,
                sharpe_cash_basis='UTC daily close returns; rf=0; sample ddof=1',
                max_drawdown_basis='original native 5m close equity including initial capital', oos_claim=False)


def derived_manifest(entry, blobs, origin, record, protocol):
    """Bind additive display evidence without relabeling it as a private run manifest."""
    rid = entry['id']
    if (origin.get('schema_version') != 'quantgraph-public-derived-display-manifest/v1'
            or origin.get('id') != rid or origin.get('origin_run_id') != entry['run_id']
            or origin.get('variant_id') != entry['variant_id']
            or origin.get('original_private_result_manifest') is not False
            or origin.get('original_results_modified') is not False):
        raise ValueError('Invalid derived display manifest identity or scope')
    origin_commit = origin.get('origin_lab_commit', '')
    if not re.fullmatch(r'[a-f0-9]{40}', origin_commit):
        raise ValueError('Derived source commit required')
    names = {'summary.json':'summary', 'protocol.json':'protocol', 'C0.json':'C0', 'base-nav-light.csv':'curve'}
    if (set(origin['files']) != set(names)
            or set(origin.get('excluded_from_self_hash', [])) != {'public-display-manifest.json', 'graph-record.json'}):
        raise ValueError('Derived evidence must exclude cyclic record/self references')
    for name, role in names.items():
        ref = origin['files'][name]
        if any(ref[k] != value for k,value in dict(path=entry['artifacts'][role]['path'],
                sha256=digest(blobs[role]),bytes=len(blobs[role])).items()):
            raise ValueError('Derived evidence file binding mismatch: '+role)
    prior = _loads(blobs['origin_publication_manifest'])
    if (prior.get('record_id') or prior.get('id')) != rid:
        raise ValueError('Historical publication identity mismatch')
    prefix = f'research/public-strategies/{rid}/'
    allowed = {}
    for item in prior['files']:
        path = item['path'] if item['path'].startswith(prefix) else prefix+item['path']
        if path in allowed:
            raise ValueError('Duplicate historical publication path')
        allowed[path] = {'sha256':item['sha256'],'bytes':item['bytes']}
    source_refs = origin['source_artifacts']
    for role, ref in source_refs.items():
        path = ref['path']
        if (not path.startswith(prefix) or '..' in Path(path).parts or '\\' in path
                or ref['url'] != f'https://github.com/KathenZK/quant-research-lab/blob/{origin_commit}/{path}'):
            raise ValueError('Derived source must pin a same-ID public artifact')
        expected = (dict(sha256=digest(blobs['origin_publication_manifest']),bytes=len(blobs['origin_publication_manifest']))
                    if role=='publication_manifest' and path==prefix+'publication-manifest.json' else allowed.get(path))
        if expected != {'sha256':ref['sha256'],'bytes':ref['bytes']}:
            raise ValueError('Derived source outside historical publication allowlist')
    for role in ['summary','protocol','C0','source_rule_card','publication_manifest']:
        selected = 'origin_publication_manifest' if role=='publication_manifest' else role
        ref = source_refs[role]
        if ref['sha256'] != digest(blobs[selected]) or ref['bytes'] != len(blobs[selected]):
            raise ValueError('Derived source hash mismatch: '+role)
    c0, card = (_loads(blobs[k]) for k in ['C0','source_rule_card'])
    if (c0.get('record_id') != rid or card.get('record_id') != rid
            or c0['protocol_sha256'] != digest(blobs['protocol'])
            or c0['source_sha256'] != protocol['source']['sha256']
            or card['source']['sha256'] != protocol['source']['sha256']):
        raise ValueError('Derived C0/rule source binding mismatch')
    expected_rules = dict(entry=card['entry'],exit=card['exit'],risk=protocol['risk'],
        execution=protocol['execution'],parameters=protocol['parameters'],
        catalog_difference_or_omission=card['catalog_difference_or_omission'])
    if record.get('rules') != expected_rules or ('rules' in protocol and protocol['rules'] != expected_rules):
        raise ValueError('Record rules differ from pinned rule card/protocol')
    reviewed(expected_rules)
    return expected_rules


def project(entry, blobs):
    rid = entry['id']
    record, summary, protocol = (_loads(blobs[k]) for k in ['record', 'summary', 'protocol'])
    _finite(summary)
    if any((v.get('id') or v.get('record_id')) != rid for v in [record, summary, protocol]):
        raise ValueError('Source record identity mismatch')
    run, variant = entry['run_id'], entry['variant_id']
    ref = record if rid == 'M0304' else record['related_results'][0]
    if (ref['origin_run_id'] != run or ref['variant_id'] != variant
            or ref['protocol_sha256'] != digest(blobs['protocol'])
            or ref['fidelity_class'] != entry['fidelity_class']
            or summary['fidelity_class'] != entry['fidelity_class']):
        raise ValueError('Frozen execution identity or fidelity mismatch')
    manifest_sha = digest(blobs['result_manifest'])
    if rid != 'M0304' and ref['manifest_sha256'] != manifest_sha:
        raise ValueError('Origin result manifest mismatch')
    if entry['fidelity_class'] not in {'ADAPTED', 'HYPOTHESIS'}:
        raise ValueError('Unsupported Lab fidelity')
    origin = _loads(blobs['result_manifest'])
    manifest_kind = entry.get('manifest_kind', MANIFEST_KIND)
    if manifest_kind not in {MANIFEST_KIND, DERIVED_MANIFEST_KIND}:
        raise ValueError('Unsupported display manifest kind')
    declared_kinds = [v.get('manifest_kind') for v in [origin, ref]]
    if manifest_kind == DERIVED_MANIFEST_KIND:
        if declared_kinds != [DERIVED_MANIFEST_KIND, DERIVED_MANIFEST_KIND]:
            raise ValueError('Derived manifest kind requires explicit matching source and reference')
        rules = derived_manifest(entry, blobs, origin, record, protocol)
    elif any(k is not None and k != MANIFEST_KIND for k in declared_kinds):
        raise ValueError('Origin manifest cannot hide a derived/unsupported kind')
    origin_files = origin['files']
    if isinstance(origin_files, list):
        origin_files = {v.get('path') or v.get('name'):v for v in origin_files}
    if any(origin_files['summary.json'][k] != v for k,v in
           [('sha256',digest(blobs['summary'])),('bytes',len(blobs['summary']))]):
        raise ValueError('Summary differs from frozen result manifest')
    for case, fee, delay in [('base',8,1),('fee0',0,1),('fee20',20,1),('delay2',8,2)]:
        result=summary['results'][case]
        config=result.get('configuration') or result.get('case') or result
        if (config.get('fee_bps',config.get('fee_bps_per_side')) != fee
                or config.get('delay_bars',config.get('lag_bars')) != delay):
            raise ValueError('Cost/delay alias differs from actual frozen configuration')
    evaluation = protocol.get('evaluation') or {}
    start = (evaluation.get('start') or evaluation.get('start_inclusive') or '2024-01-01')[:10]
    exclusive = (evaluation.get('end_exclusive') or '2025-01-01')[:10]
    end = (date.fromisoformat(exclusive) - timedelta(days=1)).isoformat()
    execution = protocol.get('execution') or protocol.get('execution_plan') or {}
    initial = execution.get('initial_cash', execution.get('initial_cash_USDT', 100000))
    if initial != 100000:
        raise ValueError('This approved batch requires frozen initial cash 100000')
    curve, peak = [], 1.0
    if 'curve' in blobs:
        rows = list(csv.DictReader(io.StringIO(blobs['curve'].decode())))
        if len(rows) != summary['results']['base']['metrics']['daily_observations']:
            raise ValueError('Public curve row count differs from summary')
        for n, row in enumerate(rows):
            stamp = row.get('date')
            if not stamp:
                # The retained M0298 timestamp is the exclusive closing boundary.
                time = row['valuation_time_utc']
                if not time.endswith('T00:00:00Z'):
                    raise ValueError('M0298 valuation boundary must be UTC midnight')
                stamp = (date.fromisoformat(time[:10]) - timedelta(days=1)).isoformat()
            if stamp != (date.fromisoformat(start) + timedelta(days=n)).isoformat():
                raise ValueError('Public curve dates are not contiguous within the fixed window')
            nav = float(row.get('nav') or float(row['equity']) / initial)
            if not math.isfinite(nav) or nav < 0 or not math.isclose(nav, float(row['equity']) / initial, rel_tol=1e-11, abs_tol=1e-250):
                raise ValueError('Public NAV does not reconcile with frozen initial cash')
            peak = max(peak, nav)
            point = dict(date=stamp, equity=nav, drawdown=nav / peak - 1)
            if 'valuation_time_utc' in row:
                point['valuation_time_utc'] = row['valuation_time_utc']
            if manifest_kind == DERIVED_MANIFEST_KIND:
                if row.get('valuation_time_utc') != (date.fromisoformat(stamp)+timedelta(days=1)).isoformat()+'T00:00:00Z':
                    raise ValueError('Derived curve valuation boundary differs from retained UTC day')
                native_dd = float(row['source_native_drawdown'])
                if not math.isfinite(native_dd) or not -1 <= native_dd <= 0:
                    raise ValueError('Invalid retained native drawdown')
                point['source_native_drawdown'] = native_dd
            curve.append(point)
        if not curve or curve[-1]['date'] != end or not math.isclose(curve[-1]['equity'] - 1, summary['results']['base']['metrics']['total_return'], abs_tol=1e-11):
            raise ValueError('Public curve end or terminal return mismatch')
        if 'curve_meta' in blobs and _loads(blobs['curve_meta'])['sampled_curve_sha256'] != digest(blobs['curve']):
            raise ValueError('Curve metadata hash mismatch')
    elif rid != 'M0304':
        raise ValueError('Expected public curve is missing')
    metric = lambda name: period(summary['results'][name]['metrics'], start, end)
    benchmark = summary['results'].get('buyhold', {}).get('metrics')
    if benchmark is None:
        benchmark = summary['benchmark_reference']['metrics']
    source = protocol.get('source') or {}
    source_url = source.get('url') or record.get('source_url')
    if not source_url and source.get('repository') and source.get('commit') and source.get('path'):
        source_url = f'https://github.com/{source["repository"]}/blob/{source["commit"]}/{source["path"]}'
    if not source_url or not source_url.startswith('https://'):
        raise ValueError('Missing public pinned source URL')
    explanation = EXECUTION_NOTES.get(rid, EXECUTION_NOTES['batch009'])
    limits = list(dict.fromkeys(COMMON_LIMITS + [explanation] + record.get('limitations', [])))
    if not curve:
        limits.append('公开清单没有获准净值曲线；完整账本仍私有。本显示仅保留已公开汇总，不补造曲线。')
    audit = deepcopy(record.get('audit', {}))
    audit.update(strict_replication=False, oos_claim=False, promotion=False, definition_bound=False,
                 data_quality_status='DIAGNOSTIC_ONLY', trusted_input=False)
    lineage = dict(origin_run_id=run, variant_id=variant, protocol_sha256=digest(blobs['protocol']),
                   manifest_sha256=manifest_sha, source_run_manifest_sha256=manifest_sha,
                   manifest_kind=manifest_kind, lab_commit=entry['lab_commit'],
                   publication_manifest_sha256=digest(blobs['publication_manifest']),
                   definition_revision_bound=False, new_execution_trials=0,
                   source_artifacts=entry['artifacts'])
    family = record.get('family') or record['families'][0]
    result_ref = dict(origin_run_id=run, variant_id=variant, fidelity_class=entry['fidelity_class'],
                      fidelity_reason=explanation, protocol_sha256=digest(blobs['protocol']),
                      manifest_sha256=manifest_sha)
    if entry['fidelity_class'] == 'ADAPTED':
        result_ref['execution_class'] = 'ADAPTED_EXECUTION_PROXY'
    if manifest_kind == DERIVED_MANIFEST_KIND:
        result_ref['manifest_kind'] = manifest_kind
        lineage['source_display_manifest_sha256'] = lineage.pop('source_run_manifest_sha256')
        lineage['origin_lab_commit'] = origin['origin_lab_commit']
    projected = dict(id=rid, name=record['name'], status='tested_adapted_only' if entry['fidelity_class']=='ADAPTED' else 'tested_hypothesis_only',
                     reason=record.get('reason') or record.get('method') or explanation, tested_variants=1,
                     families=[family], audit=audit, related_results=[result_ref],
                     implementations=[dict(result_ref, family=family)], projection_status='STAGED_NOT_IMPORTED',
                     definition_revision_bound=False, limitations=limits)
    parameters = {k: protocol[k] for k in ['parameters', 'signals', 'rules', 'risk', 'execution',
                    'execution_plan', 'risk_plan', 'runtime_resolution', 'implementation_adjustments_before_returns'] if k in protocol}
    if manifest_kind == DERIVED_MANIFEST_KIND:
        parameters['rules'] = deepcopy(rules)
    detail = dict(id=rid, name=record['name'], run_id=run, origin_run_id=run, variant_id=variant,
                  fidelity_class=entry['fidelity_class'], fidelity_reason=explanation, family=family,
                  metrics=dict(periods={'full': metric('base')}, same_instrument_benchmark={'full': period(benchmark,start,end)},
                               cost_sensitivity={str(bps): {'full': metric(case)} for bps,case in [(0,'fee0'),(20,'fee20')]},
                               additional_native_bar_lag={'full': metric('delay2')},
                               source_metric_aliases='annualized_return→cagr; daily Sharpe→sharpe; MDD→negative magnitude'),
                  spec=dict(source_url=source_url, params=parameters, assumptions=limits),
                  audit=audit, lineage=lineage, curve=curve,
                  curve_meta=dict(total_observations=len(curve), returned_points=len(curve),
                                  native_observations=summary['results']['base']['metrics']['observations'],
                                  sampling='all retained UTC daily closes; equity=original NAV, initial capital=1; no first-point rebasing',
                                  date_mapping='M0298 exclusive UTC midnight boundary→previous UTC valuation day; original timestamp retained' if rid=='M0298' else 'retained UTC daily valuation date',
                                  public_curve_available=bool(curve)),
                  limitations=limits,
                  data_attribution=record.get('data_attribution') or dict(provider='Binance',
                      license='CC BY-NC-SA-4.0 plus Binance Dataset Terms',
                      terms_url='https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md',
                      changes='Display projection of approved aggregate summary; no raw data or full logs'))
    if manifest_kind == DERIVED_MANIFEST_KIND:
        projected['manifest_kind'] = manifest_kind
        detail['manifest_kind'] = manifest_kind
        detail['curve_meta']['source_native_drawdown_basis'] = 'retained original full5m peaks; separate from daily display drawdown'
        detail['curve_meta']['date_mapping'] = 'retained UTC day and its exclusive next-midnight valuation timestamp'
        detail['spec']['economic_basis'] = deepcopy(record['economic_basis'])
    configs=summary['strategy_configurations']
    controls=summary.get('new_control_configurations',summary.get('control_configurations',summary.get('controls')))
    reused=summary.get('reused_control_configurations',0)
    if configs != 4 or controls not in {0,1} or reused not in {0,1} or controls+reused!=1:
        raise ValueError('Frozen configuration/control counts differ from this projection contract')
    detail['lab_counts'] = dict(strategy_ids=1, strategy_configurations=configs,
        new_control_configurations=controls, reused_control_configurations=reused, strict_reproductions=0)
    if 'benchmark_reference' in summary:
        # Its relative source path is provenance, not a public transport address.
        detail['lineage']['benchmark_reference'] = {k:v for k,v in summary['benchmark_reference'].items() if k!='summary_path'}
    return reviewed(projected), reviewed(detail)


def encode_asset(value):
    raw=encoded(value)
    if len(raw)>8000000:
        raise ValueError('Display object exceeds the existing Site JSON limit')
    return gzip.compress(raw, mtime=0)


def merge_snapshot(records, details, root, expected_sha256, expected_parent):
    """Build an additive draft only from a caller's pinned current readback.

    The external digest is a required review boundary, not an authentication
    mechanism. This function neither obtains nor asserts permission to activate.
    """
    raw = read_below(root, 'active-snapshot.json', limit=64*1024**2)
    if digest(raw) != expected_sha256:
        raise ValueError('Active readback receipt hash mismatch')
    receipt = _loads(raw)
    if (receipt.get('schema_version') != 'quantgraph-active-readback/v1'
            or receipt.get('source') != 'CURRENT_SITE_READBACK'
            or receipt.get('bundled_seed') is not False
            or receipt.get('active_batch') != expected_parent
            or not re.fullmatch(r'batch-[a-f0-9]{64}', expected_parent or '')):
        raise ValueError('A pinned current active readback is required; bundled seed is not a substitute')
    def read(path):
        if not path.startswith(('/data/', '/catalog/')):
            raise ValueError('Unsafe active asset path')
        ref = receipt['files'].get(path)
        if not ref:
            raise ValueError('Required active asset is not pinned: '+path)
        body = read_below(Path(root)/'assets', path[1:])
        if digest(body) != ref['sha256'] or len(body) != ref['bytes']:
            raise ValueError('Active asset hash/bytes mismatch')
        if body.startswith(b'\x1f\x8b'):
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
                expanded = stream.read(8*1024**2+1)
            if len(expanded)>8*1024**2:
                raise ValueError('Active asset expanded limit exceeded')
            return _loads(expanded), body
        return _loads(body), body
    manifest, _ = read('/data/manifest.json')
    catalog, _ = read('/catalog/manifest.json')
    merged = deepcopy(manifest)
    assets, chunks, result_refs = {}, {}, []
    for record, detail in zip(records, details, strict=True):
        rid, run, variant = record['id'], detail['run_id'], detail['variant_id']
        if detail['id'] != rid or not any(r['origin_run_id']==run and r['variant_id']==variant
                and r['manifest_sha256']==detail['lineage']['manifest_sha256'] for r in record['related_results']):
            raise ValueError('Display record/detail identity mismatch')
        kind = detail['lineage']['manifest_kind']
        if kind not in {MANIFEST_KIND, DERIVED_MANIFEST_KIND} or (kind == DERIVED_MANIFEST_KIND and (
                detail.get('manifest_kind') != kind or not any(r['origin_run_id']==run and r['variant_id']==variant
                    and r.get('manifest_kind')==kind for r in record['related_results']))):
            raise ValueError('Display record/detail manifest kind mismatch')
        binding = receipt['bindings'].get(rid)
        if not binding or not binding.get('entity_id') or not binding.get('definition_revision'):
            raise ValueError('Current entity/revision binding required')
        eid = binding['entity_id']
        catalog_detail, _ = read('/catalog/details/'+catalog[eid]['file']+'.json.gz')
        if (catalog_detail.get('entity_id') != eid or catalog_detail.get('definition_revision') != binding['definition_revision']
                or rid not in catalog_detail.get('source_native_ids', catalog_detail.get('knowledge',{}).get('source',{}).get('native_ids',[]))):
            raise ValueError('Current catalog binding differs from pinned source identity')
        shard = manifest.get('workscope_records',{}).get(rid)
        if not shard or manifest.get('workscope_entities',{}).get(eid) != rid:
            raise ValueError('Current workscope mapping required; legacy fallback is not silently rewritten')
        if shard not in chunks:
            chunks[shard] = read(shard)[0]
        previous = chunks[shard][rid]
        if (previous.get('definition_revision') != binding['definition_revision']
                or previous.get('research_scope',{}).get('entity_id') != eid):
            raise ValueError('Workscope record definition mismatch')
        key = digest((run+'\n'+variant).encode())[:24]
        path = '/data/implementations/'+key+'.json.gz'
        body = encode_asset(detail)
        old_key = manifest['details'].get(run+'|'+variant)
        # A pinned orphan object is immutable even when a partial index omitted
        # it. Re-registering identical bytes repairs navigation, never evidence.
        if path in receipt['files'] and read(path)[1] != body:
            raise ValueError('Existing immutable implementation path has different bytes')
        if old_key is not None:
            if old_key != key or read(path)[1] != body:
                raise ValueError('Existing immutable implementation has different bytes')
        else:
            assets[path] = body
            result_refs.append(dict(origin_run_id=run,variant_id=variant,
                manifest_sha256=detail['lineage']['manifest_sha256'],record_id=rid,
                detail_path=path,detail_sha256=digest(body)))
        chunks[shard][rid] = merge_record(previous, record)
        merged['details'][run+'|'+variant] = key
        if not any(r['run_id']==run for r in merged['runs']):
            merged['runs'].append(dict(run_id=run, manifest_kind=detail['lineage']['manifest_kind'],
                                      source_manifest_sha256=detail['lineage']['manifest_sha256']))
    for path, value in chunks.items():
        body = encode_asset(value)
        if body != read(path)[1]:
            assets[path] = body
    body = encoded(merged)
    if body != read('/data/manifest.json')[1]:
        assets['/data/manifest.json'] = body
    envelope = dict(schema_version='quantgraph-site-sync/v1',parent_batch_id=expected_parent,
        files=[dict(path=p,bytes=len(b),sha256=digest(b)) for p,b in sorted(assets.items())],entities=[],results=result_refs)
    return assets, envelope


def prepare(roots, output, *, registry=None, active_root=None, active_sha256=None, parent=None):
    output = Path(output)
    if output.exists() or shutil.disk_usage(output.parent).free <= RESERVE + 16*1024**2:
        raise ValueError('Use a new immutable directory with at least 5 GiB reserve')
    registry = registry or _loads(REGISTRY.read_bytes())
    if registry['schema_version'] != 'quantgraph-approved-lab-display-sources/v1':
        raise ValueError('Unsupported approved source registry')
    records, details = [], []
    seen, executions = set(), set()
    for entry in registry['records']:
        if entry['id'] in seen:
            raise ValueError('Duplicate stable source ID')
        seen.add(entry['id'])
        record, detail = project(entry, verified_source(roots[entry['group']], entry))
        identity=(detail['run_id'],detail['variant_id'])
        if identity in executions:
            raise ValueError('Duplicate immutable execution identity')
        executions.add(identity)
        records.append(record); details.append(detail)
    files = {'records.json':encoded(records)}
    for detail in details:
        key = digest((detail['run_id']+'\n'+detail['variant_id']).encode())[:24]
        files['implementations/'+key+'.json.gz'] = encode_asset(detail)
    status = dict(schema_version='quantgraph-lab-display-staging/v1',status='STAGED_NOT_IMPORTED',
                  ids=sorted(seen), records=len(records), implementations=len(details), new_execution_trials=0,
                  native_corpus_imported=False, deployed=False, ready_for_direct_site_sync=False,
                  active_merge_status='BLOCKED_CURRENT_ACTIVE_ROOT_ENTITY_REVISION_REQUIRED')
    if active_root is not None:
        assets, envelope = merge_snapshot(records, details, active_root, active_sha256, parent)
        files.update({'assets/'+p[1:]:b for p,b in assets.items()})
        files['site-sync-candidate.json'] = (canonical(envelope)+'\n').encode()
        status['active_merge_status'] = 'DRAFT_ONLY_PENDING_SOLE_SITE_WRITER_ACCEPTANCE'
        status['expected_parent'] = parent
    files['status.json'] = encoded(status)
    manifest = dict(schema_version='quantgraph-lab-display-file-manifest/v1',
        manifest_kind=MANIFEST_KIND, files={p:dict(sha256=digest(b),bytes=len(b)) for p,b in sorted(files.items())})
    kinds = sorted({d['lineage']['manifest_kind'] for d in details})
    if DERIVED_MANIFEST_KIND in kinds:
        manifest.update(manifest_kind='LAB_DISPLAY_ARTIFACT_INDEX', source_manifest_kinds=kinds)
    files['manifest.json'] = encoded(manifest)
    if shutil.disk_usage(output.parent).free <= RESERVE + sum(map(len,files.values())):
        raise ValueError('Insufficient 5 GiB reserve for the complete projection')
    output.mkdir()
    for p,raw in files.items():
        target=output/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    return status


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lab-batch009',type=Path)
    p.add_argument('--lab-dot004',type=Path)
    p.add_argument('--lab-root',action='append',default=[],metavar='GROUP=PATH')
    p.add_argument('--sources',type=Path,help='Explicit approved inventory; requires its independent SHA256')
    p.add_argument('--sources-sha256')
    p.add_argument('--ids',nargs='+',help='Explicit subset of IDs in the approved inventory')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--active-root',type=Path)
    p.add_argument('--active-sha256')
    p.add_argument('--parent-batch')
    a=p.parse_args()
    registry=_loads(REGISTRY.read_bytes())
    if a.sources:
        raw=read_below(a.sources.parent,a.sources.name)
        if digest(raw)!=a.sources_sha256:
            raise ValueError('Approved inventory independent hash required')
        registry=_loads(raw)
    if a.ids:
        if len(set(a.ids))!=len(a.ids) or not set(a.ids)<={e['id'] for e in registry['records']}:
            raise ValueError('Selected IDs must be unique members of the approved inventory')
        registry['records']=[e for e in registry['records'] if e['id'] in a.ids]
    roots={k:v for k,v in dict(batch009=a.lab_batch009,dot004=a.lab_dot004).items() if v is not None}
    for declaration in a.lab_root:
        group,sep,path=declaration.partition('=')
        if not sep or not group or not path or group in roots:
            raise ValueError('Each source group needs one explicit local root')
        roots[group]=Path(path)
    if not {e['group'] for e in registry['records']}<=roots.keys():
        raise ValueError('Explicit local root missing for an approved inventory group')
    print(json.dumps(prepare(roots,a.output,registry=registry,
        active_root=a.active_root,active_sha256=a.active_sha256,parent=a.parent_batch),ensure_ascii=False))


if __name__ == '__main__':
    main()

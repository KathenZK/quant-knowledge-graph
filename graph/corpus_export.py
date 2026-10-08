"""Deterministic metadata-only projection of one immutable delta screen run.

No source files, market data, strategy engine or inherited result is modified.
The origin protocol and every producer output are pinned independently.
"""
import argparse
import hashlib
import base64
import calendar
import gzip
import math
from datetime import datetime, timezone
from pathlib import PurePosixPath
from collections import Counter, defaultdict
import csv
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile

from quantgraph.graph.corpus_research import (
    ARTIFACTS, _csv, _digest, _fail, _index, _json, _loads, _read_file,
    _sha, _identifier, _prepare, _finite, _empty_period, build_manifest, FIDELITY_STATUS,
)

SCHEMA_V2 = 'private-strategy-screen-collection/v2'
SCHEMA_V3 = 'private-strategy-screen-collection/v3'
ATTACHMENTS_FILE = 'origin-attachments.json'
SUPPLEMENTS_FILE = 'presentation-supplements.json'
ORIGIN_NAMES = (
    'run_manifest.json', 'run_summary.json', 'strategy_metrics.json',
    'implemented_specs.json', 'implementation_status.json', 'daily_returns.csv.gz',
    'all_record_coverage.csv', 'strategy_metrics.csv', 'target_hashes.json',
)
ORIGIN_ARTIFACTS = {'origin__' + name: 'results' for name in ORIGIN_NAMES}
ORIGIN_ARTIFACTS['origin__protocol.json'] = 'results'
ANNOTATION_FILE = 'operator-annotations.json'
V2_ARTIFACTS = ARTIFACTS | ORIGIN_ARTIFACTS | {ANNOTATION_FILE: 'results'}
V3_ARTIFACTS = V2_ARTIFACTS | {ATTACHMENTS_FILE:'results', SUPPLEMENTS_FILE:'results'}


def _encoded(value):
    return (_json(value) + '\n').encode('utf-8')


def _csv_bytes(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


def _fidelity(value, annotation=None):
    proxy, hypothesis = value.get('asset_proxy'), value.get('parameter_hypothesis')
    extra = (annotation or {}).get('additional_hypothesis_reason')
    if extra:
        hypothesis = '\n'.join(v for v in [hypothesis, extra] if v)
    for reason in [proxy, hypothesis]:
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            _fail('Declared proxy/hypothesis must include an explicit nonempty reason')
    category = 'PROXY_HYPOTHESIS' if proxy and hypothesis else 'PROXY' if proxy else 'HYPOTHESIS' if hypothesis else 'STANDARDIZED'
    reason = '\n'.join(v for v in [proxy, hypothesis] if v)
    return dict(fidelity_class=category, fidelity_reason=reason)


def _merged_fidelity_declarations(metric, spec):
    """Missing/null metadata can never erase a positive deviation declaration."""
    output = {}
    for key in ['asset_proxy', 'parameter_hypothesis']:
        values = [value[key] for value in [spec, metric] if key in value and value[key] is not None]
        if any(not isinstance(v, str) or not v.strip() for v in values):
            _fail('Malformed fidelity declaration')
        unique = list(dict.fromkeys(values))
        if len(unique) > 1:
            _fail('Conflicting nonempty metric/spec fidelity reasons')
        output[key] = unique[0] if unique else None
    return output


def _relative_origin_name(name):
    if (not isinstance(name,str) or not name or len(name)>600 or "\\" in name
            or any(p in {"", ".", ".."} for p in name.split('/'))
            or PurePosixPath(name).is_absolute()):
        _fail('Unsafe relative origin artifact name')
    top_level={'frozen_input_manifest.json','protocol_amendments.json','protocol.json','producer_tests.json',
               'source_corpus_records.json','source_review.json','research_summaries.json','research_summaries.md',
               'DIA_corporate_actions.json','DIA_overnight_components.csv',
               'data_acceptance_contract.json','data_acceptance_result.json','data_gate_evaluations.json',
               'dependence_groups.json','environment.json','macro_unavailability_boundaries.json',
               'official_macro_gap_facts.json','original_records.json','pending_routes.json',
               'preperformance_freeze.json','price_quality.json','reference_xnys_sessions.json',
               'trade_clock_cost_qa.json','trade_ledger.csv','trade_ledger.csv.gz'}
    parts=PurePosixPath(name).parts
    ledger_files={'daily_book.csv.gz','trade_legs.csv.gz','scheduled_events.json','signal_decisions.json',
                  'daily_book_0bps.csv.gz','daily_book_5bps.csv.gz','daily_book_10bps.csv.gz','daily_book_25bps.csv.gz',
                  'daily_book_common_endpoint.csv.gz','daily_book_extra_session.csv.gz','first_blocked_decision.json'}
    ledger=(len(parts)==3 and parts[0]=='ledgers' and parts[2] in ledger_files)
    if ledger:_identifier(parts[1])
    opaque_input=(len(parts)==2 and parts[0]=='inputs' and parts[1].endswith('.csv'))
    opaque_code=(len(parts)==2 and parts[0]=='code' and parts[1].endswith(('.py','.json','.log')))
    # Code, input and ledger attachments are retained inert bytes only, never imported/executed.
    opaque_supplement=(len(parts)==2 and ((parts[0] in {'orders','decisions','ledgers'} and parts[1].endswith('.csv.gz'))
        or (parts[0]=='qa' and parts[1].endswith(('.json','.log')))
        or (parts[0]=='research_notes' and parts[1].endswith('.md'))
        or (parts[0]=='signals' and parts[1].endswith(('.csv','.json')))
        or (parts[0]=='sources' and parts[1].endswith(('.txt','.html','.json')))))
    allowed = name in top_level or ledger or opaque_input or opaque_code or opaque_supplement or (name.startswith(('returns/','trades/','per_variant/')) and name.count('/')==1)
    if not allowed:
        _fail('Unsupported additional origin artifact type')
    if name.startswith(('returns/','trades/')) and not name.endswith('.csv.gz'):
        _fail('Additional return/trade artifact must be gzip CSV')
    if name.startswith('per_variant/') and not name.endswith('.json'):
        _fail('Additional metric artifact must be JSON')
    return name


def _origin_file(root,name):
    _relative_origin_name(name)
    current=Path(root)
    for part in PurePosixPath(name).parts:
        current=current/part
        if current.is_symlink():
            _fail('Origin attachments cannot traverse symlinks')
    if not current.resolve().is_relative_to(Path(root).resolve()):
        _fail('Origin attachment escapes root')
    return _read_file(current)


def _attachment_bytes(blobs):
    value=_loads(blobs[ATTACHMENTS_FILE])
    if set(value)!={'schema_version','artifacts'} or value['schema_version']!='retained-origin-attachments/v1' or not isinstance(value['artifacts'],dict):
        _fail('Invalid origin attachments contract')
    if len(value['artifacts'])>5000:
        _fail('Too many origin attachments')
    out={};total=0
    for name,ref in value['artifacts'].items():
        _relative_origin_name(name)
        if not isinstance(ref,dict) or set(ref)!={'sha256','bytes','base64'}:
            _fail('Invalid attachment reference')
        try:data=base64.b64decode(ref['base64'],validate=True)
        except (ValueError,TypeError):_fail('Invalid attachment encoding')
        total+=len(data)
        if total>64*1024*1024:_fail('Origin attachment decoded budget exceeded')
        if type(ref['bytes']) is not int or ref['bytes']!=len(data) or _sha(ref['sha256'])!=_digest(data):
            _fail('Origin attachment byte/hash mismatch')
        out[name]=data
    return out


def _daily_csv(blob):
    with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
        raw=stream.read(256*1024*1024+1)
    if len(raw)>256*1024*1024:_fail('Expanded return file exceeds limit')
    rows=_csv(raw)
    for row in rows:
        value=row.get('date')
        if not value:_fail('Daily return CSV requires date')
        if len(value)==10:
            try:datetime.strptime(value,'%Y-%m-%d')
            except ValueError:_fail('Invalid daily observation date')
        else:
            try:dt=datetime.fromisoformat(value.replace('Z','+00:00'))
            except ValueError:_fail('Invalid native daily timestamp')
            if dt.tzinfo is None or dt.utcoffset().total_seconds()!=0 or (dt.hour,dt.minute,dt.second,dt.microsecond)!=(0,0,0,0):
                _fail('Native daily observations must be UTC midnight, not silently date-truncated')
            row['date']=dt.date().isoformat()
    return rows


def _normalize_daily_csv(blob):
    out=io.BytesIO()
    with gzip.GzipFile(fileobj=out,mode='wb',mtime=0) as stream:stream.write(_csv_bytes(_daily_csv(blob)))
    return out.getvalue()


def _native_fields(metric,spec):
    """Explicit metadata aliases, with original declarations retained separately."""
    if not isinstance(spec.get('assets'),list) and spec.get('instrument') in {'spot','perpetual'}:
        unit = spec.get('cash_unit')
        metric_cash_alias = ('cash_unit' not in spec and spec.get('instrument') == 'spot'
                             and isinstance(spec.get('symbol'), str)
                             and spec['symbol'].endswith('USDT')
                             and metric.get('cash_asset') == 'USDT_CASH')
        if metric_cash_alias:
            unit = 'USDT'
        if metric.get('assets')!=[spec.get('symbol')] or unit!='USDT' or metric.get('cash_asset')!='USDT_CASH':
            _fail('Native crypto symbol/cash contract does not reconcile')
        spec.update(assets=[spec['symbol']],cash_asset='USDT_CASH')
        spec['native_field_projection']='assets from source symbol; cash_asset from explicit USDT cash_unit; no USD substitution'
        if metric_cash_alias:
            spec['cash_unit'] = 'USDT'
            spec['native_field_projection'] = ('assets from source symbol; missing spot cash_unit from explicit '
                'original metric USDT_CASH with matching USDT symbol; metadata enrichment only, no USD substitution')
    price_assets = spec.get('price_assets')
    signal_assets = spec.get('signal_only_assets')
    if isinstance(price_assets, list) and isinstance(signal_assets, list):
        if (not all(isinstance(a, str) for a in [*price_assets, *signal_assets])
                or len(set(price_assets)) != len(price_assets)
                or len(set(signal_assets)) != len(signal_assets)):
            _fail('Price and signal-only asset declarations conflict')
        overlap=set(price_assets) & set(signal_assets)
        if overlap:
            if set(spec.get('assets',[]))!=set(price_assets)|set(signal_assets) or metric.get('signal_only_assets')!=signal_assets or metric.get('assets')!=spec.get('assets'):
                _fail('Overlapping signal/price declarations require identical explicit producer metadata')
            spec['signal_role_warning']='Producer price_assets and signal_only_assets overlap: '+', '.join(sorted(overlap))+'. Retained declarations are not an independently certified traded-only partition.'
            metric['signal_role_warning']=spec['signal_role_warning']
        if spec.get('assets') == price_assets and signal_assets and not overlap:
            if not isinstance(metric.get('assets'), list) or set(metric['assets']) != set(price_assets):
                _fail('Signal-only universe enrichment cannot alter traded assets')
            spec['assets'] = [*price_assets, *signal_assets]
            spec['universe_membership_projection'] = 'Original price_assets plus separately explicit signal_only_assets; traded-price binding unchanged'
    if (isinstance(price_assets,list) and isinstance(signal_assets,list)
            and metric.get('assets')==spec.get('assets')
            and set(metric['assets'])==set(price_assets)|set(signal_assets)
            and set(metric['assets'])!=set(price_assets)):
        metric['original_metric_universe_assets']=deepcopy(metric['assets'])
        metric['assets']=deepcopy(price_assets)
        metric['universe_membership_projection']='Price assets from explicit producer price_assets; original combined price/signal array retained separately.'
    if spec.get('kind') == 'cny_daily_etf' or metric.get('kind') == 'cny_daily_etf':
        if (spec.get('kind') != 'cny_daily_etf' or metric.get('kind') != 'cny_daily_etf'
                or spec.get('account_currency') != 'CNY' or metric.get('account_currency') != 'CNY'
                or spec.get('cash_asset') != 'CASH' or metric.get('cash_asset') != 'CASH'
                or spec.get('execution_calendar') != 'XSHG' or metric.get('clock') != 'Asia/Shanghai XSHG'
                or metric.get('cash_basis') != 'zero-yield CNY'
                or metric.get('assets') != spec.get('assets')
                or not isinstance(spec.get('assets'), list) or not spec['assets']
                or any(not isinstance(a, str) or not a.endswith('.SS') for a in spec['assets'])):
            _fail('CNY exchange-clock/cash/asset contract does not reconcile')
    for period in metric.get('periods',{}).values():
        if 'observations' not in period and 'n' in period:period['observations']=period['n']
        if 'annual_volatility' not in period and 'annual_vol' in period:period['annual_volatility']=period['annual_vol']
    return metric,spec


def _native_capital_tail(metric, window, rows, attachments):
    """Accept missing trailing returns only with a reconciled exhaustion ledger.

    This verifies retained accounting evidence; it does not rerun a strategy or
    certify exchange margin rules, source market data, or historic fill quality.
    """
    dates=[r['date'] for r in rows]
    if any(a>=b for a,b in zip(dates,dates[1:])):
        _fail('Native window dates must be strictly increasing')
    missing=[r for r in rows if r.get('net_return')=='']
    state=window.get('capital_state')
    if not missing and not state:
        return rows, None
    if not isinstance(state,dict):
        _fail('Missing native returns require explicit capital-state evidence')
    if state.get('state')=='POSITIVE_TERMINAL_EQUITY':
        if missing or state.get('capital_extinguished_at') is not None or state.get('events'):
            _fail('Positive capital state cannot conceal missing returns or events')
        if math.prod(1+float(r['net_return']) for r in rows)<=0:
            _fail('Positive capital state differs from retained returns')
        return rows, None
    if state.get('state')!='MODEL_CAPITAL_EXTINGUISHED':
        _fail('Unsupported native capital state')
    events=state.get('events')
    if not isinstance(events,list) or len(events)!=1 or not isinstance(events[0],dict):
        _fail('Native exhaustion requires one terminal capital event')
    event=events[0]
    if (event.get('event_type')!='capital_extinguishment_no_exchange_fill'
            or event.get('executed_exit_trade') is not False
            or state.get('capital_extinguished_at')!=event.get('at')):
        _fail('Capital reset cannot masquerade as an exchange liquidation')
    try: at=datetime.fromisoformat(event['at'])
    except (ValueError,TypeError):_fail('Invalid capital-event time')
    if at.tzinfo is None or at.utcoffset().total_seconds()!=0:
        _fail('Native capital-event time must be UTC')
    day=at.date().isoformat();kept=[];equity=1.;zero_day=None
    for row in rows:
        if row.get('net_return')=='':
            if zero_day is None or row['date']<=day:
                _fail('A missing native return precedes capital exhaustion')
            continue
        if zero_day is not None:
            _fail('Native returns cannot resume after capital exhaustion')
        number=float(row['net_return'])
        if not math.isfinite(number) or number < -1:_fail('Invalid native return')
        equity*=1+number;kept.append(row)
        if equity==0:zero_day=row['date']
    if zero_day!=day or not kept or kept[-1]['date']!=day:
        _fail('Capital event does not match the first zero-equity day')
    name='trades/'+metric['variant_id']+'__w'+str(window['window_id'])+'.csv.gz'
    if name not in attachments:_fail('Capital tail requires the retained trade log')
    with gzip.GzipFile(fileobj=io.BytesIO(attachments[name])) as stream:
        raw=stream.read(256*1024*1024+1)
    if len(raw)>256*1024*1024:_fail('Capital trade log exceeds expansion limit')
    trades=_csv(raw) if raw.strip() else []
    def event_time(value):
        try: stamp=datetime.fromisoformat(value)
        except (ValueError,TypeError):_fail('Invalid capital ledger trade time')
        if stamp.tzinfo is None or stamp.utcoffset().total_seconds()!=0:
            _fail('Capital ledger trade times must be UTC')
        return stamp
    first_time=event_time(window.get('evaluation_start',rows[0]['date']+'T00:00:00+00:00'))
    # The capital event names its containing five-minute bar. A final closing
    # fill can legitimately carry the following bar-boundary timestamp.
    from datetime import timedelta
    last_time=at+timedelta(minutes=5)
    book=1.;fees=0.;funding=0.
    for trade in trades:
        if not first_time<=event_time(trade.get('entry_time'))<=event_time(trade.get('exit_time'))<=last_time:
            _fail('Capital trade log extends beyond its valid execution interval')
        qty,entry,exit_price,pnl,entry_fee,exit_fee=[float(trade[k]) for k in
            ['quantity','entry_price','exit_price','gross_pnl','entry_cost','exit_cost']]
        if (not all(math.isfinite(x) for x in [qty,entry,exit_price,pnl,entry_fee,exit_fee])
                or entry<=0 or exit_price<=0 or min(entry_fee,exit_fee)<0
                or not _close(qty*(exit_price-entry),pnl)):
            _fail('Capital trade PnL or fee arithmetic does not reconcile')
        book+=pnl-entry_fee-exit_fee;fees+=entry_fee+exit_fee
        funding+=float(trade.get('funding_paid',0))
    active=event.get('active_position');quantity=float(event['quantity_before_model_reset'])
    mark=float(event['trade_close_mark']);unclosed=float(event['unclosed_marked_pnl'])
    if active is not None:
        if not isinstance(active,dict):_fail('Invalid active capital-event position')
        if not first_time<=event_time(active.get('entry_time'))<=last_time:
            _fail('Active capital position was not entered within its window')
        entry=float(active['entry_price']);entry_fee=float(active['entry_cost'])
        if (entry<=0 or mark<=0 or entry_fee<0 or quantity==0
                or not _close(quantity,active['quantity'])
                or not _close(quantity*(mark-entry),unclosed)):
            _fail('Unclosed capital-event position does not reconcile')
        book+=unclosed-entry_fee;fees+=entry_fee
        funding+=float(active.get('funding_paid',0))
    elif quantity!=0 or unclosed!=0:
        _fail('Capital event lacks its unclosed position evidence')
    daily_funding=sum(float(r['funding_paid']) for r in rows)
    daily_fees=sum(float(r['fees']) for r in rows)
    raw_events=[float(r['trade_event']) for r in rows]
    if any(not math.isfinite(x) or x<0 or x!=int(x) for x in raw_events):
        _fail('Invalid native trade-event count')
    if (not _close(funding,daily_funding) or not _close(fees,daily_fees)
            or sum(raw_events)!=2*len(trades)+int(active is not None)):
        _fail('Native capital funding, fees or events do not reconcile')
    before=book-daily_funding;cap=float(event['model_loss_cap_adjustment'])
    if (before>1e-8 or cap<0 or not _close(before,event['nav_before_model_loss_cap'])
            or not _close(before-unclosed,event['wallet_balance_before_model_cap'])
            or not _close(cap,-min(0,before)) or not _close(before+cap,equity)):
        _fail('Native capital loss cap does not reconcile with the trade ledger')
    return kept, dict(status='RETAINED_ACCOUNTING_RECONCILED',capital_extinguished_at=event['at'],
        excluded_missing_tail_rows=len(missing),last_valid_return_date=day,
        evidence_scope='Retained returns, completed trades, fees, funding and non-trade model reset only',
        new_economic_trials=0,original_return_bytes_changed=False)


def _native_windows(metric,attachments,period_bounds=None):
    retained=[]
    for window in metric.get('windows',[]):
        path=window.get('daily_returns_path')
        if path not in attachments or _sha(window.get('daily_returns_sha256'))!=_digest(attachments[path]):
            _fail('Native window returns lack verified origin attachment')
        raw_rows=_daily_csv(attachments[path]);rows,capital_validation=_native_capital_tail(metric,window,raw_rows,attachments)
        observations=[];equity=peak=1.;curve=[]
        for row in rows:
            number=float(row['net_return'])
            if not math.isfinite(number) or number < -1:_fail('Invalid native window return')
            day=row['date']
            if observations and day<=observations[-1][0]:_fail('Native window dates must be strictly increasing')
            observations.append([day,number]);equity*=1+number;peak=max(peak,equity)
            curve.append(dict(date=day,equity=equity,drawdown=equity/peak-1))
        if not curve:_fail('Empty native execution window')
        for name,period in window.get('periods',{}).items():
            _observations_for_period(rows,period)
            if capital_validation and period_bounds and name in period_bounds:
                start,end=period_bounds[name]
                if len([r for r in rows if start<=r['date']<=end])!=period.get('observations',period.get('n')):
                    _fail('Capital-window period count differs from its declared scope')
        if len(curve)>1200:
            ids={0,len(curve)-1,min(range(len(curve)),key=lambda i:curve[i]['drawdown']),max(range(len(curve)),key=lambda i:curve[i]['equity'])}
            ids.update(i*(len(curve)-1)//1195 for i in range(1196));curve=[curve[i] for i in sorted(ids)]
        retained.append(dict(window_id=str(window['window_id']),curve=curve,curve_meta=dict(initial_equity=1,observations=len(observations),start=observations[0][0],end=observations[-1][0],source_return_sha256=_digest(attachments[path]),independent_window=True,gaps_not_connected=True),source_window=deepcopy(window)))
        if window.get('capital_state') is not None:
            retained[-1]['capital_state']=deepcopy(window['capital_state'])
        if capital_validation:
            if window.get('presentation_periods',window['periods'])!=window['periods']:
                _fail('Inline capital presentation periods must match verified period evidence')
            retained[-1].update(capital_state_validation=capital_validation,presentation_periods=deepcopy(window['periods']))
            retained[-1]['curve_meta'].update(raw_rows=len(raw_rows),excluded_missing_tail_rows=capital_validation['excluded_missing_tail_rows'],scope='valid_returns_through_capital_exhaustion')
            if str(metric.get('primary_window_id'))==str(window['window_id']):
                if metric.get('capital_state')!=window['capital_state'] or metric.get('presentation_periods',window['periods'])!=window['periods']:
                    _fail('Primary capital state or presentation periods differ from its window')
                metric['capital_state_validation']=capital_validation
                metric['presentation_periods']=deepcopy(window['periods'])
    if retained:
        primary=str(metric.get('primary_window_id'))
        if len({w['window_id'] for w in retained})!=len(retained) or primary not in {w['window_id'] for w in retained}:
            _fail('Native primary/window IDs do not reconcile')
        metric['retained_windows']=retained
        if metric.get('kind') == 'cny_daily_etf':
            if metric.get('account_currency') != 'CNY' or metric.get('clock') != 'Asia/Shanghai XSHG' or metric.get('cash_basis') != 'zero-yield CNY':
                _fail('CNY retained windows require explicit currency and exchange clock')
            metric['return_clock']='Asia/Shanghai XSHG session closes; CNY account; zero-yield CNY idle cash'
        else:
            metric['return_clock']='UTC calendar days; native-bar execution; idle USDT'
    return metric


def _close(a,b):
    return math.isclose(float(a),float(b),rel_tol=1e-7,abs_tol=1e-8)


def _observations_for_period(rows,period):
    count=period.get('observations',period.get('n'))
    if type(count) is not int or count<0:_fail('Native period requires observationcount')
    if count==0:
        _empty_period(period)
        return []
    start,end=period.get('start'),period.get('end')
    if not isinstance(start,str) or not isinstance(end,str) or start>end:_fail('Native period dates missing/reversed')
    chosen=[r for r in rows if start<=r['date']<=end]
    if len(chosen)!=count or chosen[0]['date']!=start or chosen[-1]['date']!=end:_fail('Native period observations differ from window')
    if not _close(math.prod(1+float(r['net_return']) for r in chosen)-1,period['total_return']):_fail('Native window period return mismatch')
    return chosen


def _apply_supplements(blobs,source,origin,original_metrics,metrics,attachments):
    value=_loads(blobs[SUPPLEMENTS_FILE])
    if set(value)!={'schema_version','capital_overlay','ledger_supplement'} or value['schema_version']!='retained-presentation-supplements/v1':
        _fail('Invalid presentation supplement contract')
    digest=_digest(source['run_manifest.json']);by_variant={m['variant_id']:m for m in metrics}
    window_map={(v,str(w['window_id'])):w for v,m in original_metrics.items() for w in m.get('windows',[])}
    for obj in [value['capital_overlay'],value['ledger_supplement']]:
        if obj is not None and (obj.get('origin_run_id')!=origin['run_id'] or obj.get('origin_manifest_sha256')!=digest):
            _fail('Presentation supplement origin binding mismatch')
    ledger=value['ledger_supplement'];capital=value['capital_overlay'];verified_capital={}
    if ledger is not None:
        if ledger.get('schema_version')!='terminal-trade-ledger-supplement/v1' or ledger.get('new_return_trials')!=0 or ledger.get('original_files_changed') is not False:
            _fail('Unsupported terminal ledger supplement')
        seen=set()
        for row in ledger.get('windows',[]):
            key=(row['variant_id'],str(row['window_id']))
            if key in seen or key not in window_map:_fail('Unknown/duplicate ledgerwindow')
            seen.add(key);w=window_map[key];ret=_daily_csv(attachments[w['daily_returns_path']]);trade_name='trades/'+key[0]+'__w'+key[1]+'.csv.gz'
            if trade_name not in attachments or _sha(row['origin_trade_log_sha256'])!=_digest(attachments[trade_name]):_fail('Ledger original trade hash mismatch')
            with gzip.GzipFile(fileobj=io.BytesIO(attachments[trade_name])) as stream:raw=stream.read(256*1024*1024+1)
            if len(raw)>256*1024*1024:_fail('Trade log expansion limit')
            trades=_csv(raw) if raw.strip() else []
            end=row.get('terminal_trade_row');exhaust=row.get('non_trade_capital_event')
            if end and exhaust:_fail('Window cannot terminal-close and extinguishcapital')
            all_trades=trades+([end] if end else [])
            if (row.get('pass') is not True or row.get('original_completed_log_trades')!=len(trades)
                    or row.get('completed_log_trades_after_supplement')!=len(all_trades)):
                _fail('Supplemented ledger reported trade counts do not reconcile')
            book=1.;events=2*len(all_trades)
            for trade in all_trades:
                qty=float(trade['quantity']);ep=float(trade['entry_price']);xp=float(trade['exit_price']);pnl=float(trade['gross_pnl']);entryfee=float(trade['entry_cost']);exitfee=float(trade['exit_cost'])
                if ep<=0 or xp<=0 or entryfee<0 or exitfee<0 or not _close(qty*(xp-ep),pnl):_fail('Trade PnL/fee arithmetic mismatch')
                book+=pnl-entryfee-exitfee
            book-=sum(float(r.get('funding_paid',0)) for r in ret)
            if end and end.get('reason')!='terminal_liquidation':_fail('Unknown terminal trade type')
            equity=1.;zero_day=None
            for rr in ret:
                equity*=1+float(rr['net_return'])
                if equity==0 and zero_day is None:zero_day=rr['date']
            if exhaust:
                if exhaust.get('event_type')!='capital_extinguishment_no_market_fill' or exhaust.get('executed_exit_trade') is not False or float(exhaust.get('exit_fee_charged',-1))!=0:
                    _fail('Capital event cannot masquerade as exchangeexecution')
                day=datetime.fromisoformat(exhaust['at']).date().isoformat()
                if zero_day!=day:_fail('Reported capital extinction day differs from curve')
                qty=float(exhaust['quantity_before_model_reset']);ep=float(exhaust['entry_price']);mark=float(exhaust['trade_close_mark']);pnl=float(exhaust['unclosed_marked_pnl']);fee=float(exhaust['entry_cost']);cap=float(exhaust['model_loss_cap_adjustment'])
                if ep<=0 or mark<=0 or fee<0 or cap<0 or not _close(qty*(mark-ep),pnl):_fail('Invalid non-trade capitalmark')
                before=book+pnl-fee
                if before>1e-8 or not _close(before,exhaust['nav_before_model_loss_cap']) or not _close(cap,-min(0,before)):_fail('Capital loss cap does not reconcile')
                book=before+cap;events+=1;verified_capital[key]=exhaust
            elif zero_day is not None:_fail('Zero equity requires explicit capital-state evidence')
            observed_events=sum(int(float(r['trade_event'])) for r in ret)
            if events!=observed_events or events!=row['trade_events_with_terminal'] or not _close(book,equity) or not _close(book,row['ledger_final_nav']) or not _close(equity,row['stored_returns_final_nav']):_fail('Supplemented ledger events/NAV mismatch')
        if seen!=set(window_map):_fail('Ledger supplement must cover all retainedwindows')
    if capital is not None:
        if capital.get('schema_version')!='capital-state-metric-overlay/v1':_fail('Unsupported capitaloverlay')
        seen=set()
        for overlay in capital.get('overlays',[]):
            key=(overlay['variant_id'],str(overlay['window_id']))
            if key in seen or key not in verified_capital:_fail('Capital view lacks verified nontradeledger')
            seen.add(key);event=verified_capital[key]
            if overlay.get('origin_run_id')!=origin['run_id'] or overlay.get('economic_trials_added')!=0 or overlay['capital_extinguished_at']!=event['at']:_fail('Capital view origin/state mismatch')
            metric_path='per_variant/'+key[0]+'.json'
            if metric_path not in attachments or _sha(overlay['original_metric_file_sha256'])!=_digest(attachments[metric_path]):_fail('Capital view originalmetric hash mismatch')
            w=window_map[key];rows=_daily_csv(attachments[w['daily_returns_path']]);day=datetime.fromisoformat(event['at']).date().isoformat();overrides=overlay['presentation_period_overrides']
            if set(overrides)!=set(w['periods']):_fail('Capital period coverage mismatch')
            for name,period in w['periods'].items():
                proposed=overrides[name];selected=_observations_for_period(rows,period)
                valid=[r for r in selected if r['date']<=day]
                if not valid:
                    if proposed.get('status')!='no_positive_equity' or proposed.get('observations')!=0 or proposed.get('n')!=0:_fail('Post-extinctionperiod mustbe N/A')
                    if any(proposed.get(k) is not None for k in ['total_return','cagr','sharpe','max_drawdown','annual_volatility']):_fail('Post-extinctionperiod cannotclaimflatreturn')
                else:
                    if proposed.get('n',proposed.get('observations'))!=len(valid) or proposed.get('start')!=valid[0]['date'] or proposed.get('end')!=valid[-1]['date']:_fail('Capitalvalidsample dates/count mismatch')
                    numbers=[float(r['net_return']) for r in valid];wealth=1.;peak=1.;dd=0.
                    for number in numbers:wealth*=1+number;peak=max(peak,wealth);dd=min(dd,wealth/peak-1)
                    if not _close(wealth-1,proposed['total_return']) or not _close(dd,proposed['max_drawdown']):_fail('Capitalpresentation compoundedreturn/drawdown mismatch')
                    annual=float(period.get('annualization',365.25));mean=sum(numbers)/len(numbers);sd=math.sqrt(sum((x-mean)**2 for x in numbers)/(len(numbers)-1)) if len(numbers)>1 else 0.;cagr=wealth**(annual/len(numbers))-1 if wealth>0 else -1.
                    if not _close(cagr,proposed['cagr']) or not _close(sd*math.sqrt(annual),proposed.get('annual_volatility',proposed.get('annual_vol'))):_fail('Capitalpresentation annualizedstatistics mismatch')
                    if sd and not _close(mean/sd*math.sqrt(annual),proposed['sharpe']):_fail('Capitalpresentation Sharpe mismatch')
            state=dict(capital_extinguished_at=event['at'],state='MODEL_CAPITAL_EXTINGUISHED',event_type=event['event_type'],timestamp_interpretation='Reported5minbar label, not certifiedintrabarfilltime',source_original_metric_sha256=overlay['original_metric_file_sha256'],scenario_state_scope='Baseline only; cost/lag scenario survival not independentlyestablished')
            metric=by_variant[key[0]]
            for rw in metric.get('retained_windows',[]):
                if rw['window_id']==key[1]:rw.update(capital_state=state,presentation_periods=deepcopy(overrides))
            if str(metric.get('primary_window_id'))==key[1]:metric.update(capital_state=state,presentation_periods=deepcopy(overrides))
        if seen!=set(verified_capital):_fail('Every capitalextinction requires a presentationoverlay')
    elif verified_capital:_fail('Capital-extinguishedruns need matching presentationoverlay')
    return dict(terminal_ledger_present=ledger is not None,capital_states=len(verified_capital),supplement_sha256=_digest(blobs[SUPPLEMENTS_FILE]))


def derive(blobs):
    """Derive only declared metadata; verify origin manifests before projection."""
    advanced=ATTACHMENTS_FILE in blobs
    attachments=_attachment_bytes(blobs) if advanced else {}
    source = {name: blobs['origin__' + name] for name in ORIGIN_NAMES}
    origin = _loads(source['run_manifest.json'])
    run_id = _identifier(origin['run_id'])
    results = origin.get('result_hashes')
    legacy=advanced and results is None and 'normalized_data_sha256' in origin
    required=set(ORIGIN_NAMES)-{'run_manifest.json'}
    missing_auxiliary=[]
    if advanced and isinstance(results,dict) and 'target_hashes.json' not in results:
        marker=_encoded(dict(schema_version='absent-origin-auxiliary/v1',artifact='target_hashes.json',origin_manifest_sha256=_digest(source['run_manifest.json']),status='NOT_INCLUDED_OR_DECLARED_IN_RECEIVED_ORIGIN',not_a_target_hash=True))
        if source['target_hashes.json']!=marker:_fail('Missing target hashes require exact origin-bound absence receipt')
        required.remove('target_hashes.json');missing_auxiliary.append('target_hashes.json')
    if advanced and isinstance(results,dict) and 'strategy_metrics.csv' not in results:
        marker=_encoded(dict(schema_version='absent-origin-auxiliary/v1',artifact='strategy_metrics.csv',origin_manifest_sha256=_digest(source['run_manifest.json']),status='NOT_INCLUDED_OR_DECLARED_IN_RECEIVED_ORIGIN',not_an_original_csv=True))
        if source['strategy_metrics.csv']!=marker:_fail('Missing metrics CSV requires exact origin-bound absence receipt')
        required.remove('strategy_metrics.csv');missing_auxiliary.append('strategy_metrics.csv')
    if legacy:
        expected_legacy={'protocol_amendments.json'} if origin.get('protocol_amendments_sha256') else set()
        if set(attachments)!=expected_legacy or _sha(origin.get('implementation_specs_sha256'))!=_digest(source['implemented_specs.json']):
            _fail('Legacy origin spec digest/attachment contract does not reconcile')
        if expected_legacy and _sha(origin['protocol_amendments_sha256'])!=_digest(attachments['protocol_amendments.json']):_fail('Legacy protocol amendment hash mismatch')
    else:
        expected=required|set(attachments)
        if not isinstance(results,dict) or set(results)!=(expected if advanced else required):
            _fail('Origin manifest must pin exactly the supported producer outputs')
        for name,digest in results.items():
            content=source[name] if name in source else attachments[name]
            if _sha(digest)!=_digest(content):_fail('Origin artifact digest mismatch: '+name)
    protocol_blob = blobs['origin__protocol.json']
    if _sha(origin['protocol_sha256']) != _digest(protocol_blob):
        _fail('Origin protocol digest mismatch')
    protocol = _loads(protocol_blob)
    original_summary = _loads(source['run_summary.json'])
    if original_summary.get('run_id') != run_id:
        _fail('Origin summary belongs to another run')
    original_metrics = _index(_loads(source['strategy_metrics.json']), lambda x:x['variant_id'], 'origin metrics')
    if advanced:
        for vid,m in original_metrics.items():
            name='per_variant/'+vid+'.json'
            if name in attachments and _loads(attachments[name])!=m:_fail('Per-variant/aggregate metric declarations conflict')
    original_specs = _index(_loads(source['implemented_specs.json']), lambda x:x.get('variant_id', x['id']), 'origin specifications')
    raw_statuses=_loads(source['implementation_status.json'])
    def status_identity(row):
        if row.get('variant_id') is not None:return row['variant_id']
        if not isinstance(row.get('status'),str) or row['status'].startswith('tested'):
            _fail('Executed status must bind an explicit variant')
        return _identifier(row['id'])+'@record_scope_unexecuted_status'
    statuses = _index(raw_statuses, status_identity, 'origin implementation statuses')
    if not original_metrics or not original_specs:
        _fail('Empty origin execution cannot be imported as completed evidence')
    if not set(original_metrics) <= set(original_specs) or not set(original_metrics) <= set(statuses):
        _fail('Origin execution identities do not reconcile')
    annotations = _loads(blobs[ANNOTATION_FILE])
    if (not {'schema_version', 'run_id', 'implementations'} <= set(annotations)
            or not set(annotations) <= {'schema_version', 'run_id', 'implementations', 'description'}
            or annotations['schema_version'] != 'strategy-screen-annotations/v1'
            or annotations['run_id'] != run_id or not isinstance(annotations['implementations'], dict)
            or not set(annotations['implementations']) <= set(original_specs)):
        _fail('Operator annotations must bind known implementations of this origin run')
    for note in annotations['implementations'].values():
        if not isinstance(note, dict) or not note or not set(note) <= {'additional_hypothesis_reason', 'deep_validation_scope'}:
            _fail('Unsupported operator annotation')
        if 'additional_hypothesis_reason' in note and (not isinstance(note['additional_hypothesis_reason'], str) or not note['additional_hypothesis_reason'].strip()):
            _fail('Hypothesis annotation requires an explicit reason')
        if 'deep_validation_scope' in note and note['deep_validation_scope'] != 'FIXED_ORDER_PATH_DELAY':
            _fail('Unknown deep-validation annotation scope')
    verification = _loads(blobs['source_verification.json'])
    audit = _index([_loads(line) for line in blobs['record_audit.jsonl'].splitlines() if line.strip()], lambda x:x['id'], 'audit')
    if len(audit) != verification['input']['row_count']:
        _fail('Origin export audit corpus count does not reconcile')
    inherited = _index(_csv(source['all_record_coverage.csv']), lambda x:x['id'], 'origin cumulative coverage')
    if set(inherited) != set(audit):
        _fail('Origin coverage and requested audit corpus identities differ')
    for identity, record in inherited.items():
        if record['name'] != audit[identity]['名称'] or record['source_url'] != audit[identity]['source_url']:
            _fail('Origin source record does not match requested audit corpus')
    specs = []
    for variant_id, original in original_specs.items():
        spec = deepcopy(original)
        if advanced and variant_id in original_metrics:
            _,spec=_native_fields(deepcopy(original_metrics[variant_id]),spec)
        if original.get('origin_run_id', run_id) != run_id or original['id'] not in audit:
            _fail('Origin specification belongs to another run or corpus')
        declared = _merged_fidelity_declarations(original_metrics.get(variant_id, {}), original)
        enriched = dict(origin_run_id=run_id, origin_protocol_sha256=origin['protocol_sha256'], **_fidelity(declared, annotations['implementations'].get(variant_id)))
        for key, value in enriched.items():
            if key in original and original[key] != value:
                _fail('Conflicting producer fidelity/origin declaration')
        spec.update(enriched)
        specs.append(spec)
    specs_blob = _encoded(specs)
    metrics, deep = [], []
    by_record = defaultdict(list)
    for variant_id, original in original_metrics.items():
        if original.get('run_id') != run_id or original.get('origin_run_id', run_id) != run_id:
            _fail('Mixed-origin results cannot be relabeled into a single run')
        spec = original_specs[variant_id]
        if original['id'] != spec['id']:
            _fail('Origin metric/spec identity differs')
        if statuses[variant_id]['id'] != original['id'] or not statuses[variant_id]['status'].startswith('tested'):
            _fail('Origin result is not supported by an executed status')
        declared = _merged_fidelity_declarations(original, spec)
        annotation = annotations['implementations'].get(variant_id, {})
        metadata = dict(origin_run_id=run_id, origin_protocol_sha256=origin['protocol_sha256'],
            protocol_sha256=origin['protocol_sha256'], implementation_specs_sha256=_digest(specs_blob), **_fidelity(declared, annotation))
        executed_status = statuses[variant_id]['status']
        status_classes = {
            'tested': set(FIDELITY_STATUS),
            'tested_proxy': {'PROXY', 'PROXY_HYPOTHESIS'},
            'tested_hypothesis': {'HYPOTHESIS', 'PROXY_HYPOTHESIS'},
            'tested_proxy_hypothesis': {'PROXY_HYPOTHESIS'},
            'tested_proxy_hypothesis_truncated_at_macro_unavailability': {'PROXY_HYPOTHESIS'},
        }
        if executed_status not in status_classes or metadata['fidelity_class'] not in status_classes[executed_status]:
            _fail('Origin executed status requires explicit matching fidelity reasons')
        for key,value in metadata.items():
            if key in original and original[key]!=value:
                if advanced and key=='implementation_specs_sha256' and original[key]==_digest(source['implemented_specs.json']):continue
                _fail('Conflicting origin metric metadata')
        metric = dict(deepcopy(original), **metadata)
        if advanced:
            metric,_=_native_fields(metric,deepcopy(spec))
            metric=_native_windows(metric,attachments,origin.get('periods',protocol.get('periods')))
        metrics.append(metric)
        by_record[metric['id']].append(metric)
        if advanced and original.get('additional_native_bar_lag') is not None:
            deep.append(dict(variant_id=variant_id,origin_run_id=run_id,selection='retained_origin_native_bar_lag',additional_native_bar_lag=original['additional_native_bar_lag'],interpretation=original.get('additional_native_bar_lag_interpretation'),scope='NATIVE_STATE_REEXECUTION_REPORTED_NOT_CERTIFIED'))
        elif original.get('additional_day_lag') is not None:
            deep.append(dict(variant_id=variant_id, origin_run_id=run_id,
                selection='retained_origin_additional_day_lag', additional_day_lag=original['additional_day_lag'],
                interpretation=original.get('additional_day_lag_interpretation'),
                scope=annotation.get('deep_validation_scope', 'ORIGIN_REPORTED_SENSITIVITY_NOT_INDEPENDENTLY_VERIFIED')))
    status_by_record = defaultdict(list)
    for status in statuses.values():
        if status['id'] not in audit:
            _fail('Origin status references an unknown source record')
        status_by_record[status['id']].append(status)
    coverage = []
    for identity, record in audit.items():
        evidence = by_record[identity]
        classes = {r['fidelity_class'] for r in evidence}
        if classes:
            status = 'tested_mixed' if len(classes) > 1 or 'PROXY_HYPOTHESIS' in classes else FIDELITY_STATUS[next(iter(classes))]
            reason = '\n'.join(sorted({r['fidelity_reason'] for r in evidence if r['fidelity_reason']}))
        else:
            own = status_by_record[identity]
            states = {x['status'] for x in own}
            if any(state.startswith('tested') for state in states):
                _fail('Executed origin status has no retained result')
            status = next(iter(states)) if len(states) == 1 else 'multiple_unresolved_dependencies' if states else 'not_evaluated_in_this_run'
            reason = '\n'.join(sorted({str(x.get('reason', '')) for x in own if x.get('reason')})) or 'No retained experiment for this source record in this origin run.'
        coverage.append(dict(run_id=run_id, id=identity, name=record['名称'], status=status, reason=reason,
            tested_variants=len(evidence), source_url=record['source_url']))
    data=origin.get('input_files') if not legacy else origin['normalized_data_sha256']
    input_aliases={}
    if advanced and not legacy:
        input_aliases={key:'input_'+str(i)+'.bin' for i,(key,value) in enumerate(sorted(data.items()))}
        normalized={input_aliases[key]:_sha(value['sha256']) for key,value in data.items()}
    else:
        normalized={ticker+'.csv':_sha(value['sha256']) for ticker,value in data.items()} if not legacy else {str(key):_sha(value) for key,value in data.items()}
    code={}
    code_items=origin.get('code_hashes',{}) if not legacy else origin['engine_code_sha256']
    duplicate_names={Path(p).name for p in code_items if sum(Path(q).name==Path(p).name for q in code_items)>1}
    for path,digest in (origin.get('code_hashes',{}) if not legacy else origin['engine_code_sha256']).items():
        basename=Path(path).name
        if basename in duplicate_names:
            basename='path_'+hashlib.sha256(str(path).encode()).hexdigest()+'__'+basename
        if basename in code:_fail('Ambiguous origin engine code basename')
        code[basename]=_sha(digest)
    if not data or not code:_fail('Origin run lacks declared data/code lineage')
    periods=origin.get('periods',{})
    if legacy:
        periods={k:protocol[v] for k,v in [('development','development'),('validation','validation'),('holdout','temporal_holdout')] if v in protocol}
        if 'evaluation_start' in protocol:periods['full']=[protocol['evaluation_start'],origin['main_end']]
        year=origin['descriptive_2026_end'][:4];periods['latest_'+year]=[year+'-01-01',origin['descriptive_2026_end']]
        if origin.get('corpus_sha256')!=verification['input']['sha256']:_fail('Legacy corpusdigest doesnotmatch audit')
    main_end=periods['full'][1] if not legacy else origin['main_end']
    observation_end=max(bounds[1] for bounds in periods.values()) if not legacy else origin['descriptive_2026_end']
    origin_refs = {name: dict(sha256=_digest(blobs[name]), bytes=len(blobs[name])) for name in ORIGIN_ARTIFACTS}
    for name in missing_auxiliary:
        origin_refs['origin__'+name]['representation']='explicit_absence_receipt_not_source_artifact'
    run = dict(run_id=run_id, origin_run_id=run_id, created_at_utc=origin['created_at_utc'],
        corpus_sha256=verification['input']['sha256'], corpus_records=len(audit),
        protocol_sha256=origin['protocol_sha256'], implementation_specs_sha256=_digest(specs_blob),
        engine_code_sha256=code, normalized_data_sha256=normalized, main_end=main_end, observation_end=observation_end,
        periods=periods, base_cost_bps=protocol.get('base_cost_bps'), origin_artifacts=origin_refs,
        source_run_manifest_sha256=_digest(source['run_manifest.json']), source_implementation_specs_sha256=_digest(source['implemented_specs.json']),
        metadata_enrichment=dict(adapter='quantgraph-delta-export/v1', recomputed=False,
            operator_annotations_sha256=_digest(blobs[ANNOTATION_FILE]),
            description='Metadata-only independent-run projection. Original producer files and protocol retained byte-for-byte. Cumulative source coverage is not imported as evidence. Corpus binding uses audited matching source IDs; market/code hashes remain producer declarations.'))
    if advanced:
        run['presentation_supplement_verification']=_apply_supplements(blobs,source,origin,original_metrics,metrics,attachments)
        run['metadata_enrichment']['economic_trial_recomputed']=False
        run['metadata_enrichment']['capital_presentation_statistics_derived_and_checked']=run['presentation_supplement_verification']['capital_states']>0
        run['projection_contract']='native-retained-projection/v3'
        projected_specs = {s.get('variant_id', s['id']): s for s in specs}
        run['virtual_cash_assets']=sorted({m['cash_asset'] for m in metrics if m.get('cash_asset')=='USDT_CASH' and projected_specs[m['variant_id']].get('cash_unit')=='USDT'})
        bindings={}
        dependencies={a for m in metrics for a in m['assets']}|{a for m in metrics for a in original_specs[m['variant_id']].get('signal_only_assets',[])}|{m['cash_asset'] for m in metrics if m['cash_asset'] not in {'CASH',*run['virtual_cash_assets']}}
        for asset in sorted(dependencies):
            if legacy:
                labels=[key for key in normalized if key==asset+'.csv']
            else:
                labels=[]
                for key,value in data.items():
                    path=Path(value.get('path',key));stem=path.name.removesuffix('.gz').removesuffix('.csv')
                    if key in {asset,'signal:'+asset} or (key.startswith(asset+'/') and '..' not in PurePosixPath(key).parts) or stem==asset or asset in path.parts:labels.append(input_aliases[key])
            if not labels and 'signals/macro_signal_normalization_v1.json' in attachments:
                declaration=_loads(attachments['signals/macro_signal_normalization_v1.json'])
                matching=[d for d in declaration.get('datasets',[]) if d.get('symbol')==asset and d.get('layer')=='signal_only']
                if len(matching)==1:
                    d=matching[0];name='signals/'+Path(d.get('normalized_path','')).name
                    raw_name='signals/'+Path(d.get('raw_path','')).name
                    if (name not in attachments or raw_name not in attachments
                            or _sha(d.get('normalized_sha256'))!=_digest(attachments[name])
                            or _sha(d.get('raw_sha256'))!=_digest(attachments[raw_name])):
                        _fail('Retained macro data declaration does not match source and normalized attachments')
                    label='signal_attachment_'+_digest(attachments[name])+'.csv'
                    normalized[label]=_digest(attachments[name]);labels=[label]
                    run['metadata_enrichment'].setdefault('signal_data_from_pinned_attachments',{})[asset]=dict(normalized_artifact=name,raw_artifact=raw_name,declaration_artifact='signals/macro_signal_normalization_v1.json',not_tradable_price=True)
            if not labels:_fail('Used data series lacks matching origin data declaration: '+asset)
            bindings[asset]=sorted(set(labels))
        run['series_data_bindings']=bindings
        run['origin_format']='legacy_manifest_v1' if legacy else 'explicit_delta_manifest'
        run['metadata_enrichment']['legacy_result_pin_note']='Legacy producer did not publish per-result hashes; all supplied original result bytes are pinned by this separate operator-reviewed import manifest.' if legacy else None
        run['origin_attachment_refs']={name:dict(sha256=_digest(blob),bytes=len(blob)) for name,blob in attachments.items()}
        run['metadata_enrichment']['daily_date_normalization']='UTC-midnight timestamp labels canonicalized to YYYY-MM-DD; values unchanged, original bytes retained.'
    if missing_auxiliary:
        run['metadata_enrichment']['unavailable_origin_auxiliary_artifacts']=missing_auxiliary
        run['metadata_enrichment']['target_hash_verification']='Not available in this origin; no reconstructed targets asserted'
    series = {asset for metric in metrics for asset in metric['assets']}
    series.update(metric['cash_asset'] for metric in metrics if metric['cash_asset'] not in {'CASH',*run.get('virtual_cash_assets',[])})
    summary = dict(run_id=run_id, corpus_records=len(audit), spec_variants=len(specs), tested_variants=len(metrics),
        tested_records=len(by_record.keys() & {m['id'] for m in metrics}), families=len({m['family'] for m in metrics}),
        used_data_series=len(series), data_files=len(normalized), deep_selected=len(deep), coverage_counts=dict(Counter(r['status'] for r in coverage)))
    return {'run_manifest.json':_encoded(run), 'run_summary.json':_encoded(summary),
        'implemented_specs.json':specs_blob, 'strategy_metrics.json':_encoded(metrics),
        'all_record_coverage.csv':_csv_bytes(coverage), 'daily_returns.csv.gz':_normalize_daily_csv(source['daily_returns.csv.gz']) if advanced else source['daily_returns.csv.gz'],
        'deep_validation.json':_encoded(deep)}


def verify_derived(blobs):
    for name, expected in derive(blobs).items():
        if blobs[name] != expected:
            _fail('Derived projection differs from retained origin bytes: ' + name)


def export_delta(origin_dir, protocol_path, audit_dir, destination, annotations_path=None, *, format_version=2, capital_overlay_path=None, ledger_supplement_path=None, object_store=None):
    """Write a NEW export, reusing immutable bytes without changing manifests.

    Pass one object_store across batches for cross-batch reuse. By default,
    sibling run exports share a private store in their parent directory.
    """
    origin_dir, destination, audit_dir = Path(origin_dir), Path(destination), Path(audit_dir)
    if origin_dir.is_symlink() or not origin_dir.is_dir() or audit_dir.is_symlink() or not audit_dir.is_dir():
        _fail('Origin and audit directories must be explicit non-symlink directories')
    if destination.exists() or destination.is_symlink():
        _fail('Choose a new private export directory; no overwrite')
    manifest_blob=_read_file(origin_dir/'run_manifest.json');source_manifest=_loads(manifest_blob)
    blobs = {'origin__run_manifest.json':manifest_blob}
    for name in ORIGIN_NAMES:
        if name=='run_manifest.json':continue
        path=origin_dir/name
        absent_target=(format_version==3 and name=='target_hashes.json'
                       and isinstance(source_manifest.get('result_hashes'),dict)
                       and name not in source_manifest['result_hashes']
                       and not path.exists() and not path.is_symlink())
        absent_csv=(format_version==3 and name=='strategy_metrics.csv'
                    and isinstance(source_manifest.get('result_hashes'),dict)
                    and name not in source_manifest['result_hashes']
                    and not path.exists() and not path.is_symlink())
        if absent_csv:
            blobs['origin__'+name]=_encoded(dict(schema_version='absent-origin-auxiliary/v1',artifact=name,origin_manifest_sha256=_digest(manifest_blob),status='NOT_INCLUDED_OR_DECLARED_IN_RECEIVED_ORIGIN',not_an_original_csv=True))
            continue
        blobs['origin__'+name]=(_encoded(dict(schema_version='absent-origin-auxiliary/v1',artifact=name,origin_manifest_sha256=_digest(manifest_blob),status='NOT_INCLUDED_OR_DECLARED_IN_RECEIVED_ORIGIN',not_a_target_hash=True)) if absent_target else _read_file(path))
    blobs['origin__protocol.json'] = _read_file(protocol_path)
    if format_version not in {2,3}:_fail('Unsupported projection version')
    if format_version==3:
        om=_loads(blobs['origin__run_manifest.json']);extra={}
        for name,digest in om.get('result_hashes',{}).items():
            if name in ORIGIN_NAMES:continue
            value=_origin_file(origin_dir,name)
            if _sha(digest)!=_digest(value):_fail('Origin artifact digest mismatch: '+name)
            extra[name]=dict(sha256=_digest(value),bytes=len(value),base64=base64.b64encode(value).decode('ascii'))
        if om.get('result_hashes') is None and om.get('protocol_amendments_sha256'):
            value=_read_file(Path(protocol_path).with_name('protocol_amendments.json'))
            if _sha(om['protocol_amendments_sha256'])!=_digest(value):_fail('Legacy protocol amendment hash mismatch')
            extra['protocol_amendments.json']=dict(sha256=_digest(value),bytes=len(value),base64=base64.b64encode(value).decode('ascii'))
        blobs[ATTACHMENTS_FILE]=_encoded(dict(schema_version='retained-origin-attachments/v1',artifacts=extra))
        blobs[SUPPLEMENTS_FILE]=_encoded(dict(schema_version='retained-presentation-supplements/v1',capital_overlay=_loads(_read_file(capital_overlay_path)) if capital_overlay_path else None,ledger_supplement=_loads(_read_file(ledger_supplement_path)) if ledger_supplement_path else None))
    elif capital_overlay_path or ledger_supplement_path:_fail('Presentation supplements requirev3')
    blobs[ANNOTATION_FILE] = (_read_file(annotations_path) if annotations_path else _encoded(dict(
        schema_version='strategy-screen-annotations/v1', run_id=_loads(blobs['origin__run_manifest.json'])['run_id'], implementations={})))
    for name in ['record_audit.jsonl', 'source_verification.json']:
        blobs[name] = _read_file(audit_dir/name)
    blobs.update(derive(blobs))
    _prepare(blobs, {'run_id':_loads(blobs['run_manifest.json'])['run_id']})
    from quantgraph.graph.immutable_artifacts import materialize_immutable, publish_export_directory
    object_store = Path(object_store) if object_store is not None else destination.parent / '.corpus-export-objects'
    object_store = Path(os.path.abspath(object_store))
    destination_absolute = Path(os.path.abspath(destination))
    if object_store == destination_absolute or destination_absolute in object_store.parents:
        _fail('Object store must be outside the new export directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.corpus-export-', dir=destination.parent))
    try:
        for name, data in blobs.items():
            target = temporary/name
            materialize_immutable(data, target, object_store)
        receipt = build_manifest(temporary, temporary, temporary/'import-manifest.json')
        publish_export_directory(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return dict(receipt, origin_run_id=_loads(blobs['run_manifest.json'])['run_id'], recomputed=False)


SOURCE_PORTFOLIO_FILES={
    'source_portfolio_metrics.json','source_portfolio_record_mapping.json','component_reconstruction_tests.json',
    'published_monthly_returns.csv','source_portfolio_metrics.csv','evaluation_summary.json',
}


def validate_source_portfolio(origin_dir, expected_manifest_sha256):
    """Validate separately; this never creates an executed strategy/run."""
    root=Path(origin_dir)
    if root.is_symlink() or not root.is_dir():_fail('Explicit source-evaluation directory required')
    manifest_blob=_read_file(root/'evaluation_manifest.json')
    if _sha(expected_manifest_sha256)!=_digest(manifest_blob):_fail('Source evaluation manifest digest mismatch')
    manifest=_loads(manifest_blob)
    if manifest.get('evidence_class')!='PUBLISHED_SOURCE_PORTFOLIO':_fail('Not published source portfolio evidence')
    evaluation_id=_identifier(manifest['evaluation_id']);declared=manifest.get('result_hashes')
    if not isinstance(declared,dict) or set(declared)!=SOURCE_PORTFOLIO_FILES:_fail('Source evaluation must pin fixed permitted artifacts')
    blobs={name:_read_file(root/name) for name in SOURCE_PORTFOLIO_FILES}
    for name,blob in blobs.items():
        if _sha(declared[name])!=_digest(blob):_fail('Source evaluation artifact digest mismatch')
    metrics=_index(_loads(blobs['source_portfolio_metrics.json']),lambda x:x['id'],'source portfolio metrics')
    mapping=_index(_loads(blobs['source_portfolio_record_mapping.json']),lambda x:x['id'],'source portfolio mapping')
    summary=_loads(blobs['evaluation_summary.json'])
    if set(metrics)!=set(mapping) or summary.get('original_records_with_source_portfolio_evidence')!=len(metrics) or summary.get('new_independently_reconstructed_execution_records')!=0:
        _fail('Published source evidence cannot increase execution coverage')
    rows=_csv(blobs['published_monthly_returns.csv'])
    if not rows or set(rows[0])!={'month_end',*metrics}:_fail('Source monthly return identities mismatch')
    curves={rid:[] for rid in metrics};last=None
    for row in rows:
        day=row['month_end'];dt=datetime.strptime(day,'%Y-%m-%d')
        if dt.day!=calendar.monthrange(dt.year,dt.month)[1]:_fail('Source monthly observations must be calendar month ends')
        if last is not None and day<=last:_fail('Monthly source dates must increase')
        last=day
        for rid in metrics:
            if not row[rid]:continue
            number=float(row[rid])
            if not math.isfinite(number) or number<=-1:_fail('Invalid published factor return')
            curves[rid].append([day,number])
    records=[]
    for rid,metric in metrics.items():
        _finite(metric)
        if metric.get('evidence_class')!='PUBLISHED_SOURCE_PORTFOLIO' or metric.get('name')!=mapping[rid].get('name'):_fail('Source portfolio class/name mismatch')
        for period in metric['periods'].values():
            if period.get('observations')==0:
                _empty_period(period);continue
            selected=[(d,r) for d,r in curves[rid] if period['start']<=d<=period['end']]
            if len(selected)!=period['observations'] or not selected or selected[0][0]!=period['start'] or selected[-1][0]!=period['end'] or not _close(math.prod(1+r for _,r in selected)-1,period['total_return']):_fail('Source portfolio metrics/returns mismatch')
        equity=peak=1.;curve=[]
        for day,number in curves[rid]:
            equity*=1+number;peak=max(peak,equity);curve.append(dict(date=day,equity=equity,drawdown=equity/peak-1))
        if len(curve)>1200:
            indices={0,len(curve)-1,min(range(len(curve)),key=lambda i:curve[i]['drawdown']),max(range(len(curve)),key=lambda i:curve[i]['equity'])};indices.update(i*(len(curve)-1)//1195 for i in range(1196));curve=[curve[i] for i in sorted(indices)]
        records.append(dict(id=rid,name=metric['name'],evidence_class='PUBLISHED_SOURCE_PORTFOLIO',metrics=metric,definition_mapping=mapping[rid],curve=curve,curve_meta=dict(frequency='monthly',monthly_drawdown_not_intramonth=True,initial_normalized_factor_wealth=1,no_trade_execution_reconstructed=True,scope='all_retained_monthly_source_observations',start=curves[rid][0][0] if curves[rid] else None,end=curves[rid][-1][0] if curves[rid] else None,total_observations=len(curves[rid]),returned_points=len(curve),drawdown_computed_before_sampling=True)))
    return dict(evaluation_id=evaluation_id,evidence_class='PUBLISHED_SOURCE_PORTFOLIO',manifest_sha256=expected_manifest_sha256,manifest=manifest,artifacts={k:dict(sha256=_digest(v),bytes=len(v)) for k,v in blobs.items()},records=records,summary=summary,new_economic_trials=0,new_execution_records=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin-dir', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--object-store', type=Path, help='Shared immutable byte store across export batches; same filesystem required')
    parser.add_argument('--format-version',type=int,choices=[2,3],default=2)
    parser.add_argument('--capital-overlay',type=Path)
    parser.add_argument('--ledger-supplement',type=Path)
    parser.add_argument('--annotations', type=Path, help='Reviewed metadata annotations for missing fidelity/deep-validation declarations')
    args = parser.parse_args()
    print(json.dumps(export_delta(args.origin_dir,args.protocol,args.audit_dir,args.destination,args.annotations,format_version=args.format_version,capital_overlay_path=args.capital_overlay,ledger_supplement_path=args.ledger_supplement,object_store=args.object_store)))


if __name__ == '__main__':
    main()

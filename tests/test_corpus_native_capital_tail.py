"""Missing native tail observations need an arithmetically verified capital reset."""
import copy
import gzip
import pytest
from quantgraph.graph.corpus_export import _native_capital_tail, _native_windows
from quantgraph.graph.corpus_research import _digest


def fixture():
    event=dict(event_type='capital_extinguishment_no_exchange_fill',at='2024-01-02 12:00:00+00:00',
        active_position=dict(entry_time='2024-01-01 00:00:00+00:00',entry_price=100.,quantity=.01,entry_cost=0.,funding_paid=2.),
        quantity_before_model_reset=.01,trade_close_mark=100.,unclosed_marked_pnl=0.,
        wallet_balance_before_model_cap=-1.,nav_before_model_loss_cap=-1.,
        model_loss_cap_adjustment=1.,executed_exit_trade=False)
    state=dict(state='MODEL_CAPITAL_EXTINGUISHED',capital_extinguished_at=event['at'],events=[event])
    rows=[dict(date='2024-01-01',net_return='0',funding_paid='0',fees='0',trade_event='1'),
          dict(date='2024-01-02',net_return='-1',funding_paid='2',fees='0',trade_event='0'),
          dict(date='2024-01-03',net_return='',funding_paid='0',fees='0',trade_event='0')]
    window=dict(window_id='0',capital_state=state,periods={'full':dict(n=2,observations=2,
        start='2024-01-01',end='2024-01-02',total_return=-1.)})
    metric=dict(variant_id='R1@A',primary_window_id='0',capital_state=copy.deepcopy(state),
        presentation_periods=copy.deepcopy(window['periods']))
    attachments={'trades/R1@A__w0.csv.gz':gzip.compress(b'\n',mtime=0)}
    return metric,window,rows,attachments


def test_verified_tail_omits_missing_observations_without_zero_fill():
    metric,window,rows,attachments=fixture();original=copy.deepcopy(rows)
    kept,check=_native_capital_tail(metric,window,rows,attachments)
    assert len(kept)==2 and kept[-1]['net_return']=='-1'
    assert check['excluded_missing_tail_rows']==1 and check['new_economic_trials']==0
    assert rows==original and check['original_return_bytes_changed'] is False


@pytest.mark.parametrize('mutation,match',[
    ('no_state','explicit capital-state'),('early_gap','precedes capital'),
    ('resume','resume after'),('wrong_day','capital exhaustion|first zero-equity'),
    ('exchange_fill','exchange liquidation'),('funding','funding, fees'),
    ('fees','funding, fees'),('events','funding, fees'),
    ('cap','loss cap'),('no_active','unclosed position'),('missing_log','trade log'),
    ('non_utc','must be UTC'),('duplicate_date','strictly increasing'),
])
def test_capital_tail_rejects_unproven_or_contradictory_claims(mutation,match):
    metric,window,rows,attachments=fixture();event=window['capital_state']['events'][0]
    if mutation=='no_state':window.pop('capital_state')
    elif mutation=='early_gap':rows[0]['net_return']=''
    elif mutation=='resume':rows[-1]['net_return']='0'
    elif mutation=='wrong_day':event['at']='2024-01-03 00:00:00+00:00';window['capital_state']['capital_extinguished_at']=event['at']
    elif mutation=='exchange_fill':event['executed_exit_trade']=True
    elif mutation=='funding':rows[1]['funding_paid']='1.9'
    elif mutation=='fees':rows[0]['fees']='.1'
    elif mutation=='events':rows[0]['trade_event']='2'
    elif mutation=='cap':event['model_loss_cap_adjustment']=.9
    elif mutation=='no_active':event['active_position']=None
    elif mutation=='missing_log':attachments.clear()
    elif mutation=='non_utc':event['at']='2024-01-02 12:00:00';window['capital_state']['capital_extinguished_at']=event['at']
    elif mutation=='duplicate_date':rows[-1]['date']=rows[1]['date']
    with pytest.raises(ValueError,match=match):_native_capital_tail(metric,window,rows,attachments)


def full_fixture():
    metric,window,rows,attachments=fixture()
    raw='date,net_return,funding_paid,fees,trade_event\n'+''.join(','.join(row[k] for k in ['date','net_return','funding_paid','fees','trade_event'])+'\n' for row in rows)
    path='returns/R1@A__w0.csv.gz';blob=gzip.compress(raw.encode(),mtime=0);attachments[path]=blob
    window.update(daily_returns_path=path,daily_returns_sha256=_digest(blob));metric['windows']=[window]
    return metric,attachments


def test_projection_curve_stops_at_capital_event_and_retains_source_window():
    metric,attachments=full_fixture();original=copy.deepcopy(attachments)
    out=_native_windows(metric,attachments,{'full':['2024-01-01','2024-12-31']})
    w=out['retained_windows'][0]
    assert w['curve'][-1]['date']=='2024-01-02' and w['curve'][-1]['equity']==0
    assert w['curve_meta']['observations']==2 and w['curve_meta']['raw_rows']==3
    assert w['capital_state_validation']['status']=='RETAINED_ACCOUNTING_RECONCILED'
    assert w['source_window']['daily_returns_sha256']==_digest(original['returns/R1@A__w0.csv.gz'])
    assert attachments==original


def test_empty_native_capital_period_cannot_hide_valid_observations():
    metric,attachments=full_fixture();metric['windows'][0]['periods']['bad']={'n':0}
    with pytest.raises(ValueError,match='declared scope'):
        _native_windows(metric,attachments,{'full':['2024-01-01','2024-12-31'],'bad':['2024-01-01','2024-01-01']})


def test_primary_presentation_override_cannot_invent_performance():
    metric,attachments=full_fixture();metric['presentation_periods']['full']['total_return']=.5
    with pytest.raises(ValueError,match='Primary capital state'):_native_windows(metric,attachments)


def test_closed_trade_and_unclosed_capital_position_reconcile_together():
    metric,window,rows,attachments=fixture();event=window['capital_state']['events'][0]
    log=('entry_time,exit_time,quantity,entry_price,exit_price,gross_pnl,entry_cost,exit_cost,funding_paid\n'
         '2024-01-01 00:00:00+00:00,2024-01-01 12:00:00+00:00,0.01,100,110,0.1,0.01,0.011,0\n')
    attachments['trades/R1@A__w0.csv.gz']=gzip.compress(log.encode(),mtime=0)
    rows[0].update(net_return='.079',fees='.021',trade_event='2')
    rows[1].update(fees='.02',trade_event='1')
    event['active_position'].update(entry_time='2024-01-02 00:00:00+00:00',entry_cost=.02)
    event.update(wallet_balance_before_model_cap=-.941,nav_before_model_loss_cap=-.941,model_loss_cap_adjustment=.941)
    kept,check=_native_capital_tail(metric,window,rows,attachments)
    assert len(kept)==2 and check['status']=='RETAINED_ACCOUNTING_RECONCILED'
    attachments['trades/R1@A__w0.csv.gz']=gzip.compress(log.replace(',0.1,',',0.2,').encode(),mtime=0)
    with pytest.raises(ValueError,match='PnL'):_native_capital_tail(metric,window,rows,attachments)


def test_capital_active_entry_cannot_come_from_the_future():
    metric,window,rows,attachments=fixture()
    window['capital_state']['events'][0]['active_position']['entry_time']='2024-01-09 00:00:00+00:00'
    with pytest.raises(ValueError,match='within its window'):_native_capital_tail(metric,window,rows,attachments)

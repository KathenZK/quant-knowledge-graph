from copy import deepcopy
import gzip,hashlib
import pytest
from quantgraph.graph.corpus_export import _native_fields,_native_windows

def payload():
 s={'kind':'cny_daily_etf','account_currency':'CNY','cash_asset':'CASH','execution_calendar':'XSHG','assets':['510300.SS']}
 m={'kind':'cny_daily_etf','account_currency':'CNY','cash_asset':'CASH','clock':'Asia/Shanghai XSHG','cash_basis':'zero-yield CNY','assets':['510300.SS'],'periods':{'empty':{'observations':0,'annualization':252,'sharpe_cash_basis':'zero-yield CNY'}}}
 return m,s

def test_cny_explicit_contract_preserved():
 m,s=payload();a,b=_native_fields(deepcopy(m),deepcopy(s));assert a['account_currency']=='CNY';assert b['cash_asset']=='CASH'

@pytest.mark.parametrize('where,key,value',[('m','account_currency','USD'),('s','account_currency','USDT'),('m','clock','UTC'),('s','execution_calendar','XNYS'),('m','cash_basis','zero-yield USD'),('m','cash_asset','USDT_CASH'),('m','assets',['SPY']),('s','kind','crypto_native_bar')])
def test_cny_conflicts_rejected(where,key,value):
 m,s=payload();(m if where=='m' else s)[key]=value
 with pytest.raises(ValueError):_native_fields(m,s)

def test_cny_windows_not_relabeled_crypto():
 m,s=payload();b=gzip.compress(b'date,net_return\n2020-01-02,0.01\n2020-01-03,0.02\n',mtime=0);p={'observations':2,'start':'2020-01-02','end':'2020-01-03','total_return':.0302};m.update(windows=[{'window_id':'0','daily_returns_path':'r.gz','daily_returns_sha256':hashlib.sha256(b).hexdigest(),'periods':{'full':p}}],primary_window_id='0');m,s=_native_fields(m,s);m=_native_windows(m,{'r.gz':b});assert m['return_clock'].startswith('Asia/Shanghai');assert 'USDT' not in m['return_clock'];assert m['retained_windows'][0]['curve_meta']['observations']==2

def test_signal_only_membership_enrichment():
 s={'assets':['SPY','BIL'],'price_assets':['SPY','BIL'],'signal_only_assets':['OFR_FSI','^GSPC']};m={'assets':['BIL','SPY']};a,b=_native_fields(deepcopy(m),deepcopy(s));assert b['assets']==['SPY','BIL','OFR_FSI','^GSPC'];assert b['price_assets']==s['price_assets'];assert a['assets']==m['assets'];assert s['assets']==['SPY','BIL']

@pytest.mark.parametrize('signals,metric_assets',[(['SPY'],['SPY','BIL']),(['OFR','OFR'],['SPY','BIL']),(['OFR'],['OFR','SPY']),([None],['SPY','BIL'])])
def test_signal_only_conflicts(signals,metric_assets):
 with pytest.raises(ValueError):_native_fields({'assets':metric_assets},{'assets':['SPY','BIL'],'price_assets':['SPY','BIL'],'signal_only_assets':signals})

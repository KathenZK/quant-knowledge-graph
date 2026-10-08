import pytest
from quantgraph.graph.corpus_export import _native_fields

def test_missing_spot_cash_alias_from_explicit_original_metric():
    metric={'assets':['BTCUSDT'],'cash_asset':'USDT_CASH'};spec={'symbol':'BTCUSDT','instrument':'spot'}
    _,out=_native_fields(metric,spec)
    assert out['cash_unit']=='USDT'
    assert out['assets']==['BTCUSDT']
    assert 'explicit original metric' in out['native_field_projection']

@pytest.mark.parametrize('metric,spec',[
    ({'assets':['BTCUSDT'],'cash_asset':'USD_CASH'},{'symbol':'BTCUSDT','instrument':'spot'}),
    ({'assets':['BTCUSDT']},{'symbol':'BTCUSDT','instrument':'spot'}),
    ({'assets':['BTCUSDT'],'cash_asset':'USDT_CASH'},{'symbol':'BTCUSDT','instrument':'spot','cash_unit':'USD'}),
    ({'assets':['BTCUSDT'],'cash_asset':'USDT_CASH'},{'symbol':'BTCUSDT','instrument':'spot','cash_unit':None}),
    ({'assets':['ETHUSDT'],'cash_asset':'USDT_CASH'},{'symbol':'BTCUSDT','instrument':'spot'}),
    ({'assets':['BTCEUR'],'cash_asset':'USDT_CASH'},{'symbol':'BTCEUR','instrument':'spot'}),
    ({'assets':['BTCUSDT'],'cash_asset':'USDT_CASH'},{'symbol':'BTCUSDT','instrument':'perpetual'}),
])
def test_ambiguous_or_conflicting_cash_still_rejected(metric,spec):
    with pytest.raises(ValueError,match='symbol/cash contract'):
        _native_fields(metric,spec)

from test_corpus_export import origin  # noqa: E402, F401
from test_corpus_research import collection, encoded  # noqa: E402, F401
from test_corpus_v3 import make_native, repin, export, ingest  # noqa: E402
import json  # noqa: E402
from quantgraph.graph.corpus_research import CorpusResearch  # noqa: E402


def test_original_metric_alias_retains_virtual_cash_and_full_lineage(origin):
    make_native(origin)
    p=origin['origin']/'implemented_specs.json';specs=json.loads(p.read_bytes());specs[0].pop('cash_unit');specs[0].update(symbol='BTCUSDT',instrument='spot');p.write_bytes(encoded(specs))
    p=origin['origin']/'strategy_metrics.json';metrics=json.loads(p.read_bytes());metrics[0]['assets']=['BTCUSDT'];p.write_bytes(encoded(metrics))
    p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['input_files']['BTCUSDT']={'path':'/private/BTCUSDT.csv','sha256':'8'*64};p.write_bytes(encoded(m));repin(origin)
    r=export(origin);ingest(origin,r)
    d=CorpusResearch(origin['runtime']).implementation('R1@A')
    assert d['spec']['cash_unit']=='USDT'
    lineage=d['lineage']['declared_lineage']
    assert lineage['virtual_cash_assets']==['USDT_CASH']
    assert 'USDT_CASH' not in lineage['series_data_bindings']
    assert 'BTCUSDT' in lineage['series_data_bindings']

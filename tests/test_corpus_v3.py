"""Native/legacy presentation projections preserve evidence and fail closed."""
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import pytest

from quantgraph.graph.corpus_export import export_delta, validate_source_portfolio
from quantgraph.graph.corpus_research import CorpusResearch, import_manifest, import_source_portfolio
from test_corpus_export import origin  # noqa: F401
from test_corpus_research import collection, encoded, digest  # noqa: F401


def repin(o):
    p=o['origin']/'run_manifest.json';m=json.loads(p.read_bytes())
    for name in m['result_hashes']:m['result_hashes'][name]=digest((o['origin']/name).read_bytes())
    p.write_bytes(encoded(m))


def export(o,**kw):
    return export_delta(o['origin'],o['protocol'],o['audit'],o['export'],format_version=3,**kw)


def ingest(o,receipt):
    return import_manifest(o['runtime'],o['export']/'import-manifest.json',receipt['manifest_sha256'],o['export'],o['export'])


def test_v3_plain_preserves_source_and_pin(origin):
    before={p.name:digest(p.read_bytes()) for p in origin['origin'].iterdir()}
    r=export(origin);assert r['artifact_count']==22;ingest(origin,r)
    assert before=={p.name:digest(p.read_bytes()) for p in origin['origin'].iterdir()}
    assert CorpusResearch(origin['runtime']).implementation('R1@A')['metrics']['origin_run_id']=='synthetic-screen-v1'


def add_empty(o,count=0):
    p=o['origin']/'strategy_metrics.json';rows=json.loads(p.read_bytes())
    for row in rows:row['periods']['before']={'observations':count}
    p.write_bytes(encoded(rows));p=o['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['periods']['before']=['2023-01-01','2023-12-31'];p.write_bytes(encoded(m));repin(o)


def test_empty_declared_period_is_na_not_fabricated(origin):
    add_empty(origin);r=export(origin);ingest(origin,r)
    assert CorpusResearch(origin['runtime']).implementation('R1@A')['metrics']['periods']['before']=={'observations':0}


def test_empty_claim_cannot_hide_observations(origin):
    add_empty(origin,1)
    with pytest.raises(ValueError,match='observation count'):export(origin)


def test_signal_observation_dependency_not_treated_as_price(origin):
    p=origin['origin']/'implemented_specs.json';rows=json.loads(p.read_bytes());rows[0].update(assets=['S','UNRATE'],price_assets=['S'],signal_only_assets=['UNRATE']);p.write_bytes(encoded(rows))
    p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['input_files']['signal:UNRATE']={'path':'/private/signals/FRED_UNRATE.csv','sha256':'8'*64};p.write_bytes(encoded(m));repin(origin)
    r=export(origin);ingest(origin,r);detail=CorpusResearch(origin['runtime']).implementation('R1@A');assert detail['spec']['signal_only_assets']==['UNRATE'];assert detail['metrics']['assets']==['S']


def test_price_subset_requires_explicit_signal_partition(origin):
    p=origin['origin']/'implemented_specs.json';rows=json.loads(p.read_bytes());rows[0].update(assets=['S','UNRATE'],price_assets=['S']);p.write_bytes(encoded(rows));repin(origin)
    with pytest.raises(ValueError,match='universe'):export(origin)


def test_origin_attachment_bytes_preserved_and_checked(origin):
    p=origin['origin']/'returns';p.mkdir();f=p/'R1@A__w0.csv.gz';f.write_bytes(gzip.compress(b'date,net_return\n2024-01-01,0.1\n',mtime=0))
    mpath=origin['origin']/'run_manifest.json';m=json.loads(mpath.read_bytes());m['result_hashes']['returns/'+f.name]=digest(f.read_bytes());mpath.write_bytes(encoded(m));r=export(origin);ingest(origin,r)
    container=json.loads((origin['export']/'origin-attachments.json').read_bytes());assert container['artifacts']['returns/'+f.name]['sha256']==digest(f.read_bytes())


@pytest.mark.parametrize('name',['../outside.csv.gz','returns/../../outside.csv.gz','/absolute.csv.gz','returns\\escape.csv.gz','runner.py'])
def test_extra_paths_fail_closed(origin,name):
    p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['result_hashes'][name]='a'*64;p.write_bytes(encoded(m))
    with pytest.raises(ValueError,match='artifact'):export(origin)
    assert not origin['export'].exists()


def test_extra_symlink_refused(origin):
    d=origin['origin']/'returns';d.mkdir();(d/'R1@A__w0.csv.gz').symlink_to(origin['protocol'])
    p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['result_hashes']['returns/R1@A__w0.csv.gz']=digest(origin['protocol'].read_bytes());p.write_bytes(encoded(m))
    with pytest.raises(ValueError,match='symlinks'):export(origin)


def make_native(o,offset='+00:00'):
    p=o['origin']/'implemented_specs.json';ss=json.loads(p.read_bytes());ss[0].pop('assets');ss[0].pop('cash_asset');ss[0].update(symbol='S',instrument='perpetual',cash_unit='USDT');p.write_bytes(encoded(ss))
    p=o['origin']/'strategy_metrics.json';ms=json.loads(p.read_bytes());ms[0]['cash_asset']='USDT_CASH';ms[0]['same_instrument_benchmark']={'basis':'S perpetual, same funding'};ms[0]['additional_native_bar_lag']={'full':{'total_return':.02}}
    for per in ms[0]['periods'].values():per['n']=per.pop('observations')
    p.write_bytes(encoded(ms));p=o['origin']/'daily_returns.csv.gz';text=gzip.decompress(p.read_bytes()).decode()
    for day in ['2024-01-01','2024-01-02','2024-01-03']:text=text.replace(day+',',day+' 00:00:00'+offset+',')
    p.write_bytes(gzip.compress(text.encode(),mtime=0));repin(o)


def test_native_currency_and_sensitivity_not_recast_as_spy(origin):
    make_native(origin);r=export(origin);ingest(origin,r);d=CorpusResearch(origin['runtime']).implementation('R1@A')
    assert d['spec']['cash_asset']=='USDT_CASH';assert d['metrics']['same_instrument_benchmark']['basis'].startswith('S perpetual')
    assert 'additional_native_bar_lag' in d['deep_validation'];assert d['curve'][0]['date']=='2024-01-01'
    assert b'00:00:00+00:00' in gzip.decompress((origin['export']/'origin__daily_returns.csv.gz').read_bytes())


def test_non_utc_timestamp_never_silently_truncated(origin):
    make_native(origin,'+02:00')
    with pytest.raises(ValueError,match='UTC midnight'):export(origin)


def test_legacy_is_explicit_and_result_pins_not_claimed_original(origin):
    p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m.pop('result_hashes');m['normalized_data_sha256']={'S.csv':'7'*64};m['engine_code_sha256']={'engine.py':'6'*64};m['implementation_specs_sha256']=digest((origin['origin']/'implemented_specs.json').read_bytes());m['main_end']='2024-01-02';m['descriptive_2026_end']='2024-01-03';m['corpus_sha256']=json.loads((origin['audit']/'source_verification.json').read_bytes())['input']['sha256'];p.write_bytes(encoded(m))
    r=export(origin);ingest(origin,r);detail=CorpusResearch(origin['runtime']).implementation('R1@A');assert detail['lineage']['declared_lineage']['origin_format']=='legacy_manifest_v1'
    assert 'did not publish' in detail['lineage']['declared_lineage']['metadata_enrichment']['legacy_result_pin_note']


def test_unbound_capital_supplement_rejected(origin):
    p=origin['root']/'bad-capital.json';p.write_bytes(encoded({'origin_run_id':'wrong','origin_manifest_sha256':'f'*64}))
    with pytest.raises(ValueError,match='origin binding'):export(origin,capital_overlay_path=p)


def source_fixture(o):
    root=o['root']/'source';root.mkdir();name=json.loads((o['results']/'strategy_metrics.json').read_bytes())[0]['name'];rid='R1'
    metric=dict(id=rid,name=name,evidence_class='PUBLISHED_SOURCE_PORTFOLIO',periods={'full':dict(start='2024-01-31',end='2024-02-29',observations=2,total_return=.1*.9+.9-1)})
    blobs={'source_portfolio_metrics.json':encoded([metric]),'source_portfolio_record_mapping.json':encoded([dict(id=rid,name=name)]),'component_reconstruction_tests.json':encoded([]),'published_monthly_returns.csv':b'month_end,R1\n2024-01-31,0.1\n2024-02-29,-0.1\n','source_portfolio_metrics.csv':b'id\nR1\n','evaluation_summary.json':encoded(dict(original_records_with_source_portfolio_evidence=1,new_independently_reconstructed_execution_records=0))}
    for fn,blob in blobs.items():(root/fn).write_bytes(blob)
    manifest=dict(evaluation_id='published-example',evidence_class='PUBLISHED_SOURCE_PORTFOLIO',result_hashes={k:digest(v) for k,v in blobs.items()});(root/'evaluation_manifest.json').write_bytes(encoded(manifest));return root,digest((root/'evaluation_manifest.json').read_bytes())


def test_source_evidence_never_increases_execution_count(origin):
    r=export(origin);ingest(origin,r);root,h=source_fixture(origin)
    with sqlite3.connect(origin['runtime']/'corpus-research.sqlite') as con:before=con.execute('SELECT COUNT(*) FROM corpus_implementations').fetchone()[0]
    result=import_source_portfolio(origin['runtime'],root,h);assert result['new_execution_records']==0
    with sqlite3.connect(origin['runtime']/'corpus-research.sqlite') as con:assert con.execute('SELECT COUNT(*) FROM corpus_implementations').fetchone()[0]==before
    source=CorpusResearch(origin['runtime']).source_portfolios('R1');assert len(source)==1;assert source[0]['evidence_class']=='PUBLISHED_SOURCE_PORTFOLIO';assert import_source_portfolio(origin['runtime'],root,h)['duplicate']


def test_source_return_tampering_rejected(origin):
    root,h=source_fixture(origin);p=root/'published_monthly_returns.csv';p.write_bytes(p.read_bytes().replace(b'0.1',b'0.9'))
    with pytest.raises(ValueError,match='artifact digest'):validate_source_portfolio(root,h)


@pytest.mark.parametrize('field',['total_return','cagr','sharpe','max_drawdown','annual_volatility','annual_vol','annual_turnover','trade_events'])
def test_empty_native_window_rejects_all_performance(field):
    from quantgraph.graph.corpus_export import _observations_for_period
    with pytest.raises(ValueError,match='Empty sample'):
        _observations_for_period([],{'n':0,field:0})


def test_empty_period_accepts_null_statistics(origin):
    add_empty(origin)
    p=origin['origin']/'strategy_metrics.json';ms=json.loads(p.read_bytes())
    for m in ms:m['periods']['before'].update(cagr=None,sharpe=None,total_return=None,max_drawdown=None)
    p.write_bytes(encoded(ms));repin(origin);r=export(origin);ingest(origin,r)


@pytest.mark.parametrize('field',['cagr','sharpe','max_drawdown'])
def test_empty_primary_period_rejects_performance(origin,field):
    add_empty(origin)
    p=origin['origin']/'strategy_metrics.json';ms=json.loads(p.read_bytes());ms[0]['periods']['before'][field]=0
    p.write_bytes(encoded(ms));repin(origin)
    with pytest.raises(ValueError,match='Empty sample'):export(origin)

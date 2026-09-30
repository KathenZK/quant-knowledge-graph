import json
import pytest
from quantgraph.graph.corpus_export import export_delta
from quantgraph.graph.corpus_research import import_manifest
from test_corpus_export import origin  # noqa: F401
from test_corpus_research import collection,encoded,digest  # noqa: F401

def emit(o):return export_delta(o['origin'],o['protocol'],o['audit'],o['export'],format_version=3)
def pin(o,items):
 p=o['origin']/'run_manifest.json';m=json.loads(p.read_bytes())
 for n,b in items.items():
  f=o['origin']/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b);m['result_hashes'][n]=digest(b)
 p.write_bytes(encoded(m))
def test_inert_source_and_qa_attachments(origin):
 values={'sources/page.html':b'<script>never_execute()</script>','qa/check.log':b'not independently certified','code/fixture.json':b'{}','trade_clock_cost_qa.json':b'{}','orders/R1@A.csv.gz':b'inertbytes'}
 pin(origin,values);r=emit(origin);import_manifest(origin['runtime'],origin['export']/'import-manifest.json',r['manifest_sha256'],origin['export'],origin['export'])
 refs=json.loads((origin['export']/'origin-attachments.json').read_bytes())['artifacts'];assert all(refs[n]['sha256']==digest(b) for n,b in values.items())
def test_missing_csv_preserves_json_and_absence(origin):
 (origin['origin']/'strategy_metrics.csv').unlink();p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['result_hashes'].pop('strategy_metrics.csv');p.write_bytes(encoded(m));old=p.read_bytes();r=emit(origin)
 import_manifest(origin['runtime'],origin['export']/'import-manifest.json',r['manifest_sha256'],origin['export'],origin['export']);mark=json.loads((origin['export']/'origin__strategy_metrics.csv').read_bytes());assert mark['not_an_original_csv'] is True and mark['origin_manifest_sha256']==digest(old)
 assert p.read_bytes()==old

def test_declared_missing_csv_rejected(origin):
 (origin['origin']/'strategy_metrics.csv').unlink()
 with pytest.raises(ValueError):emit(origin)
def test_unpinned_present_csv_rejected(origin):
 p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['result_hashes'].pop('strategy_metrics.csv');p.write_bytes(encoded(m))
 with pytest.raises(ValueError):emit(origin)
def test_duplicate_code_basenames_stable_and_preserved(origin):
 p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['code_hashes']={'/private/a/engine.py':'a'*64,'/private/b/engine.py':'b'*64};p.write_bytes(encoded(m));emit(origin)
 got=json.loads((origin['export']/'run_manifest.json').read_bytes());assert len(got['engine_code_sha256'])==2;assert set(got['engine_code_sha256'].values())=={'a'*64,'b'*64};assert json.loads((origin['export']/'origin__run_manifest.json').read_bytes())==m
@pytest.mark.parametrize('n',['sources/../steal.html','sources/sub/x.html','sources/x.js','qa/x.exe','orders/x.py'])
def test_extended_paths_failclosed(origin,n):
 p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['result_hashes'][n]='a'*64;p.write_bytes(encoded(m))
 with pytest.raises(ValueError):emit(origin)
def test_extended_hash_mismatch_rejected(origin):
 pin(origin,{'qa/check.json':b'{}'});(origin['origin']/'qa/check.json').write_bytes(b'{"changed":true}')
 with pytest.raises(ValueError,match='digest mismatch'):emit(origin)

def repin(o):
 p=o['origin']/'run_manifest.json';m=json.loads(p.read_bytes())
 for n in m['result_hashes']:m['result_hashes'][n]=digest((o['origin']/n).read_bytes())
 p.write_bytes(encoded(m))
def test_unexecuted_record_status_without_variant(origin):
 p=origin['origin']/'implementation_status.json';d=json.loads(p.read_bytes());d.append({'id':'R2','variant_id':None,'status':'source_unresolved','reason':'Known missing source'});p.write_bytes(encoded(d));repin(origin);emit(origin)
def test_executed_status_requires_variant(origin):
 p=origin['origin']/'implementation_status.json';d=json.loads(p.read_bytes());d[0]['variant_id']=None;p.write_bytes(encoded(d));repin(origin)
 with pytest.raises(ValueError,match='explicit variant'):emit(origin)
def test_empty_requested_scope_is_metadata(origin):
 p=origin['origin']/'strategy_metrics.json';d=json.loads(p.read_bytes());d[0]['periods']['before']={'observations':0,'requested_start':'2023-01-01','requested_end':'2023-12-31'};p.write_bytes(encoded(d));mp=origin['origin']/'run_manifest.json';m=json.loads(mp.read_bytes());m['periods']['before']=['2023-01-01','2023-12-31'];mp.write_bytes(encoded(m));repin(origin);emit(origin)
@pytest.mark.parametrize('field',['total_return','cagr','sharpe','max_drawdown','annual_volatility'])
def test_empty_requested_scope_cannot_hide_performance(origin,field):
 p=origin['origin']/'strategy_metrics.json';d=json.loads(p.read_bytes());d[0]['periods']['before']={'observations':0,'requested_start':'2023-01-01','requested_end':'2023-12-31',field:0};p.write_bytes(encoded(d));repin(origin)
 with pytest.raises(ValueError,match='Empty sample'):emit(origin)
def test_macro_attachment_binding_checks_both_bytes(origin):
 p=origin['origin']/'implemented_specs.json';d=json.loads(p.read_bytes());d[0].update(assets=['S','UNRATE'],price_assets=['S'],signal_only_assets=['UNRATE']);p.write_bytes(encoded(d))
 raw=b'date,value\n2020-01-01,4\n';norm=b'date,macro_value\n2020-01-01,4\n';decl={'datasets':[{'symbol':'UNRATE','layer':'signal_only','normalized_path':'/private/FRED_UNRATE.csv','normalized_sha256':digest(norm),'raw_path':'/private/raw_UNRATE.csv','raw_sha256':digest(raw)}]}
 pin(origin,{'signals/macro_signal_normalization_v1.json':encoded(decl),'signals/FRED_UNRATE.csv':norm,'signals/raw_UNRATE.csv':raw});repin(origin);emit(origin)
 got=json.loads((origin['export']/'run_manifest.json').read_bytes());assert got['metadata_enrichment']['signal_data_from_pinned_attachments']['UNRATE']['not_tradable_price'] is True

def test_macro_normalization_hash_conflict_rejected(origin):
 p=origin['origin']/'implemented_specs.json';d=json.loads(p.read_bytes());d[0].update(assets=['S','UNRATE'],price_assets=['S'],signal_only_assets=['UNRATE']);p.write_bytes(encoded(d))
 decl={'datasets':[{'symbol':'UNRATE','layer':'signal_only','normalized_path':'/private/FRED_UNRATE.csv','normalized_sha256':'a'*64,'raw_path':'/private/raw_UNRATE.csv','raw_sha256':'b'*64}]};pin(origin,{'signals/macro_signal_normalization_v1.json':encoded(decl),'signals/FRED_UNRATE.csv':b'x','signals/raw_UNRATE.csv':b'y'});repin(origin)
 with pytest.raises(ValueError,match='macro data declaration'):emit(origin)


def test_overlap_metadata_remains_explicit_not_silent_role_inference():
 from quantgraph.graph.corpus_export import _native_fields
 m={'assets':['S','UNRATE'],'signal_only_assets':['S','UNRATE']};s={'assets':['S','UNRATE'],'price_assets':['S'],'signal_only_assets':['S','UNRATE']}
 a,b=_native_fields(m,s);assert a['assets']==['S'];assert a['original_metric_universe_assets']==['S','UNRATE'];assert 'overlap' in a['signal_role_warning'];assert b['signal_only_assets']==['S','UNRATE']
def test_conflicting_overlap_metadata_is_rejected():
 from quantgraph.graph.corpus_export import _native_fields
 with pytest.raises(ValueError,match='identical explicit'):_native_fields({'assets':['S','UNRATE']},{'assets':['S','UNRATE'],'price_assets':['S'],'signal_only_assets':['S','UNRATE']})

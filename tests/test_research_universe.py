import gzip
import hashlib
import json
import sqlite3

import pytest

from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.catalog_projection import item
from quantgraph.graph.research_universe import import_universe, read_universe


def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True).encode()
def sha(value):return hashlib.sha256(value).hexdigest()


def release(tmp_path, *, rule='合成规则', market='合成市场', version='synthetic-scope-v1'):
    cat=CatalogRepository(tmp_path/'catalog.sqlite')
    value=item('strategy','synthetic:strategy','Synthetic','StrategyVariant','catalog-definition',source_native_ids=['M0001'])
    raw={'raw_record':{'规则':'合成规则','市场':'合成市场'},'variant':{'original_rule_text':'合成规则','source_native_id':'M0001'}}
    with cat.connect() as con:cat._put(con,value,'synthetic',raw)
    rows=[dict(record_id='M0001',identity_namespace='grok_final_6973',entity_type='legacy_pending_review',
               definition_text=rule,definition_sha256=sha(rule.encode()),raw_record={'规则':rule,'市场':market})]
    folder=tmp_path/'release';folder.mkdir(exist_ok=True)
    blobs={'universe.jsonl.gz':gzip.compress(b'\n'.join(encoded(r) for r in rows),mtime=0),
           'summary.json':encoded({'total_research_objects_in_scope':1})}
    for name,b in blobs.items():(folder/name).write_bytes(b)
    manifest={'schema_version':'quant-research-universe-manifest/v1','version':version,'files':{n:sha(b) for n,b in blobs.items()}}
    data=encoded(manifest);(folder/'manifest.json').write_bytes(data)
    return cat,folder,sha(data)


def test_worklist_binds_real_definition_and_preserves_immutable_history(tmp_path):
    cat,folder,pin=release(tmp_path)
    assert import_universe(cat,folder,pin)['records']==1
    result=read_universe(cat)
    assert result['records'][0]['definition_revision']=='catalog-definition'
    assert result['records'][0]['binding_kind']=='EXACT_RETAINED_RULE_MARKET_AND_SOURCE'
    assert import_universe(cat,folder,pin)['replayed']
    with cat.connect() as con:
        with pytest.raises(sqlite3.IntegrityError):con.execute('DELETE FROM research_universe_records')
    data=json.loads((folder/'manifest.json').read_text());data['extra']='changed';(folder/'manifest.json').write_bytes(encoded(data))
    with pytest.raises(ValueError,match='immutable'):import_universe(cat,folder,sha(encoded(data)))


@pytest.mark.parametrize('field,value',[('rule','另一规则'),('market','另一个市场')])
def test_same_native_id_is_not_enough_for_worklist_binding(tmp_path,field,value):
    cat,folder,pin=release(tmp_path,**{field:value})
    with pytest.raises(ValueError,match='differs|differ'):import_universe(cat,folder,pin)
    assert read_universe(cat) is None


def test_worklist_files_and_native_ids_are_pinned(tmp_path):
    cat,folder,pin=release(tmp_path)
    (folder/'summary.json').write_bytes(encoded({'total_research_objects_in_scope':999}))
    with pytest.raises(ValueError,match='digest'):import_universe(cat,folder,pin)
    assert read_universe(cat) is None

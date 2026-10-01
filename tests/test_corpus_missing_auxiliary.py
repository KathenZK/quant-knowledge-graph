import json
import pytest
from quantgraph.graph.corpus_export import export_delta
from quantgraph.graph.corpus_research import CorpusResearch,build_manifest,import_manifest
from test_corpus_export import origin  # noqa: F401
from test_corpus_research import collection,encoded,digest  # noqa: F401

def remove_aux(o):
 (o['origin']/'target_hashes.json').unlink();p=o['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['result_hashes'].pop('target_hashes.json');p.write_bytes(encoded(m))

def export(o):return export_delta(o['origin'],o['protocol'],o['audit'],o['export'],format_version=3)

def test_absence_is_explicit_and_original_manifest_unchanged(origin):
 remove_aux(origin);old=(origin['origin']/'run_manifest.json').read_bytes();r=export(origin);import_manifest(origin['runtime'],origin['export']/'import-manifest.json',r['manifest_sha256'],origin['export'],origin['export']);assert (origin['origin']/'run_manifest.json').read_bytes()==old;assert not (origin['origin']/'target_hashes.json').exists()
 mark=json.loads((origin['export']/'origin__target_hashes.json').read_bytes());assert mark['not_a_target_hash'] is True and mark['origin_manifest_sha256']==digest(old)
 data=CorpusResearch(origin['runtime']).implementation('R1@A')['lineage']['declared_lineage'];assert data['source_run_manifest_sha256']==digest(old);assert data['metadata_enrichment']['unavailable_origin_auxiliary_artifacts']==['target_hashes.json'];assert data['origin_artifacts']['origin__target_hashes.json']['representation']=='explicit_absence_receipt_not_source_artifact'

def test_declared_but_missing_hash_still_rejected(origin):
 (origin['origin']/'target_hashes.json').unlink()
 with pytest.raises(ValueError):export(origin)

def test_unpinned_existing_hash_file_rejected(origin):
 p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['result_hashes'].pop('target_hashes.json');p.write_bytes(encoded(m))
 with pytest.raises(ValueError):export(origin)

def test_broken_symlink_not_absence(origin):
 remove_aux(origin);(origin['origin']/'target_hashes.json').symlink_to(origin['origin']/'not-present.json')
 with pytest.raises(ValueError):export(origin)

def test_forged_absence_receipt_rejected_on_reimport(origin):
 remove_aux(origin);export(origin);p=origin['export']/'origin__target_hashes.json';m=json.loads(p.read_bytes());m['origin_manifest_sha256']='a'*64;p.unlink();p.write_bytes(encoded(m));q=origin['root']/'repin.json';r=build_manifest(origin['export'],origin['export'],q)
 with pytest.raises(ValueError):import_manifest(origin['runtime'],q,r['manifest_sha256'],origin['export'],origin['export'])

@pytest.mark.parametrize('name',['strategy_metrics.json','daily_returns.csv.gz','implemented_specs.json'])
def test_no_other_missing_artifact_relaxed(origin,name):
 (origin['origin']/name).unlink()
 with pytest.raises(ValueError):export(origin)

def test_calendar_ledger_code_inputs_are_inert_hash_pinned(origin):
 remove_aux(origin)
 items={'ledgers/R1@A/daily_book.csv.gz':b'opaque notexecuted','ledgers/R1@A/signal_decisions.json':b'{}','code/research.py':b'raise AssertionError("never execute")','inputs/S.csv':b'date,close\n2024-01-01,100\n','research_summaries.md':b'Untrustedsource notes'}
 p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes())
 for name,value in items.items():
  t=origin['origin']/name;t.parent.mkdir(parents=True,exist_ok=True);t.write_bytes(value);m['result_hashes'][name]=digest(value)
 p.write_bytes(encoded(m));r=export(origin);import_manifest(origin['runtime'],origin['export']/'import-manifest.json',r['manifest_sha256'],origin['export'],origin['export'])
 got=json.loads((origin['export']/'origin-attachments.json').read_bytes())['artifacts'];assert all(got[name]['sha256']==digest(value) for name,value in items.items())

@pytest.mark.parametrize('name',['code/../../run.py','code/run.sh','code/sub/run.py','inputs/S.exe','ledgers/../../x.csv.gz','ledgers/R1@A/private.txt','ledgers/R1@A/nested/daily_book.csv.gz'])
def test_calendar_attachments_do_not_relax_path_or_type_guards(origin,name):
 p=origin['origin']/'run_manifest.json';m=json.loads(p.read_bytes());m['result_hashes'][name]='a'*64;p.write_bytes(encoded(m))
 with pytest.raises(ValueError):export(origin)

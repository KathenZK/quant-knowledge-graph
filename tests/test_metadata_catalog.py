"""Synthetic eleven-column CSV only; full private catalog is never a CI input."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import shutil

import pytest

from quantgraph.graph.metadata_catalog import (
    BATCH, FORMAT, canonical_hash, create_plan, load_csv, read_checkpoint,
    resume_report, stage_batch,
)
from quantgraph.graph.metadata_pilot import digest, encoded, prepare, validate
from tests.test_metadata_pilot import synthetic_lab, metadata  # noqa: F401 -- shared synthetic fixture

ROOT=Path(__file__).resolve().parents[1]


def write_csv(path,rows):
    buf=io.StringIO(newline='');w=csv.DictWriter(buf,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows);raw=buf.getvalue().encode();path.write_bytes(raw)
    numbers=[int(r['id'].strip()[1:]) for r in rows]
    return dict(sha256=digest(raw),bytes=len(raw),rows=len(rows),min_id=min(numbers),max_id=max(numbers),gaps=max(numbers)-min(numbers)+1-len(set(numbers)))


def row(rid,rule='日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。'):
    return dict(id=rid,名称='Synthetic '+rid,市场='synthetic',规则=rule,作者或机构='Synthetic only',标题='Synthetic source',source_url='https://example.org/method?page=1',页码或文件='example',可回测='高',别名来源='',提出日期='UNKNOWN')


@pytest.fixture
def source(tmp_path):
    path=tmp_path/'synthetic.csv';rows=[row('M0001'),row('M0003'),row('M0004','No supported rules.\nNEVER_COPY_PRIVATE_ORIGINAL_FULLTEXT')]
    return path,rows,write_csv(path,rows)


def plan(tmp_path,source,**kwargs):
    path,rows,contract=source;out=tmp_path/'plan'
    result=create_plan(path,ROOT/'metadata',out,contract=contract,batch_size=2,**kwargs)
    return out,result['plan_sha256'],result


def decisions(tmp_path,source,types=None):
    types=types or {'M0001':'strategy','M0004':'factor'}
    p=tmp_path/'decisions.json';records=[]
    for r in source[1]:
        if r['id'] in types:records.append(dict(record_id=r['id'],row_sha256=canonical_hash(r),entity_type=types[r['id']],reason='Explicit synthetic reviewer decision; not keyword inference',evidence=['https://example.org/review']))
    p.write_bytes(encoded(dict(schema_version='quantgraph-csv-type-decisions/v1',records=records)))
    return dict(decisions_path=p,decisions_sha256=digest(p.read_bytes()))


def test_all_unknown_inventory_preserves_ids_and_reports_duplicate_candidates(tmp_path,source):
    p,pin,report=plan(tmp_path,source)
    assert report['counts']==dict(input_rows=3,unique_original_ids=3,strategies=0,factors=0,unresolved=3,duplicate_definition_candidate_groups=1)
    m=read_checkpoint(p,pin,FORMAT);inv=json.loads((p/'inventory.json').read_bytes())
    assert m['stable_id_gaps']==['M0002'] and [r['record_id'] for r in inv]==['M0001','M0003','M0004']
    assert all(r['type_status']=='UNREVIEWED' and r['entity_type'] is None for r in inv)
    body=b''.join(x.read_bytes() for x in p.rglob('*') if x.is_file())
    assert b'NEVER_COPY_PRIVATE_ORIGINAL_FULLTEXT' not in body
    assert all(source[1][i]['规则'].encode() not in body for i in range(3))
    assert m['duplicate_definition_candidates'][0]['record_ids']==['M0001','M0003']
    assert m['duplicates_merged']==0


def test_resume_counts_complete_inventory_separately_from_classified_folders(tmp_path,source):
    p,pin,_=plan(tmp_path,source);checkpoints=[]
    for bid in ['batch-0001','batch-0002']:
        output=tmp_path/bid;result=stage_batch(p,pin,source[0],bid,output);checkpoints.append((output,result['checkpoint_sha256']))
    report=resume_report(p,pin,checkpoints)
    assert report['inventory_complete'] and not report['classified_folders_complete']
    assert report['completed_counts']['unresolved']==3 and report['completed_counts']['metadata_records']==0
    assert report['remaining_batches']==[] and not report['remote_persistence_verified']
    with pytest.raises(ValueError,match='Duplicate checkpoint'):resume_report(p,pin,checkpoints+checkpoints[:1])


def test_explicit_row_pinned_decisions_generate_facts_without_fulltext(tmp_path,source):
    p,pin,_=plan(tmp_path,source,**decisions(tmp_path,source));output=tmp_path/'stage'
    result=stage_batch(p,pin,source[0],'batch-0001',output)
    r=validate(output/'metadata')[0]
    assert result['counts']['metadata_records']==1 and result['counts']['unresolved']==1
    assert r['record_id']=='M0001' and r['lab'] is None
    assert r['catalog_origin']['original_classification'] is None
    assert r['catalog_origin']['type_status']=='REVIEWED_EXPLICIT_DECISION'
    assert r['strategy_fields']['entry']['status']=='CATALOG_REPORTED_UNVERIFIED'
    assert r['strategy_fields']['cost']['status']=='MISSING'
    assert r['sources'][0]['sha256'] is None and r['sources'][0]['verification']=='NOT_FETCHED_REFERENCE_ONLY'
    assert r['economic_basis']['status']=='MISSING' and not r['economic_basis']['paper_support']
    assert source[1][0]['规则'].encode() not in (output/'metadata/strategies/M0001.json').read_bytes()
    stage_batch(p,pin,source[0],'batch-0002',tmp_path/'factor')
    factor=validate(tmp_path/'factor/metadata')[0]
    assert factor['entity_type']=='factor' and all(x['status']=='MISSING' for x in factor['factor_fields'].values())


def test_checkpoint_rebuild_is_exact_and_output_is_create_only(tmp_path,source):
    p,pin,_=plan(tmp_path,source,**decisions(tmp_path,source));a,b=tmp_path/'a',tmp_path/'b'
    assert stage_batch(p,pin,source[0],'batch-0001',a)==stage_batch(p,pin,source[0],'batch-0001',b)
    def files(x):return {str(f.relative_to(x)):digest(f.read_bytes()) for f in x.rglob('*') if f.is_file()}
    assert files(a)==files(b)
    with pytest.raises(ValueError,match='exists'):stage_batch(p,pin,source[0],'batch-0001',a)
    with pytest.raises(ValueError,match='Unknown planned'):stage_batch(p,pin,source[0],'batch-9999',tmp_path/'wrong')


def test_csv_byte_hash_count_header_duplicate_and_id_gaps_are_hard_gates(tmp_path,source):
    path,rows,contract=source
    bad=dict(contract,sha256='0'*64)
    with pytest.raises(ValueError,match='hash'):load_csv(path,bad)
    with pytest.raises(ValueError,match='extent'):load_csv(path,dict(contract,gaps=0))
    duplicate=[rows[0],rows[0]];c=write_csv(path,duplicate)
    with pytest.raises(ValueError,match='unique'):load_csv(path,c)
    malformed=deepcopy(rows);malformed[0]['id']=' M0001';c=write_csv(path,malformed)
    with pytest.raises(ValueError,match='never trim'):load_csv(path,c)


def test_wrong_row_decision_and_new_id_do_not_create_output(tmp_path,source):
    kw=decisions(tmp_path,source);p=kw['decisions_path'];v=json.loads(p.read_bytes());v['records'][0]['row_sha256']='0'*64;p.write_bytes(encoded(v));kw['decisions_sha256']=digest(p.read_bytes())
    with pytest.raises(ValueError,match='different CSV row'):plan(tmp_path,source,**kw)
    assert not (tmp_path/'plan').exists()
    v['records'][0]['record_id']='M9999';p.write_bytes(encoded(v));kw['decisions_sha256']=digest(p.read_bytes())
    with pytest.raises(ValueError,match='new IDs'):plan(tmp_path,source,**kw)


def test_existing_reviewed_records_keep_bytes_and_type_evidence(tmp_path):
    rows=[row('M0256'),row('M0259')];path=tmp_path/'source.csv';contract=write_csv(path,rows)
    p=tmp_path/'plan';result=create_plan(path,ROOT/'metadata',p,contract=contract)
    out=tmp_path/'stage';stage_batch(p,result['plan_sha256'],path,'batch-0001',out)
    for rid in ['M0256','M0259']:
        assert (out/f'metadata/strategies/{rid}.json').read_bytes()==(ROOT/f'metadata/strategies/{rid}.json').read_bytes()
    inv=json.loads((out/'inventory.json').read_bytes())
    assert all(r['type_status']=='EXISTING_REVIEWED_METADATA' and r['original_classification'] is None for r in inv)


def test_incomplete_or_tampered_checkpoint_not_counted(tmp_path,source):
    p,pin,_=plan(tmp_path,source);out=tmp_path/'stage';r=stage_batch(p,pin,source[0],'batch-0001',out)
    (out/'inventory.json').write_bytes(b'[]')
    with pytest.raises(ValueError,match='digest'):resume_report(p,pin,[(out,r['checkpoint_sha256'])])
    partial=tmp_path/'interrupted';partial.mkdir()
    with pytest.raises(ValueError):resume_report(p,pin,[(partial,'0'*64)])


def test_untrusted_counts_rejected_even_with_new_manifest_pin(tmp_path,source):
    p,pin,_=plan(tmp_path,source);out=tmp_path/'stage';stage_batch(p,pin,source[0],'batch-0001',out)
    m=json.loads((out/'manifest.json').read_bytes());m['counts']['metadata_records']=6973;(out/'manifest.json').write_bytes(encoded(m))
    with pytest.raises(ValueError,match='counts'):resume_report(p,pin,[(out,digest((out/'manifest.json').read_bytes()))])


def test_source_links_remove_secrets_without_exporting_original_string(tmp_path,source):
    path,rows,_=source;rows[0]['source_url']='https://example.org/paper?id=7&token=never-export-this';contract=write_csv(path,rows)
    p=tmp_path/'plan';create_plan(path,ROOT/'metadata',p,contract=contract)
    inv=json.loads((p/'inventory.json').read_bytes())
    assert inv[0]['source_url']=='https://example.org/paper?id=7'
    assert inv[0]['source_link_status']=='SANITIZED_UNVERIFIED_REFERENCE'
    assert b'never-export-this' not in (p/'inventory.json').read_bytes()


def test_growing_metadata_catalog_does_not_expand_replay_pilot(metadata,synthetic_lab,tmp_path):
    v=json.loads((metadata/'strategies/M0256.json').read_bytes());v.update(record_id='M0001',native_source_id='M0001',lab=None)
    for field in v['strategy_fields'].values():field['evidence']=['strategy-source']
    path=metadata/'strategies/M0001.json';path.write_bytes(encoded(v))
    idx=json.loads((metadata/'index.json').read_bytes());idx['records'].append(dict(path='strategies/M0001.json',bytes=path.stat().st_size,sha256=digest(path.read_bytes()),record_id='M0001',entity_type='strategy',identity_namespace='grokbot'));(metadata/'index.json').write_bytes(encoded(idx))
    assert len(validate(metadata))==3
    result=prepare(metadata,synthetic_lab,tmp_path/'pilot')
    assert result['counts']['strategy_ids']==2 and result['counts']['new_trials']==0
    assert sorted(p.name for p in (tmp_path/'pilot/records').iterdir())==['M0256.json','M0259.json']


def test_full_6973_inventory_larger_than_eight_mib_is_bounded_and_resumable(tmp_path):
    numbers=list(range(1,6973))+[7019]
    rows=[row(f'M{n:04d}',rule='Unsupported synthetic rule; never copied.') for n in numbers]
    for r in rows:r['名称']='Synthetic '+('x'*220)
    path=tmp_path/'large.csv';contract=write_csv(path,rows)
    p=tmp_path/'large-plan';result=create_plan(path,ROOT/'metadata',p,contract=contract,batch_size=100)
    assert (p/'inventory.json').stat().st_size > 8*1024**2
    assert result['counts']['input_rows']==result['counts']['unique_original_ids']==6973
    m=read_checkpoint(p,result['plan_sha256'],FORMAT)
    assert len(m['stable_id_gaps'])==46 and len(m['batches'])==70
    out=tmp_path/'large-last-batch';b=stage_batch(p,result['plan_sha256'],path,'batch-0070',out)
    assert b['counts']['inventory_ids']==73
    report=resume_report(p,result['plan_sha256'],[(out,b['checkpoint_sha256'])])
    assert report['completed_counts']['inventory_ids']==73 and len(report['remaining_batches'])==69


def test_nested_indicator_input_is_not_silently_lost_in_summary(tmp_path,source):
    path,rows,_=source;rows[0]['规则']='日频：若 OBV>EMA(20 of OBV) → 满仓 QQQ，否则 SHV。';contract=write_csv(path,rows)
    source=(path,rows,contract);p,pin,_=plan(tmp_path,source,**decisions(tmp_path,source));out=tmp_path/'stage'
    stage_batch(p,pin,path,'batch-0001',out)
    value=validate(out/'metadata')[0]
    assert value['catalog_origin']['parser']['rule_type']=='threshold_switch'
    assert all(field['status']=='MISSING' for field in value['strategy_fields'].values())

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
    resume_report, stage_batch, recover_rows,
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
    path=tmp_path/'synthetic.csv';rows=[row('M0001'),row('M0003'),row('M0004','Unsupported collected summary.\nCOLLECTED_RULE_KEEP_EXACT')]
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
    assert recover_rows(p,pin)==source[1]
    for entry,original in zip(inv,source[1]):
        record=json.loads((p/entry['knowledge_record']['path']).read_bytes())
        assert {k:v['value'] for k,v in record['reported_fields'].items()}==original
        assert all(v['status']=='CATALOG_REPORTED_UNVERIFIED' for v in record['reported_fields'].values())
        assert record['entity_type']=='source_record' and record['classification']['type_status']=='UNREVIEWED'
    assert m['duplicate_definition_candidates'][0]['record_ids']==['M0001','M0003']
    assert m['duplicates_merged']==0


def test_resume_counts_complete_inventory_separately_from_classified_folders(tmp_path,source):
    p,pin,_=plan(tmp_path,source);checkpoints=[]
    for bid in ['batch-0001','batch-0002']:
        output=tmp_path/bid;result=stage_batch(p,pin,source[0],bid,output);checkpoints.append((output,result['checkpoint_sha256']))
    report=resume_report(p,pin,checkpoints)
    assert report['inventory_complete'] and not report['classified_folders_complete']
    assert report['completed_counts']['unresolved']==3 and report['completed_counts']['metadata_records']==3
    assert report['completed_counts']['knowledge_records']==3 and report['completed_counts']['classified_records']==0
    assert report['knowledge_values_complete'] and report['source_rows']==3
    assert report['remaining_batches']==[] and not report['remote_persistence_verified']
    with pytest.raises(ValueError,match='Duplicate checkpoint'):resume_report(p,pin,checkpoints+checkpoints[:1])


def test_explicit_row_pinned_decisions_generate_facts_without_fulltext(tmp_path,source):
    p,pin,_=plan(tmp_path,source,**decisions(tmp_path,source));output=tmp_path/'stage'
    result=stage_batch(p,pin,source[0],'batch-0001',output)
    r=next(r for r in validate(output/'metadata') if r['entity_type']=='strategy')
    assert result['counts']['classified_records']==1 and result['counts']['unresolved']==1
    assert r['record_id']=='M0001' and r['lab'] is None
    assert r['catalog_origin']['original_classification'] is None
    assert r['catalog_origin']['type_status']=='REVIEWED_EXPLICIT_DECISION'
    assert r['strategy_fields']['entry']['status']=='CATALOG_REPORTED_UNVERIFIED'
    assert r['strategy_fields']['cost']['status']=='MISSING'
    assert r['sources'][0]['sha256'] is None and r['sources'][0]['verification']=='NOT_FETCHED_REFERENCE_ONLY'
    assert r['economic_basis']['status']=='MISSING' and not r['economic_basis']['paper_support']
    assert source[1][0]['规则'].encode() not in (output/'metadata/strategies/M0001.json').read_bytes()
    stage_batch(p,pin,source[0],'batch-0002',tmp_path/'factor')
    factor=next(r for r in validate(tmp_path/'factor/metadata') if r['entity_type']=='factor')
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
    assert inv[0]['source_url'] is None
    assert inv[0]['source_link_status']=='PRIVATE_ONLY_BLOCKED'
    recovered=recover_rows(p,digest((p/'manifest.json').read_bytes()))
    assert recovered==rows
    assert inv[0]['knowledge_record']['path']=='private-only/source-records/M0001.json'
    assert not (p/'metadata/source-records/M0001.json').exists()
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
    assert recover_rows(out,b['checkpoint_sha256'],checkpoint_format=BATCH)==rows[-73:]
    report=resume_report(p,result['plan_sha256'],[(out,b['checkpoint_sha256'])])
    assert report['completed_counts']['inventory_ids']==73 and len(report['remaining_batches'])==69


def test_nested_indicator_input_is_not_silently_lost_in_summary(tmp_path,source):
    path,rows,_=source;rows[0]['规则']='日频：若 OBV>EMA(20 of OBV) → 满仓 QQQ，否则 SHV。';contract=write_csv(path,rows)
    source=(path,rows,contract);p,pin,_=plan(tmp_path,source,**decisions(tmp_path,source));out=tmp_path/'stage'
    stage_batch(p,pin,path,'batch-0001',out)
    value=next(r for r in validate(out/'metadata') if r['entity_type']=='strategy')
    assert value['catalog_origin']['parser']['rule_type']=='threshold_switch'
    assert all(field['status']=='MISSING' for field in value['strategy_fields'].values())


def test_unknown_preserves_every_original_value_and_restores_without_csv(tmp_path,source):
    path,rows,_=source
    rows[0].update(名称='标题'*86,市场='原市场说明'*21,规则='完整自撰采集交易规则：'+('均线条件；'*430)+'\n"保留引号、换行、空格  "',
                   作者或机构='原目录作者'*24,标题='论文标题未核实'*24,页码或文件='第 7 页；公式 A。'*20,
                   别名来源='',可回测='原标签：高（不是执行许可）',提出日期='原标签：日期未核')
    source=(path,rows,write_csv(path,rows));p,pin,_=plan(tmp_path,source)
    assert len(rows[0]['规则'])>1989-20
    path.rename(tmp_path/'source-no-longer-at-input-path.csv')
    assert recover_rows(p,pin)==rows
    out=tmp_path/'recovered-batch';r=stage_batch(p,pin,None,'batch-0001',out)
    assert recover_rows(out,r['checkpoint_sha256'],checkpoint_format=BATCH)==rows[:2]
    rec=json.loads((out/'metadata/source-records/M0001.json').read_bytes())
    assert rec['reported_fields']['规则']['value']==rows[0]['规则']
    assert rec['reported_fields']['页码或文件']['value']==rows[0]['页码或文件']
    assert rec['classification']['entity_type'] is None and rec['classification']['type_status']=='UNREVIEWED'
    assert not rec['source_webpage_fulltext_fetched'] and not rec['execution_permission_granted']


@pytest.mark.parametrize('field,value,code',[
    ('规则','已采集规则；token=synthetic-secret-314','CREDENTIAL_OR_SIGNED_URL'),
    ('别名来源','libfile_abcdef1234567890','PRIVATE_LIBRARY_OR_APP_REFERENCE'),
    ('页码或文件','/workspace/private-annotation.txt','LOCAL_PATH'),
    ('页码或文件',r'C:\Users\test\private-note.txt','LOCAL_PATH'),
    ('source_url','https://example.org/paper?X-Amz-Signature=synthetic-signature','CREDENTIAL_OR_SIGNED_URL'),
    ('作者或机构','私人批注：真实姓名仅供私人','PRIVATE_ANNOTATION'),
    ('标题','https://user:synthetic-password@example.org/','URL_USERINFO'),
])
def test_sensitive_values_are_exact_private_only_and_never_in_public_candidates(tmp_path,source,field,value,code):
    path,rows,_=source;rows[0][field]=value;source=(path,rows,write_csv(path,rows))
    p,pin,_=plan(tmp_path,source,**decisions(tmp_path,source))
    inv=json.loads((p/'inventory.json').read_bytes());entry=inv[0]
    assert entry['publication']['status']=='PRIVATE_ONLY_BLOCKED'
    assert field in entry['publication']['sensitive_fields'] and code in entry['publication']['reason_codes']
    assert recover_rows(p,pin)==rows
    out=tmp_path/'stage';result=stage_batch(p,pin,path,'batch-0001',out)
    assert result['publication_status']=='PRIVATE_ONLY_BLOCKED' and result['counts']['private_only_records']==1
    assert not (out/'metadata/source-records/M0001.json').exists()
    assert not (out/'metadata/strategies/M0001.json').exists()
    assert recover_rows(out,result['checkpoint_sha256'],checkpoint_format=BATCH)==rows[:2]
    for f in (out/'metadata').rglob('*'):
        if f.is_file():assert value.encode() not in f.read_bytes()
    assert value.encode() not in (out/'inventory.json').read_bytes()
    report=resume_report(p,pin,[(out,result['checkpoint_sha256'])])
    assert report['completed_counts']['knowledge_records']==2
    assert not report['public_publication_complete'] and not report['public_review_candidate_coverage_complete']


def test_source_layer_does_not_double_original_ids_or_change_reviewed_files(tmp_path):
    rows=[row('M0256'),row('M0259')];path=tmp_path/'input.csv';contract=write_csv(path,rows)
    p=tmp_path/'plan';r=create_plan(path,ROOT/'metadata',p,contract=contract)
    out=tmp_path/'stage';b=stage_batch(p,r['plan_sha256'],path,'batch-0001',out)
    report=resume_report(p,r['plan_sha256'],[(out,b['checkpoint_sha256'])])
    assert report['source_rows']==report['completed_counts']['inventory_ids']==2
    assert report['completed_counts']['metadata_records']==4
    assert report['completed_counts']['knowledge_records']==report['completed_counts']['classified_records']==2
    assert recover_rows(out,b['checkpoint_sha256'],checkpoint_format=BATCH)==rows
    for rid in ['M0256','M0259']:
        assert (out/f'metadata/strategies/{rid}.json').read_bytes()==(ROOT/f'metadata/strategies/{rid}.json').read_bytes()


def test_forged_public_flag_cannot_hide_sensitive_source_fields(tmp_path,source):
    path,rows,_=source;rows[0]['标题']='个人批注：不要公开';source=(path,rows,write_csv(path,rows))
    p,pin,_=plan(tmp_path,source);out=tmp_path/'stage';stage_batch(p,pin,path,'batch-0001',out)
    rec=json.loads((out/'private-only/source-records/M0001.json').read_bytes())
    rec['publication'].update(status='FIELD_REVIEW_REQUIRED',sensitive_fields=[],reason_codes=[])
    target=out/'metadata/source-records/M0001.json';target.write_bytes(encoded(rec))
    idx=json.loads((out/'metadata/index.json').read_bytes());idx['records'].append(dict(path='source-records/M0001.json',sha256=digest(target.read_bytes()),bytes=target.stat().st_size,record_id='M0001',identity_namespace='grokbot',entity_type='source_record'));(out/'metadata/index.json').write_bytes(encoded(idx))
    with pytest.raises(ValueError,match='Private-only'):validate(out/'metadata')

"""Synthetic-only tests for selective export of an immutable private checkpoint."""
import json
import subprocess
import sys

import pytest

from quantgraph.graph.metadata_catalog import create_plan, stage_batch
from quantgraph.graph.metadata_pilot import digest, encoded
from quantgraph.graph.metadata_public_subset import (
    create_public_subset, check_public_subset, restore_public_subset,
)
from tests.test_metadata_catalog import ROOT, row, write_csv


def snapshot(root):
    return {str(path.relative_to(root)):path.read_bytes() for path in root.rglob('*') if path.is_file()}


def repin(root):
    manifest=json.loads((root/'manifest.json').read_bytes())
    manifest['files']={name:dict(sha256=digest(raw),bytes=len(raw))
        for name,raw in snapshot(root).items() if name!='manifest.json'}
    raw=encoded(manifest);(root/'manifest.json').write_bytes(raw)
    return digest(raw)


def replace_json(path, mutate):
    value=json.loads(path.read_bytes());mutate(value);path.write_bytes(encoded(value))


@pytest.fixture
def mixed_batch(tmp_path):
    rows=[row(f'M{i:04d}', '采集规则；'+('完整规则；'*410)+f'\n编号 {i}') for i in range(1,101)]
    rows[34]['规则']='private-only token=synthetic-sensitive-rule'
    rows[34]['别名来源']='libfile_synthetic_only_excluded'
    rows[34]['页码或文件']='/workspace/synthetic-private-evidence.txt'
    csv=tmp_path/'synthetic.csv';contract=write_csv(csv,rows)
    plan=tmp_path/'plan';p=create_plan(csv,ROOT/'metadata',plan,contract=contract,batch_size=100)
    batch=tmp_path/'batch';b=stage_batch(plan,p['plan_sha256'],csv,'batch-0001',batch)
    return batch,b['checkpoint_sha256'],rows,plan


def test_mixed_subset_is_complete_for_99_only_and_original_bytes_never_change(tmp_path,mixed_batch):
    batch,pin,rows,plan=mixed_batch;before=snapshot(batch);plan_before=snapshot(plan)
    out=tmp_path/'subset';result=create_public_subset(batch,pin,out)
    report=check_public_subset(out,result['subset_sha256'])
    assert report['counts']==dict(source_batch_original_ids=100,included_original_ids=99,
        excluded_original_ids=1,source_records=99,metadata_records=99,strategies=0,factors=0,unresolved=99)
    assert result['excluded_record_ids']==['M0035'] and not result['public_sync_ready']
    assert not report['remote_persistence_verified']
    m=json.loads((out/'manifest.json').read_bytes())
    assert m['source_batch_sha256']==pin
    assert m['source_plan_sha256']==json.loads((batch/'manifest.json').read_bytes())['plan_sha256']
    private_file=batch/'private-only/source-records/M0035.json'
    forbidden=[rows[34]['规则'],rows[34]['别名来源'],rows[34]['页码或文件'],
               digest(private_file.read_bytes()),'private-only/source-records/M0035.json',str(batch)]
    for name,raw in snapshot(out).items():
        assert not name.startswith('private-only/')
        for value in forbidden:assert value.encode() not in raw
        if name.startswith('metadata/') and name!='metadata/index.json':assert raw==before[name]
    restored=tmp_path/'restored';receipt=restore_public_subset(out,result['subset_sha256'],restored)
    values=[json.loads(line) for line in (restored/'private-only/restored-records.jsonl').read_text().splitlines()]
    assert values==rows[:34]+rows[35:] and receipt['records']==99
    assert not receipt['original_batch_complete'] and not receipt['public_sync_ready']
    assert snapshot(batch)==before and snapshot(plan)==plan_before
    rebuilt=tmp_path/'rebuilt';assert create_public_subset(batch,pin,rebuilt)==result
    assert snapshot(rebuilt)==snapshot(out)
    with pytest.raises(ValueError,match='exists'):create_public_subset(batch,pin,out)


def test_wrong_pin_and_member_bytes_block_before_creating_output(tmp_path,mixed_batch):
    batch,pin,_,_=mixed_batch;out=tmp_path/'no-output'
    with pytest.raises(ValueError,match='source validation'):create_public_subset(batch,'0'*64,out)
    assert not out.exists()
    (batch/'metadata/source-records/M0001.json').write_text('{}')
    with pytest.raises(ValueError,match='source validation'):create_public_subset(batch,pin,out)
    assert not out.exists()


@pytest.mark.parametrize('listed',[False,True])
def test_unknown_extra_file_rejected_even_when_rehashed(tmp_path,mixed_batch,listed):
    batch,pin,_,_=mixed_batch;(batch/'unexpected.txt').write_text('synthetic unrelated text')
    if listed:pin=repin(batch)
    out=tmp_path/'no-output'
    with pytest.raises(ValueError,match='source validation'):create_public_subset(batch,pin,out)
    assert not out.exists()


@pytest.mark.parametrize('path',['../outside.json','/tmp/outside.json','metadata/../outside.json'])
def test_manifest_path_traversal_rejected(tmp_path,mixed_batch,path):
    batch,_,_,_=mixed_batch
    def mutate(m):m['files'][path]=dict(sha256='0'*64,bytes=0)
    replace_json(batch/'manifest.json',mutate);pin=digest((batch/'manifest.json').read_bytes())
    with pytest.raises(ValueError,match='source validation'):create_public_subset(batch,pin,tmp_path/'no-output')
    assert not (tmp_path/'no-output').exists()


def test_symlink_cannot_replace_member(tmp_path,mixed_batch):
    batch,_,_,_=mixed_batch;p=batch/'metadata/source-records/M0001.json'
    target=tmp_path/'external.json';p.rename(target);p.symlink_to(target)
    pin=repin(batch)
    with pytest.raises(ValueError,match='source validation'):create_public_subset(batch,pin,tmp_path/'no-output')


def test_forged_private_flag_rejected_without_echoing_private_values(tmp_path,mixed_batch):
    batch,_,rows,_=mixed_batch
    private=batch/'private-only/source-records/M0035.json';record=json.loads(private.read_bytes())
    record['publication']=dict(status='FIELD_REVIEW_REQUIRED',sensitive_fields=[],reason_codes=[],all_fields_reviewed=False)
    private.write_bytes(encoded(record))
    def mutate(inv):inv[34]['publication']=record['publication']
    replace_json(batch/'inventory.json',mutate);pin=repin(batch)
    with pytest.raises(ValueError,match='source validation') as error:
        create_public_subset(batch,pin,tmp_path/'no-output')
    assert rows[34]['规则'] not in str(error.value) and not (tmp_path/'no-output').exists()


def test_private_content_moved_to_public_path_is_still_rejected(tmp_path,mixed_batch):
    batch,_,_,_=mixed_batch;private=batch/'private-only/source-records/M0035.json'
    record=json.loads(private.read_bytes());record['publication']=dict(status='FIELD_REVIEW_REQUIRED',sensitive_fields=[],reason_codes=[],all_fields_reviewed=False)
    target=batch/'metadata/source-records/M0035.json';target.write_bytes(encoded(record));private.unlink()
    ref=dict(path='source-records/M0035.json',sha256=digest(target.read_bytes()),bytes=target.stat().st_size,
             record_id='M0035',identity_namespace='grokbot',entity_type='source_record')
    replace_json(batch/'metadata/index.json',lambda index:index['records'].append(ref))
    def mutate(inv):
        inv[34]['publication']=record['publication'];inv[34]['knowledge_record']={key:ref[key] for key in ['sha256','bytes']}
        inv[34]['knowledge_record']['path']='metadata/'+ref['path']
    replace_json(batch/'inventory.json',mutate);pin=repin(batch)
    with pytest.raises(ValueError,match='source validation'):create_public_subset(batch,pin,tmp_path/'no-output')


@pytest.mark.parametrize('mutate',[
    lambda m:m.update(public_sync_ready=True),
    lambda m:m['counts'].update(included_original_ids=100),
    lambda m:m.update(excluded_record_ids=[]),
    lambda m:m.update(private_note='libfile_synthetic_secret'),
])
def test_forged_subset_claims_rejected(tmp_path,mixed_batch,mutate):
    batch,pin,_,_=mixed_batch;out=tmp_path/'subset';create_public_subset(batch,pin,out)
    replace_json(out/'manifest.json',mutate);newpin=digest((out/'manifest.json').read_bytes())
    with pytest.raises(ValueError,match='subset validation'):check_public_subset(out,newpin)
    with pytest.raises(ValueError,match='restore validation'):restore_public_subset(out,newpin,tmp_path/'no-restore')
    assert not (tmp_path/'no-restore').exists()


def test_subset_rejects_listed_extra_file_and_unexpected_inventory_fields(tmp_path,mixed_batch):
    batch,pin,_,_=mixed_batch;out=tmp_path/'subset';create_public_subset(batch,pin,out)
    replace_json(out/'inventory.json',lambda inv:inv[0].update(extra='libfile_synthetic_secret'))
    with pytest.raises(ValueError,match='subset validation'):check_public_subset(out,repin(out))
    (out/'extra.txt').write_text('extra')
    with pytest.raises(ValueError,match='subset validation'):check_public_subset(out,repin(out))


def test_review_layers_keep_bytes_without_double_counting_original_ids(tmp_path):
    rows=[row('M0256'),row('M0259'),row('M0260','sig=synthetic-sensitive')]
    csv=tmp_path/'source.csv';contract=write_csv(csv,rows);plan=tmp_path/'plan'
    p=create_plan(csv,ROOT/'metadata',plan,contract=contract);batch=tmp_path/'batch'
    b=stage_batch(plan,p['plan_sha256'],csv,'batch-0001',batch);out=tmp_path/'subset'
    result=create_public_subset(batch,b['checkpoint_sha256'],out)
    assert result['counts']['included_original_ids']==2 and result['counts']['metadata_records']==4
    assert result['counts']['strategies']==2 and result['excluded_record_ids']==['M0260']
    for rid in ['M0256','M0259']:
        name=f'metadata/strategies/{rid}.json';assert (out/name).read_bytes()==(batch/name).read_bytes()
    assert check_public_subset(out,result['subset_sha256'])['counts']==result['counts']


def test_cli_subcommands_preserve_old_restore_contract(tmp_path,mixed_batch):
    batch,pin,_,_=mixed_batch;out=tmp_path/'subset'
    command=[sys.executable,'-m','quantgraph.graph.metadata_catalog']
    def call(*args):
        result=subprocess.run(command+list(map(str,args)),cwd=ROOT,text=True,capture_output=True,check=True)
        return json.loads(result.stdout)
    made=call('public-subset','--checkpoint',batch,'--sha256',pin,'--output',out)
    check=call('check-public-subset','--checkpoint',out,'--sha256',made['subset_sha256'])
    assert check['counts']['included_original_ids']==99
    restored=call('restore-public-subset','--checkpoint',out,'--sha256',made['subset_sha256'],'--output',tmp_path/'restore-subset')
    assert restored['records']==99
    original=call('restore','--checkpoint',batch,'--sha256',pin,'--kind','batch','--output',tmp_path/'restore-original')
    assert original['records']==100

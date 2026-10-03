"""Reading views retain original values without creating or changing native definitions."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from quantgraph.graph.metadata_catalog import create_plan, stage_batch
from quantgraph.graph.metadata_directory import prepare_directory, validate_directory, render
from quantgraph.graph.metadata_pilot import digest, encoded, validate
from tests.test_metadata_catalog import row, write_csv

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def directory_input(tmp_path):
    metadata=tmp_path/'metadata';metadata.mkdir()
    for name in ['schema.json','source-record.schema.json','index.json','strategies/M0256.json','strategies/M0259.json']:
        dest=metadata/name;dest.parent.mkdir(exist_ok=True);dest.write_bytes((ROOT/'metadata'/name).read_bytes())
    rows=[row('M0256','持有资产；完整规则'*200+'\n```原文引号与换行```'),row('M0257','信号 = 盈利 / 价格；原采集公式。'),row('M0259','模型主题，规则未明确。')]
    rows[0]['名称']='原名称<script>不执行</script>';rows[0]['别名来源']='';rows[0]['页码或文件']='第1页\n第二行'
    csv=tmp_path/'source.csv';contract=write_csv(csv,rows);plan=tmp_path/'plan'
    p=create_plan(csv,metadata,plan,contract=contract)
    rel='corpus-checkpoints/synthetic/batches/batch-0001-v2'
    batch=metadata/rel;batch.parent.mkdir(parents=True)
    b=stage_batch(plan,p['plan_sha256'],csv,'batch-0001',batch)
    decisions=[]
    for item,kind in zip(rows,['strategy','factor','unclassified']):
        record=json.loads((batch/f"metadata/source-records/{item['id']}.json").read_bytes())
        decisions.append(dict(record_id=item['id'],row_sha256=record['provenance']['row_sha256'],
            rule_sha256=record['provenance']['rule_sha256'],entity_type=kind,reason='明确的合成内容分类，定义仍未核实。',
            evidence=[dict(field='规则',quote=item['规则'])]))
    return metadata,dict(path=rel,sha256=b['checkpoint_sha256'],commit='a'*40),decisions,rows


def install(root,stage):
    for file in stage.rglob('*'):
        if file.is_file():
            dest=root/file.relative_to(stage);dest.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(file,dest)


def test_complete_eleven_values_and_native_overlays_preserved(directory_input,tmp_path):
    root,batch,decisions,rows=directory_input
    before={name:(root/name).read_bytes() for name in ['index.json','schema.json','strategies/M0256.json','strategies/M0259.json']}
    out=tmp_path/'views';result=prepare_directory(root,batch,decisions,out);install(root,out)
    manifest=validate_directory(root)
    assert result['counts']==dict(readable_original_ids=3,strategy_candidates=1,factor_candidates=1,unclassified=1,new_native_definitions=0,new_execution_trials=0)
    for original,entry in zip(rows,manifest['records']):
        text=(root/entry['view']['path']).read_text()
        for value in original.values():assert value in text or value==original['名称']
        assert 'CATALOG_REPORTED_UNVERIFIED' in text and 'CONTENT_INFERRED' in text
        assert '/blob/'+'a'*40 in entry['source']['url']
    assert '````text' in (root/'strategies/M0256.md').read_text()
    assert '&lt;script&gt;' in (root/'strategies/M0256.md').read_text().splitlines()[0]
    assert 'EXISTING_REVIEWED_METADATA' in (root/'strategies/M0256.md').read_text()
    assert before=={name:(root/name).read_bytes() for name in before}
    assert len(validate(root))==2  # Markdown does not promote a third native JSON entity.
    with pytest.raises(ValueError,match='counted twice'):prepare_directory(root,batch,decisions,tmp_path/'duplicate')


@pytest.mark.parametrize('change',[
    lambda ds:ds.pop(),
    lambda ds:ds[0].update(row_sha256='0'*64),
    lambda ds:ds[0]['evidence'][0].update(quote='不存在的规则'),
    lambda ds:ds[0].update(evidence=[dict(field='名称',quote='原名称')]),
    lambda ds:ds[0].update(reason='libfile_synthetic_private'),
])
def test_no_missing_ids_or_unbound_name_only_or_private_decisions(directory_input,tmp_path,change):
    root,batch,decisions,_=directory_input;change(decisions)
    with pytest.raises(ValueError):prepare_directory(root,batch,decisions,tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def test_wrong_checkpoint_and_traversal_rejected(directory_input,tmp_path):
    root,batch,decisions,_=directory_input
    for changed in [dict(batch,sha256='0'*64),dict(batch,path='../outside')]:
        with pytest.raises(ValueError):prepare_directory(root,changed,decisions,tmp_path/'bad')
        assert not (tmp_path/'bad').exists()


def test_reading_view_cannot_lose_content_change_status_or_duplicate_counts(directory_input,tmp_path):
    root,batch,decisions,_=directory_input;out=tmp_path/'views'
    prepare_directory(root,batch,decisions,out);install(root,out)
    p=root/'strategies/M0256.md';raw=p.read_bytes();p.write_bytes(raw[:-50])
    with pytest.raises(ValueError,match='changed or lost'):validate_directory(root)
    p.write_bytes(raw)
    index=root/'directory-index.json';original=index.read_bytes();value=json.loads(original)
    value['definition_status']='REVIEWED';index.write_bytes(encoded(value))
    with pytest.raises(ValueError,match='promoted'):validate_directory(root)
    value=json.loads(original);value['counts']['readable_original_ids']=4;index.write_bytes(encoded(value))
    with pytest.raises(ValueError,match='counts'):validate_directory(root)


def test_rebuild_is_identical_and_existing_destination_refused(directory_input,tmp_path):
    root,batch,decisions,_=directory_input
    a,b=tmp_path/'a',tmp_path/'b'
    assert prepare_directory(root,batch,decisions,a)==prepare_directory(root,batch,decisions,b)
    assert {str(p.relative_to(a)):digest(p.read_bytes()) for p in a.rglob('*') if p.is_file()}=={str(p.relative_to(b)):digest(p.read_bytes()) for p in b.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='exists'):prepare_directory(root,batch,decisions,a)


def test_render_does_not_infer_a_type_without_explicit_evidence(directory_input):
    root,batch,decisions,_=directory_input
    raw=(root/batch['path']/'metadata/source-records/M0256.json').read_bytes();record=json.loads(raw)
    bad=deepcopy(decisions[0]);bad['entity_type']='native_approved_strategy'
    with pytest.raises(ValueError):render(record,bad,{})


def test_committed_first_hundred_have_complete_views_and_honest_types():
    manifest=validate_directory(ROOT/'metadata')
    first=[r for r in manifest['records'] if r['batch_path'].endswith('/batch-0001-v2')]
    assert [r['record_id'] for r in first]==[f'M{i:04d}' for i in range(1,101)]
    assert sum(r['classification']['entity_type']=='strategy' for r in first)==86
    assert {r['record_id'] for r in first if r['classification']['entity_type']=='factor'}=={'M0017','M0018','M0019','M0020','M0021','M0026','M0027','M0028','M0068'}
    assert {r['record_id'] for r in first if r['classification']['entity_type']=='unclassified'}=={'M0041','M0066','M0085','M0092','M0100'}
    assert len(validate(ROOT/'metadata'))==2


def test_appending_batch_preserves_previous_views_classifications_and_unique_ids(directory_input,tmp_path):
    root,batch,decisions,_=directory_input;first=tmp_path/'first'
    prepare_directory(root,batch,decisions,first);install(root,first)
    previous=validate_directory(root)
    frozen={entry['view']['path']:(root/entry['view']['path']).read_bytes() for entry in previous['records']}
    rows=[row('M0301','持有指定资产，收盘离场。'),row('M0303','只有研究主题。')]
    csv=tmp_path/'next.csv';contract=write_csv(csv,[row('M0297'),row('M0299'),*rows]);plan=tmp_path/'next-plan'
    p=create_plan(csv,root,plan,contract=contract,batch_size=2)
    relative='corpus-checkpoints/synthetic/batches/batch-0002-v2'
    staged=stage_batch(plan,p['plan_sha256'],csv,'batch-0002',root/relative)
    next_decisions=[]
    for original,kind in zip(rows,['strategy','unclassified']):
        source=json.loads((root/relative/f"metadata/source-records/{original['id']}.json").read_bytes())
        next_decisions.append(dict(record_id=original['id'],row_sha256=source['provenance']['row_sha256'],
            rule_sha256=source['provenance']['rule_sha256'],entity_type=kind,reason='独立合成内容决定。',
            evidence=[dict(field='规则',quote=original['规则'])]))
    candidate=tmp_path/'candidate'
    result=prepare_directory(root,dict(path=relative,sha256=staged['checkpoint_sha256'],commit='b'*40),next_decisions,candidate)
    assert result['counts']['readable_original_ids']==5
    assert frozen=={name:(candidate/name).read_bytes() for name in frozen}
    install(root,candidate);after=validate_directory(root)
    assert after['records'][:3]==previous['records']
    assert frozen=={name:(root/name).read_bytes() for name in frozen}
    assert [r['record_id'] for r in after['records'][-2:]]==['M0301','M0303']  # Preserve gaps.
    assert len(validate(root))==2


def test_committed_second_batch_matches_manifest_ids_and_keeps_native_count():
    root=ROOT/'metadata';manifest=validate_directory(root)
    second=[r for r in manifest['records'] if r['batch_path'].endswith('/batch-0002-v2')]
    source=json.loads((root/'corpus-checkpoints/grokbot-6973-20261003/batches/batch-0002-v2/manifest.json').read_bytes())
    assert [r['record_id'] for r in second]==source['record_ids'] and len(second)==100
    assert {r['record_id'] for r in second if r['classification']['entity_type']=='factor'}=={'M0108','M0109','M0121'}
    assert {r['record_id'] for r in second if r['classification']['entity_type']=='unclassified'}=={'M0101','M0112','M0115','M0122','M0127','M0133','M0135','M0136','M0176','M0192','M0196','M0199'}
    assert manifest['counts']==dict(readable_original_ids=200,strategy_candidates=171,factor_candidates=12,unclassified=17,new_native_definitions=0,new_execution_trials=0)
    assert len({r['record_id'] for r in manifest['records']})==200
    assert len(validate(root))==2

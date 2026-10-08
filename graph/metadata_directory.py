"""Render full catalog fields into typed reading directories without promoting definitions."""
import argparse
from collections import Counter
from copy import deepcopy
import html
import json
from pathlib import Path
import re

from quantgraph.graph.metadata_catalog import BATCH, _immutable_write, read_checkpoint, recover_rows
from quantgraph.graph.metadata_pilot import digest, encoded, publication_screen, read_below, validate

FORMAT = 'quantgraph-catalog-reading-directory/v1'
FIELDS = ['id', '名称', '市场', '规则', '作者或机构', '标题', 'source_url', '页码或文件', '可回测', '别名来源', '提出日期']
FOLDERS = {'strategy':'strategies', 'factor':'factors', 'unclassified':'unclassified'}
LABELS = {'strategy':'策略候选', 'factor':'因子候选', 'unclassified':'待分类'}
INDEX = 'directory-index.json'
REPOSITORY = 'https://github.com/KathenZK/quant-knowledge-graph'


def _fence(value):
    width = max([3] + [len(x) + 1 for x in re.findall(r'`+', value)])
    fence = '`' * width
    return fence + 'text\n' + value + '\n' + fence


def _decision(decision, record):
    if set(decision) != {'record_id', 'row_sha256', 'rule_sha256', 'entity_type', 'reason', 'evidence'}:
        raise ValueError('Directory classification requires an exact evidence-bound decision')
    if (decision['record_id'] != record['record_id']
            or decision['row_sha256'] != record['provenance']['row_sha256']
            or decision['rule_sha256'] != record['provenance']['rule_sha256']
            or decision['entity_type'] not in FOLDERS or not decision['reason']
            or not isinstance(decision['evidence'], list) or not decision['evidence']):
        raise ValueError('Directory decision identity, original row or type differs')
    if not any(item['field'] == '规则' for item in decision['evidence']):
        raise ValueError('Name keywords alone cannot establish directory type')
    for item in decision['evidence']:
        if (set(item) != {'field', 'quote'} or item['field'] not in FIELDS or not item['quote']
                or item['quote'] not in record['reported_fields'][item['field']]['value']):
            raise ValueError('Classification evidence must quote the pinned collected fields exactly')
    if publication_screen({'reason':decision['reason'], 'evidence':json.dumps(decision['evidence'], ensure_ascii=False)})['status'] != 'FIELD_REVIEW_REQUIRED':
        raise ValueError('Private classification evidence cannot enter reading directories')


def render(record, decision, source):
    """Every original string is retained inside a fence, including empty values/newlines."""
    _decision(decision, record)
    fields = record['reported_fields']; rid = record['record_id']
    title = html.escape(fields['名称']['value']).replace('\n', ' ')
    kind = decision['entity_type']
    parts = [f'# {rid} · {title}',
        f'目录分类：**{LABELS[kind]}**；分类状态：**CONTENT_INFERRED**；来源与定义状态：**UNVERIFIED**。',
        '这是原目录采集摘要的阅读视图。分类依据内容，不代表已审原生定义、严格复现、收益验证或执行许可。'
        + f"原来源记录分类状态 {record['classification']['type_status']} 保持不变。",
        '## 分类依据', decision['reason']]
    for item in decision['evidence']:
        parts += [f"证据字段：{item['field']}", _fence(item['quote'])]
    parts += ['## 完整原字段',
        '以下 11 列均保留原值，状态均为 CATALOG_REPORTED_UNVERIFIED。日期与“可回测”只是原标签；空文本表示原字段为空。']
    for field in FIELDS:
        parts += ['### ' + field, _fence(fields[field]['value'])]
    parts += ['## 固定来源与恢复',
        f"[完整来源 JSON（固定提交）]({source['url']}) · [仓库内原件](../{source['path']})",
        f"来源文件 SHA-256：`{source['sha256']}`；字节数：{source['bytes']}。",
        f"原行 SHA-256：`{decision['row_sha256']}`；规则 SHA-256：`{decision['rule_sha256']}`。",
        '本视图未读取来源网页正文，未生成回测、净值、交易记录或新因子 ID。',
        '[目录与准确计数](../README.md)']
    return ('\n\n'.join(parts) + '\n').encode()


def _counts(records):
    counts = Counter(r['classification']['entity_type'] for r in records)
    return dict(readable_original_ids=len(records), strategy_candidates=counts['strategy'],
        factor_candidates=counts['factor'], unclassified=counts['unclassified'],
        new_native_definitions=0, new_execution_trials=0)


def _batch(root, ref):
    if (set(ref) != {'path','sha256','commit'} or not re.fullmatch(r'[0-9a-f]{40}', ref['commit'])
            or not re.fullmatch(r'corpus-checkpoints/[A-Za-z0-9_-]+/batches/batch-\d{4}-v2', ref['path'])):
        raise ValueError('Reading directory needs a fixed versioned checkpoint')
    batch = Path(root) / ref['path']
    manifest = read_checkpoint(batch, ref['sha256'], BATCH)
    rows = recover_rows(batch, ref['sha256'], checkpoint_format=BATCH)
    records = validate(batch / 'metadata')
    if manifest['private_only_record_ids'] or manifest['counts']['private_only_records']:
        raise ValueError('Private-only checkpoints cannot be copied into reading directories')
    by_id = {r['record_id']:r for r in records if r['entity_type']=='source_record'}
    if set(by_id) != {row['id'] for row in rows}:
        raise ValueError('Checkpoint source records must cover every original ID')
    return by_id


def _source(root, batch, rid):
    path = batch['path'] + '/metadata/source-records/' + rid + '.json'
    raw = read_below(root, path)
    return dict(path=path, sha256=digest(raw), bytes=len(raw),
                url=REPOSITORY + '/blob/' + batch['commit'] + '/metadata/' + path)


def validate_directory(root):
    """Verify content, evidence and full Markdown reconstruction without loading native definitions."""
    manifest = json.loads(read_below(root, INDEX))
    if (set(manifest) != {'schema_version','batches','records','counts','classification_status','definition_status'}
            or manifest['schema_version'] != FORMAT or manifest['classification_status'] != 'CONTENT_INFERRED'
            or manifest['definition_status'] != 'UNVERIFIED'):
        raise ValueError('Unsupported reading directory or promoted status')
    batches = {}; expected_ids = set()
    for ref in manifest['batches']:
        if ref['path'] in batches:
            raise ValueError('Duplicate directory source batch')
        records = _batch(root, ref)
        if expected_ids & set(records):
            raise ValueError('Directory batches duplicate original IDs')
        expected_ids.update(records); batches[ref['path']] = (ref, records)
    seen = set(); paths = set()
    for entry in manifest['records']:
        if set(entry) != {'record_id','batch_path','source','classification','view'}:
            raise ValueError('Unexpected directory entry fields')
        rid = entry['record_id']
        if rid in seen or rid not in expected_ids:
            raise ValueError('Duplicate or unknown reading directory ID')
        ref, records = batches[entry['batch_path']]; record = records[rid]
        if entry['source'] != _source(root, ref, rid):
            raise ValueError('Directory source hash, path or fixed URL differs')
        raw = render(record, entry['classification'], entry['source'])
        expected = FOLDERS[entry['classification']['entity_type']] + '/' + rid + '.md'
        if entry['view'] != dict(path=expected, sha256=digest(raw), bytes=len(raw)):
            raise ValueError('Directory view manifest differs from complete original fields')
        if read_below(root, expected) != raw:
            raise ValueError('Directory Markdown changed or lost original fields')
        seen.add(rid); paths.add(expected)
    actual = {str(p.relative_to(root)) for folder in FOLDERS.values() for p in (Path(root)/folder).glob('M[0-9][0-9][0-9][0-9].md')}
    if seen != expected_ids or actual != paths or manifest['counts'] != _counts(manifest['records']):
        raise ValueError('Directory coverage, unique IDs or counts differ')
    return manifest


def prepare_directory(root, batch_ref, decisions, output):
    """Create immutable reading candidates; original JSON, notes and definitions are untouched."""
    records = _batch(root, batch_ref)
    by_id = {d['record_id']:d for d in decisions}
    if len(by_id) != len(decisions) or set(by_id) != set(records):
        raise ValueError('Explicit classification must cover every batch ID exactly once')
    entries = []; batches = []; files = {}
    if (Path(root)/INDEX).exists():
        prior = validate_directory(root)
        entries = deepcopy(prior['records']); batches = deepcopy(prior['batches'])
        if set(records) & {e['record_id'] for e in entries}:
            raise ValueError('Existing reading records cannot be overwritten or counted twice')
        for entry in entries:
            files[entry['view']['path']] = read_below(root, entry['view']['path'])
    for rid, record in records.items():
        decision = by_id[rid]; source = _source(root, batch_ref, rid)
        raw = render(record, decision, source)
        path = FOLDERS[decision['entity_type']] + '/' + rid + '.md'
        if (Path(root)/path).exists():
            raise ValueError('Existing reading Markdown cannot be overwritten')
        files[path] = raw
        entries.append(dict(record_id=rid, batch_path=batch_ref['path'], source=source,
            classification=decision, view=dict(path=path,sha256=digest(raw),bytes=len(raw))))
    batches.append(deepcopy(batch_ref))
    manifest = dict(schema_version=FORMAT, batches=batches, records=entries, counts=_counts(entries),
                    classification_status='CONTENT_INFERRED', definition_status='UNVERIFIED')
    files[INDEX] = encoded(manifest)
    _immutable_write(output, files)
    return dict(directory_index_sha256=digest(files[INDEX]), counts=manifest['counts'],
                classification_status='CONTENT_INFERRED', definition_status='UNVERIFIED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata',type=Path,default=Path('metadata'))
    parser.add_argument('--decisions',type=Path)
    parser.add_argument('--batch-path');parser.add_argument('--batch-sha256');parser.add_argument('--commit')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output:
        if not all([args.decisions,args.batch_path,args.batch_sha256,args.commit]):
            parser.error('Preparation requires decisions and the fixed batch path/hash/commit')
        result=prepare_directory(args.metadata,dict(path=args.batch_path,sha256=args.batch_sha256,commit=args.commit),
                                 json.loads(args.decisions.read_bytes()),args.output)
    else:
        result=validate_directory(args.metadata)['counts']
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=='__main__':main()

"""Freeze and replay content classifications without promoting source definitions."""
import argparse
from collections import Counter
from copy import deepcopy
import html
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator

from quantgraph.graph import metadata_classification as classifier
from quantgraph.graph.metadata_catalog import _immutable_write, canonical_hash
from quantgraph.graph.metadata_pilot import digest, encoded, read_below, validate


FORMAT = 'quantgraph-content-classification-batch/v1'
DECISION_FORMAT = 'quantgraph-content-classification-decision/v1'
KINDS = ('strategy', 'factor', 'reference', 'unclassified')
LABELS = dict(strategy='策略', factor='因子', reference='参考资料', unclassified='待分类')
MAX_BYTES = 64 * 1024**2


def _pin(raw):
    return dict(sha256=digest(raw), bytes=len(raw))


def _checked(root, path, pin):
    raw = read_below(root, path, MAX_BYTES)
    if _pin(raw) != pin:
        raise ValueError('Classification artifact digest mismatch: ' + path)
    return raw


def _json(root, path):
    return json.loads(read_below(root, path, MAX_BYTES))


def source_rows(root):
    """Read the frozen corpus directly; never instantiate a recursive Catalog."""
    root = Path(root)
    corpus = _json(root, 'metadata/corpus-index.json')
    rows, seen = {}, set()
    for batch in corpus['batches']:
        prefix = 'metadata/' + batch['path']
        if prefix in seen:
            raise ValueError('Duplicate classification source batch')
        seen.add(prefix)
        raw = read_below(root, prefix + '/manifest.json', MAX_BYTES)
        if digest(raw) != batch['manifest_sha256']:
            raise ValueError('Classification corpus manifest hash mismatch')
        manifest = json.loads(raw)
        for filename in ('index.json', 'schema.json', 'source-record.schema.json'):
            relative = 'metadata/' + filename
            _checked(root, prefix + '/' + relative, manifest['files'][relative])
        metadata = prefix + '/metadata'
        index = _json(root, metadata + '/index.json')
        records = [r for r in validate(root / metadata) if r['entity_type'] == 'source_record']
        refs = {r['record_id']: r for r in index['records'] if r['entity_type'] == 'source_record'}
        if len(records) != batch['record_count'] or len(refs) != len(records):
            raise ValueError('Classification corpus count mismatch')
        for record in records:
            rid = record['record_id']
            if rid in rows:
                raise ValueError('Duplicate classification source ID')
            ref = refs[rid]
            if manifest['files']['metadata/' + ref['path']] != {k: ref[k] for k in ('sha256', 'bytes')}:
                raise ValueError('Classification source differs from frozen manifest')
            rows[rid] = dict(record=record, path=metadata + '/' + ref['path'])
    if len(rows) != corpus['counts']['public_source_records']:
        raise ValueError('Classification corpus coverage mismatch')
    return rows


def decision_schema():
    string = dict(type='string', minLength=1)
    sha = dict(type='string', pattern='^[0-9a-f]{64}$')

    def obj(properties):
        return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)

    schema = obj(dict(
        schema_version=dict(const=DECISION_FORMAT), record_id=dict(type='string', pattern='^M[0-9]{4}$'),
        row_sha256=sha, rule_sha256=sha,
        source=obj(dict(path=string, sha256=sha, bytes=dict(type='integer', minimum=1))),
        kind=dict(enum=list(KINDS)), subtype=string, rule_id=string,
        confidence=dict(enum=['LOW', 'MEDIUM', 'HIGH']), reason=string,
        evidence=dict(type='array', minItems=1, items=obj(dict(field=dict(const='规则'), quote=string))),
        quality_flags=dict(type='array', uniqueItems=True, items=string),
        classification_status=dict(const='CONTENT_INFERRED'), definition_status=dict(const='UNVERIFIED'),
    ))
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    return schema


def _algorithm():
    return dict(version=classifier.VERSION, files={
        'graph/metadata_classification.py': _pin(Path(classifier.__file__).read_bytes()),
        'graph/classification_batch.py': _pin(Path(__file__).read_bytes()),
    })


def _targets(targets, csv_rows):
    if not isinstance(targets, list) or not targets or any(not isinstance(r, str) for r in targets):
        raise ValueError('Explicit nonempty target ID list required')
    if len(set(targets)) != len(targets) or not set(targets) <= set(csv_rows):
        raise ValueError('Duplicate or unknown classification target ID')
    return sorted(targets)


def _overrides(overrides, targets, csv_rows):
    required = {'record_id', 'kind', 'subtype', 'reason', 'evidence'}
    allowed = required | {'rule_id', 'confidence', 'quality_flags', 'row_sha256', 'rule_sha256'}
    if not isinstance(overrides, list):
        raise ValueError('Explicit override list required')
    result = {}
    for item in overrides:
        if not isinstance(item, dict) or not required <= set(item) or not set(item) <= allowed:
            raise ValueError('Unexpected classification override fields')
        rid = item['record_id']
        if rid not in targets or rid in result:
            raise ValueError('Duplicate or nontarget classification override')
        if item.get('rule_id', 'INDIVIDUAL_CONTENT_REVIEW') != 'INDIVIDUAL_CONTENT_REVIEW':
            raise ValueError('Override must identify individual content review')
        pins = {key: csv_rows[rid]['record']['provenance'][key] for key in ('row_sha256', 'rule_sha256')}
        supplied = {key: item[key] for key in pins if key in item}
        if supplied and supplied != pins:
            raise ValueError('Classification override targets a different source version')
        normalized = deepcopy(item)
        normalized.update(rule_id='INDIVIDUAL_CONTENT_REVIEW', confidence=item.get('confidence', 'MEDIUM'))
        normalized.update(pins)
        normalized['quality_flags'] = sorted(set(item.get('quality_flags', [])))
        result[rid] = normalized
    return [result[rid] for rid in sorted(result)]


def _decision(root, rid, row, override):
    record = row['record']
    raw = read_below(root, row['path'], MAX_BYTES)
    if json.loads(raw) != record or record['record_id'] != rid:
        raise ValueError('Classification source path or record mismatch')
    fields = {k: v['value'] for k, v in record['reported_fields'].items()}
    if (fields['id'] != rid or canonical_hash(fields) != record['provenance']['row_sha256']
            or digest(fields['规则'].encode()) != record['provenance']['rule_sha256']):
        raise ValueError('Classification original row or rule hash mismatch')
    hypothesis = deepcopy(override if override is not None else classifier.infer(record))
    for key in ('record_id', 'row_sha256', 'rule_sha256'):
        hypothesis.pop(key, None)
    hypothesis['quality_flags'] = sorted(set(hypothesis.get('quality_flags', []) + classifier.quality_flags(record)))
    decision = dict(schema_version=DECISION_FORMAT, record_id=rid,
        row_sha256=record['provenance']['row_sha256'], rule_sha256=record['provenance']['rule_sha256'],
        source=dict(path=row['path'], **_pin(raw)), classification_status='CONTENT_INFERRED',
        definition_status='UNVERIFIED', **hypothesis)
    Draft202012Validator(decision_schema()).validate(decision)
    if any(e['quote'] not in fields['规则'] for e in decision['evidence']):
        raise ValueError('Classification evidence must quote the exact original rule')
    return decision


def _line_json(rows):
    return ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
                   + '\n' for r in rows).encode()


def _fence(text):
    fence = '`' * max([3] + [len(x) + 1 for x in re.findall(r'`+', text)])
    return fence + 'text\n' + text + '\n' + fence


def _pages(decisions, csv_rows):
    files, links = {}, []
    for kind in KINDS:
        selected = [r for r in decisions if r['kind'] == kind]
        for start in range(0, len(selected), 100):
            path = f'{kind}/page-{start // 100 + 1:04d}.md'
            links.append(f'- [{LABELS[kind]} {start + 1}–{min(start + 100, len(selected))}]({path})')
            text = [f'# {LABELS[kind]} · 第 {start // 100 + 1} 页',
                    '内容分类：CONTENT_INFERRED；来源与定义仍为 UNVERIFIED。分类不代表可回测、收益有效或商业授权。']
            for r in selected[start:start + 100]:
                name = csv_rows[r['record_id']]['record']['reported_fields']['名称']['value']
                text += [f"## {r['record_id']} · {html.escape(name).replace(chr(10), ' ')}",
                         f"类型：{r['kind']} / {r['subtype']}；置信度：{r['confidence']}。", r['reason']]
                text += [_fence(e['quote']) for e in r['evidence']]
                if r['quality_flags']:
                    text.append('内容提示：' + '、'.join(r['quality_flags']))
                text += [f"来源：`{r['source']['path']}`；SHA-256：`{r['source']['sha256']}`。",
                         f"原行 SHA-256：`{r['row_sha256']}`；规则 SHA-256：`{r['rule_sha256']}`。"]
            files[path] = ('\n\n'.join(text) + '\n').encode()
    counts = Counter(r['kind'] for r in decisions)
    readme = ['# 内容分类批次',
              '本批按已采集摘要判断用途，不读取来源网页，不补造公式或交易参数；不新增原生定义、回测、收益结论或执行权限。',
              '目标 ID、来源版本、算法代码、人工覆盖与全部产物均由 index.json 绑定。',
              '| 类型 | 条目数 |', '| --- | ---: |']
    readme += [f'| {LABELS[k]} | {counts[k]} |' for k in KINDS]
    readme += ['', '每页最多 100 条。', '', *links, '', '[待分类队列](unclassified-queue.json)',
               'decisions.jsonl 保存逐条证据；overrides.json 保存本批人工裁决。CONTENT_INFERRED / UNVERIFIED 状态不随分类升级。']
    files['README.md'] = ('\n'.join(readme) + '\n').encode()
    files['unclassified-queue.json'] = encoded([dict(record_id=r['record_id'], subtype=r['subtype'],
        reason=r['reason'], evidence=r['evidence'], quality_flags=r['quality_flags'])
        for r in decisions if r['kind'] == 'unclassified'])
    return files


def _render(root, targets, overrides, csv_rows):
    targets = _targets(targets, csv_rows)
    overrides = _overrides(overrides, targets, csv_rows)
    by_id = {r['record_id']: r for r in overrides}
    decisions = [_decision(root, rid, csv_rows[rid], by_id.get(rid)) for rid in targets]
    files = dict(**{'schema.json': encoded(decision_schema()), 'overrides.json': encoded(overrides),
                    'decisions.jsonl': _line_json(decisions)}, **_pages(decisions, csv_rows))
    counts = Counter(r['kind'] for r in decisions)
    index = dict(schema_version=FORMAT, target_ids=targets,
        classification_status='CONTENT_INFERRED', definition_status='UNVERIFIED', algorithm=_algorithm(),
        counts=dict(target_records=len(targets), kinds={k: counts[k] for k in KINDS},
                    manual_overrides=len(overrides), new_native_definitions=0, new_execution_trials=0,
                    quality_flags=dict(sorted(Counter(f for r in decisions for f in r['quality_flags']).items()))),
        files={name: _pin(raw) for name, raw in sorted(files.items())})
    files['index.json'] = encoded(index)
    return index, decisions, files


def build(root, output, targets, overrides):
    """Write a fresh immutable classification batch, returning its index."""
    index, _, files = _render(Path(root), targets, overrides, source_rows(root))
    output = Path(output)
    if any(p.is_symlink() for p in [output, *output.parents]):
        raise ValueError('Classification output cannot traverse symlinks')
    output.parent.mkdir(parents=True, exist_ok=True)
    _immutable_write(output, files)
    return index


def _validate(root, directory, csv_rows):
    index_raw = read_below(directory, 'index.json', MAX_BYTES)
    index = json.loads(index_raw)
    required = {'schema_version', 'target_ids', 'classification_status', 'definition_status', 'algorithm', 'counts', 'files'}
    if (set(index) != required or index['schema_version'] != FORMAT
            or index['classification_status'] != 'CONTENT_INFERRED' or index['definition_status'] != 'UNVERIFIED'):
        raise ValueError('Unsupported classification batch or promoted status')
    if index['algorithm'] != _algorithm():
        raise ValueError('Classification algorithm version or code hash changed')
    for name, pin in index['files'].items():
        _checked(directory, name, pin)
    actual = {str(p.relative_to(directory)) for p in Path(directory).rglob('*') if p.is_file() or p.is_symlink()}
    if actual != set(index['files']) | {'index.json'}:
        raise ValueError('Classification batch directory drift')
    schema = _json(directory, 'schema.json')
    if schema != decision_schema():
        raise ValueError('Classification decision schema drift')
    validator = Draft202012Validator(schema)
    raw = read_below(directory, 'decisions.jsonl', MAX_BYTES)
    decisions = [json.loads(line) for line in raw.splitlines()]
    targets = _targets(index['target_ids'], csv_rows)
    if [r.get('record_id') for r in decisions] != targets or index['target_ids'] != targets:
        raise ValueError('Classification target coverage or ordering mismatch')
    for decision in decisions:
        validator.validate(decision)
        source = decision['source']
        expected = csv_rows[decision['record_id']]
        if source['path'] != expected['path']:
            raise ValueError('Classification source path mismatch')
        _checked(root, source['path'], {k: source[k] for k in ('sha256', 'bytes')})
        record = expected['record']
        if any(decision[k] != record['provenance'][k] for k in ('row_sha256', 'rule_sha256')):
            raise ValueError('Classification row or rule hash mismatch')
        if any(e['quote'] not in record['reported_fields']['规则']['value'] for e in decision['evidence']):
            raise ValueError('Classification evidence must quote the exact original rule')
    rebuilt, replayed, files = _render(root, targets, _json(directory, 'overrides.json'), csv_rows)
    if index != rebuilt or decisions != replayed or index_raw != files['index.json']:
        raise ValueError('Classification decisions, counts or overrides differ from replay')
    for name, expected in files.items():
        if read_below(directory, name, MAX_BYTES) != expected:
            raise ValueError('Classification rebuilt artifact differs: ' + name)
    return index, decisions


def validate_batch(root, relative_index_path, csv_rows):
    """Validate all pins and replay infer plus reviewed overrides, without writing."""
    root = Path(root)
    read_below(root, relative_index_path, MAX_BYTES)  # validates every path component
    if Path(relative_index_path).name != 'index.json':
        raise ValueError('Classification batch index must be named index.json')
    return _validate(root, root / Path(relative_index_path).parent, csv_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--targets', type=Path, help='Explicit JSON list of original IDs')
    parser.add_argument('--overrides', type=Path, help='Explicit JSON list of individual decisions')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check', action='store_true', help='Replay an existing --output without writing')
    parser.add_argument('--validate', help='Repository-relative path to a batch index.json')
    args = parser.parse_args()
    if args.validate:
        if args.output or args.check or args.targets or args.overrides:
            parser.error('--validate cannot be combined with build arguments')
        index, _ = validate_batch(args.root, args.validate, source_rows(args.root))
    elif args.check:
        if not args.output:
            parser.error('--check requires --output')
        rows = source_rows(args.root)
        index, _ = _validate(args.root, args.output, rows)
        if args.targets or args.overrides:
            targets = json.loads(args.targets.read_bytes()) if args.targets else index['target_ids']
            overrides = json.loads(args.overrides.read_bytes()) if args.overrides else _json(args.output, 'overrides.json')
            if _render(args.root, targets, overrides, rows)[0] != index:
                raise ValueError('Explicit check inputs differ from the frozen batch')
    else:
        if not args.targets or not args.output:
            parser.error('Build requires --targets and --output')
        targets = json.loads(args.targets.read_bytes())
        overrides = json.loads(args.overrides.read_bytes()) if args.overrides else []
        index = build(args.root, args.output, targets, overrides)
    print(json.dumps(index['counts'], ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()

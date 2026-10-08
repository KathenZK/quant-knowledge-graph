"""Export a bounded, attributable factor catalogue from an explicit frozen input.

Reads existing collection results; never fetches sources, rebuilds the core graph,
executes upstream code, or writes the source collection. No input paths are stored
in the public output. Source records and source-native identities remain distinct.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator

VERSION = 'quantgraph-factor-metadata/v1'
INDEX_VERSION = 'quantgraph-factor-metadata-index/v1'
EXPORTER = 'factor-metadata-export/v1'
MAX_EXCERPT_CHARS = 400
KINDS = ['signal', 'placebo', 'withdrawn', 'parameter_template', 'factor_portfolio']
SOURCES = {'qlib', 'jkp', 'osap', 'french', 'aqr', 'wq101', 'gtja191'}
RIGHT_FIELDS = ['license', 'license_id', 'rights_status', 'commercial_use',
                'redistribution_allowed', 'derivative_allowed', 'raw_data_allowed',
                'attribution_required', 'rights_scope', 'terms_url']


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def unique(values):
    return sorted(set(v for v in values if v is not None))


def bounded_excerpt(text):
    """Keep short definitions, or complete opening sentences; never split math."""
    if not text:
        return None, False
    if len(text) <= MAX_EXCERPT_CHARS:
        return text, False
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chosen = []
    for sentence in sentences:
        proposal = ' '.join(chosen + [sentence])
        if len(proposal) > MAX_EXCERPT_CHARS:
            break
        chosen.append(sentence)
    return ' '.join(chosen) or None, True


def safe_summary(row):
    inputs = row.get('required_fields') or []
    params = row.get('parameters') or {}
    operators = params.get('operators') or []
    literals = params.get('numeric_literals') or []
    return ('已有结构化提取记录列出输入：' + ('、'.join(inputs) or '尚未提取')
            + '；算子：' + ('、'.join(operators) or '尚未提取')
            + '；数值字面量：' + ('、'.join(map(str, literals)) or '未提取到')
            + '。这些构成要素不保留完整运算顺序，也不证明计算语义。完整定义须按来源定位核对。')


def text_hash(value):
    return digest(value.encode()) if value else None


def definition(row):
    source = row['source_id']
    raw = row.get('raw_definition') or row.get('description')
    formula = None
    text = None
    truncated = False
    if source == 'qlib':
        formula = row.get('raw_formula') or row.get('formula')
        text = '由已采集的 Qlib 官方配置展开而来；输入字段、窗口和算子按来源记录保留。'
        origin, status = 'OFFICIAL_GENERATED_CONFIGURATION', 'FORMULA_AVAILABLE'
    elif source == 'french':
        formula = row.get('raw_formula') or row.get('formula')
        text, truncated = bounded_excerpt(raw)
        origin, status = 'PROJECT_AUTHORED_MATHEMATICAL_SUMMARY', 'FORMULA_AVAILABLE'
    elif source in {'jkp', 'osap'}:
        text, truncated = bounded_excerpt(raw)
        origin = 'ATTRIBUTED_SOURCE_DEFINITION_EXCERPT'
        status = 'DEFINITION_EXCERPT' if text else 'MISSING'
    elif source in {'wq101', 'gtja191'}:
        text = safe_summary(row)
        origin, status = 'PROJECT_AUTHORED_STRUCTURAL_SUMMARY', 'STRUCTURED_SUMMARY_ONLY'
    else:
        origin, status = 'REFERENCE_METADATA_ONLY', 'MISSING'
    return {
        'formula': formula, 'formula_dialect': row.get('dialect'),
        'text': text, 'parameters': row.get('parameters') or {},
        'required_fields': row.get('required_fields') or [],
        'required_fields_status': row.get('required_fields_status') or 'MISSING',
        'status': status, 'content_origin': origin, 'truncated': truncated,
        'formula_sha256': text_hash(row.get('raw_formula') or row.get('formula')),
        'definition_sha256': text_hash(raw),
        'hash_scope': 'SHA-256 of the original collected field UTF-8, before excerpting; null means absent.',
    }


def read_records(path):
    raw = Path(path).read_bytes()
    rows = []
    seen = set()
    for ordinal, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if row['record_id'] in seen:
            raise ValueError('Duplicate source record_id: ' + row['record_id'])
        seen.add(row['record_id'])
        if row['source_id'] not in SOURCES or row['record_kind'] not in KINDS:
            raise ValueError('Unreviewed source or record kind requires an explicit export policy')
        if not re.fullmatch(r'qkg:factor:[a-f0-9-]{36}', row['factor_variant_id']):
            raise ValueError('Unsafe or unexpected stable factor_variant_id')
        rows.append((row, {'record_id': row['record_id'], 'line_ordinal': ordinal,
                          'line_sha256': digest(line), 'line_bytes': len(line)}))
    return raw, rows


def read_release(path):
    path = Path(path)
    raw = (path / 'factor_variants.jsonl').read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    ids = [row['factor_variant_id'] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate variant identity in release')
    return {row['factor_variant_id']: row for row in rows}, {
        'release_id': path.resolve().name,
        'release_json_sha256': digest((path / 'release.json').read_bytes()),
        'factor_variants_sha256': digest(raw), 'variant_count': len(ids),
    }


def license_attachments(source_lock):
    """Read only two named license artifacts from the explicit source lock."""
    source_lock = Path(source_lock)
    if source_lock.parts[-3:] != ('datasets', 'raw', 'source_lock.json'):
        raise ValueError('Expected an explicit datasets/raw/source_lock.json')
    root = source_lock.parents[2]
    lock_bytes = source_lock.read_bytes()
    lock = {item['key']: item for item in json.loads(lock_bytes)}
    files, references = {}, []
    for key, name in [('osap:LICENSE', 'OSAP-GPL-2.0.txt'),
                      ('jkp:DATA_LICENSE', 'JKP-DATA-LICENSE.txt')]:
        item = lock[key]
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe license path in source lock')
        body = (root / relative).read_bytes()
        if digest(body) != item['sha256'] or len(body) != item['bytes']:
            raise ValueError('License bytes do not match frozen source lock: ' + key)
        output = 'licenses/' + name
        files[output] = body
        references.append({'path': output, 'source_key': key, 'url': item['url'],
            'revision': item['revision'], 'sha256': digest(body), 'bytes': len(body),
            'retrieved_at': item['retrieved_at'], 'artifact_kind': 'LICENSE_NOTICE',
            'counted_as_factor': False})
    return files, references, digest(lock_bytes)


def export_record(group, input_sha, curated, public):
    group = sorted(group, key=lambda pair: pair[0]['record_id'])
    rows = [pair[0] for pair in group]
    first = rows[0]
    variant = first['factor_variant_id']
    # These exact-duplicate source rows may differ in aliases/native IDs, but
    # never silently choose between distinct definitions, rights or kinds.
    comparable = ['source_id', 'record_kind', 'formula', 'raw_definition', 'parameters']
    for key in comparable:
        if len({json.dumps(r.get(key), sort_keys=True) for r in rows}) != 1:
            if key == 'parameters':
                # Qlib same expression can have different feature-generator
                # metadata. Every source's parameters remain available below.
                continue
            raise ValueError(f'Conflicting {key} for variant {variant}')
    desc = definition(first)
    sources = []
    for row in rows:
        sources.append({
            'record_id': row['record_id'], 'source_id': row['source_id'],
            'source_name': row['source_name'], 'native_id': row['source_native_id'],
            'name': row['signal_name'], 'url': row.get('source_url'),
            'locator': row.get('source_locator'), 'revision': row.get('source_revision'),
            'sha256': row.get('source_file_sha256'),
            'response_sha256': row.get('source_response_sha256'),
            'retrieved_at': row.get('retrieved_at'),
            'license': row.get('license'), 'attribution': row.get('authors') or [],
            'primary_source': row.get('primary_source'),
            'code_url': row.get('code_url'),
            'paper': {'title': row.get('paper_title'), 'url': row.get('paper_url'),
                      'year': row.get('paper_year'), 'permission': 'REVIEW_REQUIRED'},
            'parameters': row.get('parameters') or {},
            'admission': {'status': row.get('curation_status'),
                          'reasons': row.get('curation_reasons') or []},
            'rights': {key: row.get(key) for key in RIGHT_FIELDS},
        })
    missing = [
        '现有采集未验证计算语义；不代表已复现、可回测或具有收益有效性。',
        '行情供应商、历史可用时点、复权、缺失处理和实际组合交易规则尚未冻结。',
        '底层行情、原论文和研报授权分别核验，不从仓库代码许可推定。',
    ]
    if desc['status'] == 'MISSING':
        missing.append('没有可在本条完整展示的定义；保留来源定位，不能补造公式。')
    if desc['truncated']:
        missing.append('这里只保留完整开头短句摘录，原定义还有后续条件；必须回查来源才能复现。')
    if first['source_id'] in {'wq101', 'gtja191'}:
        missing.append('社区转录不证明原始公式权利；不复制完整公式，仅保留结构要素、摘要及原字段摘要。')
    if first['record_kind'] != 'signal':
        missing.append('本条类型为 ' + first['record_kind'] + '，不能作为已准入的正式单因子统计。')
    if 'partial' in desc['required_fields_status'] or 'not_extracted' in desc['required_fields_status']:
        missing.append('输入字段提取不完整，不得视为完整数据需求合同。')
    core = curated.get(variant)
    return {
        'schema_version': VERSION, 'record_id': variant, 'entity_type': 'factor',
        'identity_namespace': 'quantgraph/factor-variant',
        'native_source_ids': unique(row['source_native_id'] for row in rows),
        'identity': {
            'source_record_ids': [row['record_id'] for row in rows],
            'legacy_canonical_factor_ids': unique(row.get('legacy_canonical_factor_id') for row in rows),
            'normalized_canonical_factor_ids': unique(row.get('canonical_factor_id') for row in rows),
            'normalized_concept_ids': unique(row.get('concept_id') for row in rows),
            'curated_canonical_factor_id': core.get('canonical_factor_id') if core else None,
            'equivalence_scope': 'Existing exact-variant identity only; no new cross-source or economic-concept equivalence asserted.',
        },
        'name': first['signal_name'], 'record_kind': first['record_kind'],
        'category': first.get('category') or 'unclassified',
        'domain': {key: first.get(key) for key in ['asset_class', 'frequency', 'universe', 'lookback', 'holding_period', 'rebalance']},
        'definition': desc, 'sources': sources,
        'admission': {
            'status': 'ADMITTED' if variant in curated else 'REVIEW_REQUIRED',
            'reasons': unique(reason for row in rows for reason in row.get('curation_reasons', [])),
            'membership': {'curated': variant in curated, 'historical_public_export': variant in public},
            'scope': 'Existing definition admission only; not economic validity, execution readiness or commercial clearance.',
        },
        'quality': {
            'metadata_status': 'IMPORTED_TRACEABLE_METADATA',
            'source_quality_tiers': unique(row.get('quality_tier') for row in rows),
            'parse_status': unique(row.get('parse_status') for row in rows),
            'semantic_status': unique(row.get('semantic_status') for row in rows),
            'economic_validity': 'NOT_EVALUATED',
            'backtest_ready': False, 'upstream_code_executed_in_export': False,
        },
        'rights': {
            'license_labels': unique(row.get('license') for row in rows),
            'commercial_use': unique(row.get('commercial_use') for row in rows),
            'redistribution_allowed': unique(row.get('redistribution_allowed') for row in rows),
            'derivative_allowed': unique(row.get('derivative_allowed') for row in rows),
            'raw_data_allowed': unique(row.get('raw_data_allowed') for row in rows),
            'attribution_required': any(row.get('attribution_required') for row in rows),
            'scope': 'Directory metadata and expressly identified definition excerpts only; no blanket license over upstream papers, source implementations or market observations.',
            'source_fulltext_included': False, 'market_observations_included': False,
            'license_notice': 'README.md 中说明逐来源归属与限制；原状态保留，不因进入统一目录而放宽商业许可。',
        },
        'provenance': {
            'exporter': EXPORTER, 'source_snapshot_sha256': input_sha,
            'source_artifact': 'normalized/factor_records.jsonl',
            'source_lines': [pair[1] for pair in group],
            'line_hash_scope': 'Original UTF-8 JSONL line bytes, excluding the line terminator.',
        },
        'missing_information': missing,
    }


def schema():
    string = {'type': 'string', 'minLength': 1}
    nullable = {'type': ['string', 'null']}
    strings = {'type': 'array', 'items': string, 'uniqueItems': True}
    sha = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    obj = lambda properties, required=None: {'type': 'object', 'additionalProperties': False,
        'properties': properties, 'required': required or list(properties)}
    line = obj({'record_id': string, 'line_ordinal': {'type': 'integer', 'minimum': 1},
                'line_sha256': sha, 'line_bytes': {'type': 'integer', 'minimum': 1}})
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema',
            **obj({
        'schema_version': {'const': VERSION},
        'record_id': {'type': 'string', 'pattern': '^qkg:factor:[a-f0-9-]{36}$'},
        'entity_type': {'const': 'factor'}, 'identity_namespace': {'const': 'quantgraph/factor-variant'},
        'native_source_ids': {**strings, 'minItems': 1},
        'identity': obj({'source_record_ids': {**strings, 'minItems': 1},
            'legacy_canonical_factor_ids': strings, 'normalized_canonical_factor_ids': strings,
            'normalized_concept_ids': strings, 'curated_canonical_factor_id': nullable,
            'equivalence_scope': string}),
        'name': string, 'record_kind': {'enum': KINDS}, 'category': string,
        'domain': obj({key: {} for key in ['asset_class', 'frequency', 'universe', 'lookback', 'holding_period', 'rebalance']}),
        'definition': obj({'formula': nullable, 'formula_dialect': nullable, 'text': nullable,
            'parameters': {'type': 'object'}, 'required_fields': strings, 'required_fields_status': string,
            'status': {'enum': ['FORMULA_AVAILABLE', 'DEFINITION_EXCERPT', 'STRUCTURED_SUMMARY_ONLY', 'MISSING']},
            'content_origin': string, 'truncated': {'type': 'boolean'},
            'formula_sha256': {'anyOf': [sha, {'type': 'null'}]},
            'definition_sha256': {'anyOf': [sha, {'type': 'null'}]}, 'hash_scope': string}),
        'sources': {'type': 'array', 'minItems': 1, 'items': obj({
            'record_id': string, 'source_id': {'enum': sorted(SOURCES)}, 'source_name': string,
            'native_id': string, 'name': string, 'url': nullable, 'locator': nullable,
            'revision': nullable, 'sha256': {'anyOf': [sha, {'type': 'null'}]},
            'response_sha256': {'anyOf': [sha, {'type': 'null'}]}, 'retrieved_at': nullable,
            'license': nullable, 'attribution': {'type': 'array'}, 'primary_source': {'type': 'boolean'},
            'code_url': nullable, 'paper': obj({'title': nullable, 'url': nullable, 'year': {}, 'permission': {'const': 'REVIEW_REQUIRED'}}),
            'parameters': {'type': 'object'}, 'admission': obj({'status': string, 'reasons': strings}),
            'rights': obj({key: {} for key in RIGHT_FIELDS})})},
        'admission': obj({'status': {'enum': ['ADMITTED', 'REVIEW_REQUIRED']}, 'reasons': strings,
            'membership': obj({'curated': {'type': 'boolean'}, 'historical_public_export': {'type': 'boolean'}}), 'scope': string}),
        'quality': obj({'metadata_status': {'const': 'IMPORTED_TRACEABLE_METADATA'},
            'source_quality_tiers': strings, 'parse_status': strings, 'semantic_status': strings,
            'economic_validity': {'const': 'NOT_EVALUATED'}, 'backtest_ready': {'const': False},
            'upstream_code_executed_in_export': {'const': False}}),
        'rights': obj({'license_labels': strings, 'commercial_use': strings,
            'redistribution_allowed': strings, 'derivative_allowed': strings, 'raw_data_allowed': strings,
            'attribution_required': {'type': 'boolean'}, 'scope': string,
            'source_fulltext_included': {'const': False}, 'market_observations_included': {'const': False},
            'license_notice': string}),
        'provenance': obj({'exporter': {'const': EXPORTER}, 'source_snapshot_sha256': sha,
            'source_artifact': {'const': 'normalized/factor_records.jsonl'},
            'source_lines': {'type': 'array', 'items': line, 'minItems': 1}, 'line_hash_scope': string}),
        'missing_information': strings,
    })}


README = '''# 已采集因子目录

这是统一知识目录中的因子条目，按已有 `factor_variant_id` 登记，不按来源权限另建两套主目录。来源、准入与许可均是条目字段。`index.json` 是当前索引；`records/` 每个 JSON 对应一个既有变体，所有旧来源记录和原生 ID 保留。

`signal` 表示信号条目；`placebo` 为安慰剂/未确认预测记录；`withdrawn` 为已撤回记录；`parameter_template` 为参数模板；`factor_portfolio` 为因子组合。后三类及 placebo 不得统称为已准入正式单因子。参数不同、实现不同和经济概念不同不是一回事。目录不新增经济等价关系，不把语法已解析改写为语义已验证。

## 内容与归属

- Microsoft Qlib：保留官方配置展开公式、输入与参数，按 MIT 归属；完整声明已经随 `datasets/public` 的当前发布保存。518 个来源记录折叠为 510 个既有变体，其中 508 属于历史准入，另外 2 个仍有准入问题。
- Open Source Asset Pricing（Chen、Zimmermann 与贡献者）：保存已有短定义摘录、输入和结构化参数，原仓库 GPL-2.0 条件及署名随记录保留。超过 400 字符的定义仅取完整开头短句，明确标记截断，不能按摘录回测。源码许可不替代原论文或 CRSP/Compustat/IBES 授权。
- JKP（Jensen、Kelly、Pedersen 与贡献者）：保存已有短定义和字段，文档参考内容保守保留 CC BY-NC 4.0 限制及 DATA_LICENSE，不用代码 MIT 消除非商业限制。LaTeX 定义没有伪装成可执行公式。
- Kenneth French Data Library：仅保留项目原有独立数学摘要与来源书目，不复制网站正文或收益数据；市场数据商业权利仍待核。
- WorldQuant Alpha101 / GTJA Alpha191：保留社区转录的来源身份、输入、算子、数值参数及自撰结构摘要，不复制完整公式；原公式摘要和定位用于追溯。社区 MIT 不代表原论文/研报已授权。
- AQR：原采集仅有书目和数据集入口，没有取得定义；本目录明确缺失，不补造公式或收益数据。

许可附件：[OSAP GPL-2.0](licenses/OSAP-GPL-2.0.txt)、[JKP DATA_LICENSE](licenses/JKP-DATA-LICENSE.txt)。它们保持锁定来源的原始字节，仅用于交付必要许可声明，不计作因子或定义。JKP 引用：Jensen, Kelly and Pedersen (2023), “Is There a Replication Crisis in Finance?”, Journal of Finance, DOI 10.1111/jofi.13249。OSAP 引用：Chen and Zimmermann (2022), “Open Source Cross-Sectional Asset Pricing”, Critical Finance Review 11(2), 207–264。

本次对来源做了字段选择、JSON 格式转换、短句摘录和自撰结构摘要；`content_origin` 区分引用摘录与自撰内容，`truncated` 标记未展示后续条件。400 字符仅是本批展示摘录上限，不是准入门槛或规则完整性的证明；原有准入状态不由该上限决定。

所有许可状态直接保留采集时结论，不因进入统一目录而获得新的商业、行情或论文权限。本目录没有源代码、完整来源正文、市场观测、账户数据、执行接口或新回测结果。

## 完整性与再生成

`index.json` 保存输入文件摘要和当前条目摘要。各条 `provenance.source_lines` 保留原始 JSONL 行号、字节数及 SHA-256（不含换行符），`sources` 保留原来源文件的摘要和版本。机器绝对路径不进入条目。

```sh
python scripts/export_factor_metadata.py --validate
python scripts/export_factor_metadata.py --normalized-records /authorized/factor_records.jsonl --curated-release /authorized/curated/release --public-release /authorized/public/release --source-lock /authorized/project/datasets/raw/source_lock.json --check
```

省略 `--check` 才会写目标目录；输入必须显式提供，工具不搜索私有目录、不采集新数据、不修改原文件。缺少授权源文件时仍可对已提交目录运行 `--validate`，但这不等于重建原始采集或验证计算语义。
'''


def generate(normalized_records, curated_release, public_release, source_lock):
    raw, rows = read_records(normalized_records)
    curated, cur_ref = read_release(curated_release)
    public, pub_ref = read_release(public_release)
    grouped = defaultdict(list)
    for row, ref in rows:
        grouped[row['factor_variant_id']].append((row, ref))
    if not set(public) <= set(curated) <= set(grouped):
        raise ValueError('Release memberships must be subsets of the normalized identities')
    records = [export_record(grouped[key], digest(raw), curated, public) for key in sorted(grouped)]
    validator = Draft202012Validator(schema())
    files = {'schema.json': encode(schema()), 'README.md': README.encode()}
    license_files, license_refs, lock_sha = license_attachments(source_lock)
    files.update(license_files)
    refs = []
    for record in records:
        validator.validate(record)
        # Payload identity remains the existing namespaced ID; filenames use
        # its UUID for portable checkouts (':' is invalid on Windows).
        path = 'records/' + record['record_id'].removeprefix('qkg:factor:') + '.json'
        payload = encode(record)
        files[path] = payload
        refs.append({'path': path, 'record_id': record['record_id'], 'sha256': digest(payload), 'bytes': len(payload)})
    counts = {'variants': len(records), 'source_records': len(rows),
        'record_kind': dict(sorted(Counter(r['record_kind'] for r in records).items())),
        'source_variants': dict(sorted(Counter(r['sources'][0]['source_id'] for r in records).items())),
        'definition_status': dict(sorted(Counter(r['definition']['status'] for r in records).items())),
        'curated_members': sum(r['admission']['membership']['curated'] for r in records),
        'historical_public_export_members': sum(r['admission']['membership']['historical_public_export'] for r in records),
        'backtest_ready': 0, 'new_execution_trials': 0}
    files['index.json'] = encode({'schema_version': INDEX_VERSION, 'records': refs, 'counts': counts,
        'schema_reference': {'path': 'schema.json', 'sha256': digest(files['schema.json']),
                             'bytes': len(files['schema.json'])},
        'license_notices': license_refs,
        'source_snapshot': {'artifact': 'normalized/factor_records.jsonl', 'sha256': digest(raw),
            'bytes': len(raw), 'source_records': len(rows), 'curated': cur_ref, 'historical_public_export': pub_ref,
            'source_lock_sha256': lock_sha, 'exporter': EXPORTER}})
    return files


def validate(output):
    output = Path(output)
    index = json.loads((output / 'index.json').read_text())
    schema_ref = index['schema_reference']
    schema_bytes = (output / 'schema.json').read_bytes()
    if (schema_ref['path'] != 'schema.json' or schema_ref['sha256'] != digest(schema_bytes)
            or schema_ref['bytes'] != len(schema_bytes)):
        raise ValueError('Schema attachment digest mismatch')
    validator = Draft202012Validator(json.loads(schema_bytes))
    if index['schema_version'] != INDEX_VERSION:
        raise ValueError('Wrong index schema')
    if {ref['source_key'] for ref in index['license_notices']} != {'osap:LICENSE', 'jkp:DATA_LICENSE'}:
        raise ValueError('Required attribution licenses are missing')
    for ref in index['license_notices']:
        path = Path(ref['path'])
        if path.is_absolute() or '..' in path.parts or path.parts[0] != 'licenses':
            raise ValueError('Unsafe license path')
        body = (output / path).read_bytes()
        if digest(body) != ref['sha256'] or len(body) != ref['bytes']:
            raise ValueError('License attachment digest mismatch')
        if ref['counted_as_factor'] or ref['artifact_kind'] != 'LICENSE_NOTICE':
            raise ValueError('License attachment is not a factor')
    seen, source_ids, identities, records = set(), set(), set(), []
    for ref in index['records']:
        path = Path(ref['path'])
        if path.is_absolute() or '..' in path.parts or path.parts[0] != 'records':
            raise ValueError('Unsafe record path')
        payload = (output / path).read_bytes()
        if len(payload) != ref['bytes'] or digest(payload) != ref['sha256']:
            raise ValueError('Record digest/length mismatch: ' + str(path))
        record = json.loads(payload)
        validator.validate(record)
        if record['record_id'] != ref['record_id'] or record['record_id'] in seen:
            raise ValueError('Record identity mismatch or duplicate')
        seen.add(record['record_id']); records.append(record)
        local_source_ids = {s['record_id'] for s in record['sources']}
        if local_source_ids != set(record['identity']['source_record_ids']):
            raise ValueError('Source identity mapping mismatch')
        if local_source_ids != {line['record_id'] for line in record['provenance']['source_lines']}:
            raise ValueError('Source line mapping mismatch')
        if record['provenance']['source_snapshot_sha256'] != index['source_snapshot']['sha256']:
            raise ValueError('Wrong source snapshot binding')
        if source_ids & local_source_ids:
            raise ValueError('A source record appears in multiple variants')
        source_ids |= local_source_ids
        for source in record['sources']:
            key = (source['source_id'], source['native_id'])
            if key in identities:
                raise ValueError('Duplicate source-native identity')
            identities.add(key)
        if record['definition']['truncated'] and record['definition']['status'] not in {'DEFINITION_EXCERPT', 'MISSING'}:
            raise ValueError('Truncated definitions must remain partial')
        if any(s['source_id'] in {'wq101', 'gtja191'} for s in record['sources']) and record['definition']['formula'] is not None:
            raise ValueError('Unreviewed upstream formula copied')
    expected = {ref['path'] for ref in index['records']}
    actual = {str(path.relative_to(output)) for path in (output / 'records').glob('*.json')}
    if actual != expected:
        raise ValueError('Unindexed or missing record files')
    actual_counts = {
        'variants': len(records), 'source_records': len(source_ids),
        'record_kind': dict(sorted(Counter(r['record_kind'] for r in records).items())),
        'source_variants': dict(sorted(Counter(r['sources'][0]['source_id'] for r in records).items())),
        'definition_status': dict(sorted(Counter(r['definition']['status'] for r in records).items())),
        'curated_members': sum(r['admission']['membership']['curated'] for r in records),
        'historical_public_export_members': sum(r['admission']['membership']['historical_public_export'] for r in records),
        'backtest_ready': 0, 'new_execution_trials': 0,
    }
    if actual_counts != index['counts']:
        raise ValueError('Counts disagree with records')
    return actual_counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalized-records', type=Path)
    parser.add_argument('--curated-release', type=Path)
    parser.add_argument('--public-release', type=Path)
    parser.add_argument('--source-lock', type=Path)
    parser.add_argument('--output', type=Path, default=Path('metadata/factor-sources'))
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--validate', action='store_true')
    args = parser.parse_args()
    if args.validate:
        print(json.dumps(validate(args.output), ensure_ascii=False, sort_keys=True))
        return
    if not all([args.normalized_records, args.curated_release, args.public_release, args.source_lock]):
        parser.error('All four explicit source input paths are required')
    files = generate(args.normalized_records, args.curated_release, args.public_release, args.source_lock)
    stale = []
    old_index = args.output / 'index.json'
    if not args.check and old_index.is_file():
        for ref in json.loads(old_index.read_text())['records']:
            relative = Path(ref['path'])
            if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'records':
                raise ValueError('Unsafe previous record path')
            if ref['path'] in files:
                continue
            old = args.output / relative
            if old.is_file():
                # Only remove known prior generated records. Preserve unknown
                # edits instead of deleting them during a filename migration.
                if digest(old.read_bytes()) != ref['sha256']:
                    raise ValueError('Modified stale record needs review: ' + ref['path'])
                stale.append(old)
    for relative, body in files.items():
        path = args.output / relative
        if args.check:
            if not path.is_file() or path.read_bytes() != body:
                raise ValueError('Rebuild mismatch: ' + relative)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
    for path in stale:
        path.unlink()
    print(json.dumps(validate(args.output), ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()

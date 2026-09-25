"""Offline build, checked release generations and atomic current-pointer publication."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from quantgraph.collectors.legacy_cli import check_sources
from quantgraph.collectors.pipeline import all_collectors
from quantgraph.normalize.quality import assess
from quantgraph.normalize.dedup.legacy import graph
from quantgraph.normalize.export import export
from quantgraph.normalize.taxonomy.rules import category
from quantgraph.models.entities import ENTITY_MODELS
from quantgraph.graph.curate import curate, commercial_subset
from quantgraph.graph.store import write_graph


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(path):
    return {str(p.relative_to(path)):digest(p) for p in sorted(path.rglob('*')) if p.is_file() and p.name!='manifest.json'}


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')


def build(root):
    root=Path(root).resolve();lock=root/'datasets/.publish.lock'
    lock.parent.mkdir(parents=True,exist_ok=True)
    try:lock.mkdir()
    except FileExistsError:raise RuntimeError('Another build holds datasets/.publish.lock; inspect running processes before removing a stale lock')
    staging=None
    try:
        source_files=check_sources(root)
        c=all_collectors(root);assess(c)
        legacy=graph(c);legacy['operators']=c.operator_registry
        legacy_summary=export(c,legacy)
        tables,decisions=curate(root,legacy)
        write_json(root/'datasets/normalized/curation_decisions.json',decisions)
        # Explicit new schema projection for all records; rejected records remain discoverable offline.
        decision_map={d['record_id']:d for d in decisions}
        normalized=[]
        for r in legacy['records']:
            d=decision_map[r['record_id']]
            normalized.append({**r,'legacy_canonical_factor_id':r['canonical_factor_id'],
                'canonical_factor_id':r['concept_id'],'canonical_name':r['factor_concept'],
                'factor_variant_id':r['canonical_factor_id'],'variant_name':r['signal_name'],
                'description':r['raw_definition'],'economic_logic':None,'lookback':None,'category':category(r),
                'raw_formula':r['formula'],'created_at':r['retrieved_at'],'updated_at':r['retrieved_at'],
                'curation_status':'ADMITTED' if d['admitted'] else 'REVIEW_REQUIRED',
                'curation_reasons':d['reasons'],**d['rights']})
        (root/'datasets/normalized/factor_records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in normalized))
        for name,model in ENTITY_MODELS.items():
            write_json(root/f'models/schemas/{name}.schema.json',model.model_json_schema())
        parent=root/'datasets/curated';parent.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='.build-',dir=parent))
        code_files = [p for folder in ('collectors','models','normalize','graph','api','sdk') for p in (root/folder).rglob('*.py')]
        code_files += [root/'pyproject.toml', root/'uv.lock']
        write_json(staging/'code_manifest.json', {str(p.relative_to(root)):digest(p) for p in sorted(code_files)})
        write_graph(staging,tables)
        commercial=commercial_subset(tables)
        write_graph(staging/'commercial',commercial)
        shutil.copy2(root/'datasets/raw/sources/qlib/LICENSE',staging/'commercial/THIRD_PARTY_LICENSE.txt')
        (staging/'commercial/NOTICE.md').write_text('Qlib-derived expressions: Copyright Microsoft Corporation. MIT terms apply; see THIRD_PARTY_LICENSE.txt. QuantGraph modifies representation, grouping and metadata. Market data rights are not included. No profitability or executable semantic certification.\n')
        source_counts=Counter(r['source_id'] for r in tables['factor_variants'])
        summary={
            'schema_version':'0.2.0','source_files':source_files,
            'source_records':len(legacy['records']),'normalized_unique_variants':len(legacy['factors']),
            'exact_duplicate_records':len(legacy['records'])-len(legacy['factors']),
            'curated_variants':len(tables['factor_variants']),'curated_concepts':len(tables['factor_concepts']),
            'curated_source_records':len(tables['source_records']),
            'commercial_variants':len(commercial['factor_variants']),
            'normalized_formula_ast_count':legacy_summary['raw_formula_parse_success'],
            'curated_formula_count':len(tables['formulas']),
            'papers':len(tables['papers']),'partial_paper_citations':sum(p['metadata_status']=='PARTIAL_CITATION' for p in tables['papers']),
            'relationships':len(tables['relationships']),
            'rejected_source_records':sum(not d['admitted'] for d in decisions),
            'duplicate_candidates_pending':len(legacy['duplicate_candidates']),
            'curated_sources':dict(source_counts),'normalized_sources':dict(Counter(r['source_id'] for r in legacy['records'])),
            'strategies':0,'backtest_results':0,'backtest_ready':0,
            'admission_scope':'Traceable primary concrete definitions; not economic independence, profitability, execution readiness or commercial clearance.',
            'source_lock_sha256':digest(root/'datasets/raw/source_lock.json'),
            'id_registry_sha256':digest(root/'models/id_registry.json'),
        }
        write_json(staging/'release.json',summary)
        from quantgraph.graph.verify import verify_graph
        verify_graph(staging);verify_graph(staging/'commercial',commercial=True)
        hashes=manifest(staging)
        release_id=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:20]
        write_json(staging/'manifest.json',hashes)
        releases=parent/'releases';releases.mkdir(exist_ok=True)
        release=releases/release_id
        if release.exists():
            if json.loads((release/'manifest.json').read_text())!=hashes:
                raise RuntimeError('Release ID collision')
            shutil.rmtree(staging);staging=None
        else:
            staging.rename(release);staging=None
        link=parent/'.current-next'
        if link.is_symlink():link.unlink()
        link.symlink_to(Path('releases')/release_id)
        os.replace(link,parent/'current')
        summary['release_id']=release_id
        write_json(root/'reports/quality.json',summary)
        write_json(root/'reports/normalized_manifest.json',manifest(root/'datasets/normalized'))
        generate_report(root,summary)
        return summary
    finally:
        if staging and staging.exists():shutil.rmtree(staging)
        lock.rmdir()


def generate_report(root,s):
    lines=['# 第一阶段交付与质量报告','',
        f"实际来源记录 **{s['source_records']}**，保守去重 **{s['normalized_unique_variants']}**；curated 通过 **{s['curated_variants']}** 个具体定义/信号变体，属于 **{s['curated_concepts']}** 个当前概念分组。",
        '', '概念分组多数仍是来源局部组；没有完成全球经济机制的等价归并。窗口列计作信号变体，不计作独立因子发现。','',
        '| 来源 | normalized 来源记录 | curated 去重变体 |','|---|---:|---:|']
    for source,n in sorted(s['normalized_sources'].items()):lines.append(f"| {source} | {n} | {s['curated_sources'].get(source,0)} |")
    lines+=['',f"- 公式语法树：normalized {s['normalized_formula_ast_count']} 条；curated {s['curated_formula_count']} 个唯一公式。",
        f"- 商用自动白名单：{s['commercial_variants']} 个 Qlib 变体，须保留 MIT 声明；不包含市场数据授权。",
        f"- 论文/引文实体：{s['papers']}；其中 {s['partial_paper_citations']} 个缺少确切题目，按来源记录隔离，禁止凭作者年份合并。",
        f"- 关系：{s['relationships']}；待复核重复候选：{s['duplicate_candidates_pending']}。",
        f"- 未准入来源记录：{s['rejected_source_records']}，原因逐条见 normalized/curation_decisions.json。",
        '- Strategy 和 BacktestResult 当前都是 0。已建独立 schema、数据库表与双向查询；没有迁入研究代码或伪造策略。',
        '- 所有 backtest_ready=false；未执行第三方研究代码，未认证计算语义或收益。',
        '', '## 准入与剩余缺口','',
        '准入检查来源版本与摘要、具体定义、源内去重、原始类型、已知结构异常、关系外键和权限字段。它是定义目录的质量审核，不等于每条公式都通过了数学/数值复现。',
        'Alpha101/191 为社区转录，保留 AST 与原版本并待官方逐式比对；French 为独立数学摘要；AQR 仅元数据。这四类当前全部停留在 normalized。',
        'OSAP 的大量原论文标题未填；JKP 原论文关联不完整；economic_logic、未知 lookback 未取得可靠证据时留 null；Qlib lookback 根据 AST 计算输入跨度，required_fields 有 partial 标记。163 组疑似重复未自动合并。',
        'QLib 已关联平台论文，平台引用与单因子原始论文关系有明确 scope，不用平台论文冒充每个因子的来源论文。',
        '', '## 商业边界','',
        'commercial 库为独立的封闭关系集合；默认 API 只打开这个库。JKP 为 NONCOMMERCIAL_ONLY；OSAP 为 CONDITIONAL/REVIEW_REQUIRED；其余权利不明确条目为 REVIEW_REQUIRED。清洗不会改变上游权利。',
        '', '## 证据','',f"release: `{s['release_id']}`。输入锁、版本和每个文件摘要见 `datasets/raw/source_lock.json`；发布导出摘要见 `datasets/curated/current/manifest.json`；测试与重建证据见 `reports/validation.json`。"]
    (root/'reports/PHASE1.md').write_text('\n'.join(lines)+'\n')

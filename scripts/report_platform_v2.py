"""Recompute aggregate-only diagnostics from a private journal and factor snapshot.

Usage: uv run python scripts/report_platform_v2.py --db datasets/ingestion/platform-v2.sqlite
No raw text, record IDs, source URLs or license claims are emitted.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.graph.ontology.canonical import map_records
from quantgraph.normalize.strategy.archetypes import classify, review_reason


def report(root, db):
    repository = SQLiteIngestionRepository(db)
    status = repository.projection_status()
    if status['projection_status'] != 'READY':
        raise ValueError('Complete current projections required')
    rows = []
    for offset in range(0, status['latest_revision_count'], 1000):
        rows.extend(repository.variants(1000, offset))
    with repository.connect() as con:
        old = [json.loads(r[0]) for r in con.execute("""SELECT p.payload FROM projections p
            WHERE parser_version='grok-rule-v2.0' AND revision=(SELECT MAX(revision) FROM revisions r WHERE r.record_id=p.record_id)""")]
    if len(old) != len(rows):
        raise ValueError('Baseline and current source universes differ; freeze a matched baseline first')
    n = len(rows)
    before = sum(r['variant']['parse_status'] == 'PARSED' for r in old)
    after = sum(r['variant']['parse_status'] == 'PARSED' for r in rows)
    factors = [json.loads(line) for line in (root / 'datasets/normalized/factor_records.jsonl').read_text().splitlines()]
    mapping = map_records(factors)
    summary = {'grokbot': repository.ingest_stats(), 'parser_before': before, 'parser_after': after,
               'rule_review_before': n - before, 'rule_review_after': n - after,
               'strategy_concepts': len({r['variant']['strategy_concept_id'] for r in rows if r['variant']['strategy_concept_id']}),
               'strategy_templates': len({r['variant']['strategy_template_id'] for r in rows if r['variant']['strategy_template_id']}),
               'strategy_variants': len({r['variant']['strategy_variant_id'] for r in rows}),
               'factor_linked_strategies': sum(bool(r['factor_links']) for r in rows),
               'factor_links': sum(len(r['factor_links']) for r in rows),
               'eligible_variants': sum(r['candidate_gate']['eligible'] for r in rows),
               'candidate_blockers': dict(Counter(reason for r in rows for reason in r['candidate_gate']['blockers'])),
               'factor_ontology': mapping['summary']}
    output = root / 'reports'
    output.mkdir(exist_ok=True)
    (output / 'platform-v2-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    counts = Counter(classify(r['variant']['original_rule_text']) for r in rows)
    parsed = Counter(classify(r['variant']['original_rule_text']) for r in rows if r['variant']['parse_status'] == 'PARSED')
    errors = Counter(review_reason(r['variant']['original_rule_text']) for r in rows if r['variant']['parse_status'] == 'REVIEW')
    lines = ['# Parser coverage v2', '',
             f"输入 {n} 条；grok-rule-v2.0 parsed={before} → {status['parser_version']} parsed={after}，覆盖率 {after / n:.2%}。",
             f'规则 review: {n-before} → {n-after}。全部许可/执行待审。', '',
             f'1000 目标未达成，新增 {after-before} 条。缺口既包括未实现语法，也包括缺失规则/额外条款；不能声称所有剩余规则均无法解析。',
             '下面 25 类加 residual 只用于审核路由，不据关键词生成 AST。', '',
             '| RuleArchetype | 全部 | 严格解析 |', '|---|---:|---:|']
    lines += [f'| {name} | {count} | {parsed[name]} |' for name, count in counts.most_common()]
    lines += ['', '## Error taxonomy', ''] + [f'- {name}: {count}' for name, count in errors.items()]
    lines += ['', '现金工具、成交时序、价格复权、指标计算和缺失数据政策未写明时保持空值，AST 不等于可执行。']
    (output / 'parser-coverage-v2.md').write_text('\n'.join(lines) + '\n')
    stats = mapping['summary']
    lines = ['# Factor ontology v2', '',
             f"source factor records={stats['input_records']}；canonical economic concepts={stats['canonical_concepts']}；mapped={stats['mapped_records']}；unresolved={stats['unresolved_records']}。",
             f"conflicts={stats['conflict_groups']}；alias groups={stats['alias_groups']}；variant review groups={stats['variant_groups']}；SAME_AS merges=0。", '',
             '使用已冻结分类、JKP 原始 theme 列及来源摘要；经济分类 RELATED_TO 不代表公式等价。新增 Size/Growth/Low Risk。', '',
             '| Source | Records | Mapped | Unresolved |', '|---|---:|---:|---:|']
    lines += [f"| {source} | {v['input']} | {v['mapped']} | {v['unresolved']} |" for source, v in stats['by_source'].items()]
    lines += ['', 'source-scoped variant groups 为待审聚类，未合并跨源定义。Alpha101/191 复合公式保留未解决；12-1、6-1、残差、行业、盈余动量不能合并为同一实现。许可不随本体映射变化。']
    (output / 'factor-ontology-v2.md').write_text('\n'.join(lines) + '\n')
    (output / 'strategy-factor-coverage-v2.md').write_text(
        f"# Strategy Factor Coverage Report\n\n{n} Source Records → {summary['strategy_concepts']} Concepts → "
        f"{summary['strategy_templates']} Templates → {summary['strategy_variants']} Variants。\n\n"
        f"{summary['factor_linked_strategies']} 条策略有规则关联，{summary['factor_links']} 条 USES_FACTOR links；全部 RULE_LINK_ONLY，EMPIRICALLY_TESTED=0。\n\n"
        'RSI 阈值/资产变更共享 RSI 参数因子；显式多指标分别保存引用。link_id、strategy_id、factor_id、factor_variant_id、reason、AST evidence、confidence、source、parser_version、validation_status 均有存储。来源未验证实现仍 REVIEW_REQUIRED；未分类记录不臆造 Concept。\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(report(args.root, args.db), indent=2))

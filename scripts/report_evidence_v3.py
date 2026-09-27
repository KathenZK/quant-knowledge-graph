"""Private evidence/coverage reports and separately allowlisted public aggregates."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.graph.evidence_queue import summarize
from quantgraph.normalize.strategy.parser import VERSION
from analyze_rule_archetypes_v3 import classify


def main():
    p=argparse.ArgumentParser();p.add_argument('--journal',required=True,type=Path);p.add_argument('--out',type=Path,default=Path('reports'));a=p.parse_args()
    repo=SQLiteIngestionRepository(a.journal)
    rows=[]
    for offset in range(0,repo.ingest_stats()['semantic_records'],1000):rows.extend(repo.variants(1000,offset))
    with sqlite3.connect(f'file:{a.journal.resolve()}?mode=ro',uri=True) as con:
        baseline={r['variant']['source_native_id']:r for (payload,) in con.execute("SELECT payload FROM projections WHERE parser_version='grok-rule-v3.1'") for r in [json.loads(payload)]}
    counts=defaultdict(Counter)
    for r in rows:
        rid=r['variant']['source_native_id']
        if rid not in baseline:continue
        name=classify(r['variant']['original_rule_text'])
        before=baseline[rid]['variant']['parse_status'];after=r['variant']['parse_status']
        counts[name]['total']+=1;counts[name]['before_parsed']+=before=='PARSED';counts[name]['after_parsed']+=after=='PARSED'
    before=sum(x['before_parsed'] for x in counts.values());after=sum(x['after_parsed'] for x in counts.values());n=len(baseline)
    coverage=dict(baseline_parser='grok-rule-v3.1',current_parser=VERSION,original_corpus=n,derived_records=len(rows)-n,
        before=dict(parsed=before,review=n-before,errors=0),after=dict(parsed=after,review=n-after,errors=0),
        coverage=after/n,delta=after-before,target=1000,target_met=after>=1000,
        reason_taxonomy={'unsupported_and_ambiguous':'The legacy parser combines these states; separate unsupported/ambiguous counts are UNKNOWN, not invented',
                         'unsupported':None,'ambiguous':None},archetypes=dict(sorted(counts.items())),
        current_projection_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
    queue=summarize(rows)
    a.out.mkdir(exist_ok=True)
    for name,value in [('parser-coverage-v3',coverage),('evidence-review-queue-v3',queue),('evidence-v3-final-stats',repo.ingest_stats())]:
        (a.out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    text=['# Parser Coverage V3','',f'原始 {n} 条：PARSED {before} → {after}；规则 REVIEW {n-before} → {n-after}；覆盖 {100*after/n:.2f}%。目标 1000 未通过。',
          '', '语法解析不代表执行/权限/经济有效性。unsupported 与 ambiguous 仍是合并失败码，不能拆出假数字；处理错误为 0。手工来源派生记录单列，不充当 parser 覆盖增长。',
          '', '| Archetype | 全部 | Before parsed | After parsed |','|---|---:|---:|---:|']
    text += [f"| {k} | {v['total']} | {v['before_parsed']} | {v['after_parsed']} |" for k,v in sorted(counts.items(),key=lambda x:-x[1]['total'])]
    (a.out/'parser-coverage-v3.md').write_text('\n'.join(text)+'\n')
    print(json.dumps({'coverage':{k:v for k,v in coverage.items() if k!='archetypes'},'queue_counts':{k:v for k,v in queue.items() if 'count' in k}},ensure_ascii=False))


if __name__=='__main__':main()

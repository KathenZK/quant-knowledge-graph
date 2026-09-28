"""Private reproducible V4 funnel; no public raw/data export."""
import argparse
from collections import Counter
import json
from pathlib import Path
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.graph.evidence_queue import summarize
from analyze_rule_archetypes_v3 import classify


def report(db):
    repo=SQLiteIngestionRepository(db);stats=repo.ingest_stats();rows=[]
    for offset in range(0,stats['semantic_records'],1000):rows.extend(repo.variants(1000,offset))
    if stats['projection_status']!='READY':raise ValueError('Complete projections required')
    reviews=[r.get('reviewed_evidence') for r in rows if r.get('reviewed_evidence')]
    current=[e for e in reviews if e['schema_version']=='evidence-enrichment-v4']
    return dict(ingestion=stats,concepts=len({r['variant']['strategy_concept_id'] for r in rows if r['variant']['strategy_concept_id']}),
       templates=len({r['variant']['strategy_template_id'] for r in rows if r['variant']['strategy_template_id']}),
       factor_links=sum(len(r['factor_links']) for r in rows),reviewed_sources=len(reviews),current_v4_reviews=len(current),
       rights_research_approved=sum(r['candidate_gate']['rights_status']=='ALLOWED' for r in rows),
       execution_complete=sum(r['candidate_gate']['execution_status']=='COMPLETE' for r in rows),
       derived_requirements_complete=sum(r['candidate_gate']['data_requirement_status']=='COMPLETE' for r in rows),
       verified_datasets=sum(e['dataset_binding']['acceptance_status']=='TRUSTED' and e['dataset_binding']['coverage']['coverage_status']=='VERIFIED' for e in current),
       statuses=dict(Counter(r['candidate_gate']['status'] for r in rows)),assessments=summarize(rows),
       parser_review_archetypes=dict(Counter(classify(r['variant']['original_rule_text']) for r in rows if r['variant']['parse_status']=='REVIEW')),
       scope='PRIVATE_RESEARCH_EVIDENCE_NOT_PROFITABILITY')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=report(a.db);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in value.items() if k not in {'assessments'}},ensure_ascii=False))

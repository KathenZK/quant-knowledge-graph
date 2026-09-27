"""Template/concept assessments and readiness-first evidence queue; no return ranking."""
from collections import Counter, defaultdict


def summarize(rows):
    groups=defaultdict(list)
    for row in rows:
        groups[row['variant'].get('strategy_template_id') or 'unparsed:'+row['variant']['strategy_variant_id']].append(row)
    templates=[]
    for key,siblings in sorted(groups.items()):
        # One fully supported representative is enough to research a template.
        # Blocked siblings are retained, never inherited by the chosen experiment.
        best=min(siblings,key=lambda r:(r['candidate_gate']['status']!='ELIGIBLE',
             -r['candidate_gate']['research_readiness_score'],r['variant']['strategy_variant_id']))
        gate=best['candidate_gate'];n=len(siblings)
        missing=sorted(set(gate['blocking_reasons']))
        duplicate_penalty=min(10,n-1)
        item={**gate,'representative_variant_id':best['variant']['strategy_variant_id'],
              'sibling_variant_count':n,'eligible_variant_count':sum(r['candidate_gate']['status']=='ELIGIBLE' for r in siblings),
              'parameter_mining_penalty':duplicate_penalty,'independent_hypothesis_count':1 if best['variant'].get('strategy_template_id') else 0,
              'missing_evidence_count':len(missing),'diversity_metadata':best.get('diversity_metadata',{}),
              'priority':'HIGH' if 1<=len(missing)<=2 and gate['research_readiness_score']>=60 else 'NORMAL' if gate['research_readiness_score']>=40 else 'LOW'}
        templates.append(item)
    concepts=defaultdict(list)
    for item in templates:
        if item['strategy_concept_id']:concepts[item['strategy_concept_id']].append(item)
    concept_assessments=[]
    for key,items in sorted(concepts.items()):
        best=min(items,key=lambda x:(x['status']!='ELIGIBLE',-x['research_readiness_score'],x['strategy_template_id']))
        concept_assessments.append({**best,'strategy_concept_id':key,'template_count':len(items),
          'eligible_template_count':sum(t['status']=='ELIGIBLE' for t in items),'assessment_scope':'CONCEPT_REPRESENTATIVE_NOT_ALL_SIBLINGS'})
    queue=sorted([t for t in templates if t['status']!='ELIGIBLE'],key=lambda t:(
        {'HIGH':0,'NORMAL':1,'LOW':2}[t['priority']],-t['research_readiness_score'],t['missing_evidence_count'],
        t['parameter_mining_penalty'],t['representative_variant_id']))
    return {'gate_version':'research-candidate-gate-v3','template_assessments':templates,
        'concept_assessments':concept_assessments,'evidence_review_queue':queue,
        'variant_status_counts':dict(Counter(r['candidate_gate']['status'] for r in rows)),
        'template_status_counts':dict(Counter(t['status'] for t in templates if t['strategy_template_id'])),
        'top_blocking_reasons':dict(Counter(k for r in rows for k in r['candidate_gate']['blocking_reasons']))}

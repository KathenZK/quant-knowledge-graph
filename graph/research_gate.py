"""V4 fail-closed gate, with independent source, derivation and data checks."""
from quantgraph.graph.research_gate_v2 import ReviewDecision
from quantgraph.graph.research_gate_v3 import evaluate as legacy_evaluate, enrich_projection as legacy_enrich
from quantgraph.graph.data_requirements import derive
from quantgraph.models.evidence_v4 import EvidenceEnrichmentV4

VERSION='research-candidate-gate-v4'


def evaluate(row,decision=None):
    e=None
    old=decision
    if decision and decision.get('schema_version')=='evidence-enrichment-v4':
        e=EvidenceEnrichmentV4.model_validate(decision)
        old={k:v for k,v in decision.items() if k not in {'derived_data_requirement','dataset_binding'}}
        old['schema_version']='evidence-enrichment-v3'
    result=legacy_evaluate(row,old)
    blockers=[x for x in result['blocking_reasons'] if x!='DATA_AVAILABILITY_UNCONFIRMED']
    traceable=bool(e and e.source.url==row['variant']['source_url'] and e.source.source_evidence_level in {'PRIMARY','SECONDARY'})
    support=result['source_status']=='VERIFIED'
    derived=False; data=False; rights=result['rights_status']=='ALLOWED'
    if e:
        try:
            expected=derive(row['variant']['rule_ast'],e.execution.model_dump(mode='json'),calendar=e.derived_data_requirement.calendar)
            derived=expected==e.derived_data_requirement.model_dump(mode='json')
        except ValueError:pass
        b=e.dataset_binding;r=b.rights_evidence;d=e.data_requirement;c=b.coverage
        rights=rights and r.scope=='MARKET_DATA' and r.status=='VERIFIED' and r.research_use_allowed is True \
            and r.confidence in {'HIGH','MEDIUM'} and r.provider==d.exchange and r.source==d.data_source \
            and r.research_use_scope in {e.use_context,'PRIVATE_INTERNAL_RESEARCH'} \
            and r.derivative_allowed is True and (r.attribution_required is False or bool(r.attribution))
        data=derived and c.coverage_status=='VERIFIED' and b.acceptance_status=='TRUSTED' \
            and not b.missing_native_fields and d.quality_status=='PASS' and d.real_market_data \
            and d.data_availability_status=='VERIFIED_AVAILABLE' and c.calendar==d.calendar \
            and not e.derived_data_requirement.auxiliary_data
        if e.derived_data_requirement.auxiliary_data:blockers.append('AUXILIARY_DATA_UNVERIFIED')
        if r.status=='PROHIBITED' or r.research_use_allowed is False:result['status']='BLOCKED'
    else:
        blockers.append('V4_REVIEW_REQUIRED')
        rights=False
    if not traceable:blockers.append('SOURCE_EVIDENCE_UNVERIFIED')
    if not derived:blockers.append('DATA_REQUIREMENT_UNVERIFIED')
    if not data:blockers.append('DATA_AVAILABILITY_UNCONFIRMED')
    if not rights:blockers.append('RIGHTS_REVIEW_REQUIRED')
    blockers=sorted(set(blockers))
    status='BLOCKED' if result['status']=='BLOCKED' else 'ELIGIBLE' if not blockers else 'REVIEW_REQUIRED'
    if e and blockers==['EXECUTION_CONTRACT_INCOMPLETE'] and not e.execution.accepted_research_assumptions:
        status='CONDITIONALLY_ELIGIBLE'
    scores=dict(source=10*traceable,source_support=10*support,rights=20*rights,
        rule=20*(result['rule_status']=='VERIFIED'),execution=15*(result['execution_status']=='COMPLETE'),
        data_requirement=5*derived,data_availability=10*data,dedup=5*(result['dedup_status']!='UNRESOLVED'),
        ontology=5*(result['ontology_status']=='MAPPED'))
    return {**result,'gate_version':VERSION,'status':status,'eligible':status=='ELIGIBLE',
        'source_status':'VERIFIED' if traceable else 'UNVERIFIED',
        'source_support_status':'VERIFIED' if support else 'UNVERIFIED',
        'rights_status':'ALLOWED' if rights else 'REVIEW_REQUIRED',
        'data_requirement_status':'COMPLETE' if derived else 'UNVERIFIED',
        'data_availability_status':'VERIFIED_AVAILABLE' if data else 'UNCONFIRMED',
        'data_status':'VERIFIED_AVAILABLE' if data else 'UNCONFIRMED',
        'blocking_reasons':blockers,'blockers':blockers,'research_readiness_score':sum(scores.values()),
        'candidate_quality_score':sum(scores.values()),'score_components':scores}


def enrich_projection(row,decision):
    legacy=decision
    if decision and decision.get('schema_version')=='evidence-enrichment-v4':
        legacy={k:v for k,v in decision.items() if k not in {'derived_data_requirement','dataset_binding'}}
        legacy['schema_version']='evidence-enrichment-v3'
    row=legacy_enrich(row,legacy)
    gate=evaluate(row,decision)
    row.update(candidate_gate=gate,candidate_quality_score=gate['research_readiness_score'],
        research_allowed=gate['rights_status']=='ALLOWED',research_rights_status=gate['rights_status'],
        data_available=gate['data_status']=='VERIFIED_AVAILABLE')
    if decision:row['reviewed_evidence']=decision
    return row

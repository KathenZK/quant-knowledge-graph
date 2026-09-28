"""Fail-closed research admission. Readiness is not expected return."""
from quantgraph.models.evidence import EvidenceEnrichment, ResearchCandidateAssessment
from quantgraph.graph.research_gate_v2 import ReviewDecision  # legacy journal compatibility only

VERSION='research-candidate-gate-v3'


def evaluate(row, decision=None):
    v=row['variant']; blockers=[];warnings=[];scores={}; e=None
    if decision and decision.get('schema_version')=='evidence-enrichment-v3':
        e=EvidenceEnrichment.model_validate(decision)
    elif decision:
        blockers.append('LEGACY_REVIEW_REQUIRES_V3')
    rule=bool(v.get('rule_ast') and row.get('definition_admitted') and e and e.rule_review_status=='VERIFIED')
    source=bool(e and e.source.url==v['source_url'] and e.source.source_evidence_level in {'PRIMARY','SECONDARY'}
                and e.source.source_support_type in {'EXACT_STRATEGY','STRATEGY_FRAMEWORK','IMPLEMENTATION_EXAMPLE'}
                and all(k in e.source.supported_rule_components for k in ('indicator','entry','exit'))
                and e.provenance_type!='UNKNOWN')
    rights=False;prohibited=False
    if e:
        by_scope={r.scope:r for r in e.rights}
        scopes={'SOURCE_TEXT','MARKET_DATA'}
        if e.source.source_type=='OPEN_SOURCE_IMPLEMENTATION':scopes.add('IMPLEMENTATION_CODE')
        prohibited=any(r.research_use_allowed is False for r in e.rights)
        rights=scopes<=by_scope.keys() and all(by_scope[k].research_use_allowed is True
          and by_scope[k].license_confidence in {'HIGH','MEDIUM'}
          and by_scope[k].research_use_scope in {e.use_context,'PRIVATE_INTERNAL_RESEARCH'}
          and (not by_scope[k].attribution_required or by_scope[k].attribution) for k in scopes)
        if e.provenance_type in {'SOURCE_DERIVED','BOT_DERIVED','PARAMETER_VARIANT','MARKET_VARIANT','ASSET_VARIANT'}:
            rights=rights and by_scope.get('SOURCE_TEXT') is not None and by_scope['SOURCE_TEXT'].derivative_allowed is True
            if 'IMPLEMENTATION_CODE' in scopes:
                rights=rights and by_scope.get('IMPLEMENTATION_CODE') is not None and by_scope['IMPLEMENTATION_CODE'].derivative_allowed is True
        warnings.extend(e.warnings)
        if e.source.unsupported_rule_components:warnings.append('SOURCE_DOES_NOT_DEFINE_ALL_RESEARCH_CHOICES')
    execution=False;conditional=False
    if e:
        contract=e.execution.model_dump(mode='json')
        facts=[x for x in contract.values() if isinstance(x,dict) and 'value' in x]
        execution=e.execution.closed_bar_only and all(x['basis']!='UNKNOWN' and x['value'] is not None for x in facts)
        conditional=any(x['basis']=='RESEARCH_ASSUMPTION' for x in facts) and not e.execution.accepted_research_assumptions
        if conditional:execution=False
        if any(x['basis']=='RESEARCH_ASSUMPTION' for x in facts):warnings.append('EXPLICIT_RESEARCH_ASSUMPTIONS')
    symbols=set();unresolved=False
    def assets(node):
        nonlocal unresolved
        if isinstance(node,dict):
            for k,value in node.items():
                if k in {'risk_asset','safe_asset','asset'}:
                    if value:symbols.add(value)
                    elif ('allocation' in node or k in {'risk_asset','safe_asset'}) and node.get('cash') is not True:unresolved=True
                elif k=='assets':
                    symbols.update(x for x in value if x);unresolved|=any(x is None for x in value)
                else:assets(value)
        elif isinstance(node,list):
            for value in node:assets(value)
    assets(v.get('rule_ast'))
    data=bool(e and e.data_requirement.data_availability_status=='VERIFIED_AVAILABLE'
       and e.data_requirement.real_market_data and e.data_requirement.quality_status=='PASS'
       and symbols and not unresolved and symbols<=set(e.data_requirement.symbols)
       and {'open','close'}<=set(e.data_requirement.required_fields))
    dedup=bool(e and e.dedup_status!='UNRESOLVED')
    ontology=bool(v.get('strategy_concept_id') and v.get('strategy_template_id'))
    for name,ok,points,reason in [('source',source,20,'SOURCE_SUPPORT_UNVERIFIED'),('rights',rights,20,'RIGHTS_REVIEW_REQUIRED'),
        ('rule',rule,20,'RULE_NOT_VERIFIED'),('execution',execution,15,'EXECUTION_CONTRACT_INCOMPLETE'),
        ('data',data,15,'DATA_AVAILABILITY_UNCONFIRMED'),('dedup',dedup,5,'DEDUP_UNRESOLVED'),('ontology',ontology,5,'ONTOLOGY_INCOMPLETE')]:
        scores[name]=points if ok else 0
        if not ok:blockers.append(reason)
    if prohibited or (e and (e.rule_review_status=='SOURCE_CONFLICT' or e.data_requirement.quality_status=='FAIL')):
        status='BLOCKED'
    elif not blockers:status='ELIGIBLE'
    elif conditional and set(blockers)=={'EXECUTION_CONTRACT_INCOMPLETE'}:status='CONDITIONALLY_ELIGIBLE'
    else:status='REVIEW_REQUIRED'
    assessment=ResearchCandidateAssessment(gate_version=VERSION,status=status,
       strategy_concept_id=v.get('strategy_concept_id'),strategy_template_id=v.get('strategy_template_id'),
       source_status='VERIFIED' if source else 'UNVERIFIED',rights_status='PROHIBITED' if prohibited else 'ALLOWED' if rights else 'REVIEW_REQUIRED',
       rule_status='VERIFIED' if rule else 'INCOMPLETE',execution_status='COMPLETE' if execution else 'INCOMPLETE',
       data_status='VERIFIED_AVAILABLE' if data else 'UNCONFIRMED',dedup_status=e.dedup_status if e else 'UNRESOLVED',
       ontology_status='MAPPED' if ontology else 'INCOMPLETE',research_readiness_score=sum(scores.values()),
       blocking_reasons=blockers,warnings=sorted(set(warnings))).model_dump(mode='json')
    return {**assessment,'eligible':status=='ELIGIBLE','candidate_quality_score':sum(scores.values()),
        'blockers':blockers,'score_components':scores,'score_meaning':'RESEARCH_READINESS_NOT_EXPECTED_RETURN',
        'hypothesis_id':v.get('strategy_template_id'),'promotion_allowed':False}


def enrich_projection(row, decision):
    """Evidence overlays never mutate raw or strategy identity."""
    gate=evaluate(row,decision)
    row.update(candidate_gate=gate,candidate_quality_score=gate['research_readiness_score'])
    if decision and decision.get('schema_version')=='evidence-enrichment-v3':
        e=decision;contract=e['execution']
        row.update(reviewed_evidence=e,research_allowed=gate['rights_status']=='ALLOWED',
            research_rights_status=gate['rights_status'],data_available=gate['data_status']=='VERIFIED_AVAILABLE',
            execution_contract={**contract,'timing':contract['execution_timing']['value'],
                'price_adjustment':contract['price_adjustment']['value'],'missing_data_policy':contract['missing_data_policy']['value'],
                'indicator_semantics':contract['indicator_semantics']['value'],'closed_bar_only':contract['closed_bar_only'],
                'costs':{k:contract['transaction_cost_model'][k] for k in ('fee_bps','slippage_bps')}})
        row['variant']['source_verification']=gate['source_status']
        row['variant']['provenance_type']=e['provenance_type']
    from quantgraph.normalize.strategy.source_classification import classify_source
    row['source_evidence']=decision['source'] if decision and 'source' in decision else classify_source(row['variant']['source_url'])
    row['diversity_metadata']={'strategy_family':row['variant'].get('strategy_concept_id'),
       'factor_families':sorted({x['factor_id'] for x in row.get('factor_links',[])}),
       'asset_class':row['variant'].get('market_taxonomy',{}).get('asset_class',[]),
       'market':row['variant'].get('market_taxonomy',{}).get('regions',[]),
       'frequency':(row['variant'].get('rule_ast') or {}).get('schedule'),
       'source_type':decision['source']['source_type'] if decision and 'source' in decision else 'UNKNOWN'}
    return row

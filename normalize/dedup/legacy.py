import collections, json, re
from quantgraph.collectors.common import uid
from quantgraph.normalize.formula import digest

def graph(c):
    records=c.records; factors={};concepts={};aliases=[];relations=[]
    def relate(kind,left,right,reason,status='confirmed',left_type='factor',right_type='factor'):
        relations.append(dict(relation_id=uid('rel',kind+':'+left+':'+right),relation_type=kind,from_id=left,to_id=right,from_type=left_type,to_type=right_type,status=status,evidence=reason))
    for r in records:
        fid=r['canonical_factor_id'];cid=r['concept_id']
        concepts.setdefault(cid,dict(concept_id=cid,factor_concept=r['factor_concept'],scope='family; not a claim of formula equivalence'))
        if fid not in factors:
            factors[fid]=dict(canonical_factor_id=fid,concept_id=cid,representative_record_id=r['record_id'],signal_name=r['signal_name'],record_kind=r['record_kind'],high_quality_eligible=r['high_quality_eligible'])
            relate('variant_of',fid,cid,'Curated or source-scoped family key',right_type='concept')
        else:
            prior=factors[fid];prior['high_quality_eligible'] |= r['high_quality_eligible']
            relate('exact_duplicate',r['record_id'],prior['representative_record_id'],'Identical normalized formula, dialect, frequency and configurable equity scope; dataset membership retained.',left_type='record',right_type='record')
        # Aliases are scoped: a bare Alpha001 or SMB is never a universal identifier.
        for a in dict.fromkeys([r['signal_name'],r['source_native_id']]+r['aliases']):
            aid=uid('alias',r['source_id']+':'+a+':'+fid)
            aliases.append(dict(alias_id=aid,alias=a,normalized_alias=re.sub(r'[^\w]+','',a.casefold()),namespace=r['source_id'],canonical_factor_id=fid,record_id=r['record_id'],alias_type='synonym',evidence='source name/acronym or explicit scoped naming'))
    # Explicit source-code rows; no merges triggered by implementation count.
    byrecord={x['record_id']:x for x in records}
    impl_groups=collections.defaultdict(list)
    for i in c.implementations:
        i['canonical_factor_id']=byrecord[i['record_id']]['canonical_factor_id'];fid=i['canonical_factor_id'];impl_groups[fid].append(i)
        relate('implements',i['implementation_id'],fid,i['code_url'],left_type='implementation')
    for fid,items in impl_groups.items():
        for i in items[1:]:
            if i['implementation_id']!=items[0]['implementation_id']:relate('different_implementation',i['implementation_id'],items[0]['implementation_id'],'Same canonical signal, different source-code locator or revision.',left_type='implementation',right_type='implementation')
    # Same-family relations preserve distinct canonical factor IDs.
    families=collections.defaultdict(list)
    for f in factors.values():families[f['concept_id']].append(f)
    for cid,items in families.items():
        for f in items[1:]:relate('family_variant',items[0]['canonical_factor_id'],f['canonical_factor_id'],'Shared explicit family assignment; parameters, domain and construction may differ.')
    # Review queue: lexical similarity proposes candidates only.
    normalized=collections.defaultdict(list)
    for a in aliases:normalized[a['normalized_alias']].append(a)
    candidates=[]
    for name,items in normalized.items():
        fids=sorted({x['canonical_factor_id'] for x in items})
        if len(fids)>1 and len(fids)<=10:
            for fid in fids[1:]:
                candidates.append(dict(candidate_id=uid('candidate',name+':'+fids[0]+':'+fid),left_id=fids[0],right_id=fid,reason='same normalized alias',alias=name,status='unreviewed_do_not_merge'))
    # The same formulas across dialects may have different semantics; never merge them.
    a=next((r for r in records if r['source_id']=='wq101' and r['source_native_id']=='alpha041'),None)
    b=next((r for r in records if r['source_id']=='gtja191' and r['source_native_id']=='alpha013'),None)
    if a is not None and b is not None:
        candidates.append(dict(candidate_id=uid('candidate','wq41-gtja13'),left_id=a['canonical_factor_id'],right_id=b['canonical_factor_id'],reason='same price expression structure; compare market/VWAP conventions before merge',alias=None,status='cross_dialect_review_required'))
    return dict(records=records,factors=list(factors.values()),concepts=list(concepts.values()),implementations=list({x['implementation_id']:x for x in c.implementations}.values()),aliases=list({x['alias_id']:x for x in aliases}.values()),relationships=list({x['relation_id']:x for x in relations}.values()),duplicate_candidates=list({x['candidate_id']:x for x in candidates}.values()),issues=c.issues)

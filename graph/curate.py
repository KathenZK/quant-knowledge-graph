"""Build a reviewed definition graph; never silently promote executable semantics."""
from collections import defaultdict
import json
from pathlib import Path
from quantgraph.collectors.common import uid
from quantgraph.models.entities import ENTITY_MODELS
from quantgraph.normalize.aliases import key as alias_key
from quantgraph.normalize.dedup.policy import admission
from quantgraph.normalize.rights import rights_for, commercial_allowed
from quantgraph.normalize.taxonomy.rules import category, ALIASES
from quantgraph.normalize.formula.lookback import lookback


def curate(root, legacy):
    rows = legacy['records']
    issues = defaultdict(list)
    for issue in legacy['issues']:
        issues[issue['record_id']].append(issue['code'])
    admitted, decisions = [], []
    for row in rows:
        ok, reasons = admission(row, issues[row['record_id']])
        decisions.append(dict(record_id=row['record_id'], factor_variant_id=row['canonical_factor_id'],
                              admitted=ok, reasons=reasons, rights=rights_for(row)))
        if ok:
            admitted.append(row)
    groups = defaultdict(list)
    for row in admitted:
        groups[row['canonical_factor_id']].append(row)
    tables = {name: [] for name in ENTITY_MODELS if name not in {'strategy_concepts', 'strategy_templates', 'strategy_variants'}}
    tables.update(aliases=[], source_records=[], id_map=[])
    entity_maps = {name: {} for name in ('factor_concepts', 'sources', 'licenses', 'datasets', 'formulas', 'papers', 'authors')}
    concepts = entity_maps['factor_concepts']
    registry_path = Path(root)/'models/id_registry.json'
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {}
    for cid in sorted({r['concept_id'] for r in rows}):
        if cid not in registry:
            registry[cid] = f'F{max([int(x[1:]) for x in registry.values()] or [0])+1:06d}'
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True)+'\n')
    timestamp = max(r['retrieved_at'] for r in rows)
    edges = {}

    def edge(relation, left, ltype, right, rtype, evidence, source, confidence=1.0):
        eid = uid('edge', ':'.join([relation, left, right, evidence]))
        edges[eid] = dict(relationship_id=eid, relation=relation, from_id=left, from_type=ltype,
                          to_id=right, to_type=rtype, confidence=confidence, evidence=evidence,
                          source=source, status='CONFIRMED')

    def paper(row, title=None, year=None, authors=None, url=None, collection=False):
        title = title or row['paper_title']; year = year or row['paper_year']
        authors = authors if authors is not None else row['authors']; url = url or row['paper_url']
        if not title and not authors and not year:
            return None
        identity = (title+'|'+str(year)) if title else row['record_id']
        pid = uid('paper', row['source_id']+':'+identity)
        author_ids = []
        for name in authors:
            aid = uid('author', row['source_id']+':'+name)
            entity_maps['authors'].setdefault(aid, dict(author_id=aid, name=name,
                identity_status='UNRESOLVED_CITATION_NAME', namespace=row['source_id']))
            author_ids.append(aid)
            edge('AUTHORED_BY', pid, 'Paper', aid, 'Author', 'Source citation string; person disambiguation pending', row['source_url'])
        obj = entity_maps['papers'].setdefault(pid, dict(paper_id=pid, title=title, year=year, authors=authors,
             author_ids=author_ids, url=url, citation_label=title or ', '.join(authors)+' ('+str(year)+')',
             metadata_status='COLLECTION_REFERENCE' if collection else ('TITLE_PRESENT' if title else 'PARTIAL_CITATION'), provenance=[]))
        evidence = dict(record_id=row['record_id'], source_url=row['source_url'], source_locator=row['source_locator'], scope='collection' if collection else 'original_citation')
        if evidence not in obj['provenance']:
            obj['provenance'].append(evidence)
        return pid

    for vid, members in sorted(groups.items()):
        row = members[0]; cid = row['concept_id']; rights = rights_for(row)
        cat = category(row); sid = row['source_id']; time = row['retrieved_at']
        concept_name = ('Qlib '+row['factor_concept'].removeprefix('qlib:')+' feature family') if sid=='qlib' else (row['signal_name'] if row['factor_concept'].startswith(sid+':') else row['factor_concept'])
        concepts.setdefault(cid, dict(canonical_factor_id=cid, canonical_name=concept_name,
            short_id=registry[cid], aliases=ALIASES.get(row['factor_concept'], []),
            description='Source-scoped factor family; membership does not assert formula equivalence.',
            economic_logic=None, category=cat, scope='source_scoped_or_explicitly_reviewed_family',
            created_at=time, updated_at=time))
        lid = rights['license_id']
        entity_maps['licenses'].setdefault(lid, dict(**rights, evidence_urls=[row['terms_url']], reviewed_at=timestamp,
            notes=row['terms']))
        src = entity_maps['sources'].setdefault(sid, dict(source_id=sid, source_name=row['source_name'], url=row['source_url'],
            license_id=lid, revisions=[], collected_at=time, storage_policy='licensed_source_definitions'))
        if row['source_revision'] and row['source_revision'] not in src['revisions']:
            src['revisions'].append(row['source_revision'])
        pids = []
        pid = paper(row)
        if pid:
            pids.append(pid)
            edge('DESCRIBED_BY', vid, 'FactorVariant', pid, 'Paper', 'Exact source bibliographic association; incomplete citation explicitly marked', row['source_url'])
        if sid == 'qlib':
            pid = paper(row, title='Qlib: An AI-oriented Quantitative Investment Platform', year=2020,
                authors=['Xiao Yang', 'Weiqing Liu', 'Dong Zhou', 'Jiang Bian', 'Tie-Yan Liu'],
                url='https://arxiv.org/abs/2009.11189', collection=True)
            pids.append(pid)
            edge('DESCRIBED_BY', sid, 'Source', pid, 'Paper', 'Platform paper; not a claim that every generated feature is individually proposed in the paper', 'https://arxiv.org/abs/2009.11189')
        if sid == 'jkp':
            pid = paper(row, title='Is There a Replication Crisis in Finance?', year=2023,
                authors=['Theis Ingerslev Jensen', 'Bryan Kelly', 'Lasse Heje Pedersen'],
                url='https://doi.org/10.1111/jofi.13249', collection=True)
            pids.append(pid)
            edge('DESCRIBED_BY', sid, 'Source', pid, 'Paper', 'Collection provenance; original anomaly citation is separate', row['source_url'])
        if sid == 'osap':
            pid = paper(row, title='Open Source Cross-Sectional Asset Pricing', year=2022,
                authors=['Andrew Y. Chen', 'Tom Zimmermann'], url='https://www.openassetpricing.com/', collection=True)
            pids.append(pid)
            edge('DESCRIBED_BY', sid, 'Source', pid, 'Paper', 'Collection provenance; not substituted for original anomaly paper', row['source_url'])
        formula_id = uid('formula', row['formula_hash']) if row['formula_hash'] else None
        if formula_id:
            entity_maps['formulas'].setdefault(formula_id, dict(formula_id=formula_id, raw_formula=row['formula'],
                normalized_formula=row['normalized_formula'], formula_ast=row['formula_ast'], dialect=row['dialect'],
                semantic_status='NOT_VERIFIED', source_record_ids=[m['record_id'] for m in members]))
            edge('DERIVED_FROM', vid, 'FactorVariant', formula_id, 'Formula', 'Formula describes this signal; syntax only, execution semantics pending', row['source_url'])
        variant = dict(canonical_factor_id=cid, canonical_name=concepts[cid]['canonical_name'], factor_concept=row['factor_concept'],
            factor_variant_id=vid, variant_name=row['signal_name'],
            aliases=sorted({a for m in members for a in m['aliases']+[m['signal_name'], m['source_native_id']]}),
            description=row['raw_definition'], economic_logic=None, category=cat, raw_formula=row['formula'],
            normalized_formula=row['normalized_formula'], formula_ast=row['formula_ast'], formula_id=formula_id,
            dialect=row['dialect'], parameters=row['parameters'], required_fields=row['required_fields'],
            required_fields_status=row['required_fields_status'], lookback=lookback(row['formula_ast'],row['dialect']), frequency=row['frequency'],
            asset_class=row['asset_class'], universe=row['universe'], holding_period=row['holding_period'], rebalance=row['rebalance'],
            source_id=sid, source_name=row['source_name'], source_url=row['source_url'],
            source_record_ids=[m['record_id'] for m in members], source_native_ids=[m['source_native_id'] for m in members],
            source_sha256=row['source_file_sha256'], source_revision=row['source_revision'], source_locator=row['source_locator'],
            paper_title=row['paper_title'], paper_year=row['paper_year'], authors=row['authors'], paper_ids=sorted(set(pids)),
            code_url=row['code_url'], quality_status='CURATED_DEFINITION', semantic_status='NOT_VERIFIED', backtest_ready=False,
            issue_codes=sorted({x for m in members for x in issues[m['record_id']]}), created_at=time, updated_at=time, **rights)
        tables['factor_variants'].append(variant)
        edge('VARIANT_OF', vid, 'FactorVariant', cid, 'FactorConcept', 'Explicit or source-local family assignment; not SAME_AS', row['source_url'])
        edge('SOURCED_FROM', vid, 'FactorVariant', sid, 'Source', row['source_locator'], row['source_url'])
        for member in members:
            rid = member['record_id']; did = uid('dataset', sid+':'+(member['collection'] or 'definitions'))
            entity_maps['datasets'].setdefault(did, dict(dataset_id=did, name=member['collection'] or row['source_name']+' definitions',
                source_id=sid, content_type='feature_configuration' if sid=='qlib' else 'definition_catalog',
                revision=member['source_revision'], license_id=lid, source_url=member['source_url'], observations_ingested=False))
            edge('SOURCED_FROM', rid, 'SourceRecord', did, 'Dataset', 'Record belongs to collection; no return panel stored', member['source_url'])
            tables['source_records'].append(dict(record_id=rid, factor_variant_id=vid, source_id=sid, source_native_id=member['source_native_id'],
                source_url=member['source_url'], source_locator=member['source_locator'], sha256=member['source_file_sha256'], dataset_id=did))
            tables['id_map'].append(dict(legacy_record_id=rid, legacy_canonical_factor_id=vid, canonical_factor_id=cid, factor_variant_id=vid, short_id=registry[cid]))
            for a in sorted(set(member['aliases']+[member['signal_name'], member['source_native_id']])):
                aid=uid('alias', sid+':'+a+':'+vid)
                tables['aliases'].append(dict(alias_id=aid, alias=a, normalized_alias=alias_key(a), namespace=sid, factor_variant_id=vid, canonical_factor_id=cid))
                edge('ALIAS_OF', aid, 'Alias', vid, 'FactorVariant', 'Source-scoped name/acronym; not globally equivalent', member['source_url'])
            if member != row:
                edge('SAME_AS', rid, 'SourceRecord', row['record_id'], 'SourceRecord', 'Identical AST/dialect/frequency/domain in pinned Qlib config; source membership retained', member['source_url'])
    variants={v['factor_variant_id']:v for v in tables['factor_variants']}
    for old in legacy['implementations']:
        vid=old['canonical_factor_id']
        if vid not in variants or old['record_id'] not in {r['record_id'] for r in admitted}:
            continue
        tables['implementations'].append(dict(implementation_id=old['implementation_id'], factor_variant_id=vid,
            source_record_id=old['record_id'], code_url=old['code_url'], revision=old['source_revision'],
            sha256=old['source_file_sha256'], source_locator=old['source_locator'], language=old['language'],
            status=old['implementation_status'], license=old['source_license'], terms_url=old['source_terms_url'],
            commercial_use=variants[vid]['commercial_use'], executed=False))
        edge('IMPLEMENTATION_OF', old['implementation_id'], 'Implementation', vid, 'FactorVariant', 'Pinned source locator; program never executed', old['code_url'])
        edge('IMPLEMENTED_BY', vid, 'FactorVariant', old['implementation_id'], 'Implementation', 'Pinned source locator; equivalence not certified', old['code_url'])
    for name, entities in entity_maps.items():
        tables[name]=list(entities.values())
    tables['relationships']=list(edges.values())
    tables['aliases']=list({x['alias_id']:x for x in tables['aliases']}.values())
    for name, model in ENTITY_MODELS.items():
        if name not in tables:
            continue
        tables[name]=[model.model_validate(r).model_dump(mode='json') for r in tables[name]]
    return tables, decisions


def commercial_subset(tables):
    """Materialize a closed graph. Forbidden content cannot leak through related nodes."""
    keep={v['factor_variant_id'] for v in tables['factor_variants'] if commercial_allowed(v)}
    out={name:[] for name in tables}
    out['factor_variants']=[v for v in tables['factor_variants'] if v['factor_variant_id'] in keep]
    vids=out['factor_variants']
    refs={'factor_concepts':('canonical_factor_id',{v['canonical_factor_id'] for v in vids}),
          'sources':('source_id',{v['source_id'] for v in vids}),
          'licenses':('license_id',{v['license_id'] for v in vids}),
          'formulas':('formula_id',{v['formula_id'] for v in vids}),
          'papers':('paper_id',{p for v in vids for p in v['paper_ids']})}
    for name,(field,ids) in refs.items():
        out[name]=[r for r in tables[name] if r[field] in ids]
    author_ids={a for p in out['papers'] for a in p['author_ids']}
    out['authors']=[a for a in tables['authors'] if a['author_id'] in author_ids]
    for name in ('implementations','aliases','source_records','id_map'):
        out[name]=[r for r in tables[name] if r['factor_variant_id'] in keep]
    datasets={r['dataset_id'] for r in out['source_records']}
    out['datasets']=[d for d in tables['datasets'] if d['dataset_id'] in datasets]
    # No strategy or backtest is commercially cleared implicitly by factor rights.
    from quantgraph.graph.store import PRIMARY_KEYS
    entity_ids={r[field] for name,field in PRIMARY_KEYS.items() if name not in ('relationships','id_map','strategy_factor') for r in out.get(name, [])}
    out['relationships']=[r for r in tables['relationships'] if r['from_id'] in entity_ids and r['to_id'] in entity_ids]
    return out

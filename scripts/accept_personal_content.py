"""Real-data, deterministic reading/search acceptance; private reports stay local."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time

from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.personal_catalog import PersonalCatalogRepository, private_text
from quantgraph.graph.personal_research import RetainedResearch

SEED = 'personal-workbench-content-2026-09-v1'


def select(rows, size, key):
    groups = defaultdict(list)
    digest = lambda text: hashlib.sha256((SEED + text).encode()).hexdigest()
    for row in rows:
        groups[key(row)].append(row)
    for values in groups.values():
        values.sort(key=lambda row:digest(row['entity_id']))
    buckets = [groups[k] for k in sorted(groups, key=lambda k:digest(str(k)))]
    chosen = []
    while buckets and len(chosen) < size:
        for bucket in buckets:
            if bucket and len(chosen) < size:
                chosen.append(bucket.pop(0))
        buckets = [bucket for bucket in buckets if bucket]
    return chosen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    catalog = PersonalCatalogRepository(args.runtime / 'catalog.sqlite')
    catalog.result_reader = RetainedResearch(args.runtime)
    started = time.monotonic()
    meta = catalog.metadata()
    cold = time.monotonic()-started
    items = catalog.all_items()
    by_id = {v['entity_id']:v for v in items}
    failures, checks, raw_rows = [], Counter(), {}
    with catalog.connect() as con:
        for row in con.execute('SELECT entity_id,kind,private_payload FROM catalog_items WHERE active=1 AND is_test=0'):
            raw = json.loads(row['private_payload'])
            raw_rows[row['entity_id']] = raw
            item = by_id.get(row['entity_id'])
            if not item:
                failures.append(dict(entity_id=row['entity_id'], reason='ACTIVE_INPUT_MISSING'))
                continue
            if row['kind'] == 'strategy':
                original = raw.get('raw_record',{}).get('规则') or raw.get('variant',{}).get('original_rule_text')
                shown = item.get('knowledge',{}).get('original_rule')
                checks['strategy_records'] += 1
                if original:
                    checks['strategy_original_rules'] += 1
                    if private_text(original) != shown:
                        failures.append(dict(entity_id=row['entity_id'], reason='ORIGINAL_RULE_OMITTED_OR_CHANGED'))
                if not item.get('knowledge',{}).get('unknowns'):
                    failures.append(dict(entity_id=row['entity_id'], reason='NO_UNKNOWN_BOUNDARIES'))
            elif row['kind'] in {'variant','source'}:
                original = raw.get('raw_formula') or raw.get('formula')
                if original:
                    checks['factor_original_formulas'] += 1
                    if private_text(original) != item.get('formula'):
                        failures.append(dict(entity_id=row['entity_id'], reason='ORIGINAL_FORMULA_OMITTED_OR_CHANGED'))
            if item.get('knowledge',{}).get('summary'):
                checks['readable_summaries'] += 1
    strategies = [v for v in items if v['kind']=='strategy']
    factors = [v for v in items if v['kind']=='variant' or v.get('source_type')=='factor_source_record']
    selected_strategies = select(strategies, 50, lambda v:(v['knowledge']['method_family']['value'],
        v.get('strategy',{}).get('parse_status'), v.get('source_type')))
    selected_factors = select(factors, 30, lambda v:(v.get('source_name'),v['knowledge']['method_family']['value'],
        v['knowledge']['filters']['completeness']))
    frozen_path = args.output / 'content-sample-ids.json'
    if frozen_path.is_file():
        frozen = json.loads(frozen_path.read_text())
        selected_strategies = [by_id[eid] for eid in frozen['strategies']]
        selected_factors = [by_id[eid] for eid in frozen['factors']]
    else:
        frozen_path.write_text(json.dumps(dict(seed=SEED,
            strategies=[i['entity_id'] for i in selected_strategies],
            factors=[i['entity_id'] for i in selected_factors]), ensure_ascii=False, indent=2))
    samples = []
    for item in selected_strategies + selected_factors:
        value = catalog.detail(item['kind'],item['entity_id'])
        samples.append(dict(entity_id=value['entity_id'],kind=value['kind'],name=value['name'],
            definition_revision=value['definition_revision'],source_url=value['source_url'],
            parse_status=value.get('strategy',{}).get('parse_status'),knowledge=value['knowledge'],
            has_formula=bool(value.get('formula')),has_rule=bool(value.get('strategy',{}).get('original_rule'))))
    baseline = CatalogRepository(args.runtime / 'catalog.sqlite')
    queries = [('strategy','RSI'),('strategy','相对强弱'),('strategy','配对'),('strategy','动量'),
        ('strategy','momentum'),('strategy','换仓'),('strategy','成交量'),('strategy','突破'),
        ('variant','MA5'),('variant','moving average'),('variant','均线'),('variant','Alpha101'),
        ('variant','成交量'),('variant','价值'),('variant','WorldQuant'),('variant','rank')]
    search = []
    for kind, query in queries:
        before = baseline.search(kind=kind,q=query,page_size=10)
        started = time.monotonic()
        after = catalog.search(kind=kind,q=query,page_size=10)
        elapsed = time.monotonic()-started
        search.append(dict(kind=kind,query=query,before_total=before['total'],after_total=after['total'],
            seconds=round(elapsed,3),top_names=[v['name'] for v in after['items']],
            top_matches=[dict(entity_id=v['entity_id'],name=v['name'],matches=v.get('matches')) for v in after['items']]))
        if not after['total']:
            failures.append(dict(query=query,reason='EXPECTED_REAL_QUERY_EMPTY'))
    relation_examples = {}
    for relation in ['USES_FACTOR','ASSET_VARIANT','PARAMETER_VARIANT','CATEGORY_LINK_ONLY']:
        with catalog.connect() as con:
            edges = list(con.execute("SELECT payload FROM catalog_edges WHERE json_extract(payload,'$.relation')=?",(relation,)))
        for row in edges:
            edge = json.loads(row[0])
            if edge['from_id'] in by_id and edge['to_id'] in by_id:
                graph = catalog.relations(edge['from_id'],relation=relation,limit=3)
                if graph['items']:
                    relation_examples[relation] = graph
                    break
    report = dict(seed=SEED,mode='personal_local',metadata=meta,input_reconciliation=catalog.reconcile(),
        full_corpus_checks=dict(checks),failures=failures,cold_metadata_seconds=round(cold,3),
        sampled_strategy_count=len(selected_strategies),sampled_factor_count=len(selected_factors),
        sample_strategy_strata=dict(Counter(str((s['knowledge']['method_family']['value'],s['strategy']['parse_status'])) for s in selected_strategies)),
        sample_factor_sources=dict(Counter(s.get('source_name') for s in selected_factors)),
        search=search,relation_examples=relation_examples,
        status='PASS' if not failures else 'FAIL',
        scope='全量字段保留与可读状态自动核验；分层样本仍须审阅忠实度和网页展示，不能把本脚本当语义正确性证明。')
    (args.output/'content-samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2))
    (args.output/'content-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:report[k] for k in ['status','full_corpus_checks','sampled_strategy_count','sampled_factor_count','failures']},ensure_ascii=False))
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()

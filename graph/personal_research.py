"""Read retained Graph research evidence without starting or importing an engine."""
import json
from pathlib import Path
import re
import sqlite3

from quantgraph.graph.catalog_projection import empty_results
from quantgraph.graph.personal_catalog import private_text


def safe_metadata(value):
    if isinstance(value, dict):
        return {key: safe_metadata(item) for key, item in value.items()
                if not re.search(r'(token|secret|password|passwd|apikey|authorization|credential|privatekey|sessionkey|cookie)',
                                 re.sub(r'[^a-z0-9]', '', key.casefold()))}
    if isinstance(value, list):
        return [safe_metadata(item) for item in value]
    return private_text(value) if isinstance(value, str) else value


def reference_key(ref):
    return (ref.get('entity_type'), ref.get('entity_id'), ref.get('definition_revision'))


class RetainedResearch:
    def __init__(self, runtime):
        self.runtime = Path(runtime)
        self._stamp = None
        self._items = []
        self._counts = {}

    def _load(self):
        path = self.runtime / 'jobs.sqlite'
        paths = [self.runtime / name for name in ['jobs.sqlite', 'ingestion.sqlite', 'factor-studies.sqlite']]
        stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None
                      for database in paths for p in (database, database.with_name(database.name + '-wal')))
        if stamp == self._stamp:
            return self._items
        items, seen = [], set()
        counts = dict(job_results=0, factor_journal_records=0, legacy_evidence_records=0,
                      duplicate_run_references=0, unlinked=0)
        jobs = []
        if path.is_file():
            with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as con:
                con.row_factory = sqlite3.Row
                jobs = con.execute('SELECT job_id,status,results FROM research_jobs WHERE results IS NOT NULL ORDER BY created').fetchall()
        for job in jobs:
            for value in json.loads(job['results']):
                counts['job_results'] += 1
                meta = value.get('study_metadata') or {}
                refs = meta.get('entity_refs', [])
                if not refs:
                    counts['unlinked'] += 1
                    continue
                run = value.get('run_id') or value.get('research_run_id')
                key = (run, json.dumps(refs, sort_keys=True))
                if key in seen:
                    counts['duplicate_run_references'] += 1
                    continue
                seen.add(key)
                summary = meta.get('public_summary') or {}
                items.append(dict(
                    job_id=job['job_id'], run_id=run, entity_refs=refs,
                    study_type=meta.get('study_type', '来源未说明'),
                    study_kind=meta.get('study_kind', '来源未说明'),
                    conclusion_level=meta.get('conclusion_level', '来源未说明'),
                    limitations=meta.get('limitations', []) + value.get('limitations', []),
                    lineage=meta.get('lineage', []), status=job['status'],
                    sample=summary.get('sample') or value.get('sample', {}),
                    metrics=summary.get('metrics', {}),
                    classification=summary.get('classification'),
                    execution_status=summary.get('execution_status'),
                    failure_reason=summary.get('failure_reason'),
                    source_reproduction=summary.get('source_reproduction'),
                    conclusion_reason=summary.get('conclusion_reason'),
                    promotion_allowed=False, numerical_display='PERSONAL_LOCAL',
                    provenance=meta.get('provenance', {}),
                    notice='已有 Graph 研究记录的本地只读副本；保留原定义版本，不产生新研究或授权结论。',
                ))
        runs = {}
        for item in items:
            if item['run_id']:
                runs.setdefault(item['run_id'], set()).update(reference_key(ref) for ref in item['entity_refs'])
        for name, table, counter in [('factor-studies.sqlite', 'studies', 'factor_journal_records'),
                                     ('ingestion.sqlite', 'evidence', 'legacy_evidence_records')]:
            source = self.runtime / name
            if not source.is_file():
                continue
            with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as con:
                if not con.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('table', table)).fetchone():
                    continue
                rows = con.execute(f'SELECT payload FROM {table}').fetchall()
            for row in rows:
                value = json.loads(row[0])
                counts[counter] += 1
                run = value.get('run_id') or value.get('research_run_id')
                if table == 'studies':
                    identity = value.get('mapping', {}).get('identity', {})
                    refs = [dict(entity_type='FactorVariant', entity_id=identity.get('factor_variant_id'),
                                 definition_revision=identity.get('definition_revision'))] if identity.get('factor_variant_id') else []
                else:
                    refs = [dict(entity_type='StrategyVariant', entity_id=eid,
                                 definition_revision='NOT_PINNED_IN_EVIDENCE') for eid in value.get('source_strategy_ids', [])]
                ref_ids = {reference_key(ref) for ref in refs}
                if run and ref_ids and ref_ids <= runs.get(run, set()):
                    counts['duplicate_run_references'] += 1
                    continue
                if not refs:
                    counts['unlinked'] += 1
                items.append(dict(run_id=run, job_id=None, entity_refs=refs, source_journal=name,
                    study_type=value.get('study_type') or value.get('evidence_kind', 'LEGACY_RESEARCH_REFERENCE'),
                    study_kind=value.get('research_status', 'RETAINED_SOURCE_RECORD'),
                    conclusion_level=value.get('validation_status', 'SUBMITTED_NOT_INDEPENDENTLY_VERIFIED'),
                    limitations=value.get('limitations', []) + (['原记录未固定定义版本；仅按其来源策略 ID 关联。'] if table=='evidence' else []),
                    lineage=[], status=value.get('status', 'RETAINED'), sample=value.get('sample', {}),
                    metrics=value.get('results', {}), promotion_allowed=False, numerical_display='PERSONAL_LOCAL',
                    artifact_sha256=value.get('artifact_sha256'),
                    notice='既有研究 journal 的只读引用；未重新计算，不补造验证结论。'))
                if run:
                    runs.setdefault(run, set()).update(ref_ids)
        self._counts = counts
        self._counts['distinct_run_ids'] = len({item['run_id'] for item in items if item['run_id']})
        self._items, self._stamp = safe_metadata(items), stamp
        return self._items

    def __call__(self, kind=None, eid=None):
        items = self._load()
        if eid:
            items = [v for v in items if any(r['entity_id'] == eid for r in v['entity_refs'])]
        return empty_results() | dict(items=items, total=len(items),
            input_counts=self._counts,
            status='已有研究记录' if items else '尚未研究',
            reason='按原研究定义版本展示；不同数据、成本与样本不作收益排名。')

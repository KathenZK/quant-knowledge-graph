"""Transactional private journal. SQLite is an adapter, not the wire contract.

Every submission, revision, projection and evidence is append-only. BEGIN
IMMEDIATE serializes writers; a failed projection rolls back the entire batch.
No raw payload or source text is written into request logs.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Protocol
from uuid import uuid4

from quantgraph.graph.grokbot import content_hash, stable_json
from quantgraph.models.ingestion import IngestBatch
from quantgraph.normalize.strategy.parser import VERSION
from quantgraph.graph.ingestion_migrations import migrate, IMMUTABLE_TABLES, SEMANTIC_HASH_VERSION, SCHEMA_VERSION, LEGACY_HASH_VERSION, semantic_hash


def now():
    return datetime.now(timezone.utc).isoformat()


class ProjectionUnavailable(ValueError):
    def __init__(self, status):
        self.status = status
        super().__init__('Projection is not READY; run quantgraph reproject')


class IngestionRepository(Protocol):
    def projection_status(self) -> dict: ...
    def ingest_stats(self) -> dict: ...
    def ingest(self, batch: IngestBatch, raw_bytes: bytes, key_id: str) -> dict: ...
    def get_job(self, job_id: str) -> dict: ...
    def get_batch(self, batch_id: str) -> dict: ...
    def variants(self, limit: int = 100, offset: int = 0) -> list[dict]: ...
    def lineage(self, variant_id: str) -> list[dict]: ...
    def consume_quota(self, key_id: str, limit: int) -> bool: ...
    def log_request(self, request_id: str, key_id: str, route: str, status: int) -> None: ...
    def usage(self, key_id: str) -> list[dict]: ...
    def put_evidence(self, payload: dict, key_id: str) -> dict: ...
    def evidence_for(self, variant_id: str) -> list[dict]: ...


class SQLiteIngestionRepository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            if con.execute('PRAGMA user_version').fetchone()[0] > SCHEMA_VERSION:
                raise ValueError('Ingestion database is newer than this application')
            con.execute('PRAGMA journal_mode=WAL')
            con.executescript('''
                CREATE TABLE IF NOT EXISTS submissions (
                    job_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    raw_bytes BLOB NOT NULL, payload TEXT NOT NULL, key_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, result TEXT NOT NULL,
                    UNIQUE(batch_id, payload_hash));
                CREATE TABLE IF NOT EXISTS revisions (
                    record_id TEXT NOT NULL, revision INTEGER NOT NULL, record_hash TEXT NOT NULL,
                    raw_payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(record_id, revision));
                CREATE TABLE IF NOT EXISTS observations (
                    job_id TEXT NOT NULL REFERENCES submissions(job_id), record_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, outcome TEXT NOT NULL,
                    PRIMARY KEY(job_id, record_id),
                    FOREIGN KEY(record_id, revision) REFERENCES revisions(record_id, revision));
                CREATE TABLE IF NOT EXISTS projections (
                    record_id TEXT NOT NULL, revision INTEGER NOT NULL, parser_version TEXT NOT NULL,
                    variant_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(record_id, revision, parser_version),
                    FOREIGN KEY(record_id, revision) REFERENCES revisions(record_id, revision));
                CREATE INDEX IF NOT EXISTS projection_variant ON projections(variant_id);
                CREATE INDEX IF NOT EXISTS submission_batch ON submissions(batch_id);
                CREATE TABLE IF NOT EXISTS request_logs (
                    request_id TEXT PRIMARY KEY, key_id TEXT NOT NULL, route TEXT NOT NULL,
                    status INTEGER NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS quotas (key_id TEXT, window INTEGER, count INTEGER,
                    PRIMARY KEY(key_id, window));
                CREATE TABLE IF NOT EXISTS evidence (
                    research_run_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
                    key_id TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')
            migrate(con)
            for table in ('submissions', 'revisions', 'observations', 'projections', 'evidence', 'request_logs', *IMMUTABLE_TABLES):
                for operation in ('UPDATE', 'DELETE'):
                    con.execute(f'''CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation}
                        BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END''')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        try:
            with con:
                yield con
        finally:
            con.close()

    def ingest(self, batch, raw_bytes, key_id):
        from quantgraph.graph.ingestion import project_record
        payload = batch.audit_payload()
        digest = content_hash(payload)
        job_id = 'job-' + content_hash([batch.batch_id, digest])[:32]
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            existing = con.execute('SELECT result FROM submissions WHERE job_id=?', (job_id,)).fetchone()
            if existing:
                result = json.loads(existing['result'])
                return {**result, 'accepted': 0, 'revision': 0, 'duplicate': len(batch.records),
                        'curated': 0, 'review_required': 0, 'replayed': True}
            result = dict(job_id=job_id, batch_id=batch.batch_id, status='COMPLETED', accepted=0,
                          duplicate=0, revision=0, curated=0, review_required=0, errors=0, replayed=False)
            observations = []
            observation_payloads = []
            for record in batch.records:
                raw = record.audit_payload()
                record_hash = content_hash(raw)
                semantic_record_hash = content_hash(record.semantic_payload())
                latest = con.execute('SELECT revision,semantic_record_hash FROM revision_semantics_v2 WHERE record_id=? ORDER BY revision DESC LIMIT 1', (record.record_id,)).fetchone()
                if latest and latest['semantic_record_hash'] == semantic_record_hash:
                    revision = latest['revision']
                    outcome = 'duplicate'
                else:
                    revision = latest['revision'] + 1 if latest else 1
                    outcome = 'revision' if latest else 'accepted'
                    con.execute('INSERT INTO revisions VALUES (?,?,?,?,?)',
                                (record.record_id, revision, record_hash, stable_json(raw), now()))
                    con.execute('INSERT INTO revision_semantics_v2 VALUES (?,?,?,?)',
                                (record.record_id, revision, semantic_record_hash, SEMANTIC_HASH_VERSION))
                    con.execute('INSERT INTO revision_semantics VALUES (?,?,?,?)',
                                (record.record_id, revision, semantic_hash(raw, LEGACY_HASH_VERSION), LEGACY_HASH_VERSION))
                projection = con.execute('SELECT 1 FROM projections WHERE record_id=? AND revision=? AND parser_version=?',
                                         (record.record_id, revision, VERSION)).fetchone()
                if not projection:
                    # Always project the revision's first immutable observation,
                    # including when a duplicate arrives after a parser upgrade.
                    if outcome == 'duplicate':
                        from quantgraph.models.ingestion import IngestRecord
                        saved = con.execute('SELECT * FROM revisions WHERE record_id=? AND revision=?', (record.record_id, revision)).fetchone()
                        value = json.loads(saved['raw_payload'])
                        value.pop('auditable_unknown_fields', None)
                        first = con.execute('''SELECT s.batch_id FROM observations o JOIN submissions s USING(job_id)
                            WHERE o.record_id=? AND o.revision=? ORDER BY s.created_at,s.job_id LIMIT 1''', (record.record_id, revision)).fetchone()
                        normalized = project_record(IngestRecord.model_validate(value), first['batch_id'], revision, saved['record_hash'])
                    else:
                        normalized = project_record(record, batch.batch_id, revision, record_hash)
                    con.execute('INSERT INTO projections VALUES (?,?,?,?,?)',
                                (record.record_id, revision, VERSION, normalized['variant']['strategy_variant_id'], stable_json(normalized)))
                    if outcome != 'duplicate':
                        result['curated'] += int(normalized['definition_admitted'])
                        # This counter includes rights review even for curated rule syntax.
                        result['review_required'] += int(bool(normalized['review_reasons']))
                result[outcome] += 1
                observations.append((job_id, record.record_id, revision, outcome))
                observation_payloads.append((job_id, record.record_id, record_hash, stable_json(raw), semantic_record_hash))
            con.execute('INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?)',
                        (job_id, batch.batch_id, digest, raw_bytes, stable_json(payload), key_id, now(), stable_json(result)))
            con.executemany('INSERT INTO observations VALUES (?,?,?,?)', observations)
            con.executemany('INSERT INTO observation_payloads VALUES (?,?,?,?,?)', observation_payloads)
            con.executemany('INSERT INTO observation_hash_versions VALUES (?,?,?)',
                            [(job_id, record.record_id, SEMANTIC_HASH_VERSION) for record in batch.records])
            con.execute('INSERT INTO submission_bytes VALUES (?,?)', (job_id, hashlib.sha256(raw_bytes).hexdigest()))
        return result

    def get_job(self, job_id):
        with self.connect() as con:
            row = con.execute('SELECT result FROM submissions WHERE job_id=?', (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            return json.loads(row['result'])

    def get_batch(self, batch_id):
        with self.connect() as con:
            rows = con.execute('SELECT job_id,created_at,payload_hash,result FROM submissions WHERE batch_id=? ORDER BY created_at,job_id', (batch_id,)).fetchall()
            if not rows:
                raise KeyError(batch_id)
            return {'batch_id': batch_id, 'submissions': [{**dict(r), 'result': json.loads(r['result'])} for r in rows]}

    def variants(self, limit=100, offset=0):
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError('Invalid pagination')
        with self.connect() as con:
            con.execute('BEGIN')
            status = self._projection_status(con)
            if status['projection_status'] != 'READY':
                raise ProjectionUnavailable(status)
            rows = con.execute('''SELECT p.payload FROM projections p
                WHERE p.parser_version=? AND p.revision=(SELECT MAX(r.revision) FROM revisions r WHERE r.record_id=p.record_id)
                ORDER BY p.record_id''', (VERSION,)).fetchall()
            from quantgraph.graph.variation import apply_observed_axes
            values = apply_observed_axes([json.loads(row['payload']) for row in rows])
            result = []
            from quantgraph.graph.research_gate import evaluate
            for value in values[offset:offset + limit]:
                rid = value['variant']['source_native_id']
                digest = con.execute('SELECT semantic_record_hash FROM revision_semantics_v2 WHERE record_id=? ORDER BY revision DESC LIMIT 1', (rid,)).fetchone()[0]
                review = con.execute('SELECT payload FROM review_decisions WHERE record_id=? AND semantic_record_hash=? ORDER BY rowid DESC LIMIT 1', (rid, digest)).fetchone()
                decision = json.loads(review[0]) if review else None
                from quantgraph.graph.research_gate import enrich_projection
                enrich_projection(value, decision)
                result.append(value)
        return result

    def review_record(self, payload):
        """Local administrative review only. Deliberately not an ingestion route."""
        from quantgraph.graph.research_gate import ReviewDecision
        from quantgraph.models.evidence import EvidenceEnrichment
        from quantgraph.models.evidence_v4 import EvidenceEnrichmentV4
        model = {'evidence-enrichment-v3': EvidenceEnrichment, 'evidence-enrichment-v4': EvidenceEnrichmentV4}.get(payload.get('schema_version'), ReviewDecision)
        value = model.model_validate(payload).model_dump(mode='json')
        decision_id = 'review-' + content_hash(value)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            latest = con.execute('SELECT semantic_record_hash FROM revision_semantics_v2 WHERE record_id=? ORDER BY revision DESC LIMIT 1', (value['record_id'],)).fetchone()
            if not latest or latest[0] != value['semantic_record_hash']:
                raise ValueError('Review must reference the current semantic record hash')
            con.execute('INSERT OR IGNORE INTO review_decisions VALUES (?,?,?,?,?)',
                        (decision_id, value['record_id'], value['semantic_record_hash'], stable_json(value), now()))
        return {'decision_id': decision_id, 'promotion_allowed': False}

    def evidence_for(self, variant_id):
        with self.connect() as con:
            return [value for row in con.execute('SELECT payload FROM evidence ORDER BY created_at,research_run_id')
                    if variant_id in (value := json.loads(row[0]))['source_strategy_ids']]

    def lineage(self, variant_id):
        with self.connect() as con:
            return [dict(r) for r in con.execute('''SELECT DISTINCT s.batch_id,s.job_id,o.record_id,o.revision,
                    r.record_hash,s.payload_hash,s.created_at,p.parser_version,
                    op.raw_payload_hash,op.semantic_record_hash,ohv.hash_version,rs2.semantic_record_hash AS current_semantic_record_hash,sb.raw_payload_hash AS wire_payload_hash
                FROM projections p JOIN revisions r USING(record_id,revision)
                JOIN observations o USING(record_id,revision) JOIN submissions s USING(job_id)
                JOIN observation_payloads op ON op.job_id=o.job_id AND op.record_id=o.record_id
                JOIN observation_hash_versions ohv ON ohv.job_id=o.job_id AND ohv.record_id=o.record_id
                JOIN revision_semantics_v2 rs2 ON rs2.record_id=o.record_id AND rs2.revision=o.revision
                JOIN submission_bytes sb ON sb.job_id=s.job_id
                WHERE p.variant_id=? ORDER BY o.revision,s.created_at''', (variant_id,))]

    def _projection_status(self, con):
        latest = con.execute('SELECT COUNT(DISTINCT record_id) FROM revisions').fetchone()[0]
        current = con.execute('''SELECT COUNT(*) FROM projections p WHERE parser_version=?
            AND revision=(SELECT MAX(revision) FROM revisions r WHERE r.record_id=p.record_id)''', (VERSION,)).fetchone()[0]
        run = con.execute('SELECT status FROM projection_runs WHERE parser_version=? ORDER BY rowid DESC LIMIT 1', (VERSION,)).fetchone()
        status = 'READY' if latest == current else 'STALE'
        if run and run['status'] in {'REPROJECTING', 'FAILED'}:
            status = run['status']
        return {'latest_revision_count': latest, 'current_projection_count': current,
                'stale_projection_count': latest - current, 'parser_version': VERSION,
                'projection_status': status}

    def projection_status(self):
        with self.connect() as con:
            con.execute('BEGIN')
            return self._projection_status(con)

    def reproject(self):
        """Atomic, retryable rebuild; a killed worker stays blocked until retry.

        SQLite serializes the rebuild writers. A run marker is committed first so
        readers can see REPROJECTING without waiting for the rebuild transaction.
        """
        run_id = uuid4().hex
        with self.connect() as con:
            con.execute('INSERT INTO projection_runs VALUES (?,?,?,?,?,?)', (run_id, VERSION, 'REPROJECTING', now(), None, None))
        try:
            result = self._reproject()
        except Exception as exc:
            with self.connect() as con:
                con.execute('UPDATE projection_runs SET status=?,finished_at=?,error_code=? WHERE run_id=?',
                            ('FAILED', now(), type(exc).__name__, run_id))
            raise
        with self.connect() as con:
            con.execute('UPDATE projection_runs SET status=?,finished_at=? WHERE run_id=?', ('READY', now(), run_id))
        return {**result, **self.projection_status(), 'run_id': run_id}

    def _reproject(self):
        """Append missing projections after an explicit parser version upgrade.

        Existing identities/raw history remain intact. Never change behavior
        without bumping the parser version: a same-version mismatch fails closed.
        """
        from quantgraph.models.ingestion import IngestRecord
        from quantgraph.graph.ingestion import project_record
        added = 0
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            for raw in con.execute('SELECT * FROM revisions ORDER BY record_id,revision').fetchall():
                batch = con.execute('''SELECT s.batch_id FROM observations o JOIN submissions s USING(job_id)
                    WHERE o.record_id=? AND o.revision=? ORDER BY s.created_at,s.job_id LIMIT 1''',
                    (raw['record_id'], raw['revision'])).fetchone()
                value = json.loads(raw['raw_payload'])
                value.pop('auditable_unknown_fields', None)
                projection = project_record(IngestRecord.model_validate(value), batch['batch_id'], raw['revision'], raw['record_hash'])
                old = con.execute('SELECT payload FROM projections WHERE record_id=? AND revision=? AND parser_version=?',
                                  (raw['record_id'], raw['revision'], VERSION)).fetchone()
                encoded = stable_json(projection)
                if old:
                    if old['payload'] != encoded:
                        raise ValueError('Projection changed without a parser version bump')
                else:
                    con.execute('INSERT INTO projections VALUES (?,?,?,?,?)', (raw['record_id'], raw['revision'], VERSION,
                                projection['variant']['strategy_variant_id'], encoded))
                    added += 1
        return {'parser_version': VERSION, 'projections_added': added, 'raw_mutated': False}

    def ingest_stats(self):
        with self.connect() as con:
            con.execute('BEGIN')
            status = self._projection_status(con)
            counts = {name: con.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
                      for name in ('observations', 'revisions', 'submissions')}
            duplicates = con.execute("SELECT COUNT(*) FROM observations WHERE outcome='duplicate'").fetchone()[0]
            rows = [json.loads(r[0]) for r in con.execute('''SELECT payload FROM projections p
                WHERE parser_version=? AND revision=(SELECT MAX(revision) FROM revisions r WHERE r.record_id=p.record_id)''', (VERSION,))]
            from quantgraph.graph.research_gate import evaluate
            for value in rows:
                rid = value['variant']['source_native_id']
                digest = con.execute('SELECT semantic_record_hash FROM revision_semantics_v2 WHERE record_id=? ORDER BY revision DESC LIMIT 1', (rid,)).fetchone()[0]
                review = con.execute('SELECT payload FROM review_decisions WHERE record_id=? AND semantic_record_hash=? ORDER BY rowid DESC LIMIT 1', (rid, digest)).fetchone()
                decision = json.loads(review[0]) if review else None
                value['candidate_gate'] = evaluate(value, decision)
                if decision:
                    value['research_rights_status'] = value['candidate_gate']['rights_status']
            evidence = [json.loads(r[0]) for r in con.execute('SELECT payload FROM evidence')]
        parsed = sum(r['variant']['parse_status'] == 'PARSED' for r in rows)
        return {**status, 'total_observations': counts['observations'],
                'semantic_records': status['latest_revision_count'],
                'revision_rows': counts['revisions'], 'revisions': counts['revisions'] - status['latest_revision_count'],
                'duplicates': duplicates, 'submissions': counts['submissions'],
                'curated': sum(r['definition_admitted'] for r in rows),
                'review_queue': sum(not r['candidate_gate']['eligible'] for r in rows),
                'eligible_research_variants': sum(r['candidate_gate']['eligible'] for r in rows),
                'rule_review_queue': len(rows) - parsed, 'parsed': parsed,
                'parser_coverage': parsed / len(rows) if rows else 0,
                'factor_linked': sum(bool(r['factor_links']) for r in rows),
                'rights_status': dict(Counter(r['research_rights_status'] for r in rows)),
                'research_evidence_count': len(evidence),
                'real_market_backtest_count': sum(e.get('schema_version') == '3.0' and e.get('evidence_kind') == 'REAL_MARKET_BACKTEST'
                    and e.get('real_market_data') is True for e in evidence),
                'counts_scope': 'CURRENT_PROJECTIONS_ONLY',
                'complete': status['projection_status'] == 'READY'}

    def consume_quota(self, key_id, limit):
        window = int(time.time() // 60)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('DELETE FROM quotas WHERE window<?', (window - 2,))
            row = con.execute('SELECT count FROM quotas WHERE key_id=? AND window=?', (key_id, window)).fetchone()
            if row and row['count'] >= limit:
                return False
            con.execute('INSERT INTO quotas VALUES (?,?,1) ON CONFLICT(key_id,window) DO UPDATE SET count=count+1', (key_id, window))
            return True

    def log_request(self, request_id, key_id, route, status):
        with self.connect() as con:
            con.execute('INSERT INTO request_logs VALUES (?,?,?,?,?)', (request_id, key_id, route, status, now()))

    def usage(self, key_id):
        with self.connect() as con:
            return [dict(r) for r in con.execute('SELECT route,status,count(*) AS requests FROM request_logs WHERE key_id=? GROUP BY route,status ORDER BY route,status', (key_id,))]

    def put_evidence(self, payload, key_id):
        if payload.get('schema_version') == '3.0':
            from quantgraph.models.evidence_v4 import MarketResearchEvidenceV4
            payload = MarketResearchEvidenceV4.model_validate(payload).model_dump(mode='json')
        if payload.get('schema_version') == '2.0':
            from quantgraph.models.evidence import MarketResearchEvidence
            payload = MarketResearchEvidence.model_validate(payload).model_dump(mode='json')
        digest = content_hash(payload)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT payload_hash FROM evidence WHERE research_run_id=?', (payload['research_run_id'],)).fetchone()
            if old and old['payload_hash'] != digest:
                raise ValueError('Immutable research_run_id; use a new run for changed evidence')
            if not old:
                if payload.get('schema_version') == '2.0':
                    raise ValueError('Formal writeback requires V4 schema 3.0 dataset/rights bindings')
                if payload.get('schema_version') == '3.0':
                    # Check admission in the same write transaction: review or
                    # revision updates cannot race with evidence insertion.
                    status = self._projection_status(con)
                    if status['projection_status'] != 'READY':
                        raise ProjectionUnavailable(status)
                    from quantgraph.graph.research_gate import enrich_projection
                    for vid in payload['source_strategy_ids']:
                        current = con.execute('''SELECT p.payload, r.semantic_record_hash, p.record_id FROM projections p
                            JOIN revision_semantics_v2 r USING(record_id, revision)
                            WHERE variant_id=? AND parser_version=? AND p.revision=(
                            SELECT MAX(revision) FROM revisions rr WHERE rr.record_id=p.record_id)''', (vid, VERSION)).fetchone()
                        review = con.execute('SELECT payload FROM review_decisions WHERE record_id=? AND semantic_record_hash=? ORDER BY rowid DESC LIMIT 1',
                            (current['record_id'], current['semantic_record_hash'])).fetchone() if current else None
                        row = enrich_projection(json.loads(current['payload']), json.loads(review[0]) if review else None) if current else None
                        if not row or row['candidate_gate']['status'] != 'ELIGIBLE':
                            raise ValueError('Real research requires an ELIGIBLE source variant')
                        if any(row['variant'][k] != payload[k] for k in ('strategy_concept_id', 'strategy_template_id')):
                            raise ValueError('Research concept/template lineage mismatch')
                        if row['reviewed_evidence']['data_requirement'] != payload['data_provenance']:
                            raise ValueError('Research data differs from the admitted dataset')
                        binding = row['reviewed_evidence']['dataset_binding']
                        if any(binding[k] != payload[k] for k in ('contract_sha256', 'dataset_manifest_sha256', 'rights_id', 'rights_sha256')):
                            raise ValueError('Contract/dataset/rights binding mismatch')
                        contract = json.loads(binding['contract_json'])
                        if any(contract[k] != payload[k] for k in ('experiment_family_id', 'strategy_variant_id', 'parameter_grid', 'trial_count')):
                            raise ValueError('Frozen experiment/grid lineage mismatch')
                        if content_hash(contract['engine_config']) != payload['config_sha256']:
                            raise ValueError('Frozen engine config hash mismatch')
                # Check the full table, not a pagination-dependent universe.
                known = {r[0] for r in con.execute('SELECT DISTINCT variant_id FROM projections')}
                if not set(payload['source_strategy_ids']) <= known:
                    raise ValueError('Evidence references unknown strategy variants')
                con.execute('INSERT INTO evidence VALUES (?,?,?,?,?)', (payload['research_run_id'], digest, stable_json(payload), key_id, now()))
        return {'research_run_id': payload['research_run_id'], 'sha256': digest,
                'duplicate': bool(old), 'validation_status': 'SUBMITTED_NOT_INDEPENDENTLY_VERIFIED', 'promotion_triggered': False}

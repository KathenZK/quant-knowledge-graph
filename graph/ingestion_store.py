"""Transactional private journal. SQLite is an adapter, not the wire contract.

Every submission, revision, projection and evidence is append-only. BEGIN
IMMEDIATE serializes writers; a failed projection rolls back the entire batch.
No raw payload or source text is written into request logs.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from typing import Protocol

from quantgraph.graph.grokbot import content_hash, stable_json
from quantgraph.models.ingestion import IngestBatch
from quantgraph.normalize.strategy.parser import VERSION


def now():
    return datetime.now(timezone.utc).isoformat()


class IngestionRepository(Protocol):
    def ingest(self, batch: IngestBatch, raw_bytes: bytes, key_id: str) -> dict: ...
    def get_job(self, job_id: str) -> dict: ...
    def get_batch(self, batch_id: str) -> dict: ...
    def variants(self, limit: int = 100, offset: int = 0) -> list[dict]: ...
    def lineage(self, variant_id: str) -> list[dict]: ...
    def consume_quota(self, key_id: str, limit: int) -> bool: ...
    def log_request(self, request_id: str, key_id: str, route: str, status: int) -> None: ...
    def usage(self, key_id: str) -> list[dict]: ...
    def put_evidence(self, payload: dict, key_id: str) -> dict: ...


class SQLiteIngestionRepository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
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
                PRAGMA user_version=1;
            ''')
            for table in ('submissions', 'revisions', 'observations', 'projections', 'evidence', 'request_logs'):
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
            for record in batch.records:
                raw = record.audit_payload()
                record_hash = content_hash(raw)
                latest = con.execute('SELECT revision,record_hash FROM revisions WHERE record_id=? ORDER BY revision DESC LIMIT 1', (record.record_id,)).fetchone()
                if latest and latest['record_hash'] == record_hash:
                    revision = latest['revision']
                    outcome = 'duplicate'
                else:
                    revision = latest['revision'] + 1 if latest else 1
                    outcome = 'revision' if latest else 'accepted'
                    con.execute('INSERT INTO revisions VALUES (?,?,?,?,?)',
                                (record.record_id, revision, record_hash, stable_json(raw), now()))
                projection = con.execute('SELECT 1 FROM projections WHERE record_id=? AND revision=? AND parser_version=?',
                                         (record.record_id, revision, VERSION)).fetchone()
                if not projection:
                    normalized = project_record(record, batch.batch_id, revision, record_hash)
                    con.execute('INSERT INTO projections VALUES (?,?,?,?,?)',
                                (record.record_id, revision, VERSION, normalized['variant']['strategy_variant_id'], stable_json(normalized)))
                    if outcome != 'duplicate':
                        result['curated'] += int(normalized['definition_admitted'])
                        # This counter includes rights review even for curated rule syntax.
                        result['review_required'] += int(bool(normalized['review_reasons']))
                result[outcome] += 1
                observations.append((job_id, record.record_id, revision, outcome))
            con.execute('INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?)',
                        (job_id, batch.batch_id, digest, raw_bytes, stable_json(payload), key_id, now(), stable_json(result)))
            con.executemany('INSERT INTO observations VALUES (?,?,?,?)', observations)
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
            rows = con.execute('''SELECT p.payload FROM projections p
                WHERE p.parser_version=? AND p.revision=(SELECT MAX(r.revision) FROM revisions r WHERE r.record_id=p.record_id)
                ORDER BY p.record_id LIMIT ? OFFSET ?''', (VERSION, limit, offset)).fetchall()
        return [json.loads(r['payload']) for r in rows]

    def lineage(self, variant_id):
        with self.connect() as con:
            return [dict(r) for r in con.execute('''SELECT DISTINCT s.batch_id,s.job_id,o.record_id,o.revision,
                    r.record_hash,s.payload_hash,s.created_at,p.parser_version
                FROM projections p JOIN revisions r USING(record_id,revision)
                JOIN observations o USING(record_id,revision) JOIN submissions s USING(job_id)
                WHERE p.variant_id=? ORDER BY o.revision,s.created_at''', (variant_id,))]

    def reproject(self):
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
        digest = content_hash(payload)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT payload_hash FROM evidence WHERE research_run_id=?', (payload['research_run_id'],)).fetchone()
            if old and old['payload_hash'] != digest:
                raise ValueError('Immutable research_run_id; use a new run for changed evidence')
            if not old:
                # Check the full table, not a pagination-dependent universe.
                known = {r[0] for r in con.execute('SELECT DISTINCT variant_id FROM projections')}
                if not set(payload['source_strategy_ids']) <= known:
                    raise ValueError('Evidence references unknown strategy variants')
                con.execute('INSERT INTO evidence VALUES (?,?,?,?,?)', (payload['research_run_id'], digest, stable_json(payload), key_id, now()))
        return {'research_run_id': payload['research_run_id'], 'sha256': digest,
                'duplicate': bool(old), 'validation_status': 'SUBMITTED_NOT_INDEPENDENTLY_VERIFIED', 'promotion_triggered': False}

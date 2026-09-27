"""Additive v1 -> v2 migration. Historical revisions and wire bytes never change."""
import hashlib
import json

from quantgraph.graph.grokbot import content_hash, stable_json
from quantgraph.models.ingestion import IngestRecord

SCHEMA_VERSION = 4
LEGACY_HASH_VERSION = 'strategy-record-semantics-v1'
SEMANTIC_HASH_VERSION = 'strategy-record-semantics-v2'
IMMUTABLE_TABLES = ('revision_semantics', 'revision_semantics_v2', 'observation_hash_versions',
                    'observation_payloads', 'submission_bytes', 'review_decisions')


def semantic_hash(raw, version=SEMANTIC_HASH_VERSION):
    return content_hash(IngestRecord.model_validate(raw).semantic_payload(version))


def migrate(con):
    con.execute('BEGIN IMMEDIATE')
    version = con.execute('PRAGMA user_version').fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError('Ingestion database is newer than this application')
    con.execute('''CREATE TABLE IF NOT EXISTS revision_semantics (
        record_id TEXT NOT NULL, revision INTEGER NOT NULL,
        semantic_record_hash TEXT NOT NULL, hash_version TEXT NOT NULL,
        PRIMARY KEY(record_id, revision),
        FOREIGN KEY(record_id, revision) REFERENCES revisions(record_id, revision))''')
    con.execute('''CREATE TABLE IF NOT EXISTS observation_payloads (
        job_id TEXT NOT NULL, record_id TEXT NOT NULL, raw_payload_hash TEXT NOT NULL,
        raw_payload TEXT NOT NULL, semantic_record_hash TEXT NOT NULL,
        PRIMARY KEY(job_id, record_id),
        FOREIGN KEY(job_id, record_id) REFERENCES observations(job_id, record_id))''')
    con.execute('''CREATE TABLE IF NOT EXISTS submission_bytes (
        job_id TEXT PRIMARY KEY REFERENCES submissions(job_id), raw_payload_hash TEXT NOT NULL)''')
    con.execute('''CREATE TABLE IF NOT EXISTS projection_runs (
        run_id TEXT PRIMARY KEY, parser_version TEXT NOT NULL, status TEXT NOT NULL,
        started_at TEXT NOT NULL, finished_at TEXT, error_code TEXT)''')
    con.execute('''CREATE TABLE IF NOT EXISTS review_decisions (
        decision_id TEXT PRIMARY KEY, record_id TEXT NOT NULL, semantic_record_hash TEXT NOT NULL,
        payload TEXT NOT NULL, created_at TEXT NOT NULL)''')
    con.execute('''CREATE TABLE IF NOT EXISTS revision_semantics_v2 (
        record_id TEXT NOT NULL, revision INTEGER NOT NULL,
        semantic_record_hash TEXT NOT NULL, hash_version TEXT NOT NULL,
        PRIMARY KEY(record_id, revision),
        FOREIGN KEY(record_id, revision) REFERENCES revisions(record_id, revision))''')
    con.execute('''CREATE TABLE IF NOT EXISTS observation_hash_versions (
        job_id TEXT NOT NULL, record_id TEXT NOT NULL, hash_version TEXT NOT NULL,
        PRIMARY KEY(job_id,record_id),
        FOREIGN KEY(job_id,record_id) REFERENCES observation_payloads(job_id,record_id))''')
    if version < SCHEMA_VERSION:
        for row in con.execute('SELECT record_id,revision,raw_payload FROM revisions').fetchall():
            con.execute('INSERT OR IGNORE INTO revision_semantics VALUES (?,?,?,?)',
                        (row['record_id'], row['revision'], semantic_hash(json.loads(row['raw_payload']), LEGACY_HASH_VERSION), LEGACY_HASH_VERSION))
            con.execute('INSERT OR IGNORE INTO revision_semantics_v2 VALUES (?,?,?,?)',
                        (row['record_id'], row['revision'], semantic_hash(json.loads(row['raw_payload'])), SEMANTIC_HASH_VERSION))
        for row in con.execute('SELECT job_id,payload,raw_bytes FROM submissions').fetchall():
            con.execute('INSERT OR IGNORE INTO submission_bytes VALUES (?,?)',
                        (row['job_id'], hashlib.sha256(row['raw_bytes']).hexdigest()))
            for raw in json.loads(row['payload'])['records']:
                # A batch audit stores model_dump records, not record.audit_payload.
                value = dict(raw)
                value.pop('auditable_unknown_fields', None)
                record = IngestRecord.model_validate(value)
                payload = record.audit_payload()
                con.execute('INSERT OR IGNORE INTO observation_payloads VALUES (?,?,?,?,?)',
                            (row['job_id'], record.record_id, content_hash(payload),
                             stable_json(payload), content_hash(record.semantic_payload(LEGACY_HASH_VERSION))))
                con.execute('INSERT OR IGNORE INTO observation_hash_versions VALUES (?,?,?)',
                            (row['job_id'], record.record_id, LEGACY_HASH_VERSION))
    con.execute(f'PRAGMA user_version={SCHEMA_VERSION}')

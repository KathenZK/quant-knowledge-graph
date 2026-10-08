"""Append-only reception of authenticated QuantGraph Site feedback.

This module never interprets note text as instructions or changes source data.
Network authentication belongs to the caller; an accepted receipt is emitted
only after the SQLite transaction has durably committed.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

SCHEMA = 'quantgraph-feedback/v1'
FIELDS = {'starred', 'status', 'tags', 'group', 'note', 'summary', 'questions', 'reason', 'aliases', 'problem'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def read_envelope(path):
    path = Path(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('Feedback envelope exceeds 8 MiB')
    return json.loads(path.read_text(), object_pairs_hook=_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def _text(value, limit=500, required=True):
    if not isinstance(value, str) or len(value) > limit or (required and not value):
        raise ValueError('Invalid bounded text')
    return value


def _integer(value):
    if type(value) is not int or not 0 <= value <= 9007199254740991:
        raise ValueError('Invalid cursor or revision')
    return value


def validate_event(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid event')
    required = {'seq', 'event_id', 'owner_id', 'target_key', 'record_revision', 'target', 'payload', 'payload_sha256', 'mutation_id', 'created_at'}
    if set(value) != required:
        raise ValueError('Unexpected or missing event fields')
    _integer(value['seq']); _integer(value['record_revision'])
    if value['seq'] < 1 or value['record_revision'] < 1:
        raise ValueError('Event sequence and revision must be positive')
    for name in required - {'seq', 'record_revision', 'target', 'payload'}:
        _text(value[name])
    target = value['target']
    base = {'kind', 'entity_id', 'entity_type', 'definition_revision'}
    optional = {'origin_run_id', 'variant_id', 'manifest_sha256', 'definition_revision_bound'}
    if not isinstance(target, dict) or not base <= set(target) or set(target) - base - optional:
        raise ValueError('Invalid pinned target')
    for key in base:
        _text(target[key])
    result_keys = {'origin_run_id', 'variant_id', 'manifest_sha256'}
    if result_keys.intersection(target) and not result_keys <= set(target):
        raise ValueError('Incomplete result binding')
    for key in result_keys.intersection(target):
        _text(target[key])
    if 'definition_revision_bound' in target and type(target['definition_revision_bound']) is not bool:
        raise ValueError('Invalid definition binding flag')
    payload = value['payload']
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ValueError('Invalid personal fields')
    if type(payload['starred']) is not bool:
        raise ValueError('Invalid starred state')
    for key in FIELDS - {'starred', 'tags', 'aliases'}:
        _text(payload[key], 20000, required=False)
    for key in ('tags', 'aliases'):
        if not isinstance(payload[key], list) or len(payload[key]) > 100:
            raise ValueError('Invalid tags or aliases')
        for item in payload[key]:
            _text(item, 200)
    if value['target_key'] != digest(target) or value['payload_sha256'] != digest({'target': target, 'payload': payload}):
        raise ValueError('Feedback content digest mismatch')
    return value


class FeedbackLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS site_feedback_sources(source_url TEXT PRIMARY KEY, cursor INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS site_feedback_events(source_url TEXT NOT NULL, seq INTEGER NOT NULL,
                    event_id TEXT NOT NULL, target_key TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                    envelope TEXT NOT NULL, PRIMARY KEY(source_url,seq), UNIQUE(source_url,event_id));
                CREATE TRIGGER IF NOT EXISTS site_feedback_immutable_update BEFORE UPDATE ON site_feedback_events
                    BEGIN SELECT RAISE(ABORT,'Feedback events are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS site_feedback_immutable_delete BEFORE DELETE ON site_feedback_events
                    BEGIN SELECT RAISE(ABORT,'Feedback events are immutable'); END;
            ''')

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    @staticmethod
    def source(value):
        parsed = urlsplit(_text(value, 2000))
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}:
            raise ValueError('Source must be the verified HTTPS Site origin')
        return value.rstrip('/')

    def cursor(self, source):
        source = self.source(source)
        with self.connect() as con:
            row = con.execute('SELECT cursor FROM site_feedback_sources WHERE source_url=?', (source,)).fetchone()
            return row[0] if row else 0

    def ingest(self, source, envelope):
        source = self.source(source)
        if not isinstance(envelope, dict) or set(envelope) != {'schema_version', 'after_cursor', 'next_cursor', 'has_more', 'events'} or envelope['schema_version'] != SCHEMA:
            raise ValueError('Unsupported feedback envelope')
        before = _integer(envelope['after_cursor']); end = _integer(envelope['next_cursor'])
        if type(envelope['has_more']) is not bool or not isinstance(envelope['events'], list) or len(envelope['events']) > 1000:
            raise ValueError('Invalid bounded event batch')
        events = [validate_event(event) for event in envelope['events']]
        if end - before != len(events) or [e['seq'] for e in events] != list(range(before + 1, end + 1)):
            raise ValueError('Feedback cursor range has a gap or duplicate')
        if end < before:
            raise ValueError('Cursor cannot move backwards')
        inserted = 0
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT cursor FROM site_feedback_sources WHERE source_url=?', (source,)).fetchone()
            current = row[0] if row else 0
            if before > current:
                raise ValueError('Missing earlier feedback batch')
            for event in events:
                stored = con.execute('SELECT envelope FROM site_feedback_events WHERE source_url=? AND seq=?', (source, event['seq'])).fetchone()
                exact = canonical(event)
                if stored:
                    if stored[0] != exact:
                        raise ValueError('Existing immutable event changed')
                elif event['seq'] <= current:
                    raise ValueError('Stored cursor has missing evidence')
                else:
                    con.execute('INSERT INTO site_feedback_events VALUES(?,?,?,?,?,?)', (source, event['seq'], event['event_id'], event['target_key'], event['payload_sha256'], exact))
                    inserted += 1
            cursor = max(current, end)
            con.execute('INSERT INTO site_feedback_sources VALUES(?,?) ON CONFLICT(source_url) DO UPDATE SET cursor=excluded.cursor', (source, cursor))
        return {'source': source, 'durable_cursor': cursor, 'inserted': inserted, 'replayed': len(events) - inserted, 'ready_to_ack': True}

    def events(self, source, after=0, limit=100):
        source = self.source(source); _integer(after)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('Invalid limit')
        with self.connect() as con:
            return [json.loads(row[0]) for row in con.execute('SELECT envelope FROM site_feedback_events WHERE source_url=? AND seq>? ORDER BY seq LIMIT ?', (source, after, limit))]

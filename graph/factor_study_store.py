"""Private append-only FactorStudy evidence, separate from immutable releases."""
import json
from pathlib import Path
import sqlite3
from quantgraph.factor_study import canonical, digest, definition_identity
from quantgraph.models.factor_study import FactorStudyResult


class FactorStudyRepository:
    def __init__(self, path, db):
        self.path, self.db = Path(path).resolve(), db
        if self.path == db.path or db.release_path in self.path.parents:
            raise ValueError('Study journal must be outside graph releases')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS definitions (
                    revision TEXT PRIMARY KEY, variant_id TEXT NOT NULL, concept_id TEXT NOT NULL,
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS mappings (
                    mapping_hash TEXT PRIMARY KEY, revision TEXT NOT NULL REFERENCES definitions(revision),
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS studies (
                    run_id TEXT PRIMARY KEY, mapping_hash TEXT NOT NULL REFERENCES mappings(mapping_hash),
                    payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
                    inserted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            ''')

    def connect(self):
        con = sqlite3.connect(self.path)
        con.execute('PRAGMA foreign_keys=ON')
        return con

    def put(self, value):
        value = FactorStudyResult.model_validate(value).model_dump(mode='json')
        mapping = value['mapping']
        identity = mapping['identity']
        current = definition_identity(self.db.get_variant(identity['factor_variant_id']))
        if identity != current:
            raise ValueError('Definition/source/formula revision mismatch')
        # V1 ingests private evidence only. A producer cannot grant itself display rights.
        permissions = value['permissions']
        if any(permissions[k]['public_display'] == 'ALLOWED' for k in ('market_data', 'derived_result')):
            raise ValueError('Public market/derived evidence needs a separate rights review; unsupported in v1')
        if any(a['permissions']['public_display'] == 'ALLOWED' for a in value['artifacts']):
            raise ValueError('Public artifact review is not supported in v1')
        if value['status'] == 'SUCCESS' and any(p['internal_use'] != 'ALLOWED' for p in permissions.values()):
            raise ValueError('Successful internal research requires separate internal-use permissions')
        payload_hash, mapping_hash = digest(value), digest(mapping)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT payload_hash FROM studies WHERE run_id=?', (value['run_id'],)).fetchone()
            if old and old[0] != payload_hash:
                raise ValueError('Immutable run_id; changed evidence requires a new run')
            if not old:
                con.execute('INSERT OR IGNORE INTO definitions VALUES (?,?,?,?)',
                    (identity['definition_revision'], identity['factor_variant_id'], identity['factor_concept_id'], canonical(identity)))
                con.execute('INSERT OR IGNORE INTO mappings VALUES (?,?,?)',
                    (mapping_hash, identity['definition_revision'], canonical(mapping)))
                con.execute('INSERT INTO studies (run_id,mapping_hash,payload_hash,payload) VALUES (?,?,?,?)',
                    (value['run_id'], mapping_hash, payload_hash, canonical(value)))
        return {'run_id': value['run_id'], 'sha256': payload_hash, 'duplicate': bool(old),
                'validation_status': 'SUBMITTED_NOT_INDEPENDENTLY_VERIFIED', 'promotion_allowed': False}

    def query(self, entity_id, *, profile='commercial', limit=100, offset=0):
        if profile not in {'commercial', 'research'} or not 1 <= limit <= 1000 or offset < 0:
            raise ValueError('Invalid profile or pagination')
        if profile == 'commercial':
            return []  # No public research rights authority exists in v1.
        with self.connect() as con:
            rows = con.execute('''SELECT s.payload FROM studies s JOIN mappings m USING(mapping_hash)
                JOIN definitions d USING(revision) WHERE d.variant_id=? OR d.concept_id=?
                ORDER BY s.run_id LIMIT ? OFFSET ?''', (entity_id, entity_id, limit, offset)).fetchall()
        return [json.loads(r[0]) for r in rows]

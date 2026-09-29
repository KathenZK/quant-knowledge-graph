"""Durable, fenced job transport. Research semantics remain in Lab's registered code.

Each process uses short SQLite transactions. A reclaimed lease changes the fencing
token; an old worker cannot publish. A retry retains the job/run and experiment IDs.
"""
import json
from contextlib import contextmanager
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from quantgraph.factor_study import canonical, digest
from quantgraph.models.factor_study import ResearchRequest, FactorStudyResult, StudyMetadata

TERMINAL = {'SUCCEEDED', 'PARTIAL', 'BLOCKED', 'FAILED', 'CANCELLED'}


class LeaseLost(RuntimeError):
    pass


class CapacityExceeded(ValueError):
    pass


class ResearchJobRepository:
    def __init__(self, path, profiles, *, max_concurrency=1, max_pending=20,
                 daily_trial_budget=200, max_attempts=3, clock=time.time):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.profiles = profiles
        self.max_concurrency = max_concurrency
        self.max_pending = max_pending
        self.daily_trial_budget = daily_trial_budget
        self.max_attempts = max_attempts
        self.clock = clock
        if min(max_concurrency, max_pending, daily_trial_budget, max_attempts) < 1:
            raise ValueError('Resource limits must be positive')
        with self.connect() as con:
            con.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS research_jobs (
                    job_id TEXT PRIMARY KEY, owner TEXT NOT NULL, idem TEXT NOT NULL,
                    request_hash TEXT NOT NULL, request TEXT NOT NULL, profile TEXT NOT NULL,
                    profile_hash TEXT NOT NULL, snapshots TEXT NOT NULL, status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0, stage TEXT NOT NULL, error TEXT,
                    results TEXT, created REAL NOT NULL, updated REAL NOT NULL,
                    started REAL, completed REAL, lease_until REAL, lease_token TEXT,
                    worker TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0, trial_budget INTEGER NOT NULL,
                    seconds_budget INTEGER NOT NULL, UNIQUE(owner, idem));
                CREATE TABLE IF NOT EXISTS research_workers (
                    worker TEXT PRIMARY KEY, updated REAL NOT NULL, profiles TEXT NOT NULL);
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

    def announce(self, worker, profiles):
        with self.connect() as con:
            con.execute('INSERT OR REPLACE INTO research_workers VALUES (?,?,?)',
                        (worker, self.clock(), canonical(sorted(profiles))))

    def worker_available(self, profile):
        with self.connect() as con:
            return any(profile in json.loads(row['profiles']) for row in con.execute(
                'SELECT profiles FROM research_workers WHERE updated > ?', (self.clock() - 30,)))

    def submit(self, request, *, owner, resolve_ref):
        request = ResearchRequest.model_validate(request).model_dump(mode='json')
        idem = request.get('idempotency_key') or request['request_id']
        fingerprint = digest(request)
        with self.connect() as con:
            old = con.execute('SELECT * FROM research_jobs WHERE owner=? AND idem=?',(owner,idem)).fetchone()
            if old:
                if old['request_hash'] != fingerprint:
                    raise ValueError('Idempotency key already used for another request')
                return self._decode(old),True
        settings = request['requested_settings']
        if set(settings) != {'profile_id'}:
            raise ValueError('Choose a registered profile_id; execution settings are server controlled')
        profile_id = settings['profile_id']
        profile = self.profiles.get(profile_id)
        if profile is None or profile['study_type'] != request['study_type']:
            raise ValueError('Registered capability unavailable for this study type')
        refs = request['entity_refs']
        if len(refs) > profile.get('max_entities', 1) or len({canonical(r) for r in refs}) != len(refs):
            raise ValueError('Unsupported or duplicate entity selection')
        if any(r['entity_type'] not in profile['entity_types'] for r in refs):
            raise ValueError('Entity type is not supported by this capability')
        budget = request.get('budget') or {}
        if set(budget) - {'max_trials', 'max_seconds'}:
            raise ValueError('Unknown budget field')
        trials = budget.get('max_trials', profile['max_trials'])
        seconds = budget.get('max_seconds', profile['max_seconds'])
        if not 1 <= trials <= profile['max_trials'] or not 1 <= seconds <= profile['max_seconds']:
            raise ValueError('Budget exceeds registered resource limits')
        if trials < profile.get('trials_per_entity', 1) * len(refs):
            raise ValueError('Budget cannot cover the registered experiment count')
        snapshots = [resolve_ref(**r) for r in refs]
        now = self.clock()
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT * FROM research_jobs WHERE owner=? AND idem=?', (owner, idem)).fetchone()
            if old:
                if old['request_hash'] != fingerprint:
                    raise ValueError('Idempotency key already used for another request')
                return self._decode(old), True
            pending = con.execute("SELECT count(*) FROM research_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]
            consumed = con.execute('SELECT coalesce(sum(trial_budget),0) FROM research_jobs WHERE created>=?', (now-86400,)).fetchone()[0]
            if pending >= self.max_pending or consumed + trials > self.daily_trial_budget:
                raise CapacityExceeded('Queue or rolling 24-hour trial budget exhausted')
            job_id = 'job-' + uuid4().hex
            con.execute('''INSERT INTO research_jobs
                (job_id,owner,idem,request_hash,request,profile,profile_hash,snapshots,status,stage,
                 created,updated,trial_budget,seconds_budget) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (job_id, owner, idem, fingerprint, canonical(request), profile_id, digest(profile),
                 canonical(snapshots), 'QUEUED', 'WAITING_FOR_WORKER', now, now, trials, seconds))
            row = con.execute('SELECT * FROM research_jobs WHERE job_id=?', (job_id,)).fetchone()
        return self._decode(row), False

    def _decode(self, row):
        value = dict(row)
        for key in ('request', 'snapshots', 'results', 'error'):
            value[key] = json.loads(value[key]) if value[key] else None
        value['run_id'] = value['job_id']
        return value

    def get(self, job_id):
        with self.connect() as con:
            row = con.execute('SELECT * FROM research_jobs WHERE job_id=?', (job_id,)).fetchone()
        if row is None:
            raise KeyError('Unknown research job')
        return self._decode(row)

    def _recover(self, con, now):
        expired = con.execute("SELECT * FROM research_jobs WHERE status='RUNNING' AND lease_until<=?", (now,)).fetchall()
        for row in expired:
            state = 'CANCELLED' if row['cancel_requested'] else ('FAILED' if row['attempts'] >= self.max_attempts else 'QUEUED')
            error = {'code': 'WORKER_INTERRUPTED', 'message': 'Worker lease expired; original run retained'}
            con.execute('''UPDATE research_jobs SET status=?,stage=?,error=?,updated=?,completed=?,
                           lease_token=NULL,lease_until=NULL WHERE job_id=?''',
                        (state, 'RECOVERY_PENDING' if state == 'QUEUED' else state, canonical(error),
                         now, now if state in TERMINAL else None, row['job_id']))

    def recover_expired(self):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            self._recover(con,self.clock())

    def claim(self, worker, profiles, *, lease_seconds=15):
        now = self.clock()
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            self._recover(con, now)
            if con.execute("SELECT count(*) FROM research_jobs WHERE status='RUNNING'").fetchone()[0] >= self.max_concurrency:
                return None
            rows = con.execute("SELECT * FROM research_jobs WHERE status='QUEUED' ORDER BY created,rowid").fetchall()
            for row in rows:
                if row['profile'] not in profiles:
                    continue
                if row['profile_hash'] != digest(self.profiles.get(row['profile'])):
                    con.execute("UPDATE research_jobs SET status='BLOCKED',stage='PROFILE_CHANGED',updated=?,completed=?,error=? WHERE job_id=?",
                                (now, now, canonical({'code':'PROFILE_CHANGED','message':'Pinned server profile changed; submit a new request'}), row['job_id']))
                    continue
                token = uuid4().hex
                con.execute('''UPDATE research_jobs SET status='RUNNING',stage='STARTING',worker=?,lease_token=?,
                    lease_until=?,attempts=attempts+1,updated=?,started=coalesce(started,?),error=NULL WHERE job_id=?''',
                            (worker, token, now+lease_seconds, now, now, row['job_id']))
                return self._decode(con.execute('SELECT * FROM research_jobs WHERE job_id=?', (row['job_id'],)).fetchone())
        return None

    def heartbeat(self, job_id, token, *, stage, progress, lease_seconds=15):
        now = self.clock()
        if not 0 <= progress <= 1 or not stage or len(stage) > 100:
            raise ValueError('Invalid progress')
        with self.connect() as con:
            changed = con.execute('''UPDATE research_jobs SET stage=?,progress=?,updated=?,lease_until=?
                WHERE job_id=? AND lease_token=? AND status='RUNNING' AND lease_until>?''',
                (stage, progress, now, now+lease_seconds, job_id, token, now)).rowcount
            if not changed:
                raise LeaseLost('Worker no longer owns this job')
            return bool(con.execute('SELECT cancel_requested FROM research_jobs WHERE job_id=?', (job_id,)).fetchone()[0])

    def cancel(self, job_id):
        now = self.clock()
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT status FROM research_jobs WHERE job_id=?', (job_id,)).fetchone()
            if not row:
                raise KeyError('Unknown research job')
            if row['status'] not in TERMINAL:
                state = 'CANCELLED' if row['status'] == 'QUEUED' else 'RUNNING'
                con.execute('UPDATE research_jobs SET cancel_requested=1,status=?,stage=?,updated=?,completed=? WHERE job_id=?',
                            (state, 'CANCEL_REQUESTED' if state == 'RUNNING' else state, now, now if state == 'CANCELLED' else None, job_id))
        return self.get(job_id)

    def _validate_results(self, job, status, results):
        if status not in TERMINAL:
            raise ValueError('A terminal state is required')
        if status in {'SUCCEEDED', 'PARTIAL'} and not results:
            raise ValueError('Successful execution requires retained research evidence')
        for value in results or []:
            if status == 'SUCCEEDED' and value.get('study_metadata',{}).get('provenance',{}).get('execution_status') == 'FAILED':
                raise ValueError('Failed computation cannot be a successful job')
            metadata = StudyMetadata.model_validate(value.get('study_metadata')).model_dump(mode='json')
            if value.get('schema_version') == 'factor-study-result/v1':
                FactorStudyResult.model_validate(value)
                identity = value['mapping']['identity']
                bound = {'entity_type':'FactorVariant','entity_id':identity['factor_variant_id'],
                         'definition_revision':identity['definition_revision']}
                if bound not in job['request']['entity_refs']:
                    raise ValueError('Result definition does not match request')
                if metadata['entity_refs'] != [bound]:
                    raise ValueError('Result metadata must identify its exact factor definition')
                if status == 'SUCCEEDED' and value['status'] != 'SUCCESS':
                    raise ValueError('Failed factor computation cannot be a successful job')
            else:
                from quantgraph.api.ingestion import ResearchEvidence
                from quantgraph.models.evidence_v4 import MarketResearchEvidenceV4
                model = MarketResearchEvidenceV4 if value.get('schema_version') == '3.0' else ResearchEvidence
                model.model_validate({k:v for k,v in value.items() if k != 'study_metadata'} if model is MarketResearchEvidenceV4 else value)
                if not set(value['source_strategy_ids']) <= {r['entity_id'] for r in job['request']['entity_refs']}:
                    raise ValueError('Result strategy does not match request')
                if set(value['source_strategy_ids']) != {r['entity_id'] for r in metadata['entity_refs']}:
                    raise ValueError('Result metadata must identify its exact strategy definitions')
            if metadata['study_type'] != job['request']['study_type'] or any(r not in job['request']['entity_refs'] for r in metadata['entity_refs']):
                raise ValueError('Study metadata does not match request')

    def finish(self, job_id, token, *, status, results=None, error=None):
        job = self.get(job_id)
        self._validate_results(job,status,results)
        now = self.clock()
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM research_jobs WHERE job_id=?', (job_id,)).fetchone()
            if row['lease_token'] != token or row['status'] != 'RUNNING' or row['lease_until'] <= now:
                raise LeaseLost('Worker no longer owns this job')
            if row['cancel_requested']:
                status = 'CANCELLED'
            con.execute('''UPDATE research_jobs SET status=?,stage=?,progress=?,results=?,error=?,updated=?,completed=?,
                           lease_token=NULL,lease_until=NULL WHERE job_id=?''',
                        (status, status, 1 if status == 'SUCCEEDED' else row['progress'], canonical(results or []),
                         canonical(error) if error else None, now, now, job_id))

    def import_completed(self, request, results, *, source_receipt, owner, resolve_ref):
        """Local operator only: retain checked past evidence without running trials.

        The caller verifies source artifact bytes before this method. No HTTP
        route exposes it. Old artifacts and their original research IDs persist.
        Imported records reserve zero new computation and cannot be claimed.
        """
        request=ResearchRequest.model_validate(request).model_dump(mode='json')
        if set(request['requested_settings']) != {'profile_id'} or not results:
            raise ValueError('A registered profile and retained evidence are required')
        profile_id=request['requested_settings']['profile_id']
        profile=self.profiles.get(profile_id)
        if not profile or profile['study_type']!=request['study_type']:
            raise ValueError('Import profile does not match the study type')
        good=[v for v in results if v.get('status','SUCCESS')=='SUCCESS'
              and v.get('study_metadata',{}).get('provenance',{}).get('execution_status','SUCCESS')=='SUCCESS'
              and v.get('results',{}).get('in_sample',{}).get('status')!='FAILED']
        status='SUCCEEDED' if len(good)==len(results) else ('PARTIAL' if good else 'FAILED')
        self._validate_results({'request':request},status,results)
        snapshots=[resolve_ref(**ref) for ref in request['entity_refs']]
        fingerprint=digest({'request':request,'results':results,'source_receipt':source_receipt})
        idem='artifact-import-'+fingerprint
        job_id='import-'+fingerprint[:32]
        now=self.clock()
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old=con.execute('SELECT * FROM research_jobs WHERE job_id=?',(job_id,)).fetchone()
            if old:return self._decode(old),True
            con.execute('''INSERT INTO research_jobs
                (job_id,owner,idem,request_hash,request,profile,profile_hash,snapshots,status,stage,progress,
                 results,created,updated,completed,trial_budget,seconds_budget)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (job_id,owner,idem,fingerprint,canonical(request),profile_id,digest(profile),
                 canonical({'definitions':snapshots,'import_receipt':source_receipt}),status,
                 'IMPORTED_COMPLETED_RESEARCH',1,canonical(results),now,now,now,0,0))
            if status != 'SUCCEEDED':
                con.execute('UPDATE research_jobs SET error=? WHERE job_id=?',
                            (canonical({'code':'RETAINED_COMPUTATION_FAILURE',
                                        'message':'Original computation failure retained; inspect the authenticated evidence and later revisions'}),job_id))
            row=con.execute('SELECT * FROM research_jobs WHERE job_id=?',(job_id,)).fetchone()
        return self._decode(row),False

    def imported_for_manifest(self, sha256):
        with self.connect() as con:
            rows=con.execute("SELECT * FROM research_jobs WHERE stage='IMPORTED_COMPLETED_RESEARCH'").fetchall()
        return [self._decode(row) for row in rows
                if json.loads(row['snapshots']).get('import_receipt',{}).get('manifest_sha256')==sha256]

    def results_for(self, entity_type, entity_id, definition_revision):
        ref = dict(entity_type=entity_type, entity_id=entity_id, definition_revision=definition_revision)
        with self.connect() as con:
            rows = con.execute("SELECT * FROM research_jobs WHERE results IS NOT NULL ORDER BY created DESC").fetchall()
        return [self._decode(row) for row in rows if ref in json.loads(row['request'])['entity_refs']]

    def result_refs(self):
        with self.connect() as con:
            rows = con.execute('SELECT request FROM research_jobs WHERE results IS NOT NULL').fetchall()
        refs = {canonical(ref) for row in rows for ref in json.loads(row['request'])['entity_refs']}
        return [json.loads(ref) for ref in sorted(refs)]

"""Authenticated compute and anonymous, visibility-filtered evidence summaries."""
from datetime import datetime, timezone
import hashlib
import hmac
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from quantgraph.graph.research_jobs import CapacityExceeded
from quantgraph.models.factor_study import ResearchRequest


def public_results(repository, ref, can_view):
    if not can_view(ref['entity_id']):
        raise KeyError('Entity not visible')
    items = []
    for job in repository.results_for(**ref):
        profile = repository.profiles.get(job['profile'], {})
        policy = profile.get('display_policy')
        if not profile.get('public_display') or not policy:
            continue
        for result in job['results']:
            meta = result.get('study_metadata') or {}
            if meta.get('display_policy') != policy or ref not in meta.get('entity_refs', []):
                continue
            if any(not can_view(r['entity_id']) for r in meta.get('entity_refs', []) + meta.get('lineage', [])):
                continue
            # No local paths, raw artifact bodies, request notes or arbitrary payload
            # fields can flow through the public projection. Producers cannot grant
            # rights: the server's pinned profile supplies that independent decision.
            summary = meta.get('public_summary', {})
            metrics = summary.get('metrics', {})
            safe_metrics = {str(k)[:100]: v for k,v in metrics.items()
                            if v is None or type(v) in (int,float,bool)} if isinstance(metrics, dict) else {}
            if not profile.get('numeric_display',False):
                safe_metrics = {}
            items.append(dict(
                job_id=job['job_id'], run_id=result.get('run_id',result.get('research_run_id')),
                entity_refs=meta['entity_refs'], study_type=meta['study_type'], study_kind=meta['study_kind'],
                conclusion_level=meta['conclusion_level'], limitations=meta['limitations'],
                lineage=meta.get('lineage', []), metrics=safe_metrics,
                sample={k:summary.get('sample',{}).get(k) for k in
                        ('start','end','rows','frequency','symbols','dataset_version','real_market_data')},
                status=job['status'], promotion_allowed=False, display_policy=policy,
                assessment_version=summary.get('assessment_version'),
                numerical_display='ALLOWED' if profile.get('numeric_display',False) else 'RESTRICTED',
            ))
    return items


def install_research_jobs(app, repository, *, resolve_ref, can_view, keys=None, auth_dependency=None):
    """Install before the SPA catch-all. Catalog owns visibility and admin sessions.

    auth_dependency may return a stable owner ID (or {'id': ID}); it must reject
    unauthenticated/unauthorized requests. No browser token storage is necessary.
    """
    app.state.research_jobs = repository
    router = APIRouter(prefix='/v1/research')

    def bearer_auth(request: Request):
        header = request.headers.get('authorization', '')
        if not header.startswith('Bearer '):
            raise HTTPException(401, 'Research submission requires authentication')
        supplied = hashlib.sha256(header[7:].encode()).digest()
        for key_id, key in (keys or {}).items():
            if hmac.compare_digest(supplied, hashlib.sha256(key['token'].encode()).digest()):
                if 'research:submit' not in key['scopes']:
                    raise HTTPException(403, 'Missing research:submit permission')
                return key_id
        raise HTTPException(401, 'Invalid credentials')

    auth = auth_dependency or bearer_auth

    def owner_id(principal):
        value = principal.get('id') if isinstance(principal, dict) else principal
        if not isinstance(value,str) or not value:
            raise HTTPException(403, 'Authenticated research principal required')
        return value

    def visible_job(job_id, principal):
        try:
            job = repository.get(job_id)
        except KeyError:
            raise HTTPException(404, 'Research job not found')
        if job['owner'] != owner_id(principal):
            raise HTTPException(404, 'Research job not found')
        return job

    def status_view(job):
        available = repository.worker_available(job['profile'])
        stamps = {k: datetime.fromtimestamp(job[k],timezone.utc).isoformat() if job[k] else None
                  for k in ('created','updated','started','completed')}
        ref = job['request']['entity_refs'][0]
        return dict(job_id=job['job_id'],run_id=job['run_id'],status=job['status'],progress=job['progress'],
                    stage=job['stage'], error=job['error'], worker_available=available,
                    result_url='/v1/research/results?'+urlencode(ref), timestamps=stamps,
                    entity_refs=job['request']['entity_refs'], study_type=job['request']['study_type'],
                    attempts=job['attempts'], cancel_requested=bool(job['cancel_requested']))

    @router.get('/capabilities')
    def capabilities():
        return {'items':[dict(profile_id=key, study_type=p['study_type'], entity_types=p['entity_types'],
                              max_entities=p.get('max_entities',1), max_trials=p['max_trials'],
                              max_seconds=p['max_seconds'], worker_available=repository.worker_available(key))
                         for key,p in repository.profiles.items()]}

    @router.post('/jobs', status_code=202)
    def submit(value: ResearchRequest, principal=Depends(auth)):
        try:
            job, duplicate = repository.submit(value.model_dump(mode='json'), owner=owner_id(principal), resolve_ref=resolve_ref)
            return {**status_view(job),'duplicate':duplicate}
        except CapacityExceeded as exc:
            raise HTTPException(429,str(exc))
        except (ValueError,KeyError) as exc:
            raise HTTPException(409,str(exc))

    @router.get('/jobs/{job_id}')
    def read(job_id:str, principal=Depends(auth)):
        return status_view(visible_job(job_id,principal))

    @router.post('/jobs/{job_id}/cancel')
    def cancel(job_id:str, principal=Depends(auth)):
        visible_job(job_id,principal)
        return status_view(repository.cancel(job_id))

    @router.get('/jobs/{job_id}/evidence')
    def private_evidence(job_id:str, principal=Depends(auth)):
        job=visible_job(job_id,principal)
        # Internal numerical research is usable without distributing the market
        # attachment or providing any file-read/download endpoint.
        def without_locations(value):
            if isinstance(value,list):return [without_locations(v) for v in value]
            if isinstance(value,dict):return {k:without_locations(v) for k,v in value.items()
                                             if k not in {'uri','artifact_uri','full_result','artifacts'}}
            return value
        return {'items':[without_locations({k:r.get(k) for k in
                         ('schema_version','run_id','research_run_id','status','sample','results','limitations','study_metadata')})
                         for r in job['results'] or []], 'visibility':'AUTHENTICATED_INTERNAL_RESEARCH',
                'promotion_allowed':False}

    @router.get('/results')
    def results(entity_type:str, entity_id:str, definition_revision:str):
        ref = dict(entity_type=entity_type,entity_id=entity_id,definition_revision=definition_revision)
        try:
            resolve_ref(**ref)
            return {'items':public_results(repository,ref,can_view),'promotion_allowed':False}
        except (KeyError,ValueError):
            raise HTTPException(404,'Entity revision not visible')

    app.include_router(router)

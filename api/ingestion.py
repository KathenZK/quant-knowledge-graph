"""Opt-in authenticated ingestion and private research surface."""
import hashlib
import hmac
import json
import os
from typing import Literal
from uuid import uuid4
import zlib

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from quantgraph.models.ingestion import IngestBatch
from quantgraph.models.evidence import MarketResearchEvidence
from quantgraph.models.evidence_v4 import MarketResearchEvidenceV4

bearer = HTTPBearer(auto_error=False)


def load_keys():
    keys = json.loads(os.environ.get('QUANTGRAPH_API_KEYS', '{}'))
    if not isinstance(keys, dict):
        raise ValueError('QUANTGRAPH_API_KEYS must be an object keyed by public key ID')
    seen = set()
    for key_id, item in keys.items():
        if not key_id or not isinstance(item, dict) or not isinstance(item.get('scopes'), list):
            raise ValueError('Invalid API key configuration')
        if not item.get('token') or len(item['token']) < 32:
            raise ValueError('API tokens must contain at least 32 characters')
        if item['token'] in seen:
            raise ValueError('Duplicate API tokens would make scope assignment ambiguous')
        seen.add(item['token'])
        if int(item.get('requests_per_minute', 60)) < 1:
            raise ValueError('Rate limit must be positive')
    return keys


def require(scope):
    def authenticate(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if not credentials or credentials.scheme.lower() != 'bearer':
            raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
        supplied = hashlib.sha256(credentials.credentials.encode()).digest()
        match = None
        for key_id, item in request.app.state.ingestion_keys.items():
            expected = hashlib.sha256(item['token'].encode()).digest()
            if hmac.compare_digest(supplied, expected):
                match = (key_id, item)
        if not match:
            raise HTTPException(401, 'Invalid token', headers={'WWW-Authenticate': 'Bearer'})
        key_id, item = match
        request.state.ingestion_key_id = key_id
        if scope not in item['scopes']:
            raise HTTPException(403, 'Missing scope: ' + scope)
        if not request.app.state.ingestion.consume_quota(key_id, int(item.get('requests_per_minute', 60))):
            raise HTTPException(429, 'Rate limit exceeded', headers={'Retry-After': '60'})
        return key_id
    return authenticate


class BoundedBodyMiddleware:
    """Enforce wire and expanded limits before FastAPI/Pydantic reads JSON."""
    def __init__(self, app, max_bytes=2 * 1024 * 1024):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in {'POST', 'PUT', 'PATCH'}:
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        encoding = headers.get(b'content-encoding', b'identity')
        if encoding not in {b'identity', b'gzip'}:
            return await JSONResponse({'detail': 'Unsupported content encoding'}, 415)(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > self.max_bytes:
                return await JSONResponse({'detail': 'Payload too large'}, 413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body', False):
                break
        body = b''.join(chunks)
        wire_body = body
        if encoding == b'gzip':
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            try:
                body = decoder.decompress(body, self.max_bytes + 1)
                if len(body) > self.max_bytes or decoder.unconsumed_tail:
                    return await JSONResponse({'detail': 'Expanded payload too large'}, 413)(scope, receive, send)
                if not decoder.eof or decoder.unused_data:
                    raise ValueError('Truncated or concatenated gzip')
            except (zlib.error, ValueError):
                return await JSONResponse({'detail': 'Invalid gzip'}, 400)(scope, receive, send)
        scope.setdefault('state', {})['ingestion_wire_body'] = wire_body
        scope['headers'] = [(k, v) for k, v in scope['headers'] if k not in {b'content-encoding', b'content-length'}]
        scope['headers'].append((b'content-length', str(len(body)).encode()))
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)


class ResearchEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    schema_version: Literal['1.0'] = '1.0'
    research_run_id: str = Field(min_length=1, max_length=200)
    experiment_family_id: str = Field(min_length=1)
    source_strategy_ids: list[str] = Field(min_length=1, max_length=1000)
    artifact_uri: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    contract_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    trial_count: int = Field(ge=1)
    results: dict
    evidence_kind: Literal['PIPELINE_DIAGNOSTIC', 'LAB_REPRODUCED', 'ATTRIBUTION_ABLATION']
    validation_status: Literal['SUBMITTED_NOT_INDEPENDENTLY_VERIFIED'] = 'SUBMITTED_NOT_INDEPENDENTLY_VERIFIED'


def install_ingestion(app, repository, *, keys=None, max_bytes=None):
    from quantgraph.graph.ingestion_store import ProjectionUnavailable

    @app.exception_handler(ProjectionUnavailable)
    async def unavailable(request, exc):
        return JSONResponse({'detail': str(exc), **exc.status, 'items': [],
                             'promotion_allowed': False}, status_code=503)

    app.state.ingestion = repository
    app.state.ingestion_keys = load_keys() if keys is None else keys
    app.add_middleware(BoundedBodyMiddleware, max_bytes=max_bytes or int(os.getenv('QUANTGRAPH_MAX_BODY_BYTES', 2 * 1024 * 1024)))
    router = APIRouter()

    @app.middleware('http')
    async def audit(request, call_next):
        request_id = uuid4().hex
        try:
            response = await call_next(request)
        except Exception:
            route = getattr(request.scope.get('route'), 'path', 'unmatched')
            repository.log_request(request_id, getattr(request.state, 'ingestion_key_id', 'anonymous'), route, 500)
            raise
        if request.url.path.startswith(('/v1/ingest/', '/v1/research/', '/v1/usage')):
            # Route templates avoid source IDs, credentials or query strings in logs.
            route = getattr(request.scope.get('route'), 'path', 'unmatched')
            repository.log_request(request_id, getattr(request.state, 'ingestion_key_id', 'anonymous'), route, response.status_code)
        response.headers['X-Request-ID'] = request_id
        return response

    @router.post('/v1/ingest/grokbot/batches')
    def ingest(batch: IngestBatch, request: Request, key_id=Depends(require('ingest:write'))):
        return repository.ingest(batch, request.state.ingestion_wire_body, key_id)

    @router.get('/v1/ingest/jobs/{job_id}', dependencies=[Depends(require('ingest:read'))])
    def job(job_id: str):
        try:
            return repository.get_job(job_id)
        except KeyError:
            raise HTTPException(404, 'Job not found')

    @router.get('/v1/ingest/batches/{batch_id}', dependencies=[Depends(require('ingest:read'))])
    def batch(batch_id: str):
        try:
            return repository.get_batch(batch_id)
        except KeyError:
            raise HTTPException(404, 'Batch not found')

    @router.get('/v1/research/strategies/{kind}', dependencies=[Depends(require('research:read'))])
    def strategies(kind: Literal['concepts', 'templates', 'variants'], limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        if kind == 'variants':
            return {'items': repository.variants(limit, offset)}
        # Concept/template pagination is over unique objects, not over source rows.
        rows, cursor = {}, 0
        key = 'strategy_concept_id' if kind == 'concepts' else 'strategy_template_id'
        while page := repository.variants(1000, cursor):
            for record in page:
                for item in record[kind]:
                    rows[item[key]] = item
            cursor += len(page)
        return {'items': [rows[k] for k in sorted(rows)][offset:offset + limit]}

    @router.get('/v1/research/lineage/{variant_id}', dependencies=[Depends(require('research:read'))])
    def lineage(variant_id: str):
        rows = repository.lineage(variant_id)
        if not rows:
            raise HTTPException(404, 'Variant not found')
        return {'items': rows}

    @router.get('/v1/research/factors/{factor_id}/strategies', dependencies=[Depends(require('research:read'))])
    def by_factor(factor_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        found, cursor = [], 0
        while page := repository.variants(1000, cursor):
            found.extend(r for r in page if any(link['factor_id'] == factor_id for link in r['factor_links']))
            cursor += len(page)
        return {'items': found[offset:offset + limit]}

    @router.get('/v1/research/candidates', dependencies=[Depends(require('research:read'))])
    def candidates(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        # Triage candidates retain all blocking facts. Lab owns admission decisions.
        return {'items': repository.variants(limit, offset), 'scope': 'TRIAGE_ONLY',
                **repository.projection_status(), 'promotion_allowed': False}

    @router.get('/v1/research/assessments', dependencies=[Depends(require('research:read'))])
    def assessments():
        from quantgraph.graph.evidence_queue import summarize
        rows, cursor = [], 0
        while page := repository.variants(1000, cursor):
            rows.extend(page)
            cursor += len(page)
        return {**summarize(rows), **repository.projection_status(), 'promotion_allowed': False}

    @router.get('/v1/research/projection-status', dependencies=[Depends(require('research:read'))])
    def projection_status():
        return repository.projection_status()

    @router.get('/v1/research/chain/{variant_id}', dependencies=[Depends(require('research:read'))])
    def research_chain(variant_id: str):
        cursor=0
        while page := repository.variants(1000,cursor):
            for row in page:
                if row['variant']['strategy_variant_id']==variant_id:
                    evidence=repository.evidence_for(variant_id)
                    formal=[x for x in evidence if x.get('schema_version')=='3.0' and x.get('evidence_kind')=='REAL_MARKET_BACKTEST']
                    # BacktestResult is a deterministic projection of the same
                    # immutable transaction, never a second copy to drift.
                    results=[{'backtest_result_id':'backtest-'+x['research_run_id'],'research_run_id':x['research_run_id'],
                              'results':x['results'],'research_status':x['research_status'],
                              'dataset_sha256':x['dataset_sha256'],'dataset_manifest_sha256':x['dataset_manifest_sha256']} for x in formal]
                    return {'strategy':row,'provenance':repository.lineage(variant_id),
                            'research_evidence':evidence,'backtest_results':results,'promotion_allowed':False}
            cursor+=len(page)
        raise HTTPException(404,'Variant not found')

    @router.get('/v1/ingest/stats', dependencies=[Depends(require('ingest:read'))])
    def ingest_stats():
        return repository.ingest_stats()

    @router.post('/v1/research/evidence')
    def evidence(value: ResearchEvidence | MarketResearchEvidence | MarketResearchEvidenceV4, key_id=Depends(require('research:write'))):
        try:
            return repository.put_evidence(value.model_dump(mode='json'), key_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @router.get('/v1/research/evidence/{variant_id}', dependencies=[Depends(require('research:read'))])
    def research_evidence(variant_id: str):
        return {'items': repository.evidence_for(variant_id), 'promotion_allowed': False,
                'validation_status': 'SUBMITTED_NOT_INDEPENDENTLY_VERIFIED'}

    @router.get('/v1/usage')
    def usage(key_id=Depends(require('ingest:read'))):
        config = app.state.ingestion_keys[key_id]
        return {'key_id': key_id, 'plan': config.get('plan', 'private'), 'items': repository.usage(key_id)}

    app.include_router(router)

"""Explicit loopback personal reading service, separate from the public API."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from quantgraph.api.ingestion import BoundedBodyMiddleware
from quantgraph.api.web import Kind, ReferenceBatch, RequestDraft
from quantgraph.db import project_root
from quantgraph.models.factor_study import ResearchRequest


def create_personal_app(root=None, *, runtime=None, catalog=None, store=None):
    root = project_root(root)
    runtime = Path(runtime or root / '.artifacts/personal').resolve()
    app = FastAPI(title='QuantGraph 个人知识工作台', docs_url=None, redoc_url=None)
    if catalog is None and (runtime / 'catalog.sqlite').is_file():
        from quantgraph.graph.personal_catalog import PersonalCatalogRepository
        from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
        journal = runtime / 'ingestion.sqlite'
        catalog = PersonalCatalogRepository(runtime / 'catalog.sqlite',
            ingestion=SQLiteIngestionRepository(journal) if journal.is_file() else None)
    if catalog is not None:
        from quantgraph.api.personal import install_personal
        from quantgraph.graph.personal_store import PersonalStore
        from quantgraph.graph.personal_research import RetainedResearch
        catalog.result_reader = RetainedResearch(runtime)
        store = store or PersonalStore(runtime / 'personal.sqlite')
        catalog.personal_store = store
        install_personal(app, catalog, store)
    app.state.catalog, app.state.personal_store = catalog, store
    from quantgraph.graph.source_links import SourceLinks
    links = SourceLinks(runtime / 'source-links.sqlite')
    app.add_middleware(BoundedBodyMiddleware, max_bytes=16 * 1024 * 1024)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        if request.url.path.startswith('/v1/') and not request.url.path.startswith(('/v1/web/', '/v1/personal/')):
            return JSONResponse({'detail': '个人模式只提供知识阅读与个人记录'}, 404)
        client = request.client.host if request.client else ''
        if client not in {'127.0.0.1', '::1', 'testclient'}:
            return JSONResponse({'detail': '个人工作台只接受本机连接'}, 403)
        origin = request.headers.get('origin')
        if origin:
            parts = urlsplit(origin)
            if parts.scheme not in {'http', 'https'} or parts.netloc != request.headers.get('host'):
                return JSONResponse({'detail': '不接受跨站访问个人资料'}, 403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': '不接受跨站访问个人资料'}, 403)
        try:
            if catalog is not None and request.url.path.startswith('/v1/'):
                from starlette.concurrency import run_in_threadpool
                await run_in_threadpool(catalog.sync_ingestion)
            response = await call_next(request)
        except Exception:
            response = JSONResponse({'detail': '个人资料服务暂时不可用；请检查本地数据完整性'}, 500)
        response.headers.update({
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
            'Cache-Control': 'no-store', 'Cross-Origin-Resource-Policy': 'same-origin',
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
        })
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse({'detail': '请求字段或格式不正确'}, 422)

    def model():
        if catalog is None:
            raise HTTPException(503, '完整 Catalog 尚未初始化。请显式导入已有个人资料；不会退回 Qlib-only。')
        return catalog

    @app.get('/healthz')
    @app.get('/health')
    def health():
        return dict(status='ok' if catalog else 'initialization_required', mode='personal_local')

    @app.get('/v1/web/meta')
    def metadata():
        from importlib.metadata import version
        from quantgraph.graph.personal_build_info import build_info
        running = dict(application_version=version('quant-knowledge-graph'), build=build_info(root))
        if catalog is None:
            return dict(**running, mode='personal_local', initialized=False, release=None, counts={}, facets={},
                initialization={'status': 'MISSING', 'message': '完整 Catalog 尚未初始化。请显式导入已有个人资料；不会退回 Qlib-only。'},
                message='完整 Catalog 尚未初始化。个人工作台需要显式提供已导入资料，不会静默退回 Qlib-only。')
        snapshot = runtime / 'snapshot.json'
        provenance = json.loads(snapshot.read_text()) if snapshot.is_file() else {}
        meta = catalog.metadata()
        reconciliation = catalog.reconcile()
        imports = reconciliation.get('imports', [])
        return meta | dict(**running, mode='personal_local', initialized=True,
            snapshot=provenance.get('created_at', '未登记快照时间'),
            dataset='GrokBot 策略与多来源因子 · 本机 Catalog',
            imported_at=imports[0]['created_at'] if imports else None,
            snapshot_inputs=[{'name': Path(v['copy']).name, 'sha256': v['sha256']}
                for v in provenance.get('inputs', [])],
            retained_research_inputs=catalog.results().get('input_counts', {}),
            research_mode='只读历史研究；不运行研究任务')

    @app.get('/v1/web/search')
    def search(q: str = Query('', max_length=2000), kind: Kind = 'strategy', category: str = '',
               family: str = '', template_id: str = '', field: str = '', market: str = '', frequency: str = '',
               source_type: str = '', result_status: str = '', personal_status: str = '',
               axis: str = '', extra_data: str = '', completeness: str = '', method_family: str = '', asset_scope: str = '',
               daily_ohlcv: bool = False, starred: bool | None = None, collapse_templates: bool = False,
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50)):
        allowed_ids = None
        if personal_status or starred is not None:
            from quantgraph.graph.personal_store import STATUSES
            if personal_status and personal_status not in STATUSES:
                raise HTTPException(422, '阅读状态不正确')
            notes = {v['entity_id']: v for v in store.list()['items']} if store else {}
            allowed_ids = set()
            for item in model().all_items():
                prior = item.get('prior_version_ids', [])
                note = notes.get(item['entity_id']) or next((notes[x] for x in prior if x in notes), {})
                if personal_status and note.get('status', '待读') != personal_status:
                    continue
                if starred is not None and note.get('starred', False) != starred:
                    continue
                allowed_ids.add(item['entity_id'])
        return model().search(q=q, kind=kind, category=category, family=family, template_id=template_id, field=field,
            market=market, frequency=frequency, source_type=source_type, result_status=result_status,
            allowed_ids=allowed_ids, axis=axis, extra_data=extra_data, daily_ohlcv=daily_ohlcv, asset_scope=asset_scope,
            completeness=completeness, method_family=method_family, collapse_templates=collapse_templates,
            page=page, page_size=page_size)

    @app.get('/v1/web/entities/{kind}/{eid}')
    @app.get('/v1/web/export/{kind}/{eid}')
    def detail(kind: Kind, eid: str):
        try:
            value = model().detail(kind, eid)
            if store:
                canonical = store.resolve(eid)
                value['canonical_id'] = canonical
            return value
        except KeyError:
            raise HTTPException(404, '个人资料中没有此条目')

    @app.get('/v1/web/compare')
    def compare(ref: list[str] = Query(..., min_length=2, max_length=4)):
        if len(set(ref)) != len(ref):
            raise HTTPException(422, '请选择不同条目')
        try:
            return model().compare(ref)
        except (KeyError, ValueError):
            raise HTTPException(404, '比较条目不存在或类型不匹配')

    @app.get('/v1/web/relations/{eid}')
    def relations(eid: str, hops: int = Query(1, ge=1, le=2), relation: str = '',
                  layer: str = 'method', confidence: float = Query(0, ge=0, le=1),
                  limit: int = Query(40, ge=1, le=100), offset: int = Query(0, ge=0)):
        try:
            return model().relations(eid, hops=hops, relation=relation, layer=layer, confidence=confidence, limit=limit, offset=offset)
        except KeyError:
            raise HTTPException(404, '关系起点不存在')

    @app.get('/v1/web/results')
    def results(kind: Kind | None = None, eid: str | None = None):
        if (kind is None) != (eid is None):
            raise HTTPException(422, '条目类型与 ID 必须一起提供')
        try:
            return model().results(kind, eid)
        except KeyError:
            raise HTTPException(404, '条目不存在')

    @app.get('/v1/web/reconciliation')
    def reconciliation():
        return model().reconcile()

    @app.get('/v1/personal/source-check/{eid}')
    def link_status(eid: str):
        try:
            return links.read(model().get(eid).get('source_url'))
        except KeyError:
            raise HTTPException(404, '来源条目不存在')

    @app.post('/v1/personal/source-check/{eid}')
    def check_link(eid: str):
        try:
            return links.check(model().get(eid).get('source_url'))
        except KeyError:
            raise HTTPException(404, '来源条目不存在')

    @app.post('/v1/web/references/resolve')
    def references(body: ReferenceBatch):
        values = []
        for ref in body.refs:
            try:
                value = model().get(ref.entity_id)
            except KeyError:
                raise HTTPException(404, '引用的条目不存在')
            if value['entity_type'] != ref.entity_type or value['definition_revision'] != ref.definition_revision:
                raise HTTPException(409, '定义已更新；原笔记版本保留，请比较后重新选择')
            values.append(value)
        return dict(items=values)

    @app.post('/v1/web/research-requests')
    def export_request(body: RequestDraft):
        from uuid import uuid4
        expected = 'FactorVariant' if body.study_type == 'FACTOR_DIAGNOSTIC' else 'StrategyVariant'
        seen = set()
        for ref in body.entity_refs:
            if ref.entity_type != expected or ref.entity_id in seen:
                raise HTTPException(422, '研究类型与条目身份不匹配，或含重复引用')
            seen.add(ref.entity_id)
            try:
                model().resolve_ref(**ref.model_dump())
            except KeyError:
                raise HTTPException(409, '定义版本已变化，原研究引用保留')
        return ResearchRequest(request_id='personal-' + uuid4().hex, **body.model_dump()).model_dump(mode='json')

    dist = root / 'web/dist'
    if dist.is_dir():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

        @app.get('/favicon.svg', include_in_schema=False)
        def favicon():
            return FileResponse(dist / 'favicon.svg')

        @app.get('/{path:path}', include_in_schema=False)
        def website(path: str):
            if path and path.split('/')[0] not in {'strategies','factors','families','explore','entity','compare','list','relations','results'}:
                raise HTTPException(404, '页面不存在')
            return FileResponse(dist / 'index.html')
    return app


def main():
    parser = argparse.ArgumentParser(description='本地个人知识工作台；只绑定回环地址')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--port', type=int, default=8791)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_personal_app(runtime=args.runtime), host='127.0.0.1', port=args.port,
                access_log=False, proxy_headers=False)


if __name__ == '__main__':
    main()

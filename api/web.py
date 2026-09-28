"""Local, public-only web entry point. Reuses the existing read-only Graph API."""

import argparse
from uuid import uuid4
from typing import Literal

from fastapi import HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from quantgraph.api.app import create_app
from quantgraph.api.web_read_model import WebReadModel
from quantgraph.db import project_root
from quantgraph.models.factor_study import ResearchRequest, EntityRef

Kind = Literal["variant", "concept", "strategy", "family", "template", "source"]


class BookmarkRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: Literal["FactorVariant", "FactorConcept", "Strategy", "StrategyVariant"]
    entity_id: str = Field(min_length=1, max_length=200)
    definition_revision: str = Field(min_length=1, max_length=200)


class ReferenceBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refs: list[BookmarkRef] = Field(max_length=500)


class RequestDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_refs: list[EntityRef] = Field(min_length=1, max_length=500)
    study_type: Literal["FACTOR_DIAGNOSTIC", "STRATEGY_REPLICATION"]
    requested_settings: dict


def create_web_app(root=None, *, private_journal=None, catalog=None, admin_password=None, research_installer=None, research_profiles=None, research_database=None):
    root = project_root(root)
    app = create_app(root, public_only=True)
    repository = None
    if private_journal is not None:
        from pathlib import Path
        from quantgraph.graph.factor_study_store import FactorStudyRepository
        if not Path(private_journal).is_file():
            raise ValueError("Explicit existing local study journal required")
        repository = FactorStudyRepository(private_journal, app.state.db)
    model = catalog or WebReadModel(app.state.db, studies=repository)
    if catalog is not None:
        from quantgraph.api.admin import install_admin
        from quantgraph.api.ingestion import BoundedBodyMiddleware
        app.state.catalog = catalog
        install_admin(app, catalog, password=admin_password)
        app.add_middleware(BoundedBodyMiddleware)
        if research_installer is None:
            research_profiles = research_profiles or {}
            research_database = research_database or catalog.path.parent / "research-jobs.sqlite"
            from quantgraph.api.research_jobs import install_research_jobs, public_results
            from quantgraph.graph.research_jobs import ResearchJobRepository
            from quantgraph.graph.catalog_projection import empty_results
            jobs = ResearchJobRepository(research_database, research_profiles)
            install_research_jobs(app, jobs, resolve_ref=catalog.resolve_ref, can_view=catalog.visible,
                                  auth_dependency=app.state.require_admin)
            def result_reader(kind, eid):
                if eid:
                    selected = [catalog.get(eid)]
                else:
                    import json
                    with jobs.connect() as con:
                        references = [ref for row in con.execute("SELECT request FROM research_jobs WHERE results IS NOT NULL")
                                      for ref in json.loads(row[0])['entity_refs']]
                    selected = [catalog.get(entity_id) for entity_id in {r['entity_id'] for r in references} if catalog.visible(entity_id)]
                rows = []
                for item in selected:
                    ref = {k: item[k] for k in ['entity_type', 'entity_id', 'definition_revision']}
                    rows.extend(public_results(jobs, ref, catalog.visible))
                return empty_results() | {'items': rows, 'total': len(rows),
                    'status': '已有研究记录' if rows else '尚未研究或展示权限受限',
                    'reason': '研究结论与公开许可独立判断；无权限的内部结果不会暴露存在性或数量。'}
            catalog.result_reader = result_reader
        if research_installer:
            research_installer(app, catalog)
    app.state.web_model = model
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        try:
            if catalog is not None and request.url.path.startswith("/v1/"):
                allowed = ("/v1/web/", "/v1/admin/", "/v1/research/jobs", "/v1/research/results", "/v1/research/capabilities", "/v1/ingest/")
                if not request.url.path.startswith(allowed):
                    return JSONResponse(status_code=404, content={"detail": "请使用 Catalog 查询入口"})
                # Incremental projection observes successful existing ingestion writes.
                # No raw data is ever sent to the browser.
                from starlette.concurrency import run_in_threadpool
                await run_in_threadpool(catalog.sync_ingestion)
            response = await call_next(request)
        except Exception:
            # Do not emit exception messages, database paths, or source text to
            # HTTP responses or uvicorn's automatic unhandled-error traceback.
            response = JSONResponse(
                status_code=500, content={"detail": "公开知识服务暂时不可用"}
            )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(status_code=422, content={"detail": "请求参数格式不正确"})

    @app.exception_handler(Exception)
    async def server_error(request, exc):
        return JSONResponse(
            status_code=500, content={"detail": "公开知识服务暂时不可用"}
        )

    @app.get("/v1/web/meta")
    def metadata():
        return model.metadata()

    @app.get("/v1/web/search")
    def search(
        q: str = Query("", max_length=200),
        kind: Kind = "variant",
        category: str = "",
        family: str = "",
        frequency: str = "",
        source_type: str = "",
        field: str = "",
        market: str = "",
        result_status: str = "",
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=50),
    ):
        return model.search(
            q=q,
            kind=kind,
            category=category,
            family=family,
            field=field,
            market=market,
            result_status=result_status,
            page=page,
            page_size=page_size,
            **({"frequency": frequency, "source_type": source_type} if catalog is not None else {}),
        )

    @app.get("/v1/web/entities/{kind}/{eid}")
    def detail(kind: Kind, eid: str):
        try:
            return model.detail(kind, eid)
        except KeyError:
            raise HTTPException(404, "当前公开版本中没有此条目")

    @app.get("/v1/web/results")
    def results(kind: Kind | None = None, eid: str | None = None):
        if (kind is None) != (eid is None):
            raise HTTPException(422, "条目类型与 ID 必须同时提供")
        try:
            return model.results(kind, eid)
        except KeyError:
            raise HTTPException(404, "当前公开版本中没有此条目")

    @app.get("/v1/web/license", response_class=PlainTextResponse)
    def license_text():
        return (app.state.db.release_path / "THIRD_PARTY_LICENSE.txt").read_text()

    @app.post("/v1/web/references/resolve")
    def resolve_references(body: ReferenceBatch):
        kinds = {
            "FactorVariant": "variant",
            "FactorConcept": "concept",
            "Strategy": "strategy",
            "StrategyVariant": "strategy",
        }
        items = []
        for ref in body.refs:
            item = model.by_key.get((kinds[ref.entity_type], ref.entity_id))
            if not item or item["definition_revision"] != ref.definition_revision:
                raise HTTPException(409, "引用不在当前公开版本中或定义版本已变化")
            items.append(item)
        return {"items": items}

    @app.get("/v1/web/compare")
    def compare(ref: list[str] = Query(..., min_length=2, max_length=4)):
        if len(set(ref)) != len(ref):
            raise HTTPException(422, "请选择不同条目")
        items = []
        for key in ref:
            kind, _, eid = key.partition("/")
            try:
                items.append(model.detail(kind, eid))
            except KeyError:
                raise HTTPException(404, "当前公开版本中没有此条目")
        return {"items": items}

    @app.post("/v1/web/research-requests")
    def export_request(body: RequestDraft):
        expected_type = "FactorVariant" if body.study_type == "FACTOR_DIAGNOSTIC" else "StrategyVariant"
        expected_kind = "variant" if body.study_type == "FACTOR_DIAGNOSTIC" else "strategy"
        seen = set()
        for ref in body.entity_refs:
            item = model.by_key.get((expected_kind, ref.entity_id))
            if (ref.entity_type != expected_type or not item
                    or item["definition_revision"] != ref.definition_revision):
                raise HTTPException(409, "请选择当前公开版本的对应因子或策略变体")
            if ref.entity_id in seen:
                raise HTTPException(422, "研究请求含重复引用")
            seen.add(ref.entity_id)
        return ResearchRequest(request_id="web-" + uuid4().hex, **body.model_dump()).model_dump(mode="json")

    @app.get("/healthz")
    def health():
        return {"status": "ok", "catalog": "persistent" if catalog is not None else "public_qlib"}

    @app.get("/v1/web/relations/{eid}")
    def relations(eid: str, hops: int = Query(1, ge=1, le=2), relation: str = "",
                  limit: int = Query(40, ge=1, le=100), offset: int = Query(0, ge=0)):
        if catalog is None:
            raise HTTPException(404, "请先配置运行时 Catalog")
        try:
            return catalog.relations(eid, hops=hops, relation=relation, limit=limit, offset=offset)
        except KeyError:
            raise HTTPException(404, "当前公开版本中没有此条目")

    @app.get("/v1/web/export/{kind}/{eid}")
    def export_entity(kind: Kind, eid: str):
        try:
            return model.detail(kind, eid)
        except KeyError:
            raise HTTPException(404, "当前公开版本中没有此条目")

    dist = root / "web/dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="web-assets")

        @app.get("/favicon.svg", include_in_schema=False)
        def favicon():
            return FileResponse(dist / "favicon.svg")

        @app.get("/{path:path}", include_in_schema=False)
        def website(path: str):
            if path and path.split("/")[0] not in {
                "explore",
                "entity",
                "compare",
                "list",
                "results",
                "relations",
                "admin",
                "jobs",
            }:
                raise HTTPException(404, "页面不存在")
            return FileResponse(dist / "index.html")

    return app


def main():
    parser = argparse.ArgumentParser(
        description="QuantGraph PUBLIC website, loopback only"
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--private-study-journal", help="Explicit local-only private results journal")
    parser.add_argument("--catalog", help="Explicit persistent Catalog SQLite path")
    parser.add_argument("--ingestion-journal", help="Own writable ingestion journal for incremental projection")
    parser.add_argument("--research-profiles", help="Server-owned registered research profiles JSON")
    parser.add_argument("--research-database", help="Durable research job journal")
    args = parser.parse_args()
    import uvicorn

    catalog = None
    if args.catalog:
        from quantgraph.graph.catalog import CatalogRepository
        from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
        catalog = CatalogRepository(args.catalog, ingestion=SQLiteIngestionRepository(args.ingestion_journal) if args.ingestion_journal else None)
    import json
    from pathlib import Path
    profiles = json.loads(Path(args.research_profiles).read_text()) if args.research_profiles else None
    uvicorn.run(create_web_app(private_journal=args.private_study_journal, catalog=catalog,
                              research_profiles=profiles, research_database=args.research_database), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()

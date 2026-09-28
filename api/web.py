"""Local, public-only web entry point. Reuses the existing read-only Graph API."""

import argparse
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

Kind = Literal["variant", "concept", "strategy"]


class BookmarkRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: Literal["FactorVariant", "FactorConcept", "Strategy"]
    entity_id: str = Field(min_length=1, max_length=200)
    definition_revision: str = Field(min_length=1, max_length=200)


class ReferenceBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refs: list[BookmarkRef] = Field(max_length=500)


def create_web_app(root=None):
    root = project_root(root)
    app = create_app(root, public_only=True)
    model = WebReadModel(app.state.db)
    app.state.web_model = model
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        try:
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

    # A owns request/result contracts. Fail closed until the real contract is
    # available; browser list export remains independently usable.
    @app.post("/v1/web/research-requests")
    def export_request():
        raise HTTPException(
            503, "正式 research-request/v1 契约尚未接入；可先导出清单备份，研究未运行"
        )

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
            }:
                raise HTTPException(404, "页面不存在")
            return FileResponse(dist / "index.html")

    return app


def main():
    parser = argparse.ArgumentParser(
        description="QuantGraph PUBLIC website, loopback only"
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(create_web_app(), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()

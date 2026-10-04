"""Repository knowledge search; no runtime Catalog writes or execution routes."""
from functools import lru_cache

from fastapi import HTTPException, Query

from quantgraph.db import AmbiguousAliasError
from quantgraph.graph.knowledge_catalog import KnowledgeCatalog


def install_knowledge(app, root):
    @lru_cache(maxsize=1)
    def catalog():
        # One verified snapshot per app instance. Restart after accepting changes.
        return KnowledgeCatalog(root)

    @app.get('/v1/knowledge/stats')
    def stats():
        return catalog().stats()

    @app.get('/v1/knowledge')
    def search(q: str | None = None, kind: str | None = None, source: str | None = None,
               status: str | None = None, market: str | None = None, frequency: str | None = None,
               record_kind: str | None = None, limit: int = Query(50, ge=1, le=1000),
               offset: int = Query(0, ge=0)):
        try:
            return catalog().search(q, kind=kind, source=source, status=status, market=market,
                                    frequency=frequency, record_kind=record_kind, limit=limit, offset=offset)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get('/v1/knowledge/lookup')
    def lookup(identity: str):
        # Query parameters support source-qualified aliases containing '/'.
        return detail(identity)

    @app.get('/v1/knowledge/{entity_id}/relations')
    def relations(entity_id: str):
        try:
            return {'items': catalog().relations(entity_id)}
        except KeyError as exc:
            raise HTTPException(404, 'Knowledge entry not found') from exc
        except AmbiguousAliasError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get('/v1/knowledge/{entity_id}')
    def detail(entity_id: str):
        try:
            return catalog().get(entity_id)
        except KeyError as exc:
            raise HTTPException(404, 'Knowledge entry not found') from exc
        except AmbiguousAliasError as exc:
            raise HTTPException(409, str(exc)) from exc

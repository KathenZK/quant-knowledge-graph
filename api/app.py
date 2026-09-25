"""Read-only HTTP surface. Commercial graph is the public default."""
import os
from fastapi import FastAPI, Query, HTTPException
from quantgraph import FactorDB, AmbiguousAliasError


def create_app(root=None, profile=None):
    selected=profile or os.getenv('QUANTGRAPH_PROFILE','commercial')
    db=FactorDB(root,profile=selected)
    app=FastAPI(title='Quant Knowledge Graph',version='0.2.0',description='Curated definitions and provenance; no backtest or strategy execution endpoints.')
    app.state.db=db

    @app.get('/health')
    def health():
        return {'status':'ok','profile':db.profile,'dataset_scope':db.dataset_scope,'release':db.release_path.name}

    @app.get('/v1/stats')
    def stats():
        return db.stats()

    @app.get('/v1/factors')
    def factors(q:str|None=None,category:str|None=None,asset_class:str|None=None,source:str|None=None,
                limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0)):
        rows=db.search_factors(q,category=category,asset_class=asset_class,source=source,limit=limit,offset=offset)
        return {'items':rows,'offset':offset,'limit':limit,'profile':db.profile,'dataset_scope':db.dataset_scope}

    @app.get('/v1/factors/{factor_id}')
    def factor(factor_id:str,namespace:str|None=None):
        try:return db.get_factor(factor_id,namespace=namespace)
        except KeyError:raise HTTPException(404,'Factor not found in this profile')
        except AmbiguousAliasError as exc:raise HTTPException(409,str(exc))

    @app.get('/v1/factors/{factor_id}/related')
    def related(factor_id:str):
        try:return db.find_related_factors(factor_id)
        except KeyError:raise HTTPException(404,'Factor not found in this profile')
        except AmbiguousAliasError as exc:raise HTTPException(409,str(exc))

    @app.get('/v1/variants/{variant_id}')
    def variant(variant_id:str):
        try:return db.get_variant(variant_id)
        except KeyError:raise HTTPException(404,'Variant not found in this profile')

    @app.get('/v1/strategies')
    def strategies(factor:str|None=None,limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0)):
        try:return {'items':db.find_strategies(factor=factor,limit=limit,offset=offset)}
        except AmbiguousAliasError as exc:raise HTTPException(409,str(exc))

    @app.get('/v1/strategies/{strategy_id}/factors')
    def strategy_factors(strategy_id:str):
        try:db.get_entity('Strategy',strategy_id)
        except KeyError:raise HTTPException(404,'Strategy not found in this profile')
        return {'items':db.get_strategy_factors(strategy_id)}

    @app.get('/v1/entities/{entity_type}/{entity_id}')
    def entity(entity_type:str,entity_id:str):
        try:return db.get_entity(entity_type,entity_id)
        except KeyError:raise HTTPException(404,'Entity not found in this profile')

    @app.get('/v1/relationships/{entity_id}')
    def relationships(entity_id:str,limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0)):
        return {'items':db.relationships(entity_id,limit=limit,offset=offset)}

    return app

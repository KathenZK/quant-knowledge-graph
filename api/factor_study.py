"""Opt-in private factor studies. Public reads never expose the private journal."""
import hashlib
import hmac
from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from quantgraph.models.factor_study import FactorStudyResult


def install_factor_studies(app, repository=None, keys=None):
    @app.get('/v1/factors/{factor_id}/studies')
    def public_studies(factor_id: str):
        return {'items': [], 'profile': 'commercial', 'public_review_available': False}

    if repository is None:
        return
    from quantgraph.api.ingestion import BoundedBodyMiddleware, load_keys
    keys = load_keys() if keys is None else keys
    if not any(m.cls is BoundedBodyMiddleware for m in app.user_middleware):
        app.add_middleware(BoundedBodyMiddleware)
    bearer = HTTPBearer(auto_error=False)

    def require(scope):
        def auth(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
            if credentials is None:
                raise HTTPException(401, 'Bearer token required')
            supplied = hashlib.sha256(credentials.credentials.encode()).digest()
            for key in keys.values():
                if hmac.compare_digest(supplied, hashlib.sha256(key['token'].encode()).digest()):
                    if scope not in key['scopes']:
                        raise HTTPException(403, 'Missing scope: ' + scope)
                    return
            raise HTTPException(401, 'Invalid token')
        return auth

    @app.post('/v1/research/factor-studies', dependencies=[Depends(require('research:write'))])
    def submit(value: FactorStudyResult):
        try:
            return repository.put(value.model_dump(mode='json'))
        except (ValueError, KeyError) as exc:
            raise HTTPException(409, str(exc))

    @app.get('/v1/research/factor-studies/{entity_id}', dependencies=[Depends(require('research:read'))])
    def studies(entity_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return {'items': repository.query(entity_id, profile='research', limit=limit, offset=offset),
                'profile': 'research', 'promotion_allowed': False}

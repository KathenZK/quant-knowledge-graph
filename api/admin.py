"""Local/deployable administrative session; credentials never enter the bundle."""
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from quantgraph.graph.grokbot import stable_json, content_hash
from quantgraph.graph.ingestion_store import now

COOKIE = 'quantgraph_session'


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str = Field(min_length=1,max_length=500)


class Edit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[str] = Field(min_length=1,max_length=100)
    patch: dict


def same_origin(request):
    origin = request.headers.get('origin')
    if origin:
        parts = urlsplit(origin)
        if parts.netloc != request.headers.get('host') or parts.scheme not in {'http','https'}:
            raise HTTPException(403, '来源不允许')
    if request.method not in {'GET','HEAD','OPTIONS'} and request.headers.get('x-quantgraph-request') != '1':
        raise HTTPException(403, '需要同源操作标记')


def require_admin(request: Request):
    same_origin(request)
    token = request.cookies.get(COOKIE, '')
    digest = hashlib.sha256(token.encode()).hexdigest()
    with request.app.state.catalog.connect() as con:
        row = con.execute('SELECT actor FROM admin_sessions WHERE token_hash=? AND expires>?', (digest,time.time())).fetchone()
    if not row:
        raise HTTPException(401, '请登录管理后台')
    return row[0]


def install_admin(app, catalog, *, password=None):
    password = password or os.getenv('QUANTGRAPH_ADMIN_PASSWORD')
    if password and len(password)<16:
        raise ValueError('Admin password must contain at least 16 characters')
    salt = secrets.token_bytes(32)
    expected = hashlib.pbkdf2_hmac('sha256',password.encode(),salt,200000) if password else None
    with catalog.connect() as con:
        con.executescript('''CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,actor TEXT,expires REAL);
            CREATE TABLE IF NOT EXISTS admin_attempts(client TEXT,window INTEGER,count INTEGER,PRIMARY KEY(client,window));''')
    router = APIRouter(prefix='/v1/admin')

    @router.post('/session')
    def login(body: Login, request: Request, response: Response):
        same_origin(request)
        window = int(time.time()//300)
        client = request.client.host if request.client else 'local'
        with catalog.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('DELETE FROM admin_attempts WHERE window<?',(window-1,))
            row = con.execute('SELECT count FROM admin_attempts WHERE client=? AND window=?',(client,window)).fetchone()
            if row and row[0]>=10:
                raise HTTPException(429,'登录尝试过多，请稍后再试')
            con.execute('INSERT INTO admin_attempts VALUES(?,?,1) ON CONFLICT(client,window) DO UPDATE SET count=count+1',(client,window))
        supplied = hashlib.pbkdf2_hmac('sha256',body.password.encode(),salt,200000)
        if expected is None or not hmac.compare_digest(supplied,expected):
            raise HTTPException(401,'管理登录不可用或凭证不正确')
        token=secrets.token_urlsafe(48)
        with catalog.connect() as con:
            con.execute('DELETE FROM admin_sessions WHERE expires<?',(time.time(),))
            con.execute('INSERT INTO admin_sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),'administrator',time.time()+28800))
        response.set_cookie(COOKIE,token,max_age=28800,httponly=True,samesite='strict',secure=request.url.scheme=='https',path='/')
        return {'authenticated':True}

    @router.get('/session')
    def session(actor=Depends(require_admin)):
        return {'authenticated':True,'actor':actor}

    @router.delete('/session')
    def logout(request: Request,response: Response,actor=Depends(require_admin)):
        with catalog.connect() as con:
            con.execute('DELETE FROM admin_sessions WHERE token_hash=?',(hashlib.sha256(request.cookies.get(COOKIE,'').encode()).hexdigest(),))
        response.delete_cookie(COOKIE,path='/')
        return {'authenticated':False}

    @router.get('/catalog')
    def browse(q: str='',kind: str='strategy',page: int=Query(1,ge=1),actor=Depends(require_admin)):
        return catalog.search(q=q,kind=kind,page=page,admin=True)

    @router.patch('/catalog')
    def edit(body: Edit,actor=Depends(require_admin)):
        try:
            return catalog.edit(body.ids,body.patch,actor)
        except (ValueError,KeyError):
            raise HTTPException(422,'条目或编辑字段无效')

    @router.get('/entities/{eid}')
    def entity(eid: str,actor=Depends(require_admin)):
        try:
            return catalog.get(eid,admin=True)
        except KeyError:
            raise HTTPException(404,'条目不存在')

    @router.get('/relations/{eid}')
    def relations(eid: str,offset: int=Query(0,ge=0),actor=Depends(require_admin)):
        try:
            return catalog.relations(eid,offset=offset,admin=True)
        except KeyError:
            raise HTTPException(404,'条目不存在')

    @router.patch('/relations/{rid}')
    def edit_relation(rid: str,body: dict,actor=Depends(require_admin)):
        try:
            return catalog.edit_relation(rid,body,actor)
        except (ValueError,KeyError):
            raise HTTPException(422,'关系审核字段无效')

    @router.post('/merge-suggestions')
    def suggest(body: dict,actor=Depends(require_admin)):
        if set(body)!={'left','right','reason'} or body['left']==body['right'] or not isinstance(body['reason'],str) or len(body['reason'])>2000:
            raise HTTPException(422,'需要两个不同条目和合并依据')
        try:
            catalog.get(body['left'],admin=True);catalog.get(body['right'],admin=True)
        except KeyError:
            raise HTTPException(404,'条目不存在')
        sid=content_hash(body)
        with catalog.connect() as con:
            con.execute('INSERT OR IGNORE INTO catalog_suggestions VALUES(?,?,?,?)',(sid,stable_json(body),'PENDING',now()))
            con.execute('INSERT INTO catalog_audit(created_at,actor,action,entity_id,before_json,after_json) VALUES(?,?,?,?,?,?)',
                (now(),actor,'SUGGEST_MERGE',sid,'{}',stable_json(body)))
        return {'suggestion_id':sid,'status':'PENDING','notice':'建议不会自动合并定义或改写研究引用。'}

    @router.get('/merge-suggestions')
    def suggestions(actor=Depends(require_admin)):
        with catalog.connect() as con:
            return {'items':[dict(r) for r in con.execute('SELECT * FROM catalog_suggestions ORDER BY created_at DESC LIMIT 100')]}

    @router.get('/imports')
    def imports(actor=Depends(require_admin)):
        return catalog.reconcile()

    @router.post('/imports/retry')
    def retry(actor=Depends(require_admin)):
        result=catalog.sync_ingestion(retry=True)
        with catalog.connect() as con:
            con.execute('INSERT INTO catalog_audit(created_at,actor,action,entity_id,before_json,after_json) VALUES(?,?,?,?,?,?)',
                (now(),actor,'RETRY_PROJECTION','ingestion','{}',stable_json(result)))
        return result

    @router.post('/imports/grokbot')
    def ingest(body: dict,actor=Depends(require_admin)):
        from quantgraph.models.ingestion import IngestBatch
        if catalog.ingestion is None:
            raise HTTPException(503,'尚未配置持久化采集数据库')
        try:
            batch=IngestBatch.model_validate(body)
            result=catalog.ingestion.ingest(batch,stable_json(body).encode(),actor)
            result['catalog']=catalog.sync_ingestion()
            return result
        except (ValueError,KeyError):
            raise HTTPException(422,'导入格式或批次无效，原始数据未覆盖')

    @router.get('/audit')
    def audit(actor=Depends(require_admin)):
        return {'items':catalog.audit()}

    app.include_router(router)
    app.state.require_admin=require_admin

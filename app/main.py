from contextlib import asynccontextmanager
from datetime import date
import csv
import io
import json
import logging
import re
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import select, func, or_, delete, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from pydantic import ValidationError
from .config import settings, ROOT
from .branding import PRODUCT_TITLE
from .db import engine, get_db, today, utcnow
from .models import Store, UserStore, User, LoginSession, MODULES, AuditLog, Finding, DailyReport, AppMetadata
from .schemas import StoreInput, LoginInput, PasswordInput, UserInput, UserUpdate, ResetPasswordInput, UpdateInput, ActionInput, ReviewInput, ReportInput, BatchUserInput, StoreRoleInput, StoreRole
from .security import get_user, authenticate, set_session, clear_cookies, user_info, require_full, require_module, verify_password, hash_password, ROLES
from .services import serialize, plain, audit, readable_query, get_record, create_record, update_record, act_record, check_version
from .analytics import dashboard, source_revision, build_snapshot, external_payload, rules_config
from .reports import generate_report
from .scheduler import ReportScheduler
from .tenancy import accessible_stores, single_store, attach_scope
from .user_access_service import change_access
import os
from typing import get_args

log = logging.getLogger(__name__)
scheduler = ReportScheduler()
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_.-]{3,40}$')
# One embedded worker per process, and only for a verified local preview.
_EMBEDDED_WORKER = None
EMBEDDED_STOP_SECONDS = 20


def _embedded_runtime_worker():
    """Start the in-process Runtime worker for a verified local preview only.

    The worker module (and with it the whole Runtime) is imported only after the
    local preview configured this process and its on-disk marker is verified, so
    a normal Web deployment never embeds a worker. The worker never prepares,
    migrates or initializes the database: it refuses an unprepared instance.
    """
    global _EMBEDDED_WORKER
    if os.environ.get('HUAKANGOS_LOCAL_PREVIEW') != '1':
        return None
    if not settings.assistant_runtime_enabled:
        return None
    if _EMBEDDED_WORKER is not None:
        return _EMBEDDED_WORKER
    from pathlib import Path
    from .local_preview import marker_from_disk
    root = os.environ.get('HUAKANGOS_PREVIEW_ROOT') or ''
    if not root:
        raise RuntimeError('本地预览缺少预览目录标记，不能嵌入 Runtime worker')
    marker_from_disk(Path(root))
    from .assistant_worker import Worker, verify_instance
    verify_instance()
    _EMBEDDED_WORKER = Worker(lease_owner='preview-embed').start()
    log.info('Embedded assistant Runtime worker started for the local preview')
    return _EMBEDDED_WORKER


async def _stop_embedded_runtime_worker():
    global _EMBEDDED_WORKER
    worker, _EMBEDDED_WORKER = _EMBEDDED_WORKER, None
    if worker is not None:
        await worker.stop(timeout=EMBEDDED_STOP_SECONDS)
        log.info('Embedded assistant Runtime worker stopped')


@asynccontextmanager
async def lifespan(app):
    from sqlalchemy import inspect
    if not inspect(engine).has_table('users'):
        raise RuntimeError('数据库尚未初始化。请先运行 python -m app.cli init')
    scheduler.start()
    _embedded_runtime_worker()
    yield
    await _stop_embedded_runtime_worker()
    scheduler.stop()


app = FastAPI(title=PRODUCT_TITLE+' 门店运营系统',version='0.4.0-dev',lifespan=lifespan,
              docs_url='/docs' if settings.environment!='production' else None,redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=list(settings.allowed_hosts))


@app.middleware('http')
async def safety_headers(request: Request, call_next):
    if request.url.path.startswith('/api/') and request.method not in {'GET','HEAD','OPTIONS'}:
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail':'不允许跨站请求'},status_code=403)
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'请求来源不匹配，请使用同一个地址访问'},status_code=403)
        is_vehicle_import = bool(re.fullmatch(r'/api/vehicle-imports/orders/[1-9][0-9]*/batches',request.url.path))
        is_assistant_preview = request.url.path == '/api/business-assistant/file-preview' and request.method == 'POST'
        is_upload = (request.url.path.startswith('/api/flow/cases/') and request.url.path.endswith('/files')) or is_vehicle_import or is_assistant_preview or request.url.path == '/api/branding/photo' and request.method == 'POST'
        is_opening = request.url.path == '/api/opening-import/preflight'
        limit = 21 * 1024 * 1024 if is_assistant_preview else 256 * 1024 if is_vehicle_import else 12 * 1024 * 1024 if is_upload else 1_000_000 if is_opening else 100_000
        accepted = 'multipart/form-data' if is_upload else 'application/json'
        if not request.headers.get('content-type','').lower().startswith(accepted):
            return JSONResponse({'detail':'提交格式不正确，请从对应页面重新操作'},status_code=415)
        try: size = int(request.headers.get('content-length','0'))
        except ValueError: return JSONResponse({'detail':'无效请求长度'},status_code=400)
        if size > limit:
            return JSONResponse({'detail':'请求过大'},status_code=413)
        chunks, actual_size = [], 0
        async for chunk in request.stream():
            actual_size += len(chunk)
            if actual_size > limit:
                return JSONResponse({'detail':'请求过大'},status_code=413)
            chunks.append(chunk)
        request._body = b''.join(chunks)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.url.path != '/docs' and 'Content-Security-Policy' not in response.headers:
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    if settings.environment == 'production':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response


def validation_response(exc):
    errors = [{'field':'.'.join(str(x) for x in error['loc']),'message':error['msg']} for error in exc.errors()]
    names={'username':'账号','password':'密码','new_password':'新密码','current_password':'当前密码','business_date':'业务日期','amount':'金额','amount_cents':'金额','version':'记录版本','reason':'原因','name':'名称','role':'岗位','vin':'车架号','store_ids':'授权门店'}
    fields=list(dict.fromkeys(names.get(e['field'].split('.')[-1],'填写内容') for e in errors))
    detail='请检查'+ '、'.join(fields[:4])+'，确认必填项、长度、金额和日期格式正确。'
    return JSONResponse({'detail':detail,'errors':errors},status_code=422)


@app.exception_handler(ValidationError)
async def validation_error(request,exc): return validation_response(exc)

@app.exception_handler(RequestValidationError)
async def request_validation_error(request,exc): return validation_response(exc)


def note_refusal(request,status_code,detail):
    """记下系统自己拒绝的一步，作为评审申请的唯一依据。

    只有真实返回的 403（以及带权限/额度语义的 422）才会被记录；记录失败绝不影响原响应。
    """
    try:
        user_id = getattr(request.state,'user_id',None)
        store_id = getattr(request.state,'store_id',None)
        if not user_id or not store_id: return None
        from .db import SessionLocal
        from .escalation_service import record_refusal
        from .security import User
        with SessionLocal() as db:
            user = db.get(User,user_id)
            if not user or not user.active: return None
            class _Principal:
                id = user.id
                role = getattr(request.state,'role',user.role) or user.role
                account_role = user.role
                def __getattr__(self,name): return getattr(user,name)
            row = record_refusal(db, store_id=store_id, user=_Principal(), method=request.method,
                                 path=request.url.path, status_code=status_code, message=detail)
            refusal = None if row is None else {
                'id': row.id, 'category': row.category,
                'can_escalate': row.category in ('authority', 'amount'),
            }
            db.commit()
            return refusal
    except Exception as exc:                       # evidence must never break the response
        log.warning('Refusal evidence not recorded (%s)',type(exc).__name__)
        return None


@app.exception_handler(StarletteHTTPException)
async def http_error(request,exc):
    refusal = note_refusal(request,exc.status_code,exc.detail) if exc.status_code in (403,422) else None
    content = {'detail':exc.detail}
    if refusal is not None:
        content['refusal'] = refusal
    return JSONResponse(content,status_code=exc.status_code,headers=getattr(exc,'headers',None))

@app.exception_handler(IntegrityError)
async def integrity_error(request,exc):
    return JSONResponse({'detail':'编号、车架号或保单号重复、车辆已被占用，或关联关系不满足约束。请刷新核对，未保存本次修改。'},status_code=409)

@app.exception_handler(StaleDataError)
async def stale_error(request,exc):
    return JSONResponse({'detail':'数据已被其他人修改；未覆盖，请刷新重试。'},status_code=409)

@app.exception_handler(OperationalError)
async def operational_error(request,exc):
    log.warning('Database operation failed (%s)',type(exc).__name__)
    return JSONResponse({'detail':'数据库暂时忙或连接异常，请刷新核对后重试，避免重复录单。'},status_code=503)


@app.exception_handler(Exception)
async def unexpected_error(request,exc):
    log.error('Unexpected request failure (%s)',type(exc).__name__)
    return JSONResponse({'detail':'处理失败。请刷新核对数据是否已保存，再重试；服务器日志仅记录错误类型。'},status_code=500)


@app.get('/api/health')
def health(db=Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status':'ok','version':'0.4.0-dev','product':'huakangos','release':os.getenv('HUAKANGOS_RELEASE_SHA') or os.getenv('DEALER_RELEASE_SHA','local')}


@app.post('/api/auth/login')
def login(body: LoginInput,request: Request,response: Response,db=Depends(get_db)):
    if request.headers.get('X-App-Request') != '1':
        raise HTTPException(403,'请求校验失败')
    user = authenticate(db,body.username,body.password,request.client.host if request.client else 'unknown')
    audit(db,user.id,'login','users',user.id,reason='登录成功')
    set_session(db,user,response)
    return user_info(attach_scope(request, db, user))


@app.get('/api/auth/me')
def me(user=Depends(get_user)): return user_info(user)


@app.post('/api/auth/logout')
def logout(request: Request,response: Response,db=Depends(get_db),user=Depends(get_user)):
    db.execute(delete(LoginSession).where(LoginSession.id==request.state.session_hash)); db.commit()
    clear_cookies(response)
    return {'ok':True}


@app.post('/api/auth/password')
def change_password(body: PasswordInput,response: Response,db=Depends(get_db),user=Depends(get_user)):
    if not verify_password(body.current_password,user.password_hash): raise HTTPException(400,'当前密码不正确')
    if body.current_password == body.new_password: raise HTTPException(422,'新密码不能与旧密码相同')
    account = db.scalar(select(User).where(User.id == user.id))
    account.password_hash = hash_password(body.new_password)
    account.must_change_password = False
    db.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
    audit(db,user.id,'change_password','users',user.id,reason='修改密码并撤销全部登录会话')
    db.commit(); clear_cookies(response)
    return {'ok':True,'message':'密码已修改，请重新登录'}


def admin(user):
    if getattr(user, 'account_role', user.role) != 'admin': raise HTTPException(403,'仅系统管理员可以管理账号')


@app.get('/api/users')
def users(db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    return {'items':[account_info(db,u) for u in db.scalars(select(User).order_by(User.id))],'roles':ROLES,
            'stores':[plain(s) for s in db.scalars(select(Store).order_by(Store.id))]}


@app.post('/api/users',status_code=201)
def add_user(body: UserInput,db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    new = User(username=body.username.lower(),display_name=body.display_name,role=body.role,
               password_hash=hash_password(body.password),must_change_password=True,can_group_summary=body.can_group_summary)
    db.add(new); db.flush()
    assign_stores(db, new, body.store_ids or None, body.store_roles)
    audit(db,user.id,'create_user','users',new.id,after=account_info(db,new))
    db.commit()
    return account_info(db,new)


def batch_row_error(number,message):
    raise HTTPException(422,'第 %d 行：%s' % (number,message))


@app.post('/api/users/batch',status_code=201)
def add_users_batch(body: BatchUserInput,db=Depends(get_db),user=Depends(get_user)):
    """Several staff accounts in one transaction; only a system administrator may call this.

    Every row is checked before the first write, so a wrong line never leaves half the paste
    created. Each account keeps the single-path rules: store role, audit record and
    "first login must change password". System administrator accounts are excluded on
    purpose and still go through the single form.
    """
    admin(user)
    store = db.get(Store,body.store_id)
    if not store or not store.active:
        raise HTTPException(422,'指定门店不存在或已停用，请刷新门店列表后重试')
    allowed = set(get_args(StoreRole))
    prepared,seen = [],set()
    for number,row in enumerate(body.rows,start=1):
        username = row.username.strip().lower()
        if not USERNAME_PATTERN.fullmatch(username):
            batch_row_error(number,'登录账号只能填 3–40 位字母、数字、下划线、点或短横线')
        if username in seen:
            batch_row_error(number,'登录账号 %s 在本次粘贴里重复了' % username)
        seen.add(username)
        display_name = row.display_name.strip()
        if not display_name:
            batch_row_error(number,'员工姓名不能为空')
        role = row.role.strip()
        if role not in allowed:
            batch_row_error(number,'岗位“%s”不能批量建立；系统管理员账号请用“新增员工”单独建立' % row.role)
        prepared.append((username,display_name,role))
    taken = set(db.scalars(select(User.username).where(User.username.in_(list(seen)))))
    for number,(username,_,_) in enumerate(prepared,start=1):
        if username in taken:
            batch_row_error(number,'登录账号 %s 已经存在' % username)
    created = []
    for username,display_name,role in prepared:
        account = User(username=username,display_name=display_name,role=role,
                       password_hash=hash_password(body.password),must_change_password=True,
                       can_group_summary=False)
        db.add(account); db.flush()
        assign_stores(db,account,[store.id],[StoreRoleInput(store_id=store.id,role=role)])
        audit(db,user.id,'create_user','users',account.id,after=account_info(db,account))
        created.append(account_info(db,account))
    db.commit()
    return {'created':created,'count':len(created),'store':{'id':store.id,'name':store.name}}


@app.put('/api/users/{user_id}')
def edit_user(user_id: int,body: UserUpdate,db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    return change_access(db,user,user_id,body,account_info,assign_stores)


@app.post('/api/users/{user_id}/password')
def reset_password(user_id: int,body: ResetPasswordInput,db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    target = db.get(User,user_id)
    if not target: raise HTTPException(404,'用户不存在')
    if target.id == user.id: raise HTTPException(409,'请使用“修改我的密码”')
    target.password_hash = hash_password(body.password)
    target.must_change_password = True
    db.execute(delete(LoginSession).where(LoginSession.user_id==target.id))
    audit(db,user.id,'reset_password','users',target.id,reason=body.reason)
    if settings.assistant_runtime_enabled:
        from .assistant_runtime_access_signals import emit_user_security_changed
        record = next(row for row in db.new if type(row) is AuditLog and row.actor_id == user.id
            and row.action == 'reset_password' and row.entity_type == 'users' and row.entity_id == target.id)
        emit_user_security_changed(db, record)
    db.commit(); return {'ok':True}


def filtered_query(user,module,q='',state='',date_from=None,date_to=None):
    statement = readable_query(user,module)
    model = MODULES[module]
    if state:
        if state not in {'draft','submitted','approved','rejected','void'}: raise HTTPException(422,'状态无效')
        statement = statement.where(model.approval_state==state)
    if date_from and date_to and date_from>date_to: raise HTTPException(422,'开始日期不能晚于结束日期')
    if date_from: statement = statement.where(model.business_date>=date_from)
    if date_to: statement = statement.where(model.business_date<=date_to)
    if q:
        columns = {'vehicles':['doc_no','vin','brand','model','location'], 'sales':['doc_no','customer_name','salesperson'],
            'repairs':['doc_no','plate_number','customer_name','service_advisor'],
            'policies':['doc_no','policy_number','plate_number','customer_name','insurer'],
            'cash':['doc_no','voucher_no','account','counterparty']}[module]
        escaped = q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        predicates = [getattr(model,name).ilike('%'+escaped+'%',escape='\\') for name in columns]
        if q.isdigit(): predicates.append(model.id==int(q))
        statement = statement.where(or_(*predicates))
    return statement


@app.get('/api/records/{module}')
def list_records(module: str,q: str=Query('',max_length=100),state: str='',date_from:date|None=None,date_to:date|None=None,
                 page: int=Query(1,ge=1),page_size: int=Query(30,ge=1,le=200),db=Depends(get_db),user=Depends(get_user)):
    statement = filtered_query(user,module,q,state,date_from,date_to)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(MODULES[module].id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[serialize(r,module,user,db) for r in rows],'total':total,'page':page,'page_size':page_size}


@app.get('/api/lookup/{module}')
def lookup(module: str,q: str=Query('',max_length=100),db=Depends(get_db),user=Depends(get_user)):
    statement = filtered_query(user,module,q,'approved')
    rows = list(db.scalars(statement.order_by(MODULES[module].id.desc()).limit(20)))
    def label(r):
        if module=='vehicles': return f'{r.id} · {r.vin} · {r.model}'
        if module=='policies': return f'{r.id} · {r.doc_no} · {r.policy_number}'
        return f'{r.id} · {r.doc_no}'
    return {'items':[{'id':r.id,'label':label(r)} for r in rows],'limit':20}


@app.get('/api/records/{module}/{record_id}')
def detail(module: str,record_id: int,db=Depends(get_db),user=Depends(get_user)):
    return serialize(get_record(db,user,module,record_id),module,user,db)


def guard_legacy_write(module):
    if module in {'vehicles','sales','repairs','policies'} and not settings.legacy_business_write:
        raise HTTPException(409,'原版本业务单据仅保留查询；新业务请从流程栏目建立，未完成旧单请先由管理员制定接续方案')


@app.post('/api/records/{module}',status_code=201)
def add_record(module: str,body:dict,db=Depends(get_db),user=Depends(get_user)):
    guard_legacy_write(module)
    return serialize(create_record(db,user,module,body),module,user,db)


@app.put('/api/records/{module}/{record_id}')
def edit_record(module:str,record_id:int,body:UpdateInput,db=Depends(get_db),user=Depends(get_user)):
    guard_legacy_write(module)
    return serialize(update_record(db,user,module,record_id,body.version,body.data),module,user,db)


@app.post('/api/records/{module}/{record_id}/actions/{action}')
def action(module:str,record_id:int,action:str,body:ActionInput,db=Depends(get_db),user=Depends(get_user)):
    guard_legacy_write(module)
    return serialize(act_record(db,user,module,record_id,action,body),module,user,db)


def safe_csv(value):
    text = '' if value is None else str(value)
    # Prevent spreadsheet-formula execution when a human opens an exported CSV.
    return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else text


@app.get('/api/export/{module}')
def export_csv(module:str,q:str=Query('',max_length=100),state:str='',date_from:date|None=None,date_to:date|None=None,
               db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    rows = list(db.scalars(filtered_query(user,module,q,state,date_from,date_to).order_by(MODULES[module].id).limit(10001)))
    if len(rows)>10000: raise HTTPException(422,'导出超过 10,000 行，请缩小日期范围；未提供截断文件')
    buffer = io.StringIO(newline='')
    if rows:
        data = [serialize(r,module,user,db) for r in rows]
        fields = [k for k in data[0] if not k.endswith('_cents')]
        writer = csv.DictWriter(buffer,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        for row in data: writer.writerow({k:safe_csv(v) for k,v in row.items() if k in fields})
    else: buffer.write('无符合条件的记录\r\n')
    audit(db,user.id,'export',module,None,reason=f'导出 {len(rows)} 行')
    db.commit()
    # Export is not a business change; source_revision() deliberately excludes this action below.
    return Response(content=('\ufeff'+buffer.getvalue()).encode('utf-8'),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="{module}-{today()}.csv"'})


@app.get('/api/dashboard')
def get_dashboard(end:date|None=None,days:int=Query(30,ge=1,le=366),db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    day = end or today()
    if day>today(): raise HTTPException(422,'看板结束日期不能晚于今天')
    result = dashboard(db,day,days)
    from .analytics import load_data, daily_metrics
    ids = [i for i in db.info.get('store_scope',[]) if i]
    result['store_ids'] = ids
    result['store_name'] = next((s.name for s in accessible_stores(db,user) if s.id==db.info.get('write_store')), '已授权门店汇总')
    result['by_store'] = []
    original = dict(db.info)
    from .tenancy import set_scope
    try:
        for store in accessible_stores(db,user):
            if store.id not in ids: continue
            set_scope(db,[store.id],store.id)
            result['by_store'].append({'id':store.id,'name':store.name,'metrics':daily_metrics(load_data(db,day),day)})
    finally: db.info.clear(); db.info.update(original)
    return result


def report_stale(db,row):
    original=dict(db.info)
    try:
        from .tenancy import set_scope
        set_scope(db,[row.store_id])
        return row.source_revision < source_revision(db)
    finally:
        db.info.clear();db.info.update(original)


@app.get('/api/reports')
def reports(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    rows = db.scalars(select(DailyReport).order_by(DailyReport.id.desc()).offset((page-1)*30).limit(30))
    return {'items':[{'id':r.id,'store_id':r.store_id,'business_date':r.business_date.isoformat(),'generated_at':r.generated_at.isoformat()+'Z',
        'ai_status':r.ai_status,'finding_count':len(r.finding_ids),'source_revision':r.source_revision,
        'stale':report_stale(db,r),'provisional':r.snapshot.get('provisional',False)} for r in rows],
        'page':page,'total':db.scalar(select(func.count()).select_from(DailyReport))}


@app.get('/api/reports/{report_id}')
def report_detail(report_id:int,db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    row = db.get(DailyReport,report_id)
    if not row: raise HTTPException(404,'日报不存在')
    result = plain(row)
    result['stale'] = report_stale(db,row)
    return result


@app.post('/api/reports/preview')
def preview_report(body:ReportInput,db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    single_store(db)
    return external_payload(build_snapshot(db,body.business_date))


@app.post('/api/reports/generate')
def make_report(body:ReportInput,db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    return {'id':generate_report(body.business_date,body.use_ai,body.retry_ai,user.id,store_id=single_store(db))}


@app.get('/api/findings')
def findings(status:str='',page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    stmt = select(Finding)
    if status:
        if status not in {'open','reviewing','confirmed','dismissed','resolved'}: raise HTTPException(422,'复核状态无效')
        stmt = stmt.where(Finding.review_status==status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Finding.last_seen.desc(),Finding.id.desc()).offset((page-1)*30).limit(30))
    return {'items':[plain(r) for r in rows],'total':total,'page':page}


@app.post('/api/findings/{finding_id}/review')
def review(finding_id:int,body:ReviewInput,db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    row = db.get(Finding,finding_id)
    if not row: raise HTTPException(404,'复核项不存在')
    check_version(row,body.version)
    before = plain(row)
    row.review_status,row.review_note = body.status,body.note
    row.reviewed_by,row.reviewed_at = user.id,utcnow()
    db.flush(); audit(db,user.id,'review','findings',row.id,before,plain(row),body.note)
    db.commit(); return plain(row)


@app.get('/api/audit')
def audit_list(page:int=Query(1,ge=1),entity_type:str='',entity_id:int|None=None,db=Depends(get_db),user=Depends(get_user)):
    if user.role not in {'admin','manager','auditor'}: raise HTTPException(403,'没有查看全店审计日志的权限')
    stmt = select(AuditLog)
    if user.role != 'admin': stmt = stmt.where(AuditLog.entity_type.notin_(['users','stores','feedback','maintenance']))
    if entity_type: stmt = stmt.where(AuditLog.entity_type==entity_type)
    if entity_id is not None: stmt = stmt.where(AuditLog.entity_id==entity_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = list(db.scalars(stmt.order_by(AuditLog.id.desc()).offset((page-1)*30).limit(30)))
    labels = {u.id:u.display_name for u in db.scalars(select(User))}
    return {'items':[dict(plain(row),actor_name=labels.get(row.actor_id,'系统')) for row in rows],'total':total,'page':page}


@app.get('/api/settings')
def public_settings(db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    return {'version':'0.3.0','timezone':settings.timezone,'today':today().isoformat(),'environment':settings.environment,
        'scheduler_enabled':settings.scheduler_enabled,'daily_time':f'{settings.report_hour:02d}:{settings.report_minute:02d}',
        'multi_store':True,'active_store_id':db.info.get('write_store'),
        'catchup_days':settings.catchup_days,'ai_allowed':settings.allow_ai,'ai_key_configured':bool(settings.deepseek_key),
        'ai_model':settings.deepseek_model,'rules':rules_config(),
        'demo_database':bool(db.get(AppMetadata,'demo') and db.get(AppMetadata,'demo').value.get('enabled'))}




def account_info(db, target):
    result = user_info(target)
    result['access_version'] = target.access_version
    stores = accessible_stores(db,target)
    memberships = list(db.scalars(select(UserStore).where(UserStore.user_id==target.id).order_by(UserStore.store_id)))
    result['store_ids'] = [m.store_id for m in memberships]
    result['store_roles'] = [{'store_id':m.store_id,'role':m.role or target.role,'legacy_fallback':m.role is None} for m in memberships]
    result['stores'] = [{'id':s.id,'name':s.name,'code':s.code} for s in stores]
    return result


def assign_stores(db, target, ids, store_roles=None):
    existing = {m.store_id:m.role for m in db.scalars(select(UserStore).where(UserStore.user_id==target.id))}
    explicit = None if store_roles is None else {m.store_id:m.role for m in store_roles}
    if explicit is not None:
        if len(explicit) != len(store_roles):
            raise HTTPException(422, '同一门店不能重复分配岗位')
        if target.role == 'admin' and explicit:
            raise HTTPException(422, '系统管理员使用全局权限；门店岗位只能分配给普通账号')
        if ids is not None and set(ids) != set(explicit):
            raise HTTPException(422, '门店列表与门店岗位必须完全对应')
    ids = sorted(set(ids if ids is not None else (explicit or {})))
    if target.role != 'admin' and not ids:
        raise HTTPException(422, '非管理员账号至少分配一家门店')
    if ids and db.scalar(select(func.count()).select_from(Store).where(Store.id.in_(ids),Store.active.is_(True))) != len(ids):
        raise HTTPException(422, '指定门店不存在或已停用')
    db.execute(delete(UserStore).where(UserStore.user_id==target.id))
    db.add_all([UserStore(user_id=target.id,store_id=i,role=explicit[i] if explicit is not None else existing.get(i)) for i in ids])
    db.flush()


@app.get('/api/stores')
def stores(db=Depends(get_db),user=Depends(get_user)):
    rows = list(db.scalars(select(Store).order_by(Store.id))) if getattr(user,'account_role',user.role)=='admin' else accessible_stores(db,user)
    return {'items':[plain(row) for row in rows], 'active_store_id':db.info.get('write_store')}


@app.post('/api/stores',status_code=201)
def add_store(body:StoreInput,db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    row = Store(**body.model_dump()); db.add(row); db.flush()
    audit(db,user.id,'create_store','stores',row.id,after=plain(row))
    db.commit(); return plain(row)


@app.put('/api/stores/{store_id}')
def edit_store(store_id:int,body:StoreInput,db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    row = db.get(Store,store_id)
    if not row: raise HTTPException(404,'门店不存在')
    if not body.active and row.active and db.scalar(select(func.count()).select_from(Store).where(Store.active.is_(True)))<=1:
        raise HTTPException(409,'不能停用最后一家可用门店')
    before=plain(row)
    for k,v in body.model_dump().items(): setattr(row,k,v)
    audit(db,user.id,'update_store','stores',row.id,before,plain(row))
    if settings.assistant_runtime_enabled and before['active'] != row.active:
        from .assistant_runtime_access_signals import emit_store_access_changed
        record = next(value for value in db.new if type(value) is AuditLog and value.actor_id == user.id
            and value.action == 'update_store' and value.entity_type == 'stores' and value.entity_id == row.id)
        emit_store_access_changed(db, record)
    db.commit(); return plain(row)


from .flow_api import router as flow_router
app.include_router(flow_router)
from .escalation_api import router as escalation_router
app.include_router(escalation_router)
from .group_api import router as group_router
app.include_router(group_router)
from .transfer_api import router as transfer_router
app.include_router(transfer_router)
from .transfer_exception_api import router as transfer_exception_router
app.include_router(transfer_exception_router)
from .file_security_api import router as file_security_router
app.include_router(file_security_router)
from .master_api import router as master_router
app.include_router(master_router)
from .procurement_api import router as procurement_router
app.include_router(procurement_router)
from .vehicle_transfer_api import router as vehicle_transfer_router
app.include_router(vehicle_transfer_router)
from .stock_report_api import router as stock_report_router
app.include_router(stock_report_router)
from .reconciliation_api import router as reconciliation_router
app.include_router(reconciliation_router)
from .retail_api import router as retail_router
app.include_router(retail_router)
from .vehicle_procurement_api import router as vehicle_procurement_router
app.include_router(vehicle_procurement_router)
from .vehicle_operations_api import router as vehicle_operations_router
app.include_router(vehicle_operations_router)
from .aftercare_api import router as aftercare_router
app.include_router(aftercare_router)
from .business_finance_api import router as business_finance_router
app.include_router(business_finance_router)
from .customer_choice_api import router as customer_choice_router
app.include_router(customer_choice_router)
from .group_benefits_api import router as group_benefits_router
app.include_router(group_benefits_router)
from .repair_api import router as repair_router
app.include_router(repair_router)
from .customer_service_api import router as customer_service_router
app.include_router(customer_service_router)
from .invoice_api import router as invoice_router
app.include_router(invoice_router)
from .vehicle_income_api import router as vehicle_income_router
app.include_router(vehicle_income_router)
from .rework_extension_api import router as rework_extension_router
app.include_router(rework_extension_router)
from .member_pricing_api import router as member_pricing_router
app.include_router(member_pricing_router)
from .repair_package_api import router as repair_package_router
app.include_router(repair_package_router)
from .membership_api import router as membership_router
app.include_router(membership_router)
from .warehouse_api import router as warehouse_router
app.include_router(warehouse_router)
from .service_intake_api import router as service_intake_router
app.include_router(service_intake_router)


@app.get('/',include_in_schema=False)
def home(): return FileResponse(ROOT/'web'/'index.html')


app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')

from .opening_import_api import router as opening_import_router
app.include_router(opening_import_router)
from .recharge_bundle_api import router as recharge_bundle_router
app.include_router(recharge_bundle_router)
from .claims_api import router as claims_router
app.include_router(claims_router)
from .vehicle_imports_api import router as vehicle_imports_router
app.include_router(vehicle_imports_router)
from .retail_bundle_api import router as retail_bundle_router
app.include_router(retail_bundle_router)

from .vehicle_catalog_api import router as vehicle_catalog_router
app.include_router(vehicle_catalog_router)

from .inventory_reports_api import router as inventory_reports_router
app.include_router(inventory_reports_router)
from .service_orders_api import router as service_orders_router
app.include_router(service_orders_router)

from .sales_quote_api import router as sales_quote_router
app.include_router(sales_quote_router)

from .insurance_api import router as insurance_router
app.include_router(insurance_router)

from .addon_api import router as addon_router
app.include_router(addon_router)

from .repair_material_api import router as repair_material_router
app.include_router(repair_material_router)
from .visit_activity_api import router as visit_activity_router
app.include_router(visit_activity_router)
from .material_value_api import router as material_value_router
app.include_router(material_value_router)
from .business_entity_api import router as business_entity_router
app.include_router(business_entity_router)

from .retail_group_api import router as retail_group_router
from .observation_corrections_api import router as observation_corrections_router
from .transfer_goods_recovery_api import router as transfer_goods_recovery_router
app.include_router(retail_group_router)
app.include_router(observation_corrections_router)
app.include_router(transfer_goods_recovery_router)

# Registration does not enable bootstrap: the handler additionally requires an
# opted-in local environment, a real loopback peer, a marked isolated database
# and a short-lived one-time instance ticket. It never adopts a business DB.
from .local_preview_api import router as local_preview_router
app.include_router(local_preview_router)

from .gate_visit_api import router as gate_visit_router
app.include_router(gate_visit_router)

from .vehicle_transport_api import router as vehicle_transport_router
app.include_router(vehicle_transport_router)

from .dossier_grant_api import router as dossier_grant_router
app.include_router(dossier_grant_router)

from .dictionary_api import router as dictionary_router
from .parameter_api import router as parameter_router
app.include_router(dictionary_router)
app.include_router(parameter_router)

from .branding_api import router as branding_router
app.include_router(branding_router)

from .business_assistant_api import router as business_assistant_router
app.include_router(business_assistant_router)
from .assistant_runtime_api import router as assistant_runtime_router
app.include_router(assistant_runtime_router)

from .workflow_guides_api import router as workflow_guides_router
app.include_router(workflow_guides_router)

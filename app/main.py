from contextlib import asynccontextmanager
from datetime import date
import csv
import io
import json
import logging
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select, func, or_, delete, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from pydantic import ValidationError
from .config import settings, ROOT
from .db import engine, get_db, start_of_today_utc, today, utcnow
from .models import Store, UserStore, Feedback, MaintenanceEvent, Deployment, User, LoginSession, MODULES, AuditLog, Finding, DailyReport, AppMetadata
from .schemas import StoreInput, FeedbackInput, LoginInput, PasswordInput, UserInput, UserUpdate, ResetPasswordInput, UpdateInput, ActionInput, ReviewInput, ReportInput, EntryDraftInput
from .security import get_user, authenticate, set_session, clear_cookies, user_info, require_full, require_module, verify_password, hash_password, ROLES
from .services import serialize, plain, audit, readable_query, get_record, create_record, update_record, act_record, check_version
from .analytics import dashboard, source_revision, build_snapshot, external_payload, rules_config
from .visualization import visualization
from .reports import generate_report
from .batch_entry import extract, normalise_fields
from .scheduler import ReportScheduler
from .tenancy import accessible_stores, single_store, attach_scope
import os

log = logging.getLogger(__name__)
scheduler = ReportScheduler()


@asynccontextmanager
async def lifespan(app):
    from sqlalchemy import inspect
    if not inspect(engine).has_table('users'):
        raise RuntimeError('数据库尚未初始化。请先运行 python -m app.cli init')
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title='DealerDesk · 4S 门店经营台',version='0.2.0',lifespan=lifespan,
              docs_url='/docs' if (settings.api_docs and settings.environment!='production') else None,redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=list(settings.allowed_hosts))

# 所有表单都在 100KB 以内；批量填单允许内联图片，只有这一条路径放宽。
# 放宽的上限必须与 batch_entry 的图片预算配套：合计 5MB 原图 base64 后约 6.8MB < 8MB。
DEFAULT_BODY_LIMIT = 100_000
ENTRY_DRAFT_PATH = '/api/entry-draft/parse'
ENTRY_DRAFT_BODY_LIMIT = 8 * 1024 * 1024



@app.middleware('http')
async def safety_headers(request: Request, call_next):
    gate = os.getenv('DEALER_DEPLOYMENT_GATE', '')
    if gate and Path(gate).exists() and request.url.path.startswith('/api/') and request.url.path != '/api/health':
        return JSONResponse({'detail':'系统正在切换版本，请稍后刷新；当前不接受录入'},status_code=503)
    if request.url.path.startswith('/api/') and request.method not in {'GET','HEAD','OPTIONS'}:
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail':'不允许跨站请求'},status_code=403)
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'请求来源不匹配，请使用同一个地址访问'},status_code=403)
        if not request.headers.get('content-type','').lower().startswith('application/json'):
            return JSONResponse({'detail':'仅接受 JSON 请求'},status_code=415)
        try: size = int(request.headers.get('content-length','0'))
        except ValueError: return JSONResponse({'detail':'无效请求长度'},status_code=400)
        limit = ENTRY_DRAFT_BODY_LIMIT if request.url.path == ENTRY_DRAFT_PATH else DEFAULT_BODY_LIMIT
        oversize = '图片过大，请减少张数或压缩后重试' if limit > DEFAULT_BODY_LIMIT else '请求过大'
        if size > limit:
            return JSONResponse({'detail':oversize},status_code=413)
        chunks, actual_size = [], 0
        async for chunk in request.stream():
            actual_size += len(chunk)
            if actual_size > limit:
                return JSONResponse({'detail':oversize},status_code=413)
            chunks.append(chunk)
        request._body = b''.join(chunks)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.url.path != '/docs':
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    elif request.url.path.startswith('/static/'):
        # The script tag is /static/app.js with no version, so the URL is identical
        # across releases. Without a directive a browser may keep running the previous
        # frontend after a deploy -- which is exactly what happened after the first
        # P4 release. no-cache means "revalidate": the ETag answers a cheap 304 when
        # nothing changed and the fresh file when it did.
        response.headers['Cache-Control'] = 'no-cache'
    if settings.environment == 'production':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response


def validation_response(exc):
    errors = [{'field':'.'.join(str(x) for x in error['loc']),'message':error['msg']} for error in exc.errors()]
    return JSONResponse({'detail':'；'.join(f"{e['field']}: {e['message']}" for e in errors),'errors':errors},status_code=422)


@app.exception_handler(ValidationError)
async def validation_error(request,exc): return validation_response(exc)

@app.exception_handler(RequestValidationError)
async def request_validation_error(request,exc): return validation_response(exc)

@app.exception_handler(IntegrityError)
async def integrity_error(request,exc):
    return JSONResponse({'detail':'编号/VIN/保单号重复、车辆已被占用，或关联关系不满足约束。请刷新核对，未保存本次修改。'},status_code=409)

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
    return {'status':'ok','version':'0.2.0','release':os.getenv('DEALER_RELEASE_SHA','local')}


@app.post('/api/auth/login')
def login(body: LoginInput,request: Request,response: Response,db=Depends(get_db)):
    if request.headers.get('X-App-Request') != '1':
        raise HTTPException(403,'请求校验失败')
    user = authenticate(db,body.username,body.password,request.client.host if request.client else 'unknown')
    audit(db,user.id,'login','users',user.id,reason='登录成功')
    set_session(db,user,response)
    attach_scope(request, db, user)
    return user_info(user)


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
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
    audit(db,user.id,'change_password','users',user.id,reason='修改密码并撤销全部登录会话')
    db.commit(); clear_cookies(response)
    return {'ok':True,'message':'密码已修改，请重新登录'}


def admin(user):
    if user.role != 'admin': raise HTTPException(403,'仅系统管理员可以管理账号')


@app.get('/api/users')
def users(db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    return {'items':[account_info(db,u) for u in db.scalars(select(User).order_by(User.id))],'roles':ROLES,
            'stores':[plain(s) for s in db.scalars(select(Store).order_by(Store.id))]}


@app.post('/api/users',status_code=201)
def add_user(body: UserInput,db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    new = User(username=body.username.lower(),display_name=body.display_name,role=body.role,
               password_hash=hash_password(body.password),must_change_password=True)
    db.add(new); db.flush()
    assign_stores(db, new, body.store_ids)
    audit(db,user.id,'create_user','users',new.id,after={'username':new.username,'role':new.role})
    db.commit()
    return account_info(db,new)


@app.put('/api/users/{user_id}')
def edit_user(user_id: int,body: UserUpdate,db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    target = db.get(User,user_id)
    if not target: raise HTTPException(404,'用户不存在')
    if user_id == user.id and (body.role != 'admin' or not body.active):
        raise HTTPException(409,'不能降权或停用当前管理员自身')
    before = {'role':target.role,'active':target.active,'display_name':target.display_name}
    for key,value in body.model_dump(exclude={'store_ids'}).items(): setattr(target,key,value)
    if body.store_ids is not None: assign_stores(db,target,body.store_ids)
    db.execute(delete(LoginSession).where(LoginSession.user_id==target.id))
    audit(db,user.id,'update_user','users',target.id,before,body.model_dump(),reason='角色/状态变更后撤销会话')
    db.commit(); return account_info(db,target)


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


@app.post('/api/records/{module}',status_code=201)
def add_record(module: str,body:dict,db=Depends(get_db),user=Depends(get_user)):
    return serialize(create_record(db,user,module,body),module,user,db)


@app.put('/api/records/{module}/{record_id}')
def edit_record(module:str,record_id:int,body:UpdateInput,db=Depends(get_db),user=Depends(get_user)):
    return serialize(update_record(db,user,module,record_id,body.version,body.data),module,user,db)


@app.post('/api/records/{module}/{record_id}/actions/{action}')
def action(module:str,record_id:int,action:str,body:ActionInput,db=Depends(get_db),user=Depends(get_user)):
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


@app.get('/api/visualization')
def get_visualization(end:date|None=None,days:int=Query(90),db=Depends(get_db),user=Depends(get_user)):
    # Same role gate and store scope as /api/dashboard: the tenant hook bound by
    # get_user() already restricts load_data() to the authorized stores. Read-only.
    require_full(user)
    day = end or today()
    if day>today(): raise HTTPException(422,'可视化结束日期不能晚于今天')
    return visualization(db,day,days)


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


@app.post('/api/entry-draft/parse')
def parse_entry_draft(body:EntryDraftInput,db=Depends(get_db),user=Depends(get_user)):
    single_store(db)
    # Same permission as actually writing the module: nobody should be able to spend
    # AI budget on a module they could not enter by hand, and a read-only role must
    # not reach this at all.
    require_module(user,body.module,write=True)
    try:
        fields = normalise_fields(body.fields)
        draft = extract(body.module,fields,body.text,body.images)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from None
    rows = draft['rows'][:max(0,settings.ai_max_records)]
    audit(db,user.id,'entry_draft_parse','entry_draft',None,
          reason=f"解析批量填单草稿：模块 {body.module}，文本 {len(body.text)} 字，图片 {len(body.images)} 张，提出 {len(rows)} 行，待人工复核；未写入任何业务记录")
    db.commit()
    return {'module':body.module,'rows':rows,'issues':draft['issues'],'proposed':len(rows)}


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
    return {'version':'0.2.0','timezone':settings.timezone,'today':today().isoformat(),'environment':settings.environment,
        'scheduler_enabled':settings.scheduler_enabled,'daily_time':f'{settings.report_hour:02d}:{settings.report_minute:02d}',
        'multi_store':True,'active_store_id':db.info.get('write_store'),
        'maintenance_enabled':os.getenv('MAINTENANCE_ENABLED','false').lower() in {'true','1'},
        'catchup_days':settings.catchup_days,'ai_allowed':settings.allow_ai,'ai_key_configured':bool(settings.deepseek_key),
        'ai_model':settings.deepseek_model,'rules':rules_config(),
        'demo_database':bool(db.get(AppMetadata,'demo') and db.get(AppMetadata,'demo').value.get('enabled'))}




def account_info(db, target):
    result = user_info(target)
    stores = accessible_stores(db,target)
    result['store_ids'] = list(db.scalars(select(UserStore.store_id).where(UserStore.user_id==target.id)))
    result['stores'] = [{'id':s.id,'name':s.name,'code':s.code} for s in stores]
    return result


def assign_stores(db, target, ids):
    ids = sorted(set(ids))
    if target.role != 'admin' and not ids:
        raise HTTPException(422, '非管理员账号至少分配一家门店')
    if ids and db.scalar(select(func.count()).select_from(Store).where(Store.id.in_(ids),Store.active.is_(True))) != len(ids):
        raise HTTPException(422, '指定门店不存在或已停用')
    db.execute(delete(UserStore).where(UserStore.user_id==target.id))
    db.add_all([UserStore(user_id=target.id,store_id=i) for i in ids])


@app.get('/api/stores')
def stores(db=Depends(get_db),user=Depends(get_user)):
    rows = list(db.scalars(select(Store).order_by(Store.id))) if user.role=='admin' else accessible_stores(db,user)
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
    db.commit(); return plain(row)


def feedback_info(row):
    # Tokens, source files, test stdout and credentials are never returned to ordinary users.
    keys = ['id','store_id','created_by','title','description','category','status','created_at','updated_at',
            'attempts','base_sha','head_sha','branch','review_url','approved_by','approved_at','last_error','version']
    result={k:v for k,v in plain(row).items() if k in keys}
    result['summary']=row.proposal.get('summary','')
    result['files']=row.proposal.get('files',[])
    result['tests_passed']=row.test_result.get('passed',False)
    return result


@app.get('/api/maintenance/status')
def maintenance_status(db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    enabled=os.getenv('MAINTENANCE_ENABLED','false').lower() in {'true','1'}
    path=Path(os.getenv('MAINT_RUNTIME_DIR',str(ROOT/'data'/'maintenance')))/'status.json'
    result={'enabled':enabled,'ready':False,'paused':False,'worker_running':False,'release':'local',
            'message':'请用 start 脚本启动；未启用时只收集意见'}
    try:
        saved=json.loads(path.read_text(encoding='utf-8'))
        for key in result:
            if key in saved: result[key]=saved[key]
        if __import__('time').time()-saved.get('updated_at',0)>30:
            result.update(ready=False,worker_running=False,message='启动器状态已超过30秒未更新；请检查启动窗口')
    except (OSError,ValueError,TypeError): pass
    return result


@app.get('/api/feedback')
def feedback_list(db=Depends(get_db),user=Depends(get_user)):
    stmt=select(Feedback).order_by(Feedback.id.desc()).limit(200)
    if user.role!='admin': stmt=stmt.where(Feedback.created_by==user.id)
    return {'items':[feedback_info(r) for r in db.scalars(stmt)]}


@app.post('/api/feedback',status_code=201)
def add_feedback(body:FeedbackInput,db=Depends(get_db),user=Depends(get_user)):
    store=single_store(db)
    if db.scalar(select(func.count()).select_from(Feedback).where(Feedback.created_by==user.id,Feedback.created_at>=start_of_today_utc()))>=10:
        raise HTTPException(429,'每日最多提交10条改进意见，请合并相关问题')
    enabled=os.getenv('MAINTENANCE_ENABLED','false').lower() in {'true','1'}
    row=Feedback(store_id=store,created_by=user.id,title=body.title,description=body.description,category=body.category,
                 status='queued' if body.consent_code_review and enabled else 'new')
    db.add(row); db.flush()
    audit(db,user.id,'feedback','feedback',row.id,reason='已提交改进意见；'+('允许将意见与白名单源码发送DeepSeek' if body.consent_code_review else '未授权外发'))
    db.commit(); return feedback_info(row)


@app.post('/api/feedback/{feedback_id}/queue')
def queue_feedback(feedback_id:int,db=Depends(get_db),user=Depends(get_user)):
    admin(user); single_store(db)
    row=db.get(Feedback,feedback_id)
    if not row: raise HTTPException(404,'意见不存在')
    if row.status not in {'new','failed','manual','expired','superseded','rejected'}: raise HTTPException(409,'该任务不能重复入队')
    if row.attempts>=3: raise HTTPException(409,'已达到3次尝试上限，请人工处理')
    row.status='queued'; row.last_error=''; row.approval_token_hash=''; row.approved_sha=''; row.approved_by=''; row.approved_at=None
    audit(db,user.id,'queue_feedback','feedback',row.id,reason='管理员授权将意见与白名单源码发送DeepSeek；重新测试、重新审批')
    db.commit(); return feedback_info(row)


@app.get('/api/feedback/{feedback_id}/events')
def feedback_events(feedback_id:int,db=Depends(get_db),user=Depends(get_user)):
    row=db.get(Feedback,feedback_id)
    if not row or (user.role!='admin' and row.created_by!=user.id): raise HTTPException(404,'意见不存在')
    return {'items':[plain(e) for e in db.scalars(select(MaintenanceEvent).where(MaintenanceEvent.feedback_id==feedback_id).order_by(MaintenanceEvent.id))]}


@app.get('/')
def index(): return FileResponse(ROOT/'web'/'index.html')
app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')

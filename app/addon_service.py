"""Sales-bound accessory work, preserving quantities, original cost and consent."""
import uuid
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import utcnow,today
from .models import Vehicle,CashEntry
from .flow_models import Case,Task,Item,PaymentLink,Account,VehicleHold,FileAsset
from .flow_documents import can_file
from .tenancy import single_store
from . import flow_engine as flow
from .addon_models import *

READ={'admin','manager','sales','service','inventory','technician','finance','auditor'}
MONEY={'admin','manager','sales','service','finance','auditor'};COST={'admin','manager','finance','auditor'}
FRONT={'admin','sales','service'};MANAGE={'admin','manager'};FINANCE={'admin','finance'}
ACTIVE={'requested','approved','consented','rectification','reinspection','handback'}
ROLES={**{a:FRONT for a in ('quote','authorize','accept','resolution')},**{a:MANAGE for a in ('approve','resolution_approve','resolution_reject')},
    **{a:{'admin','inventory'} for a in ('dispatch','return_receive','return_handback')},**{a:{'admin','technician'} for a in ('install','rectify','return_rectify')},
    'quality':{'admin','service'},**{a:FINANCE for a in ('receive','refund')},**{a:FRONT|MANAGE for a in ('resolution_consent','resolution_cancel','cancel')}}
LABELS={'quote':'冻结当前加装报价','approve':'独立批准当前价格','authorize':'登记客户当前版授权','dispatch':'确认原行实际领出','install':'确认实际安装','quality':'记录实际加装检查','rectify':'记录整改并申请复检','accept':'客户接收本版加装','receive':'实际加装款到账','resolution':'提出原单处置','resolution_approve':'独立批准处置','resolution_consent':'客户同意原单处置','resolution_cancel':'撤回未执行处置','resolution_reject':'决定拒收并交回','return_receive':'检查拆回物资是否可售','return_rectify':'拆回物资整改复检','return_handback':'拒收实物交回客户','refund':'原加装款实际退回','cancel':'取消未授权加装'}

def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def _first(db,model,**kw):return db.scalar(select(model).filter_by(**kw))
def _one(db,model,key):
    r=db.scalar(select(model).where(model.id==key))
    if not r:raise HTTPException(404,'本店加装原始记录不存在')
    return r
def _role(user,roles):
    if user.role not in roles:raise HTTPException(403,'当前岗位不能办理此加装步骤')
def is_detailed(row):return row.kind=='addon' and row.flow_version==3
def get_order(db,user,key):
    single_store(db);_role(user,READ);row=flow.get_case(db,user,key)
    if not is_detailed(row):raise HTTPException(404,'本店明细加装单不存在')
    _one(db,AddonOrder,row.id);return row
def reserved_quantity(db,item_id,excluding_case_id=None):
    q=select(func.coalesce(func.sum(AddonReservation.quantity_milli),0)).where(AddonReservation.item_id==item_id)
    if excluding_case_id is not None:q=q.where(AddonReservation.case_id!=excluding_case_id)
    return int(db.scalar(q))
def _q(db,row,authorized=False):
    q=_one(db,AddonQuote,row.data.get('addon_quote_id',0))
    if q.case_id!=row.id:raise HTTPException(409,'报价不是本加装单当前版本')
    if q.pricing_version not in {1,2}:raise HTTPException(409,'无法识别原加装核价版本，请核对原记录')
    if authorized and not _first(db,AddonAuthorization,quote_id=q.id):raise HTTPException(409,'当前加装报价尚未获得客户授权')
    return q
def _lines(db,row):return _rows(db,AddonLine,quote_id=_q(db,row).id) if row.data.get('addon_quote_id') else []
def _line(db,row,key):
    l=next((l for l in _lines(db,row) if l.line_key==key),None)
    if not l:raise HTTPException(409,'不是本单当前报价项目')
    return l
def _active(db,row):return [p for p in _rows(db,AddonResolution,case_id=row.id) if p.status in ACTIVE]
def _held(db,row,key):return sum(r.quantity_milli for r in _rows(db,AddonReservation,case_id=row.id,line_key=key))
def _portion(value,quantity,remaining):
    from .retail_service import _portion as portion
    return portion(value,quantity,remaining)
def _allocate(total,weights):
    from .retail_service import _distribute
    return _distribute(total,weights)
def _source(db,row):
    o=_one(db,AddonOrder,row.id);s=_one(db,Case,o.source_order_id)
    if s.customer_id!=o.customer_id or row.customer_id!=o.customer_id or s.kind!='order' or row.parent_id!=s.id:raise HTTPException(409,'加装原销售或客户身份已经变化')
    return s
def _proof(db,user,row,key,category='evidence'):
    a=flow.file_exists(db,row,key,category)
    if a.generated or not can_file(user,row,a):raise HTTPException(403,'请使用本加装单已扫描且当前岗位可读的实际原件')
    for model in (AddonApproval,AddonAuthorization,AddonDispatch,AddonInstallation,AddonInspection,AddonRectification,AddonAcceptance,AddonResolution,AddonResolutionFact,AddonReturnPosting,AddonPayment):
        if db.scalar(select(model.id).join(FileAsset,FileAsset.id==model.evidence_id).where(FileAsset.case_id==row.id,FileAsset.sha256==a.sha256).limit(1)):raise HTTPException(409,'该原件已确认过其它事实，请上传本次实际凭据')
    return a
def _execute(db,user,key,action,values,fn):
    single_store(db);digest=flow.request_digest('addon_'+action,values)
    try:
        previous=_first(db,AddonReceipt,request_key=key)
        if previous:
            if previous.actor_id!=user.id or previous.digest!=digest:raise HTTPException(409,'请求编号已经用于其它内容或员工')
            return previous.result
        result=fn();db.flush();db.add(AddonReceipt(request_key=key,digest=digest,actor_id=user.id,result=result));db.commit();return result
    except (StaleDataError,IntegrityError,OperationalError):db.rollback();raise HTTPException(409,'原销售、库存或加装同时变化，请刷新核对并保留原请求编号')
    except Exception:db.rollback();raise
def _task(db,user,row,key):
    t=_first(db,Task,case_id=row.id,key='addon_'+key,status='open')
    if not t or user.role!='admin' and t.assignee_id!=user.id:raise HTTPException(409,'请由当前待办接手人办理，或先明确交接')
def _manager(db,row,key,title,exclude):
    users=[u for u in flow.eligible_users(db,'manager',row.store_id) if u.id not in exclude]
    if not users:raise HTTPException(409,'须配置另一位主管独立批准，申请人不能自批')
    t=_first(db,Task,case_id=row.id,key='addon_'+key,status='open')
    task=flow.ensure_task(db,row,'addon_'+key,title,'manager',assignee=t.assignee_id if t and t.assignee_id not in exclude else users[0].id,due=t.due_date if t else row.due_date,reopen=True)
    if not t:task.title=title;task.role='manager'
def _reserve(db,user,row,line,quantity,purpose):
    item=_one(db,Item,line.item_id);item.updated_at=utcnow();db.add(AddonReservation(case_id=row.id,line_id=line.id,line_key=line.line_key,item_id=item.id,quantity_milli=quantity,purpose=purpose,actor_id=user.id));db.flush()
def _posted(db,dispatch):return _rows(db,AddonReturnPosting,dispatch_id=dispatch.id)
def _returned(db,dispatch):return sum(p.quantity_milli for p in _posted(db,dispatch))
def _gifted(db,dispatch,completed_only=False):
    value=0
    for p in _rows(db,AddonResolution,case_id=dispatch.case_id,kind='vehicle_gift'):
        if p.status in ({'completed'} if completed_only else {'approved','consented','completed'}):value+=sum(x['quantity_milli'] for x in p.lines if x['dispatch_id']==dispatch.id)
    return value
def _installation_remaining(db,installation):
    used=sum(p.quantity_milli for p in _rows(db,AddonReturnPosting,installation_id=installation.id))
    for p in db.scalars(select(AddonResolution).where(AddonResolution.kind=='vehicle_gift',AddonResolution.status.in_(['approved','consented','completed']))):used+=sum(x['quantity_milli'] for x in p.lines if x.get('installation_id')==installation.id)
    return installation.quantity_milli-used
def _last_check(db,installation):
    checks=_rows(db,AddonInspection,installation_id=installation.id);return checks[-1] if checks else None
def _installed(db,dispatch):return sum(i.quantity_milli for i in _rows(db,AddonInstallation,dispatch_id=dispatch.id))
def _uninstalled(db,dispatch):return dispatch.quantity_milli-_installed(db,dispatch)-sum(p.quantity_milli for p in _posted(db,dispatch) if not p.installation_id)
def _cash_paid(db,row):return sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in _rows(db,PaymentLink,case_id=row.id))
def totals(db,row):
    from .business_finance_sources import case_credit_amount,case_reserved_amount
    credit=case_credit_amount(db,row.id);cash=_cash_paid(db,row);returns=_rows(db,AddonReturnPosting,case_id=row.id);reduction=sum(p.goods_cents+p.installation_cents-p.retained_cents for p in returns)
    charge=0 if row.state=='cancelled' else row.amount_cents-reduction;paid=cash+credit
    return dict(quoted_cents=row.amount_cents,charge_cents=charge,return_reduction_cents=reduction,retained_installation_cents=sum(p.retained_cents for p in returns),cash_paid_cents=cash,advance_credit_cents=credit,paid_cents=paid,reserved_cents=case_reserved_amount(db,row.id),receivable_cents=max(0,charge-paid),refund_due_cents=max(0,paid-charge),cost_cents=sum(d.value_cents for d in _rows(db,AddonDispatch,case_id=row.id))-sum(p.value_cents for p in returns))
def customer_due(db,row,include_reservations=True):
    t=totals(db,row);return max(0,t['receivable_cents']-(t['reserved_cents'] if include_reservations else 0))
def guard_source_adjustment(db,row,action='adjustment'):
    if is_detailed(row) and _active(db,row):raise HTTPException(409,'加装有正在办理的原单处置，请先完成或撤回')
def source_finance(db,user,row,include_reservations=True):
    get_order(db,user,row.id);_q(db,row,True)
    if row.state=='cancelled':raise HTTPException(409,'已取消加装不能收款')
    if any(p.kind!='vehicle_gift' for p in _active(db,row)):raise HTTPException(409,'原退货或取消处置期间不能更换原资金')
    t=totals(db,row)
    return dict(case_id=row.id,number=row.number,kind=row.kind,version=row.version,customer_id=row.customer_id,business_date=row.business_date.isoformat(),allocation_id=None,payer_type='customer',amount_cents=t['charge_cents'],due_cents=customer_due(db,row,include_reservations),credit_cents=t['advance_credit_cents'],allocations=[])
def record_collection(db,user,row,payment_link,evidence_id,*,original_payment=None,correction=False):
    if correction:guard_source_adjustment(db,row)
    if payment_link.case_id!=row.id or _first(db,AddonPayment,payment_link_id=payment_link.id):raise HTTPException(409,'加装真实资金链接重复或串单')
    if payment_link.direction=='out' and (not correction or not original_payment or payment_link.original_id!=original_payment.id):raise HTTPException(409,'加装退款须引用原独立处置')
    db.add(AddonPayment(case_id=row.id,payment_link_id=payment_link.id,evidence_id=evidence_id,actor_id=user.id));db.flush()
def record_advance_credit(db,user,row,credit_link,evidence_id):
    if credit_link.case_id!=row.id or credit_link.amount_cents<=0:raise HTTPException(409,'不是本加装单的原预收抵用')
    db.add(AddonPayment(case_id=row.id,credit_link_id=credit_link.id,evidence_id=evidence_id,actor_id=user.id));db.flush()
def invoice_source_amount(db,row):
    return totals(db,row)['charge_cents'] if row.data.get('addon_quote_id') and _first(db,AddonAuthorization,quote_id=row.data['addon_quote_id']) else 0
def actual_income_rows(db,row):
    result=[dict(fact_id=a.id,business_date=a.business_date.isoformat(),amount_cents=a.amount_cents,value_cents=a.value_cents,kind='acceptance') for a in _rows(db,AddonAcceptance,case_id=row.id)]
    result += [dict(fact_id=p.id,business_date=p.business_date.isoformat(),amount_cents=-(p.goods_cents+p.installation_cents-p.retained_cents),value_cents=-p.value_cents,kind='return',original_fact_id=p.acceptance_id) for p in _rows(db,AddonReturnPosting,case_id=row.id) if p.acceptance_id]
    return result

def _requires_acceptance(db,row):
    # Historical charge-based completion remains frozen. New gifts also require
    # real customer receipt while any original physical goods remain delivered.
    return totals(db,row)['charge_cents']>0 or (_q(db,row).pricing_version==2 and any(d.quantity_milli>_returned(db,d) for d in _rows(db,AddonDispatch,case_id=row.id)))

def _sync(db,user,row):
    if row.state=='cancelled':return
    q=_q(db,row) if row.data.get('addon_quote_id') else None;desired={};active=_active(db,row)
    if not q:desired['quote']=('核对加装明细并报价','front',set())
    elif not _first(db,AddonApproval,quote_id=q.id):desired['approve']=('独立批准当前加装价格','manager',{q.actor_id,row.created_by})
    elif not _first(db,AddonAuthorization,quote_id=q.id):desired['authorize']=('取得本版商品及安装费授权','front',set())
    elif not active:
        if any(_held(db,row,l.line_key)>0 for l in _lines(db,row)):desired['dispatch']=('按原VIN与授权项目实际领出','inventory',set())
        dispatches=_rows(db,AddonDispatch,case_id=row.id)
        if any(_uninstalled(db,d)>0 for d in dispatches):desired['install']=('按原领料批次实际安装','technician',set())
        installations=[i for d in dispatches for i in _rows(db,AddonInstallation,dispatch_id=d.id) if _installation_remaining(db,i)>0]
        if any(not _last_check(db,i) or not _last_check(db,i).passed and _first(db,AddonRectification,inspection_id=_last_check(db,i).id) for i in installations):desired['quality']=('检查本批实际安装或整改复检','service',set())
        if any(_last_check(db,i) and not _last_check(db,i).passed and not _first(db,AddonRectification,inspection_id=_last_check(db,i).id) for i in installations):desired['rectify']=('处理本次加装检查缺陷','technician',set())
        if not any(k in desired for k in ('dispatch','install','quality','rectify')) and not _first(db,AddonAcceptance,quote_id=q.id) and _requires_acceptance(db,row):desired['accept']=('客户确认当前加装实际接收','front',set())
    if q and _first(db,AddonAuthorization,quote_id=q.id) and customer_due(db,row)>0 and not any(p.kind!='vehicle_gift' for p in active):desired['receive']=('核对加装服务实际到账','finance',set())
    if totals(db,row)['refund_due_cents']>0:desired['refund']=('按原款退还获准加装退款','finance',set())
    for p in active:
        key='resolution_'+str(p.id)
        if p.status=='requested':desired[key]=('独立复核原加装处置','manager',{p.requested_by,row.created_by})
        elif p.status=='approved':desired[key]=('取得客户当前处置及保留费同意','front',set())
        elif p.kind=='vehicle_gift':desired[key]=('随原VIN接回已授权无偿移交的装件','inventory',set())
        elif p.status in {'consented','reinspection'}:desired[key]=('实际检查拆回商品能否恢复可售','inventory',set())
        elif p.status=='rectification':desired[key]=('整改拆回商品并重新验收','technician',set())
        elif p.status=='handback':desired[key]=('将拒收商品实际交回客户','inventory',set())
    for t in _rows(db,Task,case_id=row.id,status='open'):
        if t.key.startswith('addon_') and t.key.removeprefix('addon_') not in desired:flow.finish_task(db,row,t.key,user)
    for key,(title,role,excluded) in desired.items():
        if role=='manager':_manager(db,row,key,title,excluded)
        else:
            t=_first(db,Task,case_id=row.id,key='addon_'+key,status='open');assignee=t.assignee_id if t else row.owner_id if role=='front' else None
            task=flow.ensure_task(db,row,'addon_'+key,title,'sales' if role=='front' else role,assignee=assignee,due=t.due_date if t else row.due_date,reopen=True)
            if not t:task.title=title;task.role='sales' if role=='front' else role
    row.state='completed' if not desired else 'approval' if any(v[1]=='manager' for v in desired.values()) else 'working';row.completed_date=today() if row.state=='completed' else None
    row.cost_cents=totals(db,row)['cost_cents']
def sync_after_finance(db,user,row,evidence_id=None):
    _sync(db,user,row)
    from .invoice_service import sync_source
    sync_source(db,user,row)
def create(db,user,request_id,v):
    _role(user,FRONT)
    def run():
        source=flow.get_case(db,user,v['source_order_id'])
        if source.kind!='order' or source.flow_version not in {2,3,4} or source.state=='cancelled' or not source.customer_id:raise HTTPException(409,'请选择本店有效销售原单，历史版本不自动迁移')
        if source.version!=v['source_version']:raise HTTPException(409,'原销售版本已变化，请刷新后建立加装')
        from .aftercare_service import guard_source_action
        guard_source_action(db,user,source,'addon')
        if source.flow_version in {3,4}:
            from .sales_quote_service import guard_source_action as guard_quote
            guard_quote(db,user,source,'addon')
        if v['delivery_blocking'] and source.state=='delivered':raise HTTPException(409,'原车已经交付，不能再追加交车前条件')
        source.updated_at=utcnow();db.flush()
        row=Case(number='HKA'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='addon',flow_version=3,state='pending',title=source.title+' · 明细加装',parent_id=source.id,customer_id=source.customer_id,owner_id=user.id,created_by=user.id,business_date=today(),due_date=date.fromisoformat(v['due_date']),data={})
        db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);db.add(AddonOrder(id=row.id,source_order_id=source.id,customer_id=source.customer_id,source_snapshot={'number':source.number,'customer_id':source.customer_id,'flow_version':source.flow_version,'model':source.data.get('model','')},delivery_blocking=v['delivery_blocking'],reason=v['reason'],actor_id=user.id));db.flush();_sync(db,user,row);flow.log_event(db,user,row,'addon_create','建立销售原单明细加装');db.flush();return describe(db,user,row)
    return _execute(db,user,request_id,'create',v,run)

def create_for_sales_quote(db,user,source,quote):
    """Only a signed order/v4 activates a new detail request, never auto fulfillment."""
    single_store(db)
    from .sales_quote_models import SalesQuoteConsent,SalesQuoteResolution
    consent=_first(db,SalesQuoteConsent,quote_id=quote.id)
    activation=_first(db,SalesQuoteResolution,quote_id=quote.id,outcome='activated')
    if source.kind!='order' or source.flow_version!=4 or quote.case_id!=source.id or not quote.services.get('addon') or not consent or not activation or source.data.get('active_quote_id')!=quote.id:raise HTTPException(409,'只有销售第4版当前已签回生效报价能建立明细加装')
    if any(_one(db,Case,o.id).state!='cancelled' for o in _rows(db,AddonOrder,source_order_id=source.id)):raise HTTPException(409,'原销售已有明细加装，请在原加装单另行授权增项')
    row=Case(number='HKA'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='addon',flow_version=3,state='pending',title=source.title+' · 明细加装',parent_id=source.id,customer_id=source.customer_id,owner_id=source.owner_id,created_by=user.id,business_date=today(),due_date=quote.delivery_due,data={})
    db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);db.add(AddonOrder(id=row.id,source_order_id=source.id,customer_id=source.customer_id,source_snapshot={'number':source.number,'customer_id':source.customer_id,'flow_version':source.flow_version,'model':quote.model_snapshot,'sales_quote_id':quote.id,'sales_quote_digest':quote.digest},delivery_blocking=True,reason='客户按销售当前版签回约定另单加装',actor_id=user.id));db.flush();_sync(db,user,row);flow.log_event(db,user,row,'addon_create','从销售当前签回版本建立明细加装申请',detail={'source_order_id':source.id,'sales_quote_id':quote.id});db.flush();return row
def _quote_command(db,user,row,v):
    if _active(db,row) or _rows(db,AddonVehicleHandover,case_id=row.id):raise HTTPException(409,'原处置或随车移交后不能另改加装报价')
    old={l.line_key:l for l in _lines(db,row)};old_terms=_q(db,row).gift_terms if old else {};fixed=bool(_rows(db,AddonReservation,case_id=row.id) or _rows(db,AddonPayment,case_id=row.id));data=[];keys=set();terms={}
    from .master_data import require_active
    for x in v['lines']:
        if x['line_key'] in keys:raise HTTPException(422,'加装项目编号重复')
        keys.add(x['line_key']);item=_one(db,Item,x['item_id']);work=require_active(db,'work_items',x['work_item_id'])
        if not item.active:raise HTTPException(422,'商品已停用')
        goods=(x['quantity_milli']*x['goods_unit_cents']+500)//1000;install=(x['quantity_milli']*x['installation_unit_cents']+500)//1000
        if goods+install>1_000_000_000_000:raise HTTPException(422,'单项金额超过办理上限，请核对数量和单价')
        d=dict(line_key=x['line_key'],item_id=item.id,work_item_id=work.id,sku=item.sku,name=item.name,unit=item.unit,work_code=work.code,work_name=work.name,quantity_milli=x['quantity_milli'],goods_unit_cents=x['goods_unit_cents'],installation_unit_cents=x['installation_unit_cents'],goods_cents=goods,installation_cents=install)
        if fixed and d['line_key'] in old:
            prior=old[d['line_key']]
            if any(d[k]!=getattr(prior,k) for k in ('item_id','work_item_id','quantity_milli','goods_unit_cents','installation_unit_cents')):raise HTTPException(409,'原行已有授权占用或真实资金，不得改项改价；增项请另加明细')
            d={k:getattr(prior,k) for k in d}
        data.append(d)
    if fixed and not set(old)<=keys:raise HTTPException(409,'已有授权原行不能删除，未领取消或原退须走明确处置')
    positions=[(i,k) for i,d in enumerate(data) if not fixed or d['line_key'] not in old for k in ('goods_cents','installation_cents')]
    weights=[data[i][k] for i,k in positions];gross=sum(weights)
    if v['discount_cents']>gross:raise HTTPException(422,'本次折扣只能分摊到可报价的新商品及安装费')
    from . import member_pricing_service as pricing
    components=[]
    for i,d in enumerate(data):
        for k,component,source in [('goods_cents','goods',d['item_id']),('installation_cents','installation',d['work_item_id'])]:
            frozen=fixed and d['line_key'] in old
            components.append(dict(line_key=d['line_key'],component=component,source_id=source,basis_cents=0 if frozen else d[k],carry_cents=d[k] if frozen else 0,charge_scope='customer'))
    member_contract=pricing.prepare_quote(db,user,row,v.get('member_pricing'),components,v['discount_cents'])
    if member_contract:
        for d in data:
            for p in member_contract['lines']:
                if p['line_key']==d['line_key']:d['goods_cents' if p['component']=='goods' else 'installation_cents']=p['carry_cents']+p['net_cents']
    else:
        for (i,k),amount in zip(positions,_allocate(gross-v['discount_cents'],weights)):data[i][k]=amount
    goods=sum(d['goods_cents'] for d in data);installation=sum(d['installation_cents'] for d in data)
    if not 0<=goods+installation<=1_000_000_000_000:raise HTTPException(422,'加装合计金额不在办理范围')
    for x,d in zip(v['lines'],data):
        key=d['line_key'];reason=x.get('gift_reason','');bearer=x.get('gift_cost_bearer')
        if fixed and key in old:
            prior=old_terms.get(key)
            if (reason or bearer) and (not prior or reason!=prior['reason'] or bearer!=prior['cost_bearer']):raise HTTPException(409,'原已授权行的赠送原因和承担门店不可改写，请保留原条款')
            if prior:terms[key]=dict(prior)
            # Historical authorized zero lines stay explicitly without inferred gift terms.
        elif d['goods_cents']+d['installation_cents']==0:
            if len(reason)<2 or bearer!='selling_store':raise HTTPException(422,'新零价项目须明确赠送原因，并选择本销售门店承担商品及安装成本')
            terms[key]=dict(reason=reason,cost_bearer='selling_store',burden_store_id=row.store_id)
        elif reason or bearer:raise HTTPException(422,'赠送条款仅用于本行商品及安装合计为零的项目，请核对实际收费')
    discount=sum((d['quantity_milli']*d['goods_unit_cents']+500)//1000+(d['quantity_milli']*d['installation_unit_cents']+500)//1000-d['goods_cents']-d['installation_cents'] for d in data)
    digest_data=dict(pricing_version=2,lines=data,gift_terms=terms)
    if member_contract:digest_data['member_pricing']=pricing.canonical(member_contract)
    q=AddonQuote(case_id=row.id,revision=len(_rows(db,AddonQuote,case_id=row.id))+1,goods_cents=goods,installation_cents=installation,discount_cents=discount,pricing_version=2,gift_terms=terms,digest=flow.request_digest('addon_quote',digest_data),reason=v['reason'],actor_id=user.id);db.add(q);db.flush()
    for d in data:db.add(AddonLine(quote_id=q.id,**d))
    row.amount_cents=goods+installation;flow.set_data(row,addon_quote_id=q.id);db.flush()
    pricing.freeze_quote(db,user,row,'addon',q.id,member_contract)
def _target(db,user,row,vin):
    source=_source(db,row);hold=_first(db,VehicleHold,case_id=source.id)
    if not hold:raise HTTPException(409,'原销售尚未实际配车，不能领料并假定安装车辆')
    car=_one(db,Vehicle,hold.vehicle_id)
    if car.vin!=vin:raise HTTPException(409,'实际核对VIN与原销售配车不符，不能把安装转到其它车辆')
    target=_first(db,AddonTarget,case_id=row.id)
    if target and target.vehicle_id!=car.id:raise HTTPException(409,'原加装已经绑定另一车辆，须先实际拆回处置，不能直接换车')
    if not target:
        target=AddonTarget(case_id=row.id,vehicle_id=car.id,vin=car.vin,source_version=source.version,actor_id=user.id);db.add(target);db.flush()
    car.updated_at=utcnow();db.flush();return target
def _dispatch(db,user,row,v):
    _q(db,row,True)
    if _active(db,row):raise HTTPException(409,'原处置期间不能继续领出')
    _proof(db,user,row,v['evidence_id']);target=_target(db,user,row,v['checked_vin']);seen=set()
    from .inventory_availability import assert_can_issue
    from .retail_service import _stock
    for x in v['lines']:
        l=_line(db,row,x['line_key']);qty=x['quantity_milli']
        if l.line_key in seen or qty>_held(db,row,l.line_key):raise HTTPException(409,'实际领出超过本行获准未领数量，或重复选择原行')
        seen.add(l.line_key);item=_one(db,Item,l.item_id);assert_can_issue(db,item,qty,excluding_addon_case_id=row.id)
        ds=_rows(db,AddonDispatch,case_id=row.id,line_key=l.line_key);cancels=[p for p in _rows(db,AddonReturnPosting,case_id=row.id,line_key=l.line_key) if not p.dispatch_id]
        remaining=l.quantity_milli-sum(d.quantity_milli for d in ds)-sum(c.quantity_milli for c in cancels)
        goods=_portion(l.goods_cents-sum(d.goods_cents for d in ds)-sum(c.goods_cents for c in cancels),qty,remaining)
        install=_portion(l.installation_cents-sum(d.installation_cents for d in ds)-sum(c.installation_cents for c in cancels),qty,remaining)
        value=_portion(item.inventory_value_cents,qty,item.quantity_milli);move=_stock(db,user,row,item,-qty,-value,'addon_dispatch_v3')
        db.add(AddonDispatch(case_id=row.id,line_id=l.id,line_key=l.line_key,target_id=target.id,stock_move_id=move.id,quantity_milli=qty,value_cents=value,goods_cents=goods,installation_cents=install,evidence_id=v['evidence_id'],actor_id=user.id));_reserve(db,user,row,l,-qty,'dispatch')
    db.flush()

def _gift_portion(db,dispatch,field):
    return sum(x[field] for p in _rows(db,AddonResolution,case_id=dispatch.case_id,kind='vehicle_gift') if p.status in {'approved','consented','completed'} for x in p.lines if x['dispatch_id']==dispatch.id)
def _resolution(db,user,row,v):
    q=_q(db,row,True)
    if _active(db,row):raise HTTPException(409,'请先完成或撤回已有加装处置，不能竞争占用同一原实物')
    kind=v['kind'];lines=[];selected=set();selected_qty={};selected_values={}
    if kind=='vehicle_gift' and not v.get('confirm_no_goods_refund'):raise HTTPException(422,'随车无偿移交必须明确商品不退款；要求商品退款请实际拆回')
    for x in v['lines']:
        qty=x['quantity_milli']
        if kind=='cancel':
            l=_line(db,row,x.get('line_key',''));key=l.line_key
            if key in selected or qty>_held(db,row,l.line_key):raise HTTPException(409,'取消只能选择本行尚未实际领出的获准数量')
            selected.add(key);ds=_rows(db,AddonDispatch,case_id=row.id,line_key=l.line_key);ps=[p for p in _rows(db,AddonReturnPosting,case_id=row.id,line_key=l.line_key) if not p.dispatch_id]
            remaining=l.quantity_milli-sum(d.quantity_milli for d in ds)-sum(p.quantity_milli for p in ps)
            goods=_portion(l.goods_cents-sum(d.goods_cents for d in ds)-sum(p.goods_cents for p in ps),qty,remaining);install=_portion(l.installation_cents-sum(d.installation_cents for d in ds)-sum(p.installation_cents for p in ps),qty,remaining)
            lines.append(dict(line_id=l.id,line_key=l.line_key,dispatch_id=None,installation_id=None,quantity_milli=qty,value_cents=0,goods_cents=goods,installation_cents=install,retained_cents=0));continue
        d=_one(db,AddonDispatch,x.get('dispatch_id',0));l=_one(db,AddonLine,d.line_id);installation=_one(db,AddonInstallation,x['installation_id']) if x.get('installation_id') else None;key=(d.id,installation.id if installation else None)
        if d.case_id!=row.id or key in selected:raise HTTPException(409,'拆回或随车移交须选择本加装单未重复的原出库／安装批次')
        if installation and (installation.dispatch_id!=d.id or qty>_installation_remaining(db,installation)):raise HTTPException(409,'处置数量超过对应原安装批次尚未处置数量')
        if not installation and (kind=='vehicle_gift' or qty>_uninstalled(db,d)):raise HTTPException(409,'未安装原料仅能拆回，数量不能借用已安装批次')
        if kind=='vehicle_gift' and (not _last_check(db,installation) or not _last_check(db,installation).passed):raise HTTPException(409,'随车移交须明确已安装且检查通过的原装件')
        selected.add(key);already=selected_qty.get(d.id,0);previous=_posted(db,d);remaining=d.quantity_milli-sum(p.quantity_milli for p in previous)-_gifted(db,d)-already
        if qty>remaining:raise HTTPException(409,'多行处置合计超过原出库剩余数量')
        values={}
        for field in ('value_cents','goods_cents','installation_cents'):
            available=getattr(d,field)-sum(getattr(p,field) for p in previous)-_gift_portion(db,d,field)-selected_values.get((d.id,field),0)
            values[field]=_portion(available,qty,remaining);selected_values[(d.id,field)]=selected_values.get((d.id,field),0)+values[field]
        selected_qty[d.id]=already+qty
        lines.append(dict(line_id=l.id,line_key=l.line_key,dispatch_id=d.id,installation_id=installation.id if installation else None,quantity_milli=qty,**values,retained_cents=values['installation_cents'] if installation else 0))
    if not lines:raise HTTPException(422,'请选择本次原实物或尚未领出数量')
    _proof(db,user,row,v['evidence_id'],'authorization')
    p=AddonResolution(case_id=row.id,quote_id=q.id,kind=kind,lines=lines,reason=v['reason'],digest=flow.request_digest('addon_resolution',{'kind':kind,'lines':lines,'no_goods_refund':kind=='vehicle_gift'}),evidence_id=v['evidence_id'],requested_by=user.id);db.add(p);db.flush();return p
def _res(db,row,key):
    p=_one(db,AddonResolution,key)
    if p.case_id!=row.id:raise HTTPException(409,'原处置不属于本加装单')
    return p
def _res_fact(db,user,p,action,v):db.add(AddonResolutionFact(resolution_id=p.id,action=action,result=v.get('result',v.get('reason',LABELS.get(action,action))),evidence_id=v['evidence_id'],actor_id=user.id));db.flush()
def _post_resolution(db,user,row,p,evidence_id):
    from .retail_service import _stock
    for x in p.lines:
        l=_one(db,AddonLine,x['line_id']);move=None
        if p.kind=='return':
            d=_one(db,AddonDispatch,x['dispatch_id']);item=_one(db,Item,l.item_id);move=_stock(db,user,row,item,x['quantity_milli'],x['value_cents'],'addon_return_v3',original=d.stock_move_id)
        elif p.kind=='cancel':_reserve(db,user,row,l,-x['quantity_milli'],'cancel')
        else:raise HTTPException(409,'随车无偿移交不能重新生成物资库存')
        acceptance=next((a for a in reversed(_rows(db,AddonAcceptance,case_id=row.id)) if any(line.line_key==l.line_key for line in _rows(db,AddonLine,quote_id=a.quote_id))),None)
        db.add(AddonReturnPosting(case_id=row.id,resolution_id=p.id,line_id=l.id,line_key=l.line_key,dispatch_id=x['dispatch_id'],installation_id=x['installation_id'],stock_move_id=move.id if move else None,quantity_milli=x['quantity_milli'],value_cents=x['value_cents'],goods_cents=x['goods_cents'],installation_cents=x['installation_cents'],retained_cents=x['retained_cents'],acceptance_id=acceptance.id if acceptance else None,business_date=today(),evidence_id=evidence_id,actor_id=user.id))
    p.status='completed';db.flush()
def _resolution_command(db,user,row,action,v):
    p=_res(db,row,v['resolution_id'])
    if p.status not in ACTIVE:raise HTTPException(409,'本处置已结束，不能重复改变原事实')
    if action not in {'resolution_cancel','resolution_reject'}:_task(db,user,row,'resolution_'+str(p.id))
    category='authorization' if action in {'resolution_approve','resolution_consent','resolution_cancel','resolution_reject'} else 'inspection'
    _proof(db,user,row,v['evidence_id'],category)
    if action=='resolution_approve':
        if p.status!='requested' or user.id in {p.requested_by,row.created_by}:raise HTTPException(403,'加装处置必须由另一主管独立复核，管理员也不能自批')
        p.status='approved'
    elif action=='resolution_consent':
        if p.status!='approved':raise HTTPException(409,'客户同意必须对应当前独立批准处置')
        if p.kind=='vehicle_gift' and not v.get('confirm_no_goods_refund'):raise HTTPException(422,'须明确客户商品不退款并随原车无偿移交，不作有偿回购')
        p.status='consented'
        if p.kind=='cancel':_post_resolution(db,user,row,p,v['evidence_id'])
    elif action=='return_receive':
        if p.kind!='return' or p.status not in {'consented','reinspection'}:raise HTTPException(409,'须客户同意后实际检查拆回商品，整改后须重新申请复检')
        if not v['passed']:p.status='rectification'
        else:_post_resolution(db,user,row,p,v['evidence_id'])
    elif action=='return_rectify':
        if p.kind!='return' or p.status!='rectification':raise HTTPException(409,'只有实际不合格的拆回商品可以申请复检')
        p.status='reinspection'
    elif action=='resolution_reject':
        if p.kind!='return' or p.status not in {'rectification','reinspection'}:raise HTTPException(409,'实际收到且未验收合格的商品才能决定拒收')
        p.status='handback'
    elif action=='return_handback':
        if p.status!='handback':raise HTTPException(409,'须先明确拒收，再由库管实际交回客户')
        p.status='rejected'
    elif action=='resolution_cancel':
        if p.status not in {'requested','approved','consented'} or p.kind=='return' and _first(db,AddonResolutionFact,resolution_id=p.id,action='return_receive'):raise HTTPException(409,'已实际接回、退款或完成随车移交的处置不能撤回')
        p.status='cancelled'
    flow.finish_task(db,row,'addon_resolution_'+str(p.id),user)
    _res_fact(db,user,p,action,v)
def _refund_resolution_limit(db,row,p):
    if p.status!='completed' or p.kind=='vehicle_gift':return 0
    permitted=sum(x.goods_cents+x.installation_cents-x.retained_cents for x in _rows(db,AddonReturnPosting,resolution_id=p.id))
    refunded=0
    for fact in _rows(db,AddonPayment,resolution_id=p.id):
        if fact.payment_link_id:
            link=_one(db,PaymentLink,fact.payment_link_id)
            if link.direction=='out':refunded+=link.amount_cents
        else:
            from .business_finance_models import FinanceCreditLink
            link=_one(db,FinanceCreditLink,fact.credit_link_id)
            if link.amount_cents<0:refunded-=link.amount_cents
    return min(permitted-refunded,totals(db,row)['refund_due_cents'])
def assert_advance_return(db,user,row,credit_link,amount,evidence_id,resolution_id):
    _role(user,FINANCE);get_order(db,user,row.id);p=_res(db,row,resolution_id);flow.file_exists(db,row,evidence_id,'receipt')
    if credit_link.case_id!=row.id or credit_link.amount_cents<=0 or amount<=0 or amount>_refund_resolution_limit(db,row,p):raise HTTPException(409,'预收原退超过本加装实际处置的获准退款额度')
    return True
def _refund(db,user,row,v):
    p=_res(db,row,v['resolution_id']);amount=v['amount_cents']
    if amount>_refund_resolution_limit(db,row,p):raise HTTPException(409,'退款超过本次已完成原处置及原客户尚欠退款额')
    _proof(db,user,row,v['evidence_id'],'receipt')
    if v['kind']=='cash':
        if totals(db,row)['advance_credit_cents']>0:raise HTTPException(409,'本版先将可退原预收抵用恢复原余额，再处理剩余现金退款')
        original=_one(db,PaymentLink,v['original_id'])
        if original.case_id!=row.id or original.direction!='in' or amount>original.amount_cents-sum(x.amount_cents for x in _rows(db,PaymentLink,original_id=original.id)):raise HTTPException(409,'退款超过本加装原收款尚未退回余额')
        account=_one(db,Account,v['account_id'])
        if not account.active or account.id!=original.account_id or not v['reference'].strip():raise HTTPException(409,'真实退款须使用原账户及本次独立流水')
        if db.scalar(select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==v['reference'])):raise HTTPException(409,'此账户凭证号已经登记')
        from .business_entity_service import require_account_entity,record_cash_entity
        require_account_entity(db,user,row,account.id,today(),original_cash_id=original.cash_id)
        account.updated_at=utcnow();cash=CashEntry(doc_no='AD-'+uuid.uuid4().hex[:20],business_date=today(),created_by=user.id,approval_state='approved',direction='out',category='addon_customer_refund',amount_cents=amount,account=account.name,counterparty=row.title,payment_method=account.account_type,voucher_no=v['reference'],note='原加装退款 '+row.number);db.add(cash);db.flush();record_cash_entity(db,user,row,cash,account.id,original_cash_id=original.cash_id)
        link=PaymentLink(case_id=row.id,cash_id=cash.id,original_id=original.id,account_id=account.id,direction='out',amount_cents=amount,reference=v['reference'],business_date=today());db.add(link);db.flush();db.add(AddonPayment(case_id=row.id,payment_link_id=link.id,resolution_id=p.id,evidence_id=v['evidence_id'],actor_id=user.id))
    else:
        from .business_finance_models import FinanceCreditLink
        from .business_finance_sources import restore_addon_credit
        link=restore_addon_credit(db,user,row,_one(db,FinanceCreditLink,v['original_id']),amount,v['evidence_id'],p.id);db.add(AddonPayment(case_id=row.id,credit_link_id=link.id,resolution_id=p.id,evidence_id=v['evidence_id'],actor_id=user.id))
    db.flush()

def _ready(db,row):
    _q(db,row,True)
    if _active(db,row) or any(_held(db,row,l.line_key) for l in _lines(db,row)):return False
    for d in _rows(db,AddonDispatch,case_id=row.id):
        if _uninstalled(db,d)>0:return False
        for i in _rows(db,AddonInstallation,dispatch_id=d.id):
            if _installation_remaining(db,i)>0 and (not _last_check(db,i) or not _last_check(db,i).passed):return False
    return True

def command(db,user,key,request_id,version,action,v):
    if v.get('member_pricing') is None:v={k:value for k,value in v.items() if k!='member_pricing'}
    _role(user,ROLES.get(action,set()))
    def run():
        row=get_order(db,user,key)
        if row.version!=version:raise HTTPException(409,'加装单已经变化，请刷新核对当前报价与实物')
        if row.state=='cancelled':raise HTTPException(409,'加装已取消，原记录只读')
        source=_source(db,row);source.updated_at=utcnow();row.updated_at=utcnow();db.flush()
        from .sales_quote_service import guard_child_action
        guard_child_action(db,user,source,action)
        from .aftercare_service import guard_source_action
        guard_source_action(db,user,source,'addon')
        if source.flow_version in {3,4} and action in {'quote','authorize','dispatch','install','accept'}:
            from .sales_quote_service import guard_source_action as guard_quote
            guard_quote(db,user,source,'addon')
        if action=='quote':_quote_command(db,user,row,v)
        elif action=='approve':
            q=_q(db,row);_task(db,user,row,'approve')
            if _first(db,AddonApproval,quote_id=q.id) or user.id in {q.actor_id,row.created_by}:raise HTTPException(403,'本版报价必须另一位主管独立批准，管理员也不能自批')
            if row.amount_cents<v['minimum_cents'] and not v['allow_below_minimum']:raise HTTPException(409,'低于本次明确最低价，须主管明确确认例外及原因')
            if q.gift_terms and not v.get('confirm_gift'):raise HTTPException(409,'请独立核对本版赠送原因，并明确批准本销售门店承担商品及安装成本')
            if not q.gift_terms and v.get('confirm_gift'):raise HTTPException(409,'本版没有明确赠送条款，不能补记赠送批准')
            _proof(db,user,row,v['evidence_id'],'authorization');db.add(AddonApproval(quote_id=q.id,minimum_cents=v['minimum_cents'],allow_below_minimum=v['allow_below_minimum'],gift_confirmed=bool(q.gift_terms and v.get('confirm_gift')),reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='authorize':
            q=_q(db,row);_task(db,user,row,'authorize')
            if q.id!=v['quote_id'] or not _first(db,AddonApproval,quote_id=q.id) or _first(db,AddonAuthorization,quote_id=q.id):raise HTTPException(409,'客户授权须明确关联当前已获批报价')
            _proof(db,user,row,v['evidence_id'],'authorization')
            from .inventory_availability import assert_can_issue
            for l in _lines(db,row):
                prior=_rows(db,AddonReservation,case_id=row.id,line_key=l.line_key)
                if not prior:
                    item=_one(db,Item,l.item_id);assert_can_issue(db,item,l.quantity_milli);_reserve(db,user,row,l,l.quantity_milli,'reserve')
            from .member_pricing_service import record_authorization
            record_authorization(db,user,row,q.id,v['evidence_id'])
            db.add(AddonAuthorization(quote_id=q.id,evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='dispatch':_task(db,user,row,'dispatch');_dispatch(db,user,row,v)
        elif action=='install':
            _q(db,row,True);_task(db,user,row,'install');d=_one(db,AddonDispatch,v['dispatch_id'])
            if d.case_id!=row.id or _active(db,row) or v['quantity_milli']>_uninstalled(db,d):raise HTTPException(409,'实际安装超过本单原领料尚未安装数量，或原处置未结束')
            _proof(db,user,row,v['evidence_id'],'inspection');db.add(AddonInstallation(dispatch_id=d.id,quantity_milli=v['quantity_milli'],result=v['result'],evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='quality':
            _task(db,user,row,'quality');i=_one(db,AddonInstallation,v['installation_id']);d=_one(db,AddonDispatch,i.dispatch_id);last=_last_check(db,i)
            if d.case_id!=row.id or _active(db,row) or _installation_remaining(db,i)<=0 or last and (last.passed or not _first(db,AddonRectification,inspection_id=last.id)):raise HTTPException(409,'本批次未安装、已经通过、已处置或缺陷尚未整改，不能直接复检放行')
            _proof(db,user,row,v['evidence_id'],'inspection');db.add(AddonInspection(installation_id=i.id,passed=v['passed'],result=v['result'],evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='rectify':
            _task(db,user,row,'rectify');c=_one(db,AddonInspection,v['inspection_id']);i=_one(db,AddonInstallation,c.installation_id);d=_one(db,AddonDispatch,i.dispatch_id)
            if d.case_id!=row.id or _active(db,row) or c.passed or _last_check(db,i).id!=c.id or _first(db,AddonRectification,inspection_id=c.id):raise HTTPException(409,'整改须关联本单当前不合格检查')
            _proof(db,user,row,v['evidence_id'],'inspection');db.add(AddonRectification(inspection_id=c.id,result=v['result'],evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='accept':
            q=_q(db,row,True);_task(db,user,row,'accept')
            if v['quote_id']!=q.id or not _ready(db,row) or _first(db,AddonAcceptance,quote_id=q.id):raise HTTPException(409,'当前版尚有未领料、未施工、未合格或未完成处置，不能确认接收')
            _proof(db,user,row,v['evidence_id'],'authorization');facts=actual_income_rows(db,row);t=totals(db,row)
            amount=t['charge_cents']-sum(f['amount_cents'] for f in facts);value=t['cost_cents']-sum(f['value_cents'] for f in facts)
            if amount<0 or value<0:raise HTTPException(409,'本版接收增量与原履约事实不一致，请先核对处置')
            db.add(AddonAcceptance(case_id=row.id,quote_id=q.id,amount_cents=amount,value_cents=value,business_date=today(),evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='resolution':_resolution(db,user,row,v)
        elif action.startswith('resolution_') or action in {'return_receive','return_rectify','return_handback'}:_resolution_command(db,user,row,action,v)
        elif action=='receive':
            source_finance(db,user,row);_task(db,user,row,'receive');_proof(db,user,row,v['evidence_id'],'receipt')
            if v['amount_cents']>customer_due(db,row):raise HTTPException(409,'本次到账超过加装当前尚欠及未占用额度')
            link=flow.add_payment(db,user,row,v,amount=v['amount_cents']);record_collection(db,user,row,link,v['evidence_id'])
        elif action=='refund':_task(db,user,row,'refund');_refund(db,user,row,v)
        elif action=='cancel':
            if _rows(db,AddonAuthorization,quote_id=_q(db,row).id) if row.data.get('addon_quote_id') else False:raise HTTPException(409,'已授权加装须明确原数量取消及客户退款，不能普通取消')
            if _rows(db,AddonReservation,case_id=row.id) or _rows(db,AddonPayment,case_id=row.id):raise HTTPException(409,'已有实际占用或资金须原单处置')
            row.state='cancelled';flow.close_tasks(db,row,user)
        else:raise HTTPException(404,'加装办理动作不存在')
        flow.log_event(db,user,row,'addon_'+action,LABELS[action],detail=v);db.flush();sync_after_finance(db,user,row,v.get('evidence_id'));db.flush();return describe(db,user,row)
    return _execute(db,user,request_id,action,{'case_id':key,'version':version,'values':v},run)

def guard_order_delivery(db,order):
    for o in _rows(db,AddonOrder,source_order_id=order.id):
        row=_one(db,Case,o.id)
        if row.state=='cancelled' or not o.delivery_blocking:continue
        if not row.data.get('addon_quote_id') or not _ready(db,row):raise HTTPException(409,'交车前加装尚未完成本版授权、实物接收或收退款结清')
        t=totals(db,row)
        if _requires_acceptance(db,row) and not _first(db,AddonAcceptance,quote_id=_q(db,row).id) or t['receivable_cents'] or t['refund_due_cents']:raise HTTPException(409,'交车前加装尚未完成本版授权、实物接收或收退款结清')

def guard_parent_aftercare(db,user,order,phase='request'):
    excluded=set()
    for o in _rows(db,AddonOrder,source_order_id=order.id):
        row=_one(db,Case,o.id);excluded.add(row.id)
        if row.state=='cancelled':continue
        if not row.data.get('addon_quote_id'):raise HTTPException(409,'尚未报价的加装须明确取消，不得随父销售静默抹除')
        if any(_held(db,row,l.line_key) for l in _lines(db,row)):raise HTTPException(409,'请先在原加装单明确取消尚未领出项目')
        t=totals(db,row)
        if t['receivable_cents'] or t['refund_due_cents'] or t['reserved_cents']:raise HTTPException(409,'请先结清原加装的保留费用、原款退款及资金占额')
        if _requires_acceptance(db,row) and not _first(db,AddonAcceptance,quote_id=_q(db,row).id):raise HTTPException(409,'原加装已履约项目须有本版客户实际接收确认')
        for d in _rows(db,AddonDispatch,case_id=row.id):
            if _returned(db,d)+_gifted(db,d,phase=='apply')!=d.quantity_milli:raise HTTPException(409,'原加装须实际拆回或由客户明确同意装件不退款随车无偿移交；生效前须已接回原车')
        if any(p.status in ACTIVE and not (phase=='request' and p.kind=='vehicle_gift' and p.status=='consented') for p in _rows(db,AddonResolution,case_id=row.id)):raise HTTPException(409,'原加装处置仍未完成主管批准、客户同意或实际验收')
    return excluded

def finalize_vehicle_accessories(db,user,aftercare,source_order,new_vehicle,evidence_id):
    _role(user,{'admin','inventory'});single_store(db)
    from .vehicle_operations_models import VehicleOperation
    operation=db.scalar(select(VehicleOperation).where(VehicleOperation.aftercare_case_id==aftercare.id))
    if not operation or operation.source_order_id!=source_order.id or operation.kind!='customer_return':raise HTTPException(409,'装件移交缺少当前售后原VIN实际接收链')
    asset=flow.file_exists(db,_one(db,Case,operation.id),evidence_id)
    if asset.generated or new_vehicle.store_id!=source_order.store_id:raise HTTPException(409,'随车装件必须关联本店本次实际验收原件')
    guard_parent_aftercare(db,user,source_order,'request')
    for o in _rows(db,AddonOrder,source_order_id=source_order.id):
        row=_one(db,Case,o.id);target=_first(db,AddonTarget,case_id=row.id)
        for p in _rows(db,AddonResolution,case_id=row.id,kind='vehicle_gift',status='consented'):
            if not target or target.vin!=new_vehicle.vin or target.vehicle_id==new_vehicle.id:raise HTTPException(409,'装件实际移交须保留原VIN并关联本次退车新代次')
            attachments=[dict(item_id=_one(db,AddonLine,x['line_id']).item_id,name=_one(db,AddonLine,x['line_id']).name,quantity_milli=x['quantity_milli'],dispatch_id=x['dispatch_id'],installation_id=x['installation_id']) for x in p.lines]
            db.add(AddonVehicleHandover(case_id=row.id,resolution_id=p.id,aftercare_case_id=aftercare.id,vehicle_operation_id=operation.id,new_vehicle_id=new_vehicle.id,vin=new_vehicle.vin,attachments=attachments,incremental_value_cents=0,evidence_id=evidence_id,actor_id=user.id));p.status='completed';row.updated_at=utcnow();db.flush();_sync(db,user,row);flow.log_event(db,user,row,'addon_vehicle_handover','客户授权装件随原车实际无偿移交',detail={'resolution_id':p.id,'aftercare_case_id':aftercare.id,'new_vehicle_id':new_vehicle.id,'evidence_id':evidence_id});db.flush()

def describe(db,user,row):
    money=user.role in MONEY;cost=user.role in COST;o=_one(db,AddonOrder,row.id)
    def fields(x,names):return {k:(getattr(x,k).isoformat() if isinstance(getattr(x,k),date) else getattr(x,k)) for k in names}
    result=fields(row,['id','number','version','state','store_id','customer_id','business_date','due_date']);result.update(kind='addon',flow_version=3,source_order_id=o.source_order_id,source_number=o.source_snapshot['number'],delivery_blocking=o.delivery_blocking,quote=None,lines=[],dispatches=[],installations=[],inspections=[],rectifications=[],plans=[],return_postings=[],payments=[],acceptances=[],handovers=[],tasks=[],actions=[])
    if row.data.get('addon_quote_id'):
        q=_q(db,row);result['quote']=fields(q,['id','revision']);result['quote'].update(approved=bool(_first(db,AddonApproval,quote_id=q.id)),authorized=bool(_first(db,AddonAuthorization,quote_id=q.id)))
        if money:
            result['quote'].update(fields(q,['reason','goods_cents','installation_cents','discount_cents','pricing_version','gift_terms']))
            from .member_pricing_service import describe_quote
            member_price=describe_quote(db,user,row,q.id)
            if member_price:result['quote']['member_pricing']=member_price
    target=_first(db,AddonTarget,case_id=row.id);result['target']=fields(target,['vehicle_id','vin']) if target else None
    for l in _lines(db,row):
        d=fields(l,['id','line_key','item_id','sku','name','unit','work_item_id','work_code','work_name','quantity_milli']);d['held_milli']=_held(db,row,l.line_key)
        if money:
            d.update(fields(l,['goods_unit_cents','installation_unit_cents','goods_cents','installation_cents']));d['gift']=_q(db,row).gift_terms.get(l.line_key)
        result['lines'].append(d)
    for d in _rows(db,AddonDispatch,case_id=row.id):
        x=fields(d,['id','line_key','stock_move_id','quantity_milli','evidence_id']);x.update(uninstalled_milli=_uninstalled(db,d),remaining_milli=d.quantity_milli-_returned(db,d)-_gifted(db,d))
        if money:x.update(fields(d,['goods_cents','installation_cents']))
        if cost:x['value_cents']=d.value_cents
        result['dispatches'].append(x)
        for i in _rows(db,AddonInstallation,dispatch_id=d.id):
            x=fields(i,['id','dispatch_id','quantity_milli','result','evidence_id']);x['remaining_milli']=_installation_remaining(db,i);result['installations'].append(x)
            for c in _rows(db,AddonInspection,installation_id=i.id):
                x=fields(c,['id','installation_id','passed','result','evidence_id']);x['rectified']=bool(_first(db,AddonRectification,inspection_id=c.id));result['inspections'].append(x)
                for r in _rows(db,AddonRectification,inspection_id=c.id):result['rectifications'].append(fields(r,['id','inspection_id','result','evidence_id']))
    for p in _rows(db,AddonResolution,case_id=row.id):
        x=fields(p,['id','version','kind','status','quote_id']);x['lines']=[{k:v for k,v in l.items() if not k.endswith('_cents') or money and (k!='value_cents' or cost)} for l in p.lines];x['facts']=[fields(f,['id','action']+(['result'] if money or not f.action.startswith('resolution_') else [])) for f in _rows(db,AddonResolutionFact,resolution_id=p.id)]
        if money:x.update(reason=p.reason,evidence_id=p.evidence_id,refund_available_cents=_refund_resolution_limit(db,row,p))
        result['plans'].append(x)
    for p in _rows(db,AddonReturnPosting,case_id=row.id):
        x=fields(p,['id','resolution_id','dispatch_id','installation_id','quantity_milli','stock_move_id','business_date'])
        if money:x.update(fields(p,['goods_cents','installation_cents','retained_cents']))
        if cost:x['value_cents']=p.value_cents
        result['return_postings'].append(x)
    result['acceptances']=[fields(a,['id','quote_id','business_date']) for a in _rows(db,AddonAcceptance,case_id=row.id)]
    result['handovers']=[fields(h,['id','resolution_id','aftercare_case_id','new_vehicle_id','vin','attachments']) for h in _rows(db,AddonVehicleHandover,case_id=row.id)]
    if money:
        result['quote_history']=[]
        for q in _rows(db,AddonQuote,case_id=row.id):
            approval=_first(db,AddonApproval,quote_id=q.id);authorization=_first(db,AddonAuthorization,quote_id=q.id)
            result['quote_history'].append(dict(quote=fields(q,['id','revision','reason','goods_cents','installation_cents','discount_cents','pricing_version','gift_terms']),lines=[dict(**fields(l,['line_key','name','work_name','quantity_milli','goods_cents','installation_cents']),gift=q.gift_terms.get(l.line_key)) for l in _rows(db,AddonLine,quote_id=q.id)],approval=fields(approval,['minimum_cents','allow_below_minimum','reason','evidence_id','gift_confirmed']) if approval else None,authorization=fields(authorization,['evidence_id']) if authorization else None))
        result['totals']=totals(db,row)
        if not cost:result['totals'].pop('cost_cents')
        for p in _rows(db,PaymentLink,case_id=row.id):
            x=fields(p,['id','direction','amount_cents','original_id'])
            from .business_finance_models import FinanceCashBatch,FinanceCorrection
            batch=_first(db,FinanceCashBatch,cash_id=p.cash_id);x['cash_kind']=batch.kind if batch else 'collection' if p.direction=='in' else 'refund'
            x['superseded']=bool(_first(db,FinanceCorrection,original_cash_id=p.cash_id))
            x['available_cents']=max(0,p.amount_cents-sum(r.amount_cents for r in _rows(db,PaymentLink,original_id=p.id))) if p.direction=='in' else 0
            if cost:x.update(fields(p,['account_id','reference','cash_id']))
            result['payments'].append(x)
        from .business_finance_models import FinanceCreditLink
        result['credits']=[fields(c,['id','amount_cents','original_id']) for c in _rows(db,FinanceCreditLink,case_id=row.id)]
    for t in _rows(db,Task,case_id=row.id,status='open'):
        result['tasks'].append(fields(t,['id','key','title','assignee_id','due_date']))
    result['actions']=[a for a,roles in ROLES.items() if user.role in roles and row.state!='cancelled']
    return result

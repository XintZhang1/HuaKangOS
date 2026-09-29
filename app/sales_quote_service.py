"""V3 commercial revisions wrap the proven v2 physical and cash workflow."""
from datetime import date,datetime
from decimal import Decimal
import hashlib,json,uuid
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .tenancy import single_store
from .models import Vehicle,Sale,Store
from .flow_models import Case,Customer,Task,VehicleHold,PaymentLink,FileAsset
from .sales_quote_models import SalesQuote as Quote,SalesQuoteReview as Review,SalesQuoteResolution as Resolution,SalesQuoteConsent as Consent,SalesVehicleRelease as Release,SalesQuoteAdjustment as Adjustment
from . import flow_engine as flow

WRITE={'sales','manager','admin'}
SERVICE_KINDS=('addon','insurance','agency')
CURRENT_ORDER_VERSION=4

def is_quoted(row):return row.kind=='order' and row.flow_version in {3,4}
def clean(row):return {c.name:(getattr(row,c.name).isoformat() if isinstance(getattr(row,c.name),(date,datetime)) else getattr(row,c.name)) for c in row.__table__.columns}
def quote_digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _quote(db,row,key):
    quote=db.scalar(select(Quote).where(Quote.id==key,Quote.case_id==row.id)) if key else None
    if key and not quote:raise HTTPException(409,'订单报价来源不完整，请由管理员核对')
    return quote
def pending(db,row):return _quote(db,row,row.data.get('pending_quote_id'))
def active(db,row):return _quote(db,row,row.data.get('active_quote_id'))
def current(db,row):return pending(db,row) or active(db,row)
def review(db,quote):return db.scalar(select(Review).where(Review.quote_id==quote.id)) if quote else None
def _role(user,roles):
    if user.role not in roles:raise HTTPException(403,'当前岗位不能办理此报价事项')
def _get(db,user,key):
    single_store(db);row=flow.get_case(db,user,key)
    if not is_quoted(row):raise HTTPException(404,'请选择采用版本报价的本店车辆订单')
    return row
def _touch(db,row,version):
    db.scalar(select(Case).where(Case.id==row.id).with_for_update())
    if row.version!=version:raise HTTPException(409,'订单已变化，请刷新核对当前报价与办理状态')
    row.updated_at=utcnow();db.flush()
def _valid(quote):
    if quote.valid_until<today():raise HTTPException(409,'本版报价已超过确认有效期，请撤回后提交新的报价版本')
def _event(db,user,row,key,label,values):flow.log_event(db,user,row,'sales_quote_'+key,label,detail=values)

def _money_holds(db,row):
    from .business_finance_sources import case_reserved_amount
    from .group_service import case_reserved_amount as group_reserved
    from .group_benefits_service import case_reserved_amount as benefit_reserved
    return case_reserved_amount(db,row.id)+group_reserved(db,row.id)+benefit_reserved(db,row.id)

def vehicle_model(db,vehicle_id):
    from .vehicle_catalog_service import known_vehicle_models
    from .vehicle_catalog_models import VehicleClassification
    original=known_vehicle_models(db).get(vehicle_id)
    explicit=db.scalar(select(VehicleClassification).where(VehicleClassification.vehicle_id==vehicle_id))
    if original and explicit and original!=explicit.model_id:raise HTTPException(409,'车辆明确车型归属与原入库来源不一致')
    result=original or (explicit.model_id if explicit else None)
    if not result:raise HTTPException(409,'车辆尚无明确车型归属，请先由库管核对 VIN 和车型目录；不可仅按名称猜测')
    return result

def _proposal_guard(db,user,row,quote=None):
    if row.state not in {'reserved','executing'}:raise HTTPException(409,'当前订单状态不能变更报价')
    if flow.task_done(db,row,'dispatch') or row.data.get('dispatched_at'):raise HTTPException(409,'车辆已实际出库，请按退车或原单售后流程处理，不可覆盖报价')
    from .aftercare_service import guard_source_action as aftercare_guard
    aftercare_guard(db,user,row,'sales_quote')
    if _money_holds(db,row):raise HTTPException(409,'原单仍有预收或权益抵用占额，请先撤销在办占额再变更报价')
    if quote:
        old=active(db,row)
        if row.flow_version==4:
            from .sales_service_dispatch import guard_quote_change
            guard_quote_change(db,row,old,quote)
        for child in flow.children(db,row):
            if child.kind not in SERVICE_KINDS or child.flow_version!=2 or child.state in {'cancelled','rejected'}:continue
            if child.state!='pending' and not quote.services.get(child.kind):raise HTTPException(409,'已开始或已履约的配套服务不能由报价移除，请先办理对应终止及费用售后')
            if old and old.model_id!=quote.model_id and child.state!='pending':raise HTTPException(409,'原车型已有配套服务开始或完成，请先办理原实物、保单及费用售后，不可直接换车型')

def _new_quote(db,user,row,values):
    from .vehicle_catalog_service import model_snapshot
    snap=model_snapshot(db,values['model_id'])
    if snap['version']!=values['model_version']:raise HTTPException(409,'车型资料已更新，请刷新车型目录重新核对报价')
    due=date.fromisoformat(values['delivery_due']);expiry=date.fromisoformat(values['valid_until'])
    if not today()<=due<=date(2100,1,1) or not today()<=expiry<=date(2100,1,1):raise HTTPException(422,'交付日期和本版确认有效期不能早于今天或超出范围')
    revision=(db.scalar(select(func.max(Quote.revision)).where(Quote.case_id==row.id)) or 0)+1
    facts={'revision':revision,'prior_id':row.data.get('active_quote_id'),'model_id':snap['id'],'model_snapshot':snap,
        'amount_cents':values['amount_cents'],'delivery_due':due.isoformat(),'valid_until':expiry.isoformat(),
        'services':{kind:values[kind] for kind in SERVICE_KINDS},'terms':values['terms'],'reason':values['reason']}
    quote=Quote(case_id=row.id,**{**facts,'delivery_due':due,'valid_until':expiry},digest=quote_digest(facts),actor_id=user.id)
    _proposal_guard(db,user,row,quote)
    db.add(quote);db.flush();flow.set_data(row,pending_quote_id=quote.id)
    if not active(db,row):row.amount_cents=quote.amount_cents;row.due_date=quote.delivery_due;flow.set_data(row,model=snap['name'])
    flow.ensure_task(db,row,'quote_approve','复核车辆报价第 '+str(revision)+' 版','manager',due=quote.valid_until,reopen=True)
    _event(db,user,row,'propose','提交车辆报价新版本',{'quote_id':quote.id,'revision':revision,'digest':quote.digest,'reason':quote.reason})
    return quote

def _execute(db,user,key,operation,payload,callback):
    single_store(db);_role(user,WRITE);hashed=flow.request_digest(operation,payload)
    try:
        old=flow.prior_request(db,user,key,hashed)
        if old:return detail(db,user,old.id)
        row=callback();db.flush();flow.save_receipt(db,user,key,hashed,row);db.commit();return detail(db,user,row.id)
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'报价或车辆正在变化，请刷新核对；保留原请求编号查询结果')
    except Exception:db.rollback();raise

def create(db,user,key,values):
    def operation():
        if any(k in values for k in ('customer_name','customer_phone','confirm_new_customer')):
            from .customer_choice import resolve_customer
            customer=resolve_customer(db,user,values)
        else:
            customer=flow.scoped_get(db,Customer,values['customer_id'])
        if not customer:raise HTTPException(404,'本店客户不存在')
        if user.role=='sales' and customer.owner_id!=user.id:raise HTTPException(403,'仅可为本人负责的客户建立车辆报价')
        lead=None
        if values.get('lead_id'):
            lead=flow.get_case(db,user,values['lead_id'])
            if lead.kind!='lead' or lead.state!='intent' or lead.customer_id!=customer.id:raise HTTPException(409,'请选择本客户仍在意向跟进中的接待单')
            _touch(db,lead,values.get('lead_version'))
        elif values.get('lead_version'):raise HTTPException(422,'接待版本须与明确接待单一起提交')
        row=Case(number='HK'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='order',flow_version=CURRENT_ORDER_VERSION,state='reserved',
            title=customer.name+' · 车辆报价与交付',owner_id=user.id,created_by=user.id,customer_id=customer.id,parent_id=lead.id if lead else None,
            amount_cents=0,business_date=today(),due_date=today(),data={})
        db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);_new_quote(db,user,row,values['quote'])
        if lead:lead.state='converted';flow.close_tasks(db,lead,user);_event(db,user,lead,'convert','已建立版本报价订单',{'order_id':row.id})
        from .flow_documents import generate_document
        generate_document(db,user,row,'contract');return row
    return _execute(db,user,key,'sales_quote_create',values,operation)

def propose(db,user,case_id,key,version,values):
    def operation():
        row=_get(db,user,case_id);_touch(db,row,version)
        if user.role=='sales' and row.owner_id!=user.id:raise HTTPException(403,'报价变更须由本订单销售负责人办理')
        if pending(db,row):raise HTTPException(409,'请先处理或撤回当前在办报价，不能并行提交多个变更')
        if flow.paid_amount(db,row)>row.amount_cents:raise HTTPException(409,'上一版已批准的超收退款尚未办理完毕，请先完成原款退差额')
        _new_quote(db,user,row,values)
        from .flow_documents import generate_document
        generate_document(db,user,row,'contract');return row
    return _execute(db,user,key,'sales_quote_propose:'+str(case_id),{'version':version,'quote':values},operation)

def guard_source_action(db,user,row,action):
    if not is_quoted(row):return
    guard_child_action(db,user,row,action)
    if pending(db,row):raise HTTPException(409,'车辆报价尚待审批或客户确认，暂停资金抵用、收款更正及原单售后；请先完成或撤回本次报价')
    if not active(db,row):raise HTTPException(409,'车辆报价尚未获得本版客户签回，不能办理资金或售后')


def guard_child_action(db,user,source,action):
    """Only the new default sales version freezes children during cancellation."""
    if source.kind=='order' and source.flow_version==4 and source.state in {'cancel_review','refund_pending','cancelled'}:
        raise HTTPException(409,'原销售正在退订审批、退款或已经取消，不能新建或继续关联服务；如须继续，请先由主管拒绝退订并恢复原销售')

def blocking_reason(db,user,row,key):
    if not is_quoted(row):return ''
    physical={'allocate':{'admin','inventory'},'release_vehicle':{'admin','inventory'},'dispatch':{'admin','inventory'},'inspect':{'admin','service','technician'},'rectify':{'admin','service','technician'},'reinspect':{'admin','service','technician'}}
    if key in physical and user.role not in physical[key]:return '本步须由明确的库管或检测岗位确认实际事实，店长批准不能代替实物办理'
    quote=pending(db,row);old=active(db,row);approved=review(db,quote)
    if key in {'quote_approve','quote_reject','quote_withdraw'}:
        if not quote:return '当前没有待处理的新报价'
        if key!='quote_withdraw' and approved:return '本版报价已经复核，撤回后才能重新提交'
        if key!='quote_withdraw' and quote.actor_id==user.id:return '报价必须由另一位主管复核，不能审批本人提交的报价'
        if key=='quote_approve' and quote.valid_until<today():return '本版报价已过确认有效期，请撤回并重新报价'
        if key=='quote_withdraw' and row.vehicle_id and old and vehicle_model(db,row.vehicle_id)!=old.model_id:return '原配车已变更，请库管先释放当前配车再撤回报价'
        return ''
    if key=='release_vehicle':
        if not row.vehicle_id:return '当前没有已占用的配车'
        if not quote or not approved or approved.decision!='approved':return '释放原配车须先取得本次报价变更批准'
        if row.data.get('dispatched_at'):return '车辆已出库，不能释放销售占用；请办理实车退回'
        if any(c.kind in SERVICE_KINDS and c.state not in {'pending','cancelled','rejected'} for c in flow.children(db,row)):return '原配车服务已开始，请先处理原实物、保单及费用售后'
        return ''
    if key in {'allocate','sign'}:
        if quote and (not approved or approved.decision!='approved'):return '请先由独立主管批准本版报价'
        if quote and quote.valid_until<today():return '本版报价已过确认有效期，请撤回并重新报价'
        if not quote and not old:return '当前没有有效报价'
        if key=='sign' and quote and quote.valid_until<today():return '本版报价已过确认有效期，请撤回并重新报价'
        if key=='sign' and row.vehicle_id and vehicle_model(db,row.vehicle_id)!=(quote or old).model_id:return '当前车辆不符合本版报价车型，请库管释放原车并重新配车'
        return ''
    if quote:return '当前有尚未完成的报价审批或客户签回，请先办理或撤回本次变更'
    if key=='refund_excess':
        if flow.paid_amount(db,row)<=row.amount_cents:return '本单没有待退的超收车辆款'
    if key in {'receive','inspect','rectify','reinspect','dispatch','deliver'} and not old:return '当前报价尚未获得客户本版签回'
    if key in {'cancel_request','cancel_approve','refund'}:
        if _money_holds(db,row):return '请先释放在办预收或权益抵用占额，再处理退订'
        from .business_finance_sources import case_credit_amount
        if case_credit_amount(db,row.id):return '本单有已抵用预收，请从原单售后申请退订并选择原预收抵用退回，不能把抵用额当现金退款'
    return ''

def readiness(db,row):
    result=[];quote=active(db,row)
    if pending(db,row):result.append('报价变更尚待审批或本版客户签回')
    consent=flow.scoped_get(db,Consent,row.data.get('sales_consent_id')) if row.data.get('sales_consent_id') else None
    if not quote or not consent or consent.quote_id!=quote.id or consent.vehicle_id!=row.vehicle_id:result.append('当前车型、VIN 与报价缺少同版客户确认')
    if quote and row.vehicle_id and vehicle_model(db,row.vehicle_id)!=quote.model_id:result.append('当前配车与已确认车型不一致')
    if flow.paid_amount(db,row)>row.amount_cents:result.append('变更后的超收款尚未按原款退回')
    if _money_holds(db,row):result.append('尚有未完成的预收或权益抵用占额')
    if row.data.get('inspection',{}).get('vehicle_id')!=row.vehicle_id:result.append('当前配车尚无对应的合格交车检查')
    return result

def _task(db,row,key,title,role,reopen=False):
    existing=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    # Quote synchronization does not undo an employee's task handoff or date.
    return flow.ensure_task(db,row,key,title,role,None if existing else row.owner_id if role=='sales' else None,
        None if existing else row.due_date,reopen=reopen)

def _tasks(db,user,row):
    for key,title,role in [('allocate','选择报价车型配车','inventory'),('sign','确认本版合同签回','sales'),('receive','登记车辆款到账','finance'),('inspect','交车检查','service'),('dispatch','车辆出库','inventory'),('deliver','客户提车','sales')]:
        _task(db,row,key,title,role)

def _restore_tasks(db,user,row):
    quote=active(db,row)
    flow.finish_task(db,row,'quote_approve',user)
    if not quote:
        row.state='reserved'
        for t in db.scalars(select(Task).where(Task.case_id==row.id,Task.status=='open',Task.key.in_(['allocate','sign','receive','inspect','dispatch','deliver']))):t.status='cancelled';t.done_by=user.id;t.done_at=utcnow()
        return
    row.state='executing';_tasks(db,user,row)
    if not row.vehicle_id:
        _task(db,row,'allocate','重新选择原报价车型配车','inventory',reopen=True)
        _task(db,row,'sign','确认当前配车合同签回','sales',reopen=True)
    elif row.data.get('sales_consent_id'):flow.finish_task(db,row,'sign',user)

def apply_action(db,user,row,key,values):
    """Called only after catalogue role/state, case version and source guards."""
    if key in {'quote_approve','quote_reject','quote_withdraw','release_vehicle'} and not 2<=len(values.get('reason',''))<=500:
        raise HTTPException(422,'报价复核、撤回或配车释放说明须为 2 至 500 个字')
    quote=pending(db,row)
    if key in {'quote_approve','quote_reject','quote_withdraw'}:
        _role(user,{'admin','manager'} if key!='quote_withdraw' else WRITE)
        if not quote:raise HTTPException(409,'本单没有在办报价')
        _proposal_guard(db,user,row,quote)
        if key=='quote_approve':
            _valid(quote)
            db.add(Review(quote_id=quote.id,decision='approved',reason=values['reason'],actor_id=user.id))
            row.state='executing';flow.finish_task(db,row,'quote_approve',user);_tasks(db,user,row)
            _task(db,row,'sign','确认报价第 '+str(quote.revision)+' 版及当前配车','sales',reopen=True)
        else:
            if key=='quote_reject':db.add(Review(quote_id=quote.id,decision='rejected',reason=values['reason'],actor_id=user.id))
            db.add(Resolution(quote_id=quote.id,outcome='rejected' if key=='quote_reject' else 'withdrawn',reason=values['reason'],actor_id=user.id))
            flow.set_data(row,pending_quote_id=None);_restore_tasks(db,user,row)
    elif key=='release_vehicle':
        flow.file_exists(db,row,values['evidence_id']);car=db.scalar(select(Vehicle).where(Vehicle.id==row.vehicle_id).with_for_update())
        hold=db.scalar(select(VehicleHold).where(VehicleHold.case_id==row.id,VehicleHold.vehicle_id==row.vehicle_id))
        if not car or not hold or hold.delivered:raise HTTPException(409,'原配车占用不完整，不能释放')
        from .vehicle_transfer_service import assert_vehicle_available
        assert_vehicle_available(db,user,car)
        car.updated_at=utcnow();db.add(Release(case_id=row.id,quote_id=quote.id,vehicle_id=car.id,evidence_id=values['evidence_id'],reason=values['reason'],actor_id=user.id))
        db.delete(hold);row.vehicle_id=None;row.cost_cents=None
        flow.set_data(row,inspection_status=None,inspection={},sales_consent_id=None,signed_file=None)
        for taskkey,role,title in [('allocate','inventory','按本版车型重新配车'),('inspect','service','对重新配车开展交车检查'),('sign','sales','重新配车后确认本版合同签回')]:
            _task(db,row,taskkey,title,role,reopen=True)
        for task in db.scalars(select(Task).where(Task.case_id==row.id,Task.key.in_(['rectify','reinspect']),Task.status=='open')):task.status='cancelled';task.done_by=user.id;task.done_at=utcnow()
    elif key=='allocate':
        selected=current(db,row);car=db.scalar(select(Vehicle).where(Vehicle.id==values['vehicle_id']).with_for_update())
        if not car or car.approval_state!='approved':raise HTTPException(422,'请选择本店已审核入库车辆')
        from .vehicle_transfer_service import assert_vehicle_available
        assert_vehicle_available(db,user,car)
        if vehicle_model(db,car.id)!=selected.model_id:raise HTTPException(409,'所选车辆的明确车型与本版报价不一致')
        if db.scalar(select(Sale.id).where(Sale.active_vehicle_id==car.id)) or db.scalar(select(VehicleHold).where(VehicleHold.vehicle_id==car.id)):raise HTTPException(409,'该车已被其他订单占用')
        car.updated_at=utcnow();db.add(VehicleHold(vehicle_id=car.id,case_id=row.id));row.vehicle_id=car.id;row.cost_cents=car.purchase_cost_cents
        flow.finish_task(db,row,'allocate',user)
        # The responsible salesperson generates the VIN-bound contract. Stock
        # confirmation must not require financial document privileges.
    elif key=='sign':
        from .flow_documents import verify_signed
        selected=current(db,row);verify_signed(db,row,values['evidence_id'],'contract',user=user)
        asset=flow.file_exists(db,row,values['evidence_id'],'signed_contract');source=flow.scoped_get(db,FileAsset,asset.source_file_id)
        from .business_finance_sources import case_credit_amount
        consent=Consent(quote_id=selected.id,vehicle_id=row.vehicle_id,evidence_id=asset.id,source_file_id=source.id,fingerprint=source.source_fingerprint,
            paid_before_cents=flow.paid_amount(db,row),advance_before_cents=case_credit_amount(db,row.id),actor_id=user.id)
        db.add(consent);db.flush()
        if quote:
            _proposal_guard(db,user,row,quote);_valid(quote)
            db.add(Resolution(quote_id=quote.id,outcome='activated',reason='客户按本版车型、VIN、价款及条款签回',actor_id=user.id));db.flush()
            old_due=row.due_date;row.amount_cents=quote.amount_cents;row.due_date=quote.delivery_due
            if old_due!=quote.delivery_due:
                for task in db.scalars(select(Task).where(Task.case_id==row.id,Task.status=='open',Task.due_date==old_due,
                        Task.key.in_(['allocate','sign','receive','inspect','dispatch','deliver']))):task.due_date=quote.delivery_due
            flow.set_data(row,active_quote_id=quote.id,pending_quote_id=None,model=quote.model_snapshot['name'],**quote.services)
            _sync_services(db,user,row,quote)
            from .sales_quote_finance import restore_excess_advance
            restore_excess_advance(db,user,row,quote,asset.id)
        flow.set_data(row,sales_consent_id=consent.id,signed_file=asset.id)
        flow.finish_task(db,row,'sign',user);_sync_cash_tasks(db,user,row)
    elif key=='refund_excess':
        if values['amount']>flow.paid_amount(db,row)-row.amount_cents:raise HTTPException(409,'退款不得超过本版已生效报价的实际超收差额')
        original=flow.scoped_get(db,PaymentLink,values['original_id'])
        if not original:raise HTTPException(422,'本店原收款不存在')
        link=flow.add_payment(db,user,row,values,'out',original)
        db.add(Adjustment(quote_id=active(db,row).id,kind='cash_refund',payment_id=link.id,amount_cents=link.amount_cents,evidence_id=values['evidence_id'],actor_id=user.id))
        _sync_cash_tasks(db,user,row)
    else:
        flow._apply_action_v2(db,user,row,key,values)

def _sync_cash_tasks(db,user,row):
    paid=flow.paid_amount(db,row)
    if paid>row.amount_cents:flow.ensure_task(db,row,'refund_excess','按原款退回已确认报价差额','finance',reopen=True)
    else:flow.finish_task(db,row,'refund_excess',user)
    if paid<row.amount_cents:flow.ensure_task(db,row,'receive','登记当前报价未收车辆款','finance',reopen=True)
    else:flow.finish_task(db,row,'receive',user)

def _sync_services(db,user,row,quote):
    if row.flow_version==4:
        from .sales_service_dispatch import synchronize
        return synchronize(db,user,row,quote)
    customer=flow.scoped_get(db,Customer,row.customer_id)
    for kind in SERVICE_KINDS:
        live=[c for c in flow.children(db,row) if c.kind==kind and c.flow_version==2 and c.state not in {'cancelled','rejected'}]
        if not quote.services[kind]:
            for child in live:
                if child.state!='pending':raise HTTPException(409,'配套服务已开始，不能直接移除')
                child.state='cancelled';child.completed_date=today();flow.close_tasks(db,child,user)
                flow.log_event(db,user,child,'sales_quote_remove','客户新报价取消尚未开始的配套服务',detail={'quote_id':quote.id})
        elif not live:flow.new_case(db,user,kind,{},row,customer,internal=True)

def detail(db,user,key):
    row=_get(db,user,key)
    from .flow_api import case_detail
    info=case_detail(row.id,db,user)
    quotes=list(db.scalars(select(Quote).where(Quote.case_id==row.id).order_by(Quote.revision)))
    ids=[q.id for q in quotes];reviews={r.quote_id:r for r in db.scalars(select(Review).where(Review.quote_id.in_(ids)))}
    resolutions={r.quote_id:r for r in db.scalars(select(Resolution).where(Resolution.quote_id.in_(ids)))}
    visible=flow.money_visible(user,row)
    result=[]
    for q in quotes:
        value=clean(q)
        value.update(review=clean(reviews[q.id]) if q.id in reviews else None,resolution=clean(resolutions[q.id]) if q.id in resolutions else None)
        if not visible:
            for field in ('amount_cents','terms','reason','review'):value.pop(field,None)
            value['model_snapshot']={k:v for k,v in q.model_snapshot.items() if 'price' not in k}
            if value['resolution']:value['resolution']={k:v for k,v in value['resolution'].items() if k!='reason'}
        result.append(value)
    info.update(quotes=result,pending_quote_id=row.data.get('pending_quote_id'),active_quote_id=row.data.get('active_quote_id'),
        can_propose=user.role in WRITE and (user.role!='sales' or row.owner_id==user.id) and not pending(db,row) and row.state in {'reserved','executing'} and not row.data.get('dispatched_at'))
    if visible:info['excess_cents']=max(0,flow.paid_amount(db,row)-row.amount_cents)
    from .sales_quote_facts import project_facts
    info['business_facts']=project_facts(db,user,row)
    return info

def vehicles(db,user,key):
    row=_get(db,user,key);_role(user,{'admin','manager','inventory'})
    quote=current(db,row)
    if not quote:return {'items':[]}
    from .vehicle_catalog_service import catalogue
    result=catalogue(db,user,model_id=quote.model_id,include_inactive=True)
    matched=next((model for model in result['items'] if model['id']==quote.model_id),None)
    cars=[v for v in matched['vehicles'] if v['available']] if matched else []
    return {'items':[{'id':v['id'],'label':v['vin']+' · '+quote.model_snapshot['name']+' · '+str(v.get('color') or '')} for v in cars]}

def document_snapshot(db,row,kind):
    selected=active(db,row) if kind=='handover' else current(db,row)
    if not selected:raise HTTPException(409,'本单没有可生成的有效报价版本')
    if kind=='handover' and (pending(db,row) or not row.data.get('sales_consent_id')):raise HTTPException(409,'本版报价尚未完成客户确认，不能生成交付确认单')
    customer=flow.scoped_get(db,Customer,row.customer_id);store=db.get(Store,row.store_id);car=flow.scoped_get(db,Vehicle,row.vehicle_id) if row.vehicle_id else None
    snap=selected.model_snapshot
    fuel={'electric':'纯电动','petrol':'汽油','diesel':'柴油','hybrid':'混合动力','plugin_hybrid':'插电混动','phev':'插电混动','hydrogen':'氢能源','other':'其他'}.get(snap['fuel_type'],snap['fuel_type'])
    info={'单据编号':row.number,'门店':store.name,'客户':customer.name,'联系电话':customer.phone,
        '报价版本':selected.revision,'报价校验摘要':selected.digest,'车型目录编码':snap['code'],'品牌 / 车系':str(snap.get('brand_name') or snap.get('brand',''))+' / '+str(snap.get('series_name') or '未设置'),
        '订购车型':snap['name'],'车型资料版本':snap['version'],'车型参数':str(snap['model_year'])+' 年 / '+fuel+' / '+str(snap['seats'])+' 座',
        '车架号':car.vin if car else '待配车（正式客户确认前须绑定实车）','车辆约定金额（元）':format(Decimal(selected.amount_cents)/100,'.2f'),
        '预计交付日期':selected.delivery_due.isoformat(),'本版确认有效期':selected.valid_until.isoformat(),
        '另单办理服务':'、'.join(label for key,label in [('addon','精品加装'),('insurance','本店保险'),('agency','代办服务')] if selected.services[key]) or '无',
        '金额口径':'车辆价款不含另单确认的精品加装、保险和代办费用；配套服务须分别批准和客户确认。',
        '本版约定':selected.terms}
    return info

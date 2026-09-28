"""VIN purchase workflow. Approval, cash, transit and physical receipt are separate facts."""
from datetime import timedelta
import uuid,json
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .models import Vehicle,Sale,Store,CashEntry
from .flow_models import Case,VehicleHold,Account
from .group_models import GroupIdentity,GroupIdentityLink
from .group_service import authority as identity_authority
from .transfer_service import authority,assert_task
from .vehicle_transfer_models import VehicleCustody
from .master_data import require_active
from .flow_documents import can_file
from . import flow_engine as flow
from . import business_entity_service as entities
from .vehicle_procurement_models import (VehiclePurchaseOrder as Order,VehiclePurchaseLine as Line,VehiclePurchasePrice as Price,
    VehiclePurchaseShipment as Shipment,VehiclePurchaseReceipt as Receipt,VehiclePurchaseReturn as Return,
    VehiclePurchaseCancellation as Cancellation,VehiclePurchaseFundsRequest as Funds,VehiclePurchasePayment as Payment,VehiclePurchaseMovement as Movement)

READ={'admin','manager','inventory','finance','auditor'}
MONEY={'admin','manager','finance','auditor'}
MANAGE={'admin','manager'}
ROLES={'approve':MANAGE,'reject':MANAGE,'cancel_remaining':MANAGE,'request_funds':MANAGE,'cancel_funds':MANAGE,
    'pay':{'admin','finance'},'refund':{'admin','finance'},'ship':{'admin','inventory'},'receive':{'admin','inventory'},
    'return_request':{'admin','inventory'},'return_approve':MANAGE,'return_cancel':MANAGE,'return_dispatch':{'admin','inventory'}}
LABELS={'approve':'批准整车采购与逐行价格','reject':'拒绝整车采购计划','cancel_remaining':'终止未发运余量',
    'request_funds':'申请采购付款','cancel_funds':'取消未付请款余量','pay':'登记实际采购付款','refund':'登记原款实际退回',
    'ship':'核对供应商逐VIN发运','receive':'逐VIN实际验收入库','return_request':'申请整车退回','return_approve':'批准整车退回',
    'return_cancel':'撤销未发出退车','return_dispatch':'确认实车退回供应商'}
# 请款、付款与原款退回属于资金事实；后勤岗位不得用业务/检测凭据顶替。
PROCUREMENT_FINANCIAL_CATEGORIES=('receipt','invoice','signed_contract','procurement_contract')


def rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(*model.__table__.primary_key.columns)))
def one(db,model,key):
    row=db.scalar(select(model).where(model.id==key).with_for_update())
    if not row:raise HTTPException(404,'当前门店记录不存在')
    return row
def get_order(db,user,key):
    if user.role not in READ:raise HTTPException(403,'当前岗位不能读取整车采购')
    row=flow.get_case(db,user,key)
    if row.kind!='vehicle_procurement' or row.flow_version!=2:raise HTTPException(404,'整车采购单不存在或版本不支持')
    return row,one(db,Order,key)
def evidence(db,user,row,key,financial=False):
    asset=flow.file_exists(db,row,key)
    if not can_file(user,row,asset):raise HTTPException(403,flow.category_requirement_message(asset.category,None,role=user.role))
    if asset.generated:raise HTTPException(422,'请使用实际业务凭据，系统模板不能证明实际收款或交接')
    if financial and asset.category not in PROCUREMENT_FINANCIAL_CATEGORIES:
        raise HTTPException(422,flow.category_requirement_message(asset.category,PROCUREMENT_FINANCIAL_CATEGORIES))
    return asset


def totals(db,row):
    lines=rows(db,Line,case_id=row.id);prices={p.line_id:p for p in rows(db,Price,case_id=row.id)}
    cancelled=sum(c.quantity*prices[c.line_id].unit_cost_cents for c in rows(db,Cancellation,case_id=row.id)) if prices else 0
    shipments=rows(db,Shipment,case_id=row.id);receipts=rows(db,Receipt,case_id=row.id);moves=rows(db,Movement,case_id=row.id)
    returned=sum(-m.value_cents for m in moves if m.kind=='return')
    cancelled_transit=sum(prices[s.line_id].unit_cost_cents for s in shipments if s.status=='returned' and not any(r.shipment_id==s.id for r in receipts))
    received=sum(r.value_cents for r in receipts);paid=sum(p.amount_cents*(1 if p.direction=='out' else -1) for p in rows(db,Payment,case_id=row.id))
    commitment=row.amount_cents-cancelled-cancelled_transit-returned
    accepted=received-returned;transit=sum(1 for s in shipments if s.status=='transit')
    # Advance for outstanding acquisition differs from money owed back after cancellation.
    refund_due=max(0,paid-commitment);advance=max(0,paid-accepted-refund_due)
    unapplied=paid;due_rows=[]
    for receipt in sorted(receipts,key=lambda r:(r.due_date,r.id)):
        value=receipt.value_cents+sum(m.value_cents for m in moves if m.shipment_id==receipt.shipment_id and m.kind=='return')
        applied=min(value,unapplied);unapplied-=applied
        if value>applied:due_rows.append({'receipt_id':receipt.id,'due_date':receipt.due_date.isoformat(),'amount_cents':value-applied})
    return {'approved_cents':row.amount_cents,'cancelled_cents':cancelled+cancelled_transit,'received_cents':received,'returned_cents':returned,
        'commitment_cents':commitment,'paid_net_cents':paid,'payable_cents':max(0,accepted-paid),'prepaid_cents':advance,
        'supplier_refund_due_cents':refund_due,'due_rows':due_rows,'in_transit_quantity':transit,
        'in_transit_cents':sum(prices[s.line_id].unit_cost_cents for s in shipments if s.status=='transit'),'received_quantity':len(receipts),
        'returned_quantity':sum(m.kind=='return' for m in moves),'unshipped_quantity':sum(l.quantity for l in lines)-sum(c.quantity for c in rows(db,Cancellation,case_id=row.id))-len(shipments)}


def describe(db,user,row):
    header=one(db,Order,row.id);money=user.role in MONEY
    def fields(obj,names):return {k:getattr(obj,k) for k in names}
    result=fields(row,['id','number','state','version','flow_version','store_id'])|{'supplier_name':header.supplier_name,'supplier_id':header.supplier_id,
        'reason':header.reason,'contracting_party':header.contracting_party,'business_date':row.business_date.isoformat(),'due_date':row.due_date.isoformat()}
    lines=rows(db,Line,case_id=row.id);shipments=rows(db,Shipment,case_id=row.id);cancels=rows(db,Cancellation,case_id=row.id)
    prices={p.line_id:p for p in rows(db,Price,case_id=row.id)}
    result['lines']=[]
    for line in lines:
        detail=fields(line,['id','model_id','model_code','model_name','brand','model_year','fuel_type','color','quantity'])
        detail['unshipped_quantity']=line.quantity-sum(s.line_id==line.id for s in shipments)-sum(c.quantity for c in cancels if c.line_id==line.id)
        if money and line.id in prices:detail.update(unit_cost_cents=prices[line.id].unit_cost_cents,list_price_cents=prices[line.id].list_price_cents)
        result['lines'].append(detail)
    result['shipments']=[fields(s,['id','line_id','vin','status','evidence_id'])|{'shipped_date':s.shipped_date.isoformat(),'expected_date':s.expected_date.isoformat()} for s in shipments]
    result['receipts']=[fields(r,['id','shipment_id','vehicle_id','location_id','evidence_id'])|({'value_cents':r.value_cents,'due_date':r.due_date.isoformat()} if money else {}) for r in rows(db,Receipt,case_id=row.id)]
    result['returns']=[fields(r,['id','version','shipment_id','status','reason','evidence_id']) for r in rows(db,Return,case_id=row.id)]
    result['movements']=[fields(m,['id','shipment_id','vehicle_id','kind','quantity','original_id','evidence_id'])|({'value_cents':m.value_cents} if money else {}) for m in rows(db,Movement,case_id=row.id)]
    result['cancellations']=[fields(c,['line_id','quantity','reason']) for c in cancels]
    payments=rows(db,Payment,case_id=row.id)
    result['funds_requests']=[fields(r,['id','version','amount_cents','status','reason','evidence_id'])|{'unpaid_cents':r.amount_cents-sum(p.amount_cents for p in payments if p.funds_request_id==r.id)} for r in rows(db,Funds,case_id=row.id)] if money else []
    result['payments']=[fields(p,['id','direction','amount_cents','account_id','original_id','funds_request_id','reference','cash_id','evidence_id']) for p in payments] if money else []
    if money:result['totals']=totals(db,row)
    result['actions']=[k for k,roles in ROLES.items() if user.role in roles]
    return result


def execute(db,user,key,action,payload,op,roles):
    # Shared authority protects central VIN custody as well as physical transfers.
    with authority(db,user,roles):
        digest=flow.request_digest('vehicle_purchase_'+action,json.loads(json.dumps(payload,default=str)))
        try:
            old=flow.prior_request(db,user,key,digest)
            if old:return describe(db,user,get_order(db,user,old.id)[0])
            row=op();db.flush();flow.save_receipt(db,user,key,digest,row);db.commit();return describe(db,user,row)
        except (IntegrityError,OperationalError,StaleDataError) as exc:
            db.rollback();raise HTTPException(409,'记录、VIN或流水冲突；本次未保存，请刷新核对并保留原请求编号') from exc
        except Exception:db.rollback();raise


def create(db,user,key,v):
    def op():
        supplier=require_active(db,'suppliers',v['supplier_id'])
        if len({(l['model_id'],l['color']) for l in v['lines']})!=len(v['lines']):raise HTTPException(422,'同车型同颜色请合并数量')
        if not today()<=v['due_date']<=today()+timedelta(days=365):raise HTTPException(422,'计划到货日期须为今天起一年内')
        row=Case(number='HKVP'+uuid.uuid4().hex[:18].upper(),kind='vehicle_procurement',flow_version=2,state='approval',
            title='整车采购计划 · '+supplier.name,owner_id=user.id,created_by=user.id,business_date=today(),due_date=v['due_date'],amount_cents=0,data={})
        db.add(row);db.flush()
        context=entities.freeze_case_entity(db,user,row)
        if context and entities.case_entity_snapshot(db,user,row)['entity']['legal_name']!=v['contracting_party']:
            raise HTTPException(409,'采购合同经营主体必须与本店本次冻结的批准主体一致，不能使用集团品牌或其他公司名称')
        db.add(Order(id=row.id,supplier_id=supplier.id,supplier_name=supplier.name,supplier_code=supplier.code,
            payment_terms_days=supplier.payment_terms_days,contracting_party=v['contracting_party'],reason=v['reason']))
        for item in v['lines']:
            model=require_active(db,'vehicle_models',item['model_id'])
            db.add(Line(case_id=row.id,model_id=model.id,model_code=model.code,model_name=model.name,brand=model.brand,model_year=model.model_year,
                fuel_type=model.fuel_type,color=item['color'],quantity=item['quantity']))
        flow.ensure_task(db,row,'vp_approve','主管确认整车数量、单车成本及采购约定','manager')
        flow.log_event(db,user,row,'vp_create','提交整车采购计划',detail={'line_count':len(v['lines'])});return row
    return execute(db,user,key,'create',v,op,{'admin','manager','inventory'})


def assert_no_purchase_return(db,vehicle_id):
    if db.scalar(select(Return.id).join(Receipt,Receipt.shipment_id==Return.shipment_id).where(Receipt.vehicle_id==vehicle_id,Return.status.in_(['requested','approved'])).limit(1)):
        raise HTTPException(409,'车辆已有采购退回申请，不能配车或调拨；先核对退回安排')


def _vin_state(db,vin,ignore_shipment=None):
    """Read-only global conflict check; never expose another store's business rows."""
    previous={k:db.info.get(k) for k in ('store_scope','write_store')};generation=0;blocked=False
    store_ids=list(db.scalars(select(Store.id)))
    with db.no_autoflush:
        try:
            for sid in store_ids:
                db.info['store_scope']=(sid,);db.info['write_store']=None
                claim=select(Shipment.id).where(Shipment.active_vin==vin)
                if ignore_shipment:claim=claim.where(Shipment.id!=ignore_shipment)
                if db.scalar(claim.limit(1)):blocked=True
                for car in db.scalars(select(Vehicle).where(Vehicle.vin==vin)):
                    generation=max(generation,car.inventory_generation)
                    holds=rows(db,VehicleHold,vehicle_id=car.id)
                    sales=rows(db,Sale,vehicle_id=car.id)
                    delivered_holds={h.case_id for h in holds if h.delivered and db.scalar(select(Case.id).where(Case.id==h.case_id,Case.kind=='order',Case.state.in_(['delivered','completed','credit_open']),Case.completed_date.is_not(None)))}
                    sold=bool(delivered_holds) or any(s.approval_state=='approved' and s.sale_stage=='delivered' and s.delivery_date for s in sales)
                    unfinished=any(h.case_id not in delivered_holds for h in holds) or any(s.approval_state=='approved' and s.sale_stage!='delivered' for s in sales)
                    if unfinished or (car.approval_state not in {'void','rejected'} and not sold):blocked=True
        finally:
            for k,v in previous.items():
                if v is None:db.info.pop(k,None)
                else:db.info[k]=v
    return blocked,generation


def _custody(db,user,vin,model,ignore_shipment=None):
    from .vehicle_operations_service import assert_no_vehicle_operation
    assert_no_vehicle_operation(db,vin=vin)
    custody=db.scalar(select(VehicleCustody).where(VehicleCustody.vin==vin).with_for_update())
    if custody and custody.pending_transfer_id:raise HTTPException(409,'该VIN存在库存、销售或调拨占用，请核对原记录')
    blocked,generation=_vin_state(db,vin,ignore_shipment)
    if blocked:raise HTTPException(409,'该VIN存在库存、销售或发运占用，请核对原记录')
    if not custody:
        with identity_authority(db,user,{'admin','inventory'}):
            identity=db.scalar(select(GroupIdentity).where(GroupIdentity.kind=='vehicle',GroupIdentity.canonical_key==vin))
            if not identity:
                identity=GroupIdentity(kind='vehicle',name=model,canonical_key=vin,search_key=vin,created_by=user.id);db.add(identity);db.flush()
            custody=VehicleCustody(vin=vin,identity_id=identity.id,current_vehicle_id=None,current_store_id=None,generation=generation)
            db.add(custody);db.flush()
    custody.generation=max(custody.generation,generation);custody.current_vehicle_id=None;custody.current_store_id=None;custody.version+=1
    return custody


def _sync(db,user,row):
    if row.state in {'approval','rejected'}:return
    t=totals(db,row)
    pending=any(r.status in {'requested','approved'} for r in rows(db,Return,case_id=row.id))
    openfunds=any(r.status=='open' for r in rows(db,Funds,case_id=row.id))
    stages={'vp_ship':(t['unshipped_quantity']>0,'inventory','登记供应商逐VIN实际发运'),
        'vp_receive':(t['in_transit_quantity']>0,'inventory','核对实车VIN并验收或申请退回'),
        'vp_pay':(openfunds,'finance','按获准请款登记分笔实际付款'),
        'vp_request_funds':(t['payable_cents']>0 and not openfunds,'manager','安排已验收整车应付款'),
        'vp_refund':(t['supplier_refund_due_cents']>0,'finance','核对原付款账户实际退款'),
        'vp_return_approve':(any(r.status=='requested' for r in rows(db,Return,case_id=row.id)),'manager','复核整车退回申请'),
        'vp_return_dispatch':(any(r.status=='approved' for r in rows(db,Return,case_id=row.id)),'inventory','核对原车并实际退回供应商')}
    for key,(needed,role,title) in stages.items():
        if needed:flow.ensure_task(db,row,key,title,role,reopen=True)
        else:flow.finish_task(db,row,key,user)
    done=not(t['unshipped_quantity'] or t['in_transit_quantity'] or t['payable_cents'] or t['supplier_refund_due_cents'] or pending or openfunds)
    row.state='completed' if done else 'receiving';row.completed_date=today() if done else None


def _cash(db,user,row,v,original=None):
    account=one(db,Account,v['account_id'])
    if not account.active:raise HTTPException(409,'资金账户已停用')
    if original and account.id!=original.account_id:raise HTTPException(409,'退款必须回到原付款账户')
    entities.require_account_entity(db,user,row,account.id,today(),original_cash_id=original.cash_id if original else None)
    if db.scalar(select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==v['reference'])):raise HTTPException(409,'该账户流水编号已登记，不能重复记款')
    account.updated_at=utcnow();direction='in' if original else 'out'
    cash=CashEntry(doc_no='HKVPC'+uuid.uuid4().hex[:24],business_date=today(),created_by=user.id,approval_state='approved',direction=direction,
        category='vehicle_procurement_refund' if original else 'vehicle_procurement_payment',amount_cents=v['amount_cents'],account=account.name,
        payment_method='cash' if account.account_type=='cash' else 'bank',voucher_no=v['reference'],counterparty=one(db,Order,row.id).supplier_name,note='整车采购 '+row.number)
    db.add(cash);db.flush();entities.record_cash_entity(db,user,row,cash,account.id,original_cash_id=original.cash_id if original else None)
    db.add(Payment(case_id=row.id,cash_id=cash.id,account_id=account.id,direction=direction,amount_cents=v['amount_cents'],
        original_id=original.id if original else None,funds_request_id=None if original else v['funds_request_id'],reference=v['reference'],evidence_id=v['evidence_id']))


def command(db,user,case_id,key,version,action,v):
    if action not in ROLES:raise HTTPException(404,'整车采购动作不存在')
    return execute(db,user,key,action,{'case_id':case_id,'version':version,**v},
        lambda:command_in_transaction(db,user,case_id,version,action,v),ROLES[action])


def command_in_transaction(db,user,case_id,version,action,v):
    """Shared guarded primitive; caller owns one outer atomic commit/idempotency receipt."""
    if action not in ROLES:raise HTTPException(404,'整车采购动作不存在')
    if not db.info.get('_transfer_authority') or user.role not in ROLES[action]:raise HTTPException(403,'当前岗位不能办理此采购动作')
    row,header=get_order(db,user,case_id)
    if row.version!=version:raise HTTPException(409,'整车采购单已变化，请刷新核对，不能覆盖并行办理')
    task_key={'approve':'vp_approve','reject':'vp_approve','ship':'vp_ship','receive':'vp_receive','pay':'vp_pay','refund':'vp_refund',
        'return_approve':'vp_return_approve','return_dispatch':'vp_return_dispatch'}.get(action)
    if task_key:assert_task(db,user,row,task_key)
    row.updated_at=utcnow()
    if action in {'approve','reject'}:
        if row.state!='approval':raise HTTPException(409,'采购计划已复核，不能重复审批')
        if row.created_by==user.id and user.role!='admin':raise HTTPException(403,'申请与批准须由不同员工办理')
        if action=='approve':
            require_active(db,'suppliers',header.supplier_id);evidence(db,user,row,v['evidence_id'],True)
            lines=rows(db,Line,case_id=row.id)
            if len(v['prices'])!=len(lines) or {p['line_id'] for p in v['prices']}!={l.id for l in lines}:raise HTTPException(422,'须逐行确认全部车型价格，不得重复或遗漏')
            row.amount_cents=0
            for value in v['prices']:
                line=one(db,Line,value['line_id']);require_active(db,'vehicle_models',line.model_id)
                row.amount_cents+=line.quantity*value['unit_cost_cents']
                db.add(Price(case_id=row.id,approved_by=user.id,evidence_id=v['evidence_id'],**value))
            if row.amount_cents>1_000_000_000_000:raise HTTPException(422,'采购金额超出本版上限')
            row.state='receiving'
        else:row.state='rejected';row.completed_date=today()
        flow.finish_task(db,row,'vp_approve',user)
    else:
        if row.state not in {'receiving','completed'}:raise HTTPException(409,'采购尚未批准或已经拒绝')
        if 'evidence_id' in v:
            asset=evidence(db,user,row,v['evidence_id'],action in {'request_funds','pay','refund'})
            if action in {'pay','refund'} and asset.category!='receipt':raise HTTPException(422,'实际收退款须上传收退款凭据；采购合同不能代替资金到账证据')
        if action=='cancel_remaining':
            changed=False
            for line in rows(db,Line,case_id=row.id):
                remaining=line.quantity-len(rows(db,Shipment,line_id=line.id))-sum(c.quantity for c in rows(db,Cancellation,line_id=line.id))
                if remaining:db.add(Cancellation(case_id=row.id,line_id=line.id,quantity=remaining,reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id));changed=True
            if not changed:raise HTTPException(409,'没有未发运余量；已发运车辆必须验收或办理实物退回')
        elif action=='request_funds':
            t=totals(db,row);payments=rows(db,Payment,case_id=row.id)
            reserved=sum(f.amount_cents-sum(p.amount_cents for p in payments if p.funds_request_id==f.id) for f in rows(db,Funds,case_id=row.id) if f.status=='open')
            if v['amount_cents']>t['commitment_cents']-t['paid_net_cents']-reserved:raise HTTPException(409,'请款超过尚未支付且未占请款的有效采购约定')
            db.add(Funds(case_id=row.id,requested_by=user.id,**v))
        elif action=='cancel_funds':
            funds=one(db,Funds,v['funds_request_id'])
            if funds.case_id!=row.id or funds.status!='open':raise HTTPException(409,'请款不存在或未付余量已结束')
            if funds.version!=v['funds_version']:raise HTTPException(409,'请款已变化，请刷新')
            funds.status='cancelled'
        elif action=='pay':
            funds=one(db,Funds,v['funds_request_id']);t=totals(db,row)
            if funds.case_id!=row.id or funds.status!='open':raise HTTPException(409,'请选择本单有效请款')
            paid=sum(p.amount_cents for p in rows(db,Payment,funds_request_id=funds.id))
            if v['amount_cents']>min(funds.amount_cents-paid,t['commitment_cents']-t['paid_net_cents']):raise HTTPException(409,'付款超过请款余量或有效采购约定；请核对取消及退车')
            _cash(db,user,row,v)
            if paid+v['amount_cents']==funds.amount_cents:funds.status='closed'
            funds.updated_at=utcnow()
        elif action=='refund':
            original=one(db,Payment,v['original_payment_id'])
            if original.case_id!=row.id or original.direction!='out':raise HTTPException(422,'原付款不属于本单')
            remaining=original.amount_cents-sum(p.amount_cents for p in rows(db,Payment,original_id=original.id))
            if v['amount_cents']>min(remaining,totals(db,row)['supplier_refund_due_cents']):raise HTTPException(409,'退款超过原款未退金额或供应商当前应退额')
            _cash(db,user,row,v,original)
        elif action=='ship':
            line=one(db,Line,v['line_id'])
            if line.case_id!=row.id:raise HTTPException(422,'车型行不属于本单')
            if len(rows(db,Shipment,line_id=line.id))+sum(c.quantity for c in rows(db,Cancellation,line_id=line.id))>=line.quantity:raise HTTPException(409,'该行没有未发运数量')
            if not row.business_date<=v['shipped_date']<=today() or not v['shipped_date']<=v['expected_date']<=today()+timedelta(days=365):raise HTTPException(422,'请核对实际发运日期和预计到货日期')
            _custody(db,user,v['vin'],line.model_name)
            db.add(Shipment(case_id=row.id,line_id=line.id,vin=v['vin'],active_vin=v['vin'],shipped_date=v['shipped_date'],expected_date=v['expected_date'],evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='receive':
            shipment=one(db,Shipment,v['shipment_id'])
            if shipment.case_id!=row.id or shipment.status!='transit':raise HTTPException(409,'请选择本单尚未验收的发运VIN')
            if rows(db,Return,active_shipment_id=shipment.id):raise HTTPException(409,'该车已有退回申请，不能同时验收入库')
            if v['vin']!=shipment.vin:raise HTTPException(422,'现场VIN与发运VIN不一致，不能验收')
            line=one(db,Line,shipment.line_id);price=rows(db,Price,line_id=line.id)[0]
            location=require_active(db,'locations',v['location_id']);warehouse=require_active(db,'warehouses',location.warehouse_id)
            if warehouse.warehouse_type not in {'vehicles','mixed'}:raise HTTPException(422,'请选择本店整车仓或混合仓库位')
            custody=_custody(db,user,shipment.vin,line.model_name,shipment.id);custody.generation+=1
            vehicle=Vehicle(vin=shipment.vin,inventory_generation=custody.generation,brand=line.brand,model=line.model_name,color=line.color,supplier=header.supplier_name,
                purchase_cost_cents=price.unit_cost_cents,list_price_cents=price.list_price_cents,location=warehouse.name+' / '+location.name,
                doc_no=row.number+'-'+str(shipment.id),business_date=today(),approval_state='approved',created_by=user.id,note='采购实车验收来源 '+row.number)
            db.add(vehicle);db.flush()
            with identity_authority(db,user,{'admin','inventory'}):
                db.add(GroupIdentityLink(identity_id=custody.identity_id,local_kind='vehicle',local_id=vehicle.id,confirmed_by=user.id));db.flush()
            custody.current_vehicle_id=vehicle.id;custody.current_store_id=row.store_id;shipment.status='received';shipment.active_vin=None
            from .vehicle_operations_service import record_receipt_position
            record_receipt_position(db,user,row,vehicle,location.id,v['evidence_id'])
            db.add(Receipt(case_id=row.id,shipment_id=shipment.id,vehicle_id=vehicle.id,location_id=location.id,value_cents=price.unit_cost_cents,
                due_date=today()+timedelta(days=header.payment_terms_days),evidence_id=v['evidence_id'],business_date=today(),actor_id=user.id))
            db.add(Movement(case_id=row.id,shipment_id=shipment.id,vehicle_id=vehicle.id,kind='receive',quantity=1,value_cents=price.unit_cost_cents,evidence_id=v['evidence_id'],business_date=today(),actor_id=user.id))
        elif action=='return_request':
            shipment=one(db,Shipment,v['shipment_id'])
            if shipment.case_id!=row.id or shipment.status=='returned':raise HTTPException(409,'该VIN不存在或已退回')
            if rows(db,Return,active_shipment_id=shipment.id):raise HTTPException(409,'该VIN已有未取消的退回申请')
            _returnable(db,shipment)
            db.add(Return(case_id=row.id,shipment_id=shipment.id,active_shipment_id=shipment.id,reason=v['reason'],evidence_id=v['evidence_id'],requested_by=user.id))
        elif action.startswith('return_'):
            ret=one(db,Return,v['return_id'])
            if ret.case_id!=row.id or ret.version!=v['return_version']:raise HTTPException(409,'退回申请不存在或版本已变化')
            shipment=one(db,Shipment,ret.shipment_id)
            if action=='return_approve':
                if ret.status!='requested':raise HTTPException(409,'退回申请已审批')
                if ret.requested_by==user.id and user.role!='admin':raise HTTPException(403,'申请退车与批准须由不同员工办理')
                _returnable(db,shipment);ret.approved_by=user.id;ret.status='approved'
            elif action=='return_cancel':
                if ret.status not in {'requested','approved'}:raise HTTPException(409,'实际退回不能撤销；重新采购须有新来源')
                ret.status='cancelled';ret.active_shipment_id=None
            elif action=='return_dispatch':
                if ret.status!='approved':raise HTTPException(409,'退回须经主管批准再实际发出')
                vehicle,custody=_returnable(db,shipment)
                original=next(iter(rows(db,Movement,shipment_id=shipment.id,kind='receive')),None)
                if vehicle:
                    vehicle.approval_state='void';vehicle.updated_at=utcnow();custody.current_vehicle_id=None;custody.current_store_id=None
                    from .vehicle_operations_service import record_exit_position
                    record_exit_position(db,user,row,vehicle,v['evidence_id'],'purchase_return')
                shipment.status='returned';shipment.active_vin=None;ret.status='dispatched'
                db.add(Movement(case_id=row.id,shipment_id=shipment.id,vehicle_id=vehicle.id if vehicle else None,return_id=ret.id,original_id=original.id if original else None,
                    kind='return' if vehicle else 'transit_return',quantity=-1 if vehicle else 0,value_cents=-original.value_cents if original else 0,
                    evidence_id=v['evidence_id'],business_date=today(),actor_id=user.id))
        else:raise HTTPException(404,'整车采购动作不存在')
    db.flush();_sync(db,user,row)
    # Operational events never embed cash, account or price fields for stock users.
    flow.log_event(db,user,row,'vp_'+action,LABELS[action],detail={'reason':v.get('reason','已核对实际凭据')})
    return row


def _returnable(db,shipment):
    receipt=next(iter(rows(db,Receipt,shipment_id=shipment.id)),None)
    # Match allocation/transfer lock ordering: store Vehicle first, then central custody.
    vehicle=one(db,Vehicle,receipt.vehicle_id) if receipt else None
    custody=db.scalar(select(VehicleCustody).where(VehicleCustody.vin==shipment.vin).with_for_update())
    if not custody or custody.pending_transfer_id:raise HTTPException(409,'该VIN保管事实异常或正在调拨，请先核对')
    from .vehicle_operations_service import assert_no_vehicle_operation
    assert_no_vehicle_operation(db,vin=shipment.vin)
    if not receipt:return None,custody
    if vehicle.approval_state!='approved' or custody.current_vehicle_id!=vehicle.id or custody.current_store_id!=vehicle.store_id:
        raise HTTPException(409,'原入库车辆已出库或不在本店，不能退回原批次')
    if rows(db,VehicleHold,vehicle_id=vehicle.id) or db.scalar(select(Sale.id).where(Sale.active_vehicle_id==vehicle.id)):
        raise HTTPException(409,'车辆已被销售占用或交付，不能按供应商退车办理')
    vehicle.updated_at=utcnow();custody.version+=1;return vehicle,custody


def has_open_supplier_orders(db,supplier_id):
    return bool(db.scalar(select(Order.id).join(Case,Case.id==Order.id).where(Order.supplier_id==supplier_id,Case.state.not_in(['completed','rejected'])).limit(1)))

"""Purchase facts post once with the Case version and original receipt/cash links."""
from datetime import timedelta
import uuid,json
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .models import CashEntry
from .flow_models import Case,Item,StockMove,Account,Task
from . import flow_engine as flow
from . import business_entity_service as entities
from .flow_documents import can_file
from .flow_specs import flow_spec
from .tenancy import single_store
from .procurement_models import (PurchaseOrder,PurchaseLine,PurchaseReceipt,PurchaseReturn,
    PurchaseReturnLine,PurchaseReturnPosting,PurchasePayment)
from . import procurement_prepayment_service as prepayments

CURRENT_FLOW_VERSION=3

READ_ROLES={'admin','manager','finance','auditor','inventory'}
MONEY_ROLES={'admin','manager','finance','auditor'}
ROLES={'approve':{'admin','manager'},'reject':{'admin','manager'},'cancel':{'admin','manager'},
    'close_receiving':{'admin','manager'},'receive':{'admin','inventory'},'pay':{'admin','finance'},
    'return_request':{'admin','inventory','manager'},'return_approve':{'admin','manager'},
    'return_cancel':{'admin','manager'},'return_dispatch':{'admin','inventory'},'refund':{'admin','finance'}}
ROLES.update(prepayments.ROLES)


def _rows(db,model,**filters):
    return list(db.scalars(select(model).filter_by(**filters).order_by(model.id)))


def _one(db,model,key):
    row=db.scalar(select(model).where(model.id==key))
    if not row:raise HTTPException(404,'当前门店记录不存在')
    return row


def get_order(db,user,case_id):
    if user.role not in READ_ROLES:raise HTTPException(403,'当前岗位不能查看采购业务')
    row=flow.get_case(db,user,case_id)
    if row.kind!='procurement':raise HTTPException(404,'采购单不存在')
    flow_spec(row.kind,row.flow_version)
    if row.flow_version not in {2,3}:raise HTTPException(409,'采购流程版本不受支持')
    return row,_one(db,PurchaseOrder,case_id)


def totals(db,row):
    receipts=_rows(db,PurchaseReceipt,case_id=row.id);returns=_rows(db,PurchaseReturnPosting,case_id=row.id)
    payments=_rows(db,PurchasePayment,case_id=row.id)
    received=sum(r.value_cents for r in receipts);returned=sum(r.value_cents for r in returns)
    paid=sum(p.amount_cents*(1 if p.direction=='out' else -1) for p in payments)
    unapplied=max(0,paid);due_rows=[]
    for receipt in receipts:
        value=receipt.value_cents-sum(r.value_cents for r in returns if r.receipt_id==receipt.id)
        applied=min(value,unapplied);unapplied-=applied
        if value>applied:due_rows.append({'receipt_id':receipt.id,'due_date':receipt.due_date.isoformat(),'amount_cents':value-applied})
    return prepayments.adjust_totals(db,row,{'received_cents':received,'returned_cents':returned,'paid_net_cents':paid,
        'payable_cents':max(0,received-returned-paid),'supplier_refund_due_cents':max(0,paid-received+returned),
        'due_rows':due_rows})


def describe(db,user,row):
    header=_one(db,PurchaseOrder,row.id);money=user.role in MONEY_ROLES
    receipts=_rows(db,PurchaseReceipt,case_id=row.id);returns=_rows(db,PurchaseReturnPosting,case_id=row.id)
    def fields(obj,names):return {k:getattr(obj,k) for k in names}
    result=fields(row,['id','number','state','version','flow_version','store_id'])
    result.update(supplier_id=header.supplier_id,supplier_name=header.supplier_name,
        business_date=row.business_date.isoformat(),receiving_closed=bool(row.data.get('receiving_closed')),reason=row.data.get('reason',''))
    result['lines']=[]
    for line in _rows(db,PurchaseLine,case_id=row.id):
        d=fields(line,['id','item_id','sku','item_name','unit','quantity_milli'])
        d['received_milli']=sum(r.quantity_milli for r in receipts if r.line_id==line.id)
        if money:d.update(unit_cost_cents=line.unit_cost_cents,amount_cents=line.amount_cents)
        result['lines'].append(d)
    result['receipts']=[]
    for receipt in receipts:
        d=fields(receipt,['id','line_id','quantity_milli','stock_move_id','evidence_id'])
        d['returnable_milli']=receipt.quantity_milli-sum(r.quantity_milli for r in returns if r.receipt_id==receipt.id)
        if money:d.update(value_cents=receipt.value_cents,due_date=receipt.due_date.isoformat())
        result['receipts'].append(d)
    result['returns']=[fields(r,['id','version','status','reason','requested_by','approved_by'])|
        {'lines':[fields(l,['id','receipt_id','quantity_milli']) for l in _rows(db,PurchaseReturnLine,return_id=r.id)]}
        for r in _rows(db,PurchaseReturn,case_id=row.id)]
    result['payments']=[fields(p,['id','direction','amount_cents','account_id','original_id','reference','cash_id','evidence_id'])
        for p in _rows(db,PurchasePayment,case_id=row.id)] if money else []
    if money:
        from .procurement_cost_models import PurchaseReturnValuation
        valuations={v.id:v for v in db.scalars(select(PurchaseReturnValuation).where(PurchaseReturnValuation.id.in_([p.id for p in returns])))}
        result.update(amount_cents=row.amount_cents,totals=totals(db,row))
        result['return_costs']=[{'id':p.id,'receipt_id':p.receipt_id,'stock_move_id':p.stock_move_id,'quantity_milli':p.quantity_milli,
            'supplier_credit_cents':p.value_cents,'inventory_cost_cents':valuations[p.id].inventory_cost_cents if p.id in valuations else p.value_cents,
            'variance_cents':valuations[p.id].variance_cents if p.id in valuations else 0,'evidence_id':p.evidence_id} for p in returns]
        result['totals']['return_cost_variance_cents']=sum(v.variance_cents for v in valuations.values())
        result['prepayments']=prepayments.describe(db,user,row)
    result['actions']=[key for key,roles in ROLES.items() if user.role in roles]
    return result


def _execute(db,user,request_id,operation,payload,callback):
    single_store(db);digest=flow.request_digest('procurement_'+operation,json.loads(json.dumps(payload,default=str)))
    try:
        old=flow.prior_request(db,user,request_id,digest)
        if old:return describe(db,user,old)
        row=callback();db.flush();flow.save_receipt(db,user,request_id,digest,row);db.commit()
        return describe(db,user,row)
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'记录冲突或其他员工正在办理，请刷新核对并保留原请求编号确认结果')
    except Exception:
        db.rollback();raise


def create(db,user,request_id,values):
    if user.role not in {'admin','manager','inventory'}:raise HTTPException(403,'当前岗位不能申请采购')
    def operation():
        from .master_data import require_active
        supplier=require_active(db,'suppliers',values['supplier_id'])
        if len({l['item_id'] for l in values['lines']})!=len(values['lines']):raise HTTPException(422,'同一物资请合并为一行')
        items=[];total=0
        for v in values['lines']:
            item=_one(db,Item,v['item_id'])
            if not item.active:raise HTTPException(422,'采购物资已停用')
            amount=(v['quantity_milli']*v['unit_cost_cents']+500)//1000
            total+=amount
            if total>1_000_000_000_000:raise HTTPException(422,'采购约定金额超出允许范围')
            items.append((item,v,amount))
        row=Case(number='HKP'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='procurement',flow_version=CURRENT_FLOW_VERSION,
            state='approval',title=supplier.name+' · 多行物资采购',owner_id=user.id,created_by=user.id,
            amount_cents=total,business_date=today(),due_date=today(),data={'reason':values['reason'],'receiving_closed':False})
        db.add(row);db.flush()
        entities.freeze_case_entity(db,user,row)
        db.add(PurchaseOrder(id=row.id,supplier_id=supplier.id,supplier_name=supplier.name,supplier_code=supplier.code,
            supplier_tax_identifier=supplier.tax_identifier,payment_terms_days=supplier.payment_terms_days))
        for item,v,amount in items:db.add(PurchaseLine(case_id=row.id,item_id=item.id,sku=item.sku,item_name=item.name,
            unit=item.unit,quantity_milli=v['quantity_milli'],unit_cost_cents=v['unit_cost_cents'],amount_cents=amount))
        flow.ensure_task(db,row,'procurement_approve','复核采购明细及供应商','manager')
        flow.log_event(db,user,row,'procurement_create','申请多行采购',detail={'supplier_id':supplier.id,'line_count':len(items)})
        return row
    return _execute(db,user,request_id,'create',values,operation)


def _evidence(db,user,row,key):
    asset=flow.file_exists(db,row,key)
    if not can_file(user,row,asset):raise HTTPException(403,'当前岗位不能使用此类凭据')
    return asset


def _portion(value,quantity,remaining):
    return value if quantity==remaining else (2*value*quantity+remaining)//(2*remaining)


def _stock(db,user,row,item,quantity,value,purpose,original=None,return_id=None):
    if quantity<0:
        from .inventory_availability import assert_can_issue
        assert_can_issue(db,item,-quantity,excluding_procurement_return_id=return_id)
    if item.quantity_milli+quantity<0 or item.inventory_value_cents+value<0:
        raise HTTPException(409,'本店可用数量或库存价值不足，不能假定已发出的原批次仍可退货')
    item.quantity_milli+=quantity;item.inventory_value_cents+=value
    if not item.quantity_milli and item.inventory_value_cents:
        raise HTTPException(409,'退回原批次后会留下无数量的库存价值，请先核对混合批次及领用记录')
    item.unit_cost_cents=(item.inventory_value_cents*1000*2+item.quantity_milli)//(2*item.quantity_milli) if item.quantity_milli else 0
    item.updated_at=utcnow()
    move=StockMove(case_id=row.id,item_id=item.id,quantity_milli=quantity,value_cents=value,
        unit_cost_cents=abs(value)*1000//abs(quantity),purpose=purpose,original_id=original,
        actor_id=user.id,business_date=today())
    db.add(move);db.flush()
    from .warehouse_stock import after_stock_move
    after_stock_move(db,user,row,item,move)
    return move


def _task(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or (task.assignee_id!=user.id and user.role not in {'admin','manager'}):
        raise HTTPException(409,'本步骤没有待办或已交给其他员工，请核对接手人')


def _sync(db,user,row):
    if row.state in {'approval','cancelled','rejected'}:return
    prepayments.synchronize_allocations(db,user,row)
    lines=_rows(db,PurchaseLine,case_id=row.id);receipts=_rows(db,PurchaseReceipt,case_id=row.id)
    if all(sum(r.quantity_milli for r in receipts if r.line_id==line.id)==line.quantity_milli for line in lines):
        flow.set_data(row,receiving_closed=True)
    closed=row.data.get('receiving_closed',False);net=totals(db,row)
    if closed:flow.finish_task(db,row,'procurement_receive',user)
    else:flow.ensure_task(db,row,'procurement_receive','按批次验收采购到货','inventory',reopen=True)
    for amount,key,title in [(net['payable_cents'],'procurement_pay','核对供应商应付并登记付款'),
                             (net['supplier_refund_due_cents'],'procurement_refund','按原付款账户核对供应商退款')]:
        if amount:
            due=min((r['due_date'] for r in net['due_rows']),default=today().isoformat())
            from datetime import date
            flow.ensure_task(db,row,key,title,'finance',due=date.fromisoformat(due),reopen=True)
        else:flow.finish_task(db,row,key,user)
    pending=any(r.status in {'requested','approved'} for r in _rows(db,PurchaseReturn,case_id=row.id))
    row.state='completed' if closed and not pending and not net['payable_cents'] and not net['supplier_refund_due_cents'] else 'receiving'
    row.completed_date=today() if row.state=='completed' else None
    prepayments.sync_tasks(db,user,row)


def _return(db,row,values):
    result=_one(db,PurchaseReturn,values['return_id'])
    if result.case_id!=row.id:raise HTTPException(404,'退货申请不属于本采购')
    if result.version!=values['return_version']:raise HTTPException(409,'退货申请已变化，请刷新')
    return result


def _remaining_receipt(db,receipt):
    posted=_rows(db,PurchaseReturnPosting,receipt_id=receipt.id)
    return receipt.quantity_milli-sum(x.quantity_milli for x in posted),receipt.value_cents-sum(x.value_cents for x in posted)


def _cash(db,user,row,values,direction,original=None):
    account=db.scalar(select(Account).where(Account.id==values['account_id']).with_for_update())
    if not account:raise HTTPException(404,'本店资金账户不存在')
    if not account.active:raise HTTPException(409,'资金账户已停用')
    if original and original.account_id!=account.id:raise HTTPException(409,'供应商退款须进入原付款账户')
    entities.require_account_entity(db,user,row,account.id,today(),original_cash_id=original.cash_id if original else None)
    if db.scalar(select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==values['reference'])):
        raise HTTPException(409,'该账户的流水凭证号已经使用，请核对是否重复记款')
    account.updated_at=utcnow()
    cash=CashEntry(doc_no='HKPC-'+uuid.uuid4().hex[:24],business_date=today(),created_by=user.id,approval_state='approved',
        direction=direction,category='procurement_payment' if direction=='out' else 'procurement_refund',amount_cents=values['amount_cents'],
        account=account.name,payment_method='cash' if account.account_type=='cash' else 'bank',voucher_no=values['reference'],
        counterparty=_one(db,PurchaseOrder,row.id).supplier_name,note='采购单 '+row.number)
    db.add(cash);db.flush()
    entities.record_cash_entity(db,user,row,cash,account.id,original_cash_id=original.cash_id if original else None)
    payment=PurchasePayment(case_id=row.id,cash_id=cash.id,account_id=account.id,direction=direction,
        original_id=original.id if original else None,amount_cents=values['amount_cents'],reference=values['reference'],evidence_id=values['evidence_id'])
    db.add(payment);db.flush();return payment


def command(db,user,case_id,request_id,version,action,values):
    if action not in ROLES:raise HTTPException(404,'采购动作不存在')
    if user.role not in ROLES[action]:raise HTTPException(403,'当前门店岗位不能办理此采购动作')
    def operation():
        row,header=get_order(db,user,case_id)
        if row.version!=version:raise HTTPException(409,'采购单已变化，请刷新核对后再办理')
        before=row.state;source_before=prepayments.source_ids(db,row);row.updated_at=utcnow()
        if action in prepayments.ROLES:
            prepayments.apply(db,user,row,action,values)
        elif action in {'approve','reject'}:
            if row.state!='approval':raise HTTPException(409,'采购已复核，不能重复审批')
            if row.created_by==user.id and user.role!='admin':raise HTTPException(403,'采购申请与审批须由不同员工办理')
            flow.finish_task(db,row,'procurement_approve',user)
            row.state='receiving' if action=='approve' else 'rejected'
            if action=='reject':row.completed_date=today()
        elif action=='cancel':
            prepayments.guard_cancel(db,row)
            if row.state not in {'approval','receiving'} or _rows(db,PurchaseReceipt,case_id=row.id) or _rows(db,PurchasePayment,case_id=row.id):
                raise HTTPException(409,'有实际到货或付款的采购不能取消；请终止余量或办理退货退款')
            row.state='cancelled';row.completed_date=today();flow.close_tasks(db,row,user)
        else:
            if row.state not in {'receiving','completed'}:raise HTTPException(409,'采购尚未批准或已取消')
            if action=='close_receiving':
                if row.data.get('receiving_closed'):raise HTTPException(409,'到货余量已经关闭')
                flow.set_data(row,receiving_closed=True,close_receiving_reason=values['reason'])
                prepayments.close_unpaid(db,user,row,values['reason'])
            elif action=='receive':
                if row.data.get('receiving_closed'):raise HTTPException(409,'采购到货已关闭，退货不会重新开放采购数量')
                _task(db,user,row,'procurement_receive');_evidence(db,user,row,values['evidence_id'])
                if len({r['line_id'] for r in values['lines']})!=len(values['lines']):raise HTTPException(422,'同一采购行不能重复验收')
                for v in values['lines']:
                    line=_one(db,PurchaseLine,v['line_id'])
                    if line.case_id!=row.id:raise HTTPException(404,'采购明细不属于本单')
                    old=_rows(db,PurchaseReceipt,line_id=line.id);remaining=line.quantity_milli-sum(r.quantity_milli for r in old)
                    if v['quantity_milli']>remaining:raise HTTPException(409,'验收数量超过该行尚未到货数量')
                    value=_portion(line.amount_cents-sum(r.value_cents for r in old),v['quantity_milli'],remaining)
                    item=_one(db,Item,line.item_id)
                    move=_stock(db,user,row,item,v['quantity_milli'],value,'procurement_receipt')
                    db.add(PurchaseReceipt(case_id=row.id,line_id=line.id,stock_move_id=move.id,quantity_milli=v['quantity_milli'],
                        value_cents=value,evidence_id=values['evidence_id'],due_date=today()+timedelta(days=header.payment_terms_days)))
            elif action=='return_request':
                _evidence(db,user,row,values['evidence_id'])
                if len({v['receipt_id'] for v in values['lines']})!=len(values['lines']):raise HTTPException(422,'同一到货批次不能重复填写')
                request=PurchaseReturn(case_id=row.id,requested_by=user.id,reason=values['reason'],evidence_id=values['evidence_id'])
                db.add(request);db.flush()
                for v in values['lines']:
                    receipt=_one(db,PurchaseReceipt,v['receipt_id'])
                    if receipt.case_id!=row.id:raise HTTPException(404,'退货批次不属于本单')
                    if v['quantity_milli']>_remaining_receipt(db,receipt)[0]:raise HTTPException(409,'退货超过该批次尚未退回数量')
                    db.add(PurchaseReturnLine(return_id=request.id,receipt_id=receipt.id,quantity_milli=v['quantity_milli']))
                flow.ensure_task(db,row,'procurement_return_review_'+str(request.id),'复核采购退货申请','manager')
            elif action in {'return_approve','return_cancel','return_dispatch'}:
                request=_return(db,row,values);review='procurement_return_review_'+str(request.id);dispatch='procurement_return_dispatch_'+str(request.id)
                if action=='return_approve':
                    if request.status!='requested':raise HTTPException(409,'退货已复核或已结束')
                    if request.requested_by==user.id and user.role!='admin':raise HTTPException(403,'退货申请人不能审批本人申请')
                    for line in _rows(db,PurchaseReturnLine,return_id=request.id):
                        receipt=_one(db,PurchaseReceipt,line.receipt_id)
                        reserved=db.scalar(select(func.coalesce(func.sum(PurchaseReturnLine.quantity_milli),0))
                            .join(PurchaseReturn,PurchaseReturn.id==PurchaseReturnLine.return_id)
                            .where(PurchaseReturnLine.receipt_id==receipt.id,PurchaseReturn.status=='approved',PurchaseReturn.id!=request.id))
                        if line.quantity_milli>_remaining_receipt(db,receipt)[0]-reserved:
                            raise HTTPException(409,'原批次剩余数量已被其他批准的退货占用，请先核对或撤销另一申请')
                    if row.flow_version==3:
                        needed={}
                        for line in _rows(db,PurchaseReturnLine,return_id=request.id):
                            receipt=_one(db,PurchaseReceipt,line.receipt_id);part=_one(db,PurchaseLine,receipt.line_id)
                            needed[part.item_id]=needed.get(part.item_id,0)+line.quantity_milli
                        from .inventory_availability import assert_can_issue
                        for item_id,quantity in sorted(needed.items()):
                            item=_one(db,Item,item_id);assert_can_issue(db,item,quantity);item.updated_at=utcnow()
                    request.status='approved';request.approved_by=user.id;flow.finish_task(db,row,review,user)
                    flow.ensure_task(db,row,dispatch,'核对原批次并确认退货实物发出','inventory')
                elif action=='return_cancel':
                    if request.status not in {'requested','approved'}:raise HTTPException(409,'实际退货已发生，不能撤销流水')
                    if row.flow_version==3 and request.status=='approved':
                        for line in _rows(db,PurchaseReturnLine,return_id=request.id):
                            receipt=_one(db,PurchaseReceipt,line.receipt_id);part=_one(db,PurchaseLine,receipt.line_id)
                            _one(db,Item,part.item_id).updated_at=utcnow()
                    request.status='cancelled';flow.finish_task(db,row,review,user,'cancelled');flow.finish_task(db,row,dispatch,user,'cancelled')
                else:
                    if request.status!='approved':raise HTTPException(409,'退货须先由主管批准')
                    _task(db,user,row,dispatch);_evidence(db,user,row,values['evidence_id'])
                    for line in _rows(db,PurchaseReturnLine,return_id=request.id):
                        receipt=_one(db,PurchaseReceipt,line.receipt_id);remaining,value_remaining=_remaining_receipt(db,receipt)
                        if line.quantity_milli>remaining:raise HTTPException(409,'原批次已退货，剩余数量不足')
                        value=_portion(value_remaining,line.quantity_milli,remaining)
                        original_line=_one(db,PurchaseLine,receipt.line_id);item=_one(db,Item,original_line.item_id)
                        if row.flow_version==3:
                            from .procurement_costs import require_recorded_balance
                            require_recorded_balance(db,item)
                        before_qty=item.quantity_milli;before_value=item.inventory_value_cents
                        if line.quantity_milli>before_qty:raise HTTPException(409,'当前实际可退数量不足，不能按原采购数假定物品仍在店内')
                        cost=_portion(before_value,line.quantity_milli,before_qty) if row.flow_version==3 else value
                        move=_stock(db,user,row,item,-line.quantity_milli,-cost,'procurement_return',receipt.stock_move_id,return_id=request.id)
                        posting=PurchaseReturnPosting(case_id=row.id,return_line_id=line.id,receipt_id=receipt.id,
                            stock_move_id=move.id,quantity_milli=line.quantity_milli,value_cents=value,evidence_id=values['evidence_id'])
                        db.add(posting);db.flush()
                        if row.flow_version==3:
                            from .procurement_cost_models import PurchaseReturnValuation
                            db.add(PurchaseReturnValuation(id=posting.id,quantity_before_milli=before_qty,value_before_cents=before_value,
                                inventory_cost_cents=cost,supplier_credit_cents=value,variance_cents=value-cost))
                    request.status='dispatched';flow.finish_task(db,row,dispatch,user)
            elif action in {'pay','refund'}:
                net=totals(db,row);_task(db,user,row,'procurement_pay' if action=='pay' else 'procurement_refund')
                _evidence(db,user,row,values['evidence_id']);amount=values['amount_cents'];original=None
                if action=='pay':
                    if amount>net['payable_cents']:raise HTTPException(409,'付款超过实际验收到货扣除退货后的未付金额；不支持预付款')
                    prepayments.guard_regular_payment(db,row,amount)
                else:
                    original=_one(db,PurchasePayment,values['original_payment_id'])
                    if original.case_id!=row.id or original.direction!='out':raise HTTPException(404,'原付款不属于本采购')
                    refunded=sum(p.amount_cents for p in _rows(db,PurchasePayment,original_id=original.id))
                    if amount>net['supplier_refund_due_cents'] or amount>original.amount_cents-refunded:
                        raise HTTPException(409,'退款超过实际退货形成的应退金额或原付款剩余金额')
                    prepayments.guard_refund(db,row,original,amount)
                _cash(db,user,row,values,'out' if action=='pay' else 'in',original)
        db.flush();_sync(db,user,row);db.flush()
        # Financial application prose stays in the money-role projection, never generic events.
        event_values={k:v for k,v in values.items() if k!='reason'} if action in prepayments.ROLES else values
        source_facts=prepayments.new_sources(db,row,source_before)
        if source_facts:event_values={**event_values,'prepayment_sources':source_facts}
        flow.log_event(db,user,row,'procurement_'+action,{**prepayments.LABELS,'approve':'批准采购','reject':'退回采购','cancel':'取消未执行采购',
            'receive':'确认分批到货','pay':'确认供应商付款','close_receiving':'终止剩余到货','return_request':'申请采购退货',
            'return_approve':'批准采购退货','return_cancel':'撤销未执行退货','return_dispatch':'确认采购退货发出','refund':'确认供应商原款退款'}[action],before,json.loads(json.dumps(event_values,default=str)))
        return row
    return _execute(db,user,request_id,action,{'case_id':case_id,'version':version,'values':values},operation)


def has_open_supplier_orders(db,supplier_id):
    return db.scalar(select(PurchaseOrder.id).join(Case,Case.id==PurchaseOrder.id)
        .where(PurchaseOrder.supplier_id==supplier_id,Case.state.notin_(['cancelled','rejected','completed'])).limit(1)) is not None


def reserved_return_quantity(db,item_id,excluding_return_id=None):
    """V3 approval holds actual stock as well as its original receipt capacity."""
    query=select(func.coalesce(func.sum(PurchaseReturnLine.quantity_milli),0)).join(PurchaseReturn,PurchaseReturn.id==PurchaseReturnLine.return_id).join(PurchaseReceipt,PurchaseReceipt.id==PurchaseReturnLine.receipt_id).join(PurchaseLine,PurchaseLine.id==PurchaseReceipt.line_id).join(Case,Case.id==PurchaseReturn.case_id).where(PurchaseReturn.status=='approved',Case.flow_version==3,PurchaseLine.item_id==item_id)
    if excluding_return_id is not None:query=query.where(PurchaseReturn.id!=excluding_return_id)
    return db.scalar(query) or 0

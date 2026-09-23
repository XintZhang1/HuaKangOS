"""Explicit store business finance, one transaction and one actual cash source."""
from contextlib import contextmanager
from datetime import date,datetime,timedelta
import hashlib,json,uuid
from fastapi import HTTPException
from sqlalchemy import select,func,or_
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .models import User,Store,CashEntry
from .tenancy import single_store,role_for_store
from .flow_models import Case,Customer,Account,PaymentLink,StockMove,Task
from .business_finance_models import *
from . import flow_engine as flow
from . import business_entity_service as entities
from .business_finance_sources import case_credit_amount,case_reserved_amount,source_details,sync_source

FRONT={'admin','manager','finance','sales','service','reception','customer_service'}
READ=FRONT|{'auditor'}
FINANCE={'admin','finance'}
MANAGERS={'admin','manager'}
LABELS={'advance':'客户预收款','advance_apply':'预收抵用原单','advance_refund':'未用预收原款退款','statement':'客户期间月结','correction':'原收款误记更正','stored_correction':'预收／会员原充值误记更正','other_return':'其他入库退货应收','other_return_adjust':'供应方应退目标更正','other_return_refund':'供应方超收原款退款'}
LABELS['fee_correction']='续会费同额登记更正'


def clean(row):return {c.name:(getattr(row,c.name).isoformat() if isinstance(getattr(row,c.name),(date,datetime)) else getattr(row,c.name)) for c in row.__table__.columns}
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def can_read(user,row):
    if row.data.get('finance_purpose')=='fee_correction':return user.role in FINANCE|MANAGERS|{'auditor'}
    return user.role in READ and (user.role not in {'sales','reception'} or row.owner_id==user.id)


@contextmanager
def authority(db,user,roles=READ):
    sid=single_store(db)
    if role_for_store(db,user,sid) not in roles or not db.scalar(select(Store.id).where(Store.id==sid,Store.active.is_(True))):raise HTTPException(403,'当前门店岗位不能办理此财务事项')
    old=db.info.get('_business_finance_authority');db.info['_business_finance_authority']=(user.id,sid)
    try:yield sid
    finally:
        db.flush()
        if old is None:db.info.pop('_business_finance_authority',None)
        else:db.info['_business_finance_authority']=old


def execute(db,user,key,action,values,roles,callback):
    try:
        with authority(db,user,roles):
            hashed=digest({'action':action,'values':values})
            old=db.scalar(select(FinanceReceipt).where(FinanceReceipt.request_key==key))
            if old:
                if old.actor_id!=user.id or old.digest!=hashed:raise HTTPException(409,'请求编号已用于其他财务动作或内容')
                return old.result
            result=callback();db.flush()
            db.add(FinanceReceipt(request_key=key,actor_id=user.id,digest=hashed,result=result));db.commit();return result
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'原单或资金正在变化，请刷新核对并保留原请求号查询结果')
    except Exception:db.rollback();raise


def _one(db,model,key):
    result=db.scalar(select(model).where(model.id==key).with_for_update())
    if not result:raise HTTPException(404,'本店财务来源不存在')
    return result
def _version(row,version):
    if type(version) is not int or row.version!=version:raise HTTPException(409,'记录已变化，请刷新核对后再办理')
def _customer(db,user,key):
    customer=_one(db,Customer,key)
    if user.role in {'sales','reception'} and customer.owner_id not in {None,user.id}:raise HTTPException(403,'仅可为本人负责客户发起财务申请')
    return customer
def _order(db,user,key):
    row=flow.get_case(db,user,key)
    if row.kind!='business_finance' or row.flow_version!=2:raise HTTPException(404,'本店业务财务单不存在')
    order=db.scalar(select(FinanceOrder).where(FinanceOrder.case_id==row.id).with_for_update())
    if not order:raise HTTPException(404,'业务财务来源不存在')
    return row,order
def _event(db,user,row,action,reason,evidence=None,detail=None):
    db.add(FinanceEvent(case_id=row.id,actor_id=user.id,action=action,reason=reason,evidence_id=evidence,detail=detail or {}))
    flow.log_event(db,user,row,'business_finance_'+action,'业务财务办理',detail={'reason':reason,'evidence_id':evidence,**(detail or {})})
def _task(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or (task.assignee_id!=user.id and user.role!='admin'):raise HTTPException(403,'请由当前待办经办人办理，主管可明确转交')
def _done(db,user,row,order):
    order.status='completed';row.state='completed';row.completed_date=today();flow.finish_task(db,row,'business_finance_execute',user);flow.close_tasks(db,row,user)
def _touch_source(db,user,key,version,customer_id,include_reservations=True,allow_correcting=False):
    row,info=source_details(db,user,key,include_reservations,allow_correcting)
    if row.customer_id!=customer_id:raise HTTPException(409,'结算原单必须属于同一本店客户')
    _version(row,version);row.updated_at=utcnow();db.flush();return row,info
def _source_assignee(db,user,row,info):
    if user.role=='admin':return
    from .service_orders_service import is_detailed as service_order
    key='addon_receive' if row.kind=='addon' and row.flow_version==3 else 'insurance_receive' if row.kind=='insurance' and row.flow_version==3 else 'serviceorder_receive' if service_order(row) else 'repair_receive_'+str(info['allocation_id']) if info['allocation_id'] else 'retail_receive' if row.kind=='retail' else 'receive'
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or task.assignee_id!=user.id:raise HTTPException(403,'原单收款待办由其他员工负责，请主管明确转交后集中办理')


def sources(db,user,customer_id,start=None,end=None):
    with authority(db,user):
        _customer(db,user,customer_id)
        query=select(Case).where(Case.customer_id==customer_id,Case.kind.in_(['order','repair','addon','agency','insurance','retail','other_income'])).order_by(Case.id)
        if start:query=query.where(Case.business_date>=start)
        if end:query=query.where(Case.business_date<=end)
        rows=list(db.scalars(query.limit(1001)))
        if len(rows)>1000:raise HTTPException(422,'客户原单超过单次1000条，请缩小期间')
        result=[]
        for row in rows:
            try:_,value=source_details(db,user,row.id)
            except HTTPException as error:
                if error.status_code in {403,404,409}:continue
                raise
            if value['due_cents']>0:result.append(value)
        return {'items':result}


def advances(db,user,customer_id):
    with authority(db,user):
        _customer(db,user,customer_id)
        rows=list(db.scalars(select(FinanceAdvance).where(FinanceAdvance.customer_id==customer_id).order_by(FinanceAdvance.id.desc()).limit(501)))
        if len(rows)>500:raise HTTPException(422,'客户预收来源超过500笔，请按期间核对后归档')
        from .business_finance_stored import effective_cash
        return {'items':[clean(r)|{'available_cents':r.balance_cents-r.reserved_cents,'effective_initial_cents':r.initial_cents+r.correction_cents,
            'effective_account_id':effective_cash(db,r.cash_id,r.account_id)[1]} for r in rows]}


def orders(db,user):
    with authority(db,user):
        rows=list(db.scalars(select(Case).where(Case.kind=='business_finance').order_by(Case.id.desc()).limit(200)))
        return {'items':[{'case_id':r.id,'number':r.number,'title':r.title,'state':r.state,'customer_id':r.customer_id,'purpose':r.data['finance_purpose']} for r in rows if can_read(user,r)]}


def receipt_sources(db,user,customer_id):
    with authority(db,user,FINANCE|MANAGERS):
        _customer(db,user,customer_id)
        keys=list(db.scalars(select(PaymentLink.cash_id).join(Case,Case.id==PaymentLink.case_id).where(Case.customer_id==customer_id,PaymentLink.direction=='in').distinct().limit(1001)))
        # A fully refunded effective original still exists even with zero net links.
        keys=list(dict.fromkeys(keys+list(db.scalars(select(FinanceCashBatch.cash_id).join(FinanceCorrection,FinanceCorrection.corrected_batch_id==FinanceCashBatch.id)
            .join(FinanceCorrectionBasis,FinanceCorrectionBasis.case_id==FinanceCorrection.case_id).join(Case,Case.id==FinanceCorrection.case_id).where(Case.customer_id==customer_id)))))
        if len(keys)>1000:raise HTTPException(422,'本客户收款来源超过1000笔，请缩小核对范围')
        result=[]
        for key in keys:
            try:cash,links=_correction_origin(db,user,key,customer_id,allow_partial=True)
            except HTTPException as error:
                if error.status_code in {403,404,409}:continue
                raise
            from .business_finance_partial_corrections import state as partial_state,source_ids
            partial=partial_state(db,cash,links);sources=[]
            for p in links:
                source=flow.get_case(db,user,p.case_id)
                sources.append({'case_id':source.id,'number':source.number,'amount_cents':p.amount_cents})
            for key in sorted(source_ids(links,partial)-{s['case_id'] for s in sources}):
                source=flow.get_case(db,user,key);sources.append({'case_id':key,'number':source.number,'amount_cents':0})
            result.append({'cash_id':cash.id,'business_date':cash.business_date.isoformat(),'amount_cents':cash.amount_cents,'account':cash.account,'reference':cash.voucher_no,'sources':sources,
                'refunded_cents':partial['refunded_cents'],'net_amount_cents':cash.amount_cents-partial['refunded_cents']})
        from .business_finance_stored import sources as stored_sources
        result.extend(stored_sources(db,user,customer_id))
        from .membership_fee_corrections import sources as fee_sources
        result.extend(fee_sources(db,user,customer_id))
        return {'items':result}


def other_return_sources(db,user):
    with authority(db,user,FINANCE):
        query=select(StockMove).join(Case,Case.id==StockMove.case_id).where(StockMove.purpose=='wh_other_return',Case.state=='completed',
            ~StockMove.id.in_(select(FinanceReturnReceivable.stock_move_id))).order_by(StockMove.id.desc()).limit(1001)
        rows=list(db.scalars(query))
        if len(rows)>1000:raise HTTPException(422,'未建应收的退货超过1000笔，请先核对归档')
        from .flow_models import Item
        return {'items':[{'stock_move_id':r.id,'source_version':_one(db,Case,r.case_id).version,'case_id':r.case_id,
            'number':_one(db,Case,r.case_id).number,'item_name':_one(db,Item,r.item_id).name,'quantity_milli':-r.quantity_milli,'value_cents':-r.value_cents} for r in rows]}


def describe(db,user,key):
    with authority(db,user):
        row,order=_order(db,user,key);result={'case':clean(row),'order':clean(order),'events':[clean(e) for e in db.scalars(select(FinanceEvent).where(FinanceEvent.case_id==row.id).order_by(FinanceEvent.id))]}
        application=db.scalar(select(FinanceApplication).where(FinanceApplication.case_id==row.id))
        if application:result['application']=clean(application);result['advance']=clean(_one(db,FinanceAdvance,application.advance_id))
        own=db.scalar(select(FinanceAdvance).where(FinanceAdvance.case_id==row.id))
        if own:result['advance']=clean(own)
        if result.get('advance'):
            from .business_finance_stored import effective_cash
            result['advance']['account_name']=_one(db,Account,result['advance']['account_id']).name
            current,account_id=effective_cash(db,result['advance']['cash_id'],result['advance']['account_id'])
            result['advance']['effective_account_name']=_one(db,Account,account_id).name if current else '已撤销误记，无有效原款'
        statement=db.scalar(select(FinanceStatement).where(FinanceStatement.case_id==row.id))
        if statement:
            result['statement']=clean(statement)
            result['lines']=[clean(l) for l in db.scalars(select(FinanceStatementLine).where(FinanceStatementLine.statement_id==statement.id).order_by(FinanceStatementLine.id))]
        batches=list(db.scalars(select(FinanceCashBatch).where(FinanceCashBatch.case_id==row.id)))
        result['batches']=[clean(b) for b in batches]
        result['allocations']=[clean(a) for a in db.scalars(select(FinanceCashAllocation).where(FinanceCashAllocation.batch_id.in_([b.id for b in batches])))]
        source_ids={application.target_case_id} if application and application.target_case_id else set()
        if order.purpose in {'correction','stored_correction','fee_correction'}:
            if order.purpose=='correction':
                from .business_finance_partial_corrections import describe as partial_detail
                result['partial_correction']=partial_detail(db,row.id)
                if result['partial_correction']:source_ids.update(r['case_id'] for r in result['partial_correction']['refunds'])
            source_ids.update(v['source_case_id'] for v in order.values.get('allocations',[]))
            source_ids.update(db.scalars(select(PaymentLink.case_id).where(PaymentLink.cash_id==order.values['original_cash_id'])))
            if order.purpose=='stored_correction':
                source_ids.add(order.values['source_case_id'])
                result['stored_request']=clean(db.scalar(select(FinanceStoredCorrectionRequest).where(FinanceStoredCorrectionRequest.case_id==row.id)))
                if order.values.get('bundle_purchase_id'):
                    from .business_finance_bundle_corrections import describe as bundle_detail
                    result['bundle_correction']=bundle_detail(db,user,_one(db,FinanceStoredCorrectionRequest,result['stored_request']['id']))
            if order.purpose=='fee_correction':
                from .membership_fee_corrections import request_for
                from .membership_fee_correction_models import MembershipFeeCorrection
                source_ids.add(order.values['source_case_id'])
                result['fee_correction_request']=clean(request_for(db,row))
                fact=db.scalar(select(MembershipFeeCorrection).where(MembershipFeeCorrection.case_id==row.id))
                result['fee_correction_fact']=clean(fact) if fact else None
            original=_one(db,CashEntry,order.values['original_cash_id'])
            result['original_cash']={'amount_cents':original.amount_cents,'account':original.account,'reference':original.voucher_no,'business_date':original.business_date.isoformat()}
            result['corrected_account_name']=_one(db,Account,order.values['account_id']).name if order.values['amount_cents'] else None
        if order.purpose=='other_return':
            from .master_models import Supplier
            from .flow_models import Item
            move=_one(db,StockMove,order.values['stock_move_id']);source_ids.add(move.case_id)
            item=_one(db,Item,move.item_id)
            result['return_source']={'case_id':move.case_id,'item_name':item.name,'unit':item.unit,'quantity_milli':-move.quantity_milli,'value_cents':-move.value_cents,'supplier_name':_one(db,Supplier,order.values['supplier_id']).name}
        if order.purpose in {'other_return','other_return_adjust','other_return_refund'}:
            from .business_finance_return_adjustments import describe as target_detail
            receivable=db.scalar(select(FinanceReturnReceivable).where(FinanceReturnReceivable.case_id==row.id)) if order.purpose=='other_return' else _one(db,FinanceReturnReceivable,order.values['receivable_id'])
            if receivable:
                result['return_target']=target_detail(db,receivable)
                if order.purpose!='other_return':source_ids.add(receivable.case_id)
                if user.role in FINANCE|MANAGERS|{'auditor'}:
                    from .business_finance_supplier_refunds import sources as refund_sources
                    result['supplier_refund_sources']=refund_sources(db,receivable)
            if order.purpose=='other_return_refund':
                request=db.scalar(select(FinanceSupplierRefund).where(FinanceSupplierRefund.case_id==row.id))
                result['supplier_refund']=clean(request)
                result['supplier_refund_account_name']=_one(db,Account,order.values['original_account_id']).name
        result['source_cases']=[{'id':source.id,'number':source.number} for source in [flow.get_case(db,user,key) for key in sorted(source_ids)]]
        return result


def _new(db,user,customer,purpose,values,reason):
    row=Case(number='HK-BF-'+uuid.uuid4().hex[:16].upper(),kind='business_finance',flow_version=2,state='pending',
        title=(customer.name+' · ' if customer else '')+LABELS[purpose],customer_id=customer.id if customer else None,
        owner_id=user.id,created_by=user.id,business_date=today(),due_date=today()+timedelta(days=2),amount_cents=values.get('amount_cents',0),data={'finance_purpose':purpose})
    db.add(row);db.flush()
    order=FinanceOrder(case_id=row.id,purpose=purpose,values=values,requested_by=user.id);db.add(order);db.flush()
    source=None
    if purpose=='advance_refund':source=_one(db,Case,_one(db,FinanceAdvance,values['advance_id']).case_id)
    elif purpose=='correction':source=entities.cash_source_case(db,user,values['original_cash_id'])
    elif purpose in {'stored_correction','fee_correction'}:source=entities.cash_source_case(db,user,values['original_cash_id']) or _one(db,Case,values['source_case_id'])
    elif purpose in {'other_return_adjust','other_return_refund'}:source=_one(db,Case,values['source_case_id'])
    elif purpose=='other_return':source=_one(db,Case,_one(db,StockMove,values['stock_move_id']).case_id)
    if source:entities.freeze_derived_case_entity(db,user,row,source)
    else:entities.freeze_case_entity(db,user,row)
    flow.ensure_task(db,row,'business_finance_execute' if purpose=='advance' else 'business_finance_review',
        '确认本店实际预收到账' if purpose=='advance' else '独立复核'+LABELS[purpose],'finance' if purpose=='advance' else 'manager',due=row.due_date)
    _event(db,user,row,'create',reason);return row,order


def create_order(db,user,request_id,customer_id,purpose,values,reason):
    roles=FRONT if purpose in {'advance','advance_apply','advance_refund'} else FINANCE
    def operation():
        customer=_customer(db,user,customer_id) if customer_id else None
        if purpose not in {'other_return','other_return_adjust','other_return_refund'} and not customer:raise HTTPException(422,'请选择本店客户')
        if purpose in {'advance_apply','advance_refund'}:
            advance=_one(db,FinanceAdvance,values['advance_id']);_version(advance,values['advance_version'])
            if advance.customer_id!=customer.id or values['amount_cents']>advance.balance_cents-advance.reserved_cents:raise HTTPException(409,'超过本客户这笔原预收的未用余额')
            if purpose=='advance_apply':
                _,info=_touch_source(db,user,values['target_case_id'],values['target_version'],customer.id)
                if values['amount_cents']>info['due_cents']:raise HTTPException(409,'抵用超过原单当前客户未结额度')
                entities.assert_same_case_entities(db,user,[_one(db,Case,advance.case_id),_one(db,Case,values['target_case_id'])])
            row,order=_new(db,user,customer,purpose,values,reason)
            db.add(FinanceApplication(case_id=row.id,advance_id=advance.id,target_case_id=values.get('target_case_id'),amount_cents=values['amount_cents'],kind='apply' if purpose=='advance_apply' else 'refund'))
        elif purpose=='statement':
            return _new_statement(db,user,customer,values,reason)
        elif purpose=='correction':
            from .business_finance_partial_corrections import state as partial_state,freeze,source_ids
            original,links=_correction_origin(db,user,values['original_cash_id'],customer.id,allow_partial=values.get('allocation_basis')=='remaining_after_refunds')
            partial=partial_state(db,original,links);refunded=partial['refunded_cents']
            if values['amount_cents']<refunded:raise HTTPException(409,'正确总原款不能少于已经真实退回的原款；不能覆盖原退款')
            _check_correction_allocations(values['allocations'],values['amount_cents']-refunded)
            actual_date=_correction_date(values,original)
            row,order=_new(db,user,customer,purpose,{**values,'actual_business_date':actual_date.isoformat(),**({'correction_basis_version':2,'refunded_cents':refunded} if refunded else {})},reason)
            if refunded:freeze(db,row,original,values,partial)
            entities.assert_same_case_entities(db,user,[row]+[_one(db,Case,k) for k in sorted(source_ids(links,partial)|{v['source_case_id'] for v in values['allocations']})])
        elif purpose=='stored_correction':
            from . import business_finance_stored as stored
            frozen=stored.prepare(db,user,customer,values)
            row,order=_new(db,user,customer,purpose,frozen,reason);stored.create_request(db,row,frozen)
        elif purpose=='fee_correction':
            from . import membership_fee_corrections as fees
            frozen=fees.prepare(db,user,customer,values)
            row,order=_new(db,user,customer,purpose,frozen,reason);fees.create_request(db,row,frozen)
        elif purpose=='other_return_adjust':
            from .business_finance_return_adjustments import prepare
            row,order=_new(db,user,None,purpose,prepare(db,user,values),reason)
        elif purpose=='other_return_refund':
            from . import business_finance_supplier_refunds as supplier_refunds
            frozen=supplier_refunds.prepare(db,user,values)
            row,order=_new(db,user,None,purpose,frozen,reason);supplier_refunds.create_request(db,row,frozen)
        elif purpose=='other_return':
            _return_source(db,values)
            row,order=_new(db,user,None,purpose,values,reason)
        else:row,order=_new(db,user,customer,purpose,values,reason)
        db.flush();return describe(db,user,row.id)
    return execute(db,user,request_id,'create',{'customer_id':customer_id,'purpose':purpose,'values':values,'reason':reason},roles,operation)


def _new_statement(db,user,customer,values,reason,previous=None):
    try:start=date.fromisoformat(values['starts_on']);end=date.fromisoformat(values['ends_on'])
    except ValueError:raise HTTPException(422,'请填写有效的月结起止日期')
    if start>end or end>today() or (end-start).days>365:raise HTTPException(422,'月结须为不超过一年且截止今天的明确期间')
    if not previous and db.scalar(select(FinanceStatement.id).where(FinanceStatement.customer_id==customer.id,FinanceStatement.starts_on==start,FinanceStatement.ends_on==end)):
        raise HTTPException(409,'本期间已有客户账单，请从原单明确重算追加版本')
    lines=sources(db,user,customer.id,start,end)['items']
    if not lines:raise HTTPException(409,'该客户期间没有可列入本次月结的客户应收')
    sources_for_entity=[_one(db,Case,line['case_id']) for line in lines]
    entities.assert_same_case_entities(db,user,sources_for_entity)
    row,order=_new(db,user,customer,'statement',values,reason);row.amount_cents=sum(l['due_cents'] for l in lines)
    entities.assert_same_case_entities(db,user,[row,*sources_for_entity])
    statement=FinanceStatement(case_id=row.id,customer_id=customer.id,starts_on=start,ends_on=end,revision=previous.revision+1 if previous else 1,
        previous_id=previous.id if previous else None,digest=digest(lines));db.add(statement);db.flush()
    for line in lines:db.add(FinanceStatementLine(statement_id=statement.id,source_case_id=line['case_id'],snapshot=line,due_cents=line['due_cents']))
    db.flush();return describe(db,user,row.id)


def _return_source(db,values):
    from .master_models import Supplier
    from .warehouse_models import WarehouseDocument
    move=_one(db,StockMove,values['stock_move_id']);case=_one(db,Case,move.case_id)
    _version(case,values['source_version'])
    document=db.scalar(select(WarehouseDocument).where(WarehouseDocument.id==case.id,WarehouseDocument.operation=='other_in_return'))
    supplier=_one(db,Supplier,values['supplier_id'])
    if not supplier.active or not document or move.purpose!='wh_other_return' or move.quantity_milli>=0 or not move.original_id or case.state!='completed':
        raise HTTPException(409,'应收只能关联本店已经实际执行的其他入库原单退货及启用供应方')
    if db.scalar(select(FinanceReturnReceivable.id).where(FinanceReturnReceivable.stock_move_id==move.id)):raise HTTPException(409,'这笔实际退货已建立独立应收，不能重复申请')
    return move,supplier


def _cash(db,user,row,values,amount,direction,category,exclude_original=None,actual_date=None,original_cash_id=None):
    account=_one(db,Account,values['account_id'])
    if not account.active:raise HTTPException(409,'实际账户已停用')
    entities.require_account_entity(db,user,row,account.id,actual_date or today(),original_cash_id=original_cash_id)
    reference=values['reference']
    excluded=set()
    if exclude_original:
        cursor=exclude_original
        while cursor:
            if cursor in excluded or len(excluded)>=1000:raise HTTPException(409,'原收款更正链异常或超出本次核对范围')
            excluded.add(cursor)
            current=cursor
            cursor=db.scalar(select(FinanceCorrection.original_cash_id).join(FinanceCashBatch,FinanceCashBatch.id==FinanceCorrection.corrected_batch_id).where(FinanceCashBatch.cash_id==current))
            if cursor is None:cursor=db.scalar(select(FinanceStoredCorrection.original_cash_id).where(FinanceStoredCorrection.corrected_cash_id==current))
            if cursor is None:
                from .membership_fee_corrections import previous_cash_id
                cursor=previous_cash_id(db,current)
    query=select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==reference)
    if excluded:query=query.where(~CashEntry.id.in_(excluded))
    if db.scalar(query):raise HTTPException(409,'该实际账户凭证号已登记，请核对原收款，不可重复入账')
    payment_query=select(PaymentLink.id).where(PaymentLink.account_id==account.id,PaymentLink.reference==reference)
    if excluded:payment_query=payment_query.where(~PaymentLink.cash_id.in_(excluded))
    if db.scalar(payment_query):raise HTTPException(409,'该实际账户凭证号已用于原单支付')
    flow.file_exists(db,row,values['evidence_id'],'receipt');account.updated_at=utcnow();db.flush()
    cash=CashEntry(doc_no='BF-'+uuid.uuid4().hex[:20].upper(),business_date=actual_date or today(),created_by=user.id,approval_state='approved',direction=direction,
        category=category,amount_cents=amount,account=account.name,counterparty=row.title,payment_method='cash' if account.account_type=='cash' else 'bank',
        voucher_no=reference,note='关联业务财务 '+row.number)
    db.add(cash);db.flush();entities.record_cash_entity(db,user,row,cash,account.id,original_cash_id=original_cash_id)
    return cash,account


def _check_allocations(lines,total):
    if not lines or len(lines)>100 or len({l['source_case_id'] for l in lines})!=len(lines):raise HTTPException(422,'分配必须为1至100个不同原单')
    if any(type(l['amount_cents']) is not int or l['amount_cents']<=0 for l in lines) or sum(l['amount_cents'] for l in lines)!=total:
        raise HTTPException(422,'逐单分配必须使用正整数分，合计等于本次真实现金')


def _check_correction_allocations(lines,total):
    if total==0 and not lines:return
    _check_allocations(lines,total)


def _correction_date(values,original):
    try:actual_date=date.fromisoformat(values['actual_business_date']) if values.get('actual_business_date') else original.business_date
    except ValueError:raise HTTPException(422,'请填写有效的实际到账日期')
    if actual_date>today():raise HTTPException(422,'实际到账日期不能晚于今天')
    return actual_date


def _batch(db,user,row,cash,kind,evidence):
    batch=FinanceCashBatch(case_id=row.id,cash_id=cash.id,kind=kind,amount_cents=cash.amount_cents,evidence_id=evidence,actor_id=user.id)
    db.add(batch);db.flush();return batch


def _allocate(db,user,batch,cash,account,source,amount,evidence,original=None,line_id=None):
    entities.assert_same_case_entities(db,user,[_one(db,Case,batch.case_id),source])
    link=PaymentLink(case_id=source.id,cash_id=cash.id,original_id=original.id if original else None,account_id=account.id,
        direction=cash.direction,amount_cents=amount,reference=cash.voucher_no,business_date=cash.business_date)
    db.add(link);db.flush();db.add(FinanceCashAllocation(batch_id=batch.id,case_id=source.id,payment_link_id=link.id,statement_line_id=line_id,amount_cents=amount))
    from .repair_service import is_detailed
    if is_detailed(source):
        from .repair_models import RepairAllocation,RepairPayment
        allocation=db.scalar(select(RepairAllocation).where(RepairAllocation.case_id==source.id,RepairAllocation.payer_type=='customer'))
        if not allocation:raise HTTPException(409,'原维修没有客户承担可分配')
        db.add(RepairPayment(allocation_id=allocation.id,payment_link_id=link.id,evidence_id=evidence))
    elif source.kind=='retail':
        from .retail_models import RetailPayment
        db.add(RetailPayment(case_id=source.id,payment_link_id=link.id,evidence_id=evidence))
    from .service_orders_service import is_detailed as service_order,record_collection
    if service_order(source):record_collection(db,user,source,link,evidence,original_payment=original,correction=bool(original))
    from .insurance_service import is_detailed as insurance_order,record_collection as insurance_collection
    if insurance_order(source):insurance_collection(db,user,source,link,evidence,original_payment=original,correction=bool(original))
    from .addon_service import is_detailed as addon_order,record_collection as addon_collection
    if addon_order(source):addon_collection(db,user,source,link,evidence,original_payment=original,correction=bool(original))
    db.flush();return link


def _correction_origin(db,user,key,customer_id,*,allow_partial=False):
    cash=_one(db,CashEntry,key)
    if cash.approval_state!='approved' or cash.direction!='in' or not (cash.category.startswith('workflow_') or cash.category in {'business_finance_collection','business_finance_corrected'}):
        raise HTTPException(409,'更正只处理有原业务支付关联的客户实收，集团充值或预收原款须走其原业务')
    if db.scalar(select(FinanceCorrection.id).where(FinanceCorrection.original_cash_id==cash.id)):raise HTTPException(409,'原现金已被更正，请从后继真实记录核对')
    links=list(db.scalars(select(PaymentLink).where(PaymentLink.cash_id==cash.id).order_by(PaymentLink.id)))
    from .business_finance_partial_corrections import state as partial_state,source_ids,guard_source
    current=partial_state(db,cash,links)
    if not links and not current['previous_id'] or any(p.direction!='in' for p in links):raise HTTPException(409,'原收款分配与现金不守恒')
    if current['refunded_cents'] and not allow_partial:raise HTTPException(409,'原款已有实际退款，请明确使用保留已退款切片的剩余原款更正')
    for key in sorted(source_ids(links,current)):
        source=flow.get_case(db,user,key)
        guard_source(db,source.id)
        from .claims_service import guard_source_adjustment
        guard_source_adjustment(db,source,'cash_correction')
        from .service_orders_service import guard_source_adjustment as guard_service
        guard_service(db,source,'cash_correction')
        from .insurance_service import guard_source_adjustment as guard_insurance
        from .business_finance_partial_corrections import fully_returned_insurance
        if not (allow_partial and fully_returned_insurance(db,source)):guard_insurance(db,source,'cash_correction')
        from .addon_service import guard_source_adjustment as guard_addon
        guard_addon(db,source,'cash_correction')
        if source.customer_id!=customer_id:raise HTTPException(409,'原收款属于其他客户')
    return cash,links


def superseded_cash_ids(db):return set(db.scalars(select(FinanceCorrection.original_cash_id)))|set(db.scalars(select(FinanceStoredCorrection.original_cash_id)))
def adjustment_cash_ids(db):return set(db.scalars(select(FinanceCashBatch.cash_id).where(FinanceCashBatch.kind=='correction_reverse')))|set(db.scalars(select(FinanceStoredCorrection.reversing_cash_id)))


def command(db,user,key,request_id,version,case_version,action,values):
    roles=MANAGERS if action in {'approve','reject'} else FINANCE if action in {'execute','collect'} else FRONT
    def operation():
        row,order=_order(db,user,key);_version(row,case_version);_version(order,version);row.updated_at=utcnow()
        if action=='recalculate':
            if order.purpose!='statement' or order.status in {'cancelled','superseded'} or user.role not in FINANCE:raise HTTPException(409,'仅财务可为当前客户账单追加重算版本')
            previous=db.scalar(select(FinanceStatement).where(FinanceStatement.case_id==row.id))
            if db.scalar(select(FinanceStatement.id).where(FinanceStatement.previous_id==previous.id)):raise HTTPException(409,'账单已有后继版本')
            order.status='superseded';row.state='completed';flow.close_tasks(db,row,user)
            return _new_statement(db,user,_customer(db,user,row.customer_id),order.values,values['reason'],previous)
        if order.status in {'completed','cancelled','superseded'}:raise HTTPException(409,'财务办理已结束，请核对原记录')
        if action in {'cancel','reject'}:
            if action=='cancel' and user.id!=order.requested_by and user.role not in MANAGERS:raise HTTPException(403,'仅申请人或主管可取消')
            if db.scalar(select(FinanceCashBatch.id).where(FinanceCashBatch.case_id==row.id)):raise HTTPException(409,'已有真实收款，不能取消抹去账单')
            if order.purpose=='other_return' and order.status=='approved':raise HTTPException(409,'已独立批准的应收须通过供应方应退目标更正追加修订，不能取消抹账')
            if order.purpose=='stored_correction':
                from .business_finance_stored import release
                release(db,user,row)
            if order.purpose=='fee_correction':
                from .membership_fee_corrections import release
                release(db,user,row)
            if order.purpose=='other_return_refund':
                from .business_finance_supplier_refunds import release
                release(db,user,row)
            application=db.scalar(select(FinanceApplication).where(FinanceApplication.case_id==row.id).with_for_update())
            if application:
                if application.status=='reserved':
                    advance=_one(db,FinanceAdvance,application.advance_id);advance.reserved_cents-=application.amount_cents;advance.updated_at=utcnow()
                application.status='released'
            order.status='cancelled';row.state='cancelled';row.completed_date=today();flow.close_tasks(db,row,user)
        elif action=='approve':
            if order.purpose=='advance' or order.status!='draft':raise HTTPException(409,'当前办理不等待复核')
            if user.id==order.requested_by:raise HTTPException(403,'申请与批准须不同人员，管理员也不能自批')
            _task(db,user,row,'business_finance_review');flow.file_exists(db,row,values['evidence_id'])
            _approve(db,user,row,order,values)
            order.approved_by=user.id;order.status='approved';flow.finish_task(db,row,'business_finance_review',user)
            flow.ensure_task(db,row,'business_finance_execute','按已批准来源确认'+LABELS[order.purpose],'finance',due=row.due_date)
        elif action in {'execute','collect'}:
            _task(db,user,row,'business_finance_execute');flow.file_exists(db,row,values['evidence_id'])
            if order.purpose!='advance' and order.status!='approved':raise HTTPException(409,'须先取得独立批准')
            _post(db,user,row,order,values)
        else:raise HTTPException(404,'业务财务动作不存在')
        _event(db,user,row,action,values['reason'],values.get('evidence_id'));db.flush();return describe(db,user,key)
    return execute(db,user,request_id,str(key)+':'+action,{'version':version,'case_version':case_version,'values':values},roles,operation)


def _approve(db,user,row,order,values):
    if order.purpose in {'advance_apply','advance_refund'}:
        application=db.scalar(select(FinanceApplication).where(FinanceApplication.case_id==row.id).with_for_update())
        advance=_one(db,FinanceAdvance,application.advance_id)
        if application.amount_cents>advance.balance_cents-advance.reserved_cents:raise HTTPException(409,'原预收可用余额已变化，不能批准占额')
        if application.kind=='apply':
            target,info=_touch_source(db,user,application.target_case_id,values['source_versions'].get(str(application.target_case_id)),row.customer_id)
            if application.amount_cents>info['due_cents']:raise HTTPException(409,'原单客户可抵用额度已变化')
        advance.reserved_cents+=application.amount_cents;advance.updated_at=utcnow();application.status='reserved'
    elif order.purpose=='statement':
        statement=db.scalar(select(FinanceStatement).where(FinanceStatement.case_id==row.id))
        for line in db.scalars(select(FinanceStatementLine).where(FinanceStatementLine.statement_id==statement.id)):
            _,current=source_details(db,user,line.source_case_id)
            if current['due_cents']!=line.due_cents or current['amount_cents']!=line.snapshot['amount_cents']:raise HTTPException(409,'账单原来源余额已变化，请重算新增版本后复核')
    elif order.purpose=='correction':
        if order.values.get('correction_basis_version')==2:
            from .business_finance_partial_corrections import validate,execution
            with execution(db,row.id):validate(db,user,row,order,touch=True)
        else:_correction_origin(db,user,order.values['original_cash_id'],row.customer_id)
    elif order.purpose=='stored_correction':
        from .business_finance_stored import approve
        approve(db,user,row,order)
    elif order.purpose=='fee_correction':
        from .membership_fee_corrections import approve
        approve(db,user,row,order)
    elif order.purpose=='other_return_adjust':
        from .business_finance_return_adjustments import validate
        validate(db,user,row,order,values)
    elif order.purpose=='other_return_refund':
        from .business_finance_supplier_refunds import approve
        approve(db,user,row,order,values)
    elif order.purpose=='other_return':
        move,supplier=_return_source(db,order.values)
        db.add(FinanceReturnReceivable(case_id=row.id,stock_move_id=move.id,supplier_id=supplier.id,amount_cents=order.values['amount_cents'],
            quantity_milli=-move.quantity_milli,value_cents=-move.value_cents,approved_by=user.id,evidence_id=values['evidence_id']))


def _post(db,user,row,order,values):
    if order.purpose=='advance':
        cash,account=_cash(db,user,row,values,order.values['amount_cents'],'in','business_finance_advance')
        advance=FinanceAdvance(case_id=row.id,customer_id=row.customer_id,cash_id=cash.id,account_id=account.id,initial_cents=cash.amount_cents,balance_cents=cash.amount_cents)
        db.add(advance);db.flush();db.add(FinanceAdvanceEntry(advance_id=advance.id,case_id=row.id,purpose='receive',amount_cents=cash.amount_cents,cash_id=cash.id,evidence_id=values['evidence_id'],actor_id=user.id));_done(db,user,row,order)
    elif order.purpose in {'advance_apply','advance_refund'}:
        application=db.scalar(select(FinanceApplication).where(FinanceApplication.case_id==row.id).with_for_update());advance=_one(db,FinanceAdvance,application.advance_id)
        if application.status!='reserved' or advance.reserved_cents<application.amount_cents:raise HTTPException(409,'原预收批准占额已变化')
        if application.kind=='apply':
            target,info=_touch_source(db,user,application.target_case_id,values['source_versions'].get(str(application.target_case_id)),row.customer_id,False)
            entities.assert_same_case_entities(db,user,[row,_one(db,Case,advance.case_id),target])
            if application.amount_cents>info['due_cents']:raise HTTPException(409,'客户原单余额已变化，请取消占额后重新核对')
            _source_assignee(db,user,target,info);cash=None
        else:
            from .business_finance_stored import effective_cash
            actual_original,account_id=effective_cash(db,advance.cash_id,advance.account_id)
            if not actual_original or values['account_id']!=account_id:raise HTTPException(409,'未用预收按本笔经核对更正后的原账户退回')
            cash,_=_cash(db,user,row,values,application.amount_cents,'out','business_finance_advance_refund',original_cash_id=actual_original.id)
        entry=FinanceAdvanceEntry(advance_id=advance.id,case_id=row.id,purpose=application.kind,amount_cents=-application.amount_cents,cash_id=cash.id if cash else None,
            original_id=db.scalar(select(FinanceAdvanceEntry.id).where(FinanceAdvanceEntry.advance_id==advance.id,FinanceAdvanceEntry.purpose=='receive')),evidence_id=values['evidence_id'],actor_id=user.id)
        advance.balance_cents-=application.amount_cents;advance.reserved_cents-=application.amount_cents;advance.updated_at=utcnow();application.status='applied'
        db.add(entry);db.flush()
        if application.kind=='apply':
            credit=FinanceCreditLink(case_id=target.id,entry_id=entry.id,application_id=application.id,amount_cents=application.amount_cents)
            db.add(credit);db.flush()
            from .service_orders_service import is_detailed as service_order,record_advance_credit
            if service_order(target):record_advance_credit(db,user,target,credit,values['evidence_id'])
            from .insurance_service import is_detailed as insurance_order,record_advance_credit as insurance_credit
            if insurance_order(target):insurance_credit(db,user,target,credit,values['evidence_id'])
            from .addon_service import is_detailed as addon_order,record_advance_credit as addon_credit
            if addon_order(target):addon_credit(db,user,target,credit,values['evidence_id'])
        _done(db,user,row,order);db.flush()
        if application.kind=='apply':sync_source(db,user,target,values['evidence_id'])
    elif order.purpose=='statement':_collect(db,user,row,order,values)
    elif order.purpose=='correction':_correct(db,user,row,order,values)
    elif order.purpose=='stored_correction':
        from .business_finance_stored import post
        post(db,user,row,order,values)
    elif order.purpose=='fee_correction':
        from .membership_fee_corrections import post
        post(db,user,row,order,values)
    elif order.purpose=='other_return_adjust':
        from .business_finance_return_adjustments import post
        post(db,user,row,order,values)
    elif order.purpose=='other_return_refund':
        from .business_finance_supplier_refunds import post
        post(db,user,row,order,values)
    elif order.purpose=='other_return':
        from .business_finance_return_adjustments import effective_target,received,guard_collection
        receivable=db.scalar(select(FinanceReturnReceivable).where(FinanceReturnReceivable.case_id==row.id))
        guard_collection(db,receivable);target=effective_target(db,receivable);paid=received(db,receivable)
        amount=values['amount_cents']
        if amount>target-paid:raise HTTPException(409,'超过已独立批准且尚未收到的原退货款')
        cash,account=_cash(db,user,row,values,amount,'in','business_finance_collection');batch=_batch(db,user,row,cash,'collection',values['evidence_id'])
        _allocate(db,user,batch,cash,account,row,amount,values['evidence_id'])
        if amount+paid==target:_done(db,user,row,order)


def _collect(db,user,row,order,values):
    _check_allocations(values['allocations'],values['amount_cents'])
    statement=db.scalar(select(FinanceStatement).where(FinanceStatement.case_id==row.id))
    lines={l.source_case_id:l for l in db.scalars(select(FinanceStatementLine).where(FinanceStatementLine.statement_id==statement.id))}
    prepared=[]
    for selected in sorted(values['allocations'],key=lambda v:v['source_case_id']):
        line=lines.get(selected['source_case_id'])
        if not line:raise HTTPException(409,'本次分配原单不在已批准冻结账单内')
        source,info=_touch_source(db,user,line.source_case_id,values['source_versions'].get(str(line.source_case_id)),row.customer_id)
        _source_assignee(db,user,source,info)
        previous=db.scalar(select(func.coalesce(func.sum(FinanceCashAllocation.amount_cents),0)).where(FinanceCashAllocation.statement_line_id==line.id)) or 0
        if selected['amount_cents']>min(info['due_cents'],line.due_cents-previous):raise HTTPException(409,'分配超过本次冻结原单额度或当前未收余额，请核对晚到收款')
        prepared.append((source,line,selected['amount_cents']))
    entities.assert_same_case_entities(db,user,[row]+[source for source,_,_ in prepared])
    cash,account=_cash(db,user,row,values,values['amount_cents'],'in','business_finance_collection');batch=_batch(db,user,row,cash,'collection',values['evidence_id'])
    for source,line,amount in prepared:_allocate(db,user,batch,cash,account,source,amount,values['evidence_id'],line_id=line.id)
    for source,_,_ in prepared:sync_source(db,user,source,values['evidence_id'])
    if sum(db.scalar(select(func.coalesce(func.sum(FinanceCashAllocation.amount_cents),0)).where(FinanceCashAllocation.statement_line_id==line.id)) or 0 for line in lines.values())==sum(l.due_cents for l in lines.values()):_done(db,user,row,order)


def _correct(db,user,row,order,values):
    from .business_finance_partial_corrections import execution
    with execution(db,row.id):return _correct_record(db,user,row,order,values)


def _correct_record(db,user,row,order,values):
    frozen=order.values
    if frozen.get('correction_basis_version')==2:
        from .business_finance_partial_corrections import validate,source_ids
        original,links,partial=validate(db,user,row,order)
        affected=source_ids(links,partial);remaining=partial['remaining']
    else:
        original,links=_correction_origin(db,user,frozen['original_cash_id'],row.customer_id)
        affected={p.case_id for p in links};remaining={p.id:p.amount_cents for p in links}
    affected|={v['source_case_id'] for v in frozen['allocations']};sources={}
    for key in sorted(affected):
        source,_=_touch_source(db,user,key,values['source_versions'].get(str(key)),row.customer_id,False,True);sources[key]=source
    entities.assert_same_case_entities(db,user,[row,*sources.values()])
    if links:account_id=links[0].account_id
    else:
        previous=_one(db,FinanceCorrectionBasis,partial['previous_id'])
        prior_order=db.scalar(select(FinanceOrder).where(FinanceOrder.case_id==previous.case_id))
        account_id=prior_order.values['account_id']
    original_account=_one(db,Account,account_id)
    contra_values={'account_id':original_account.id,'reference':'CORRECTION-'+uuid.uuid4().hex,'evidence_id':values['evidence_id']}
    reversal,_=_cash(db,user,row,contra_values,original.amount_cents,'out','business_finance_correction_reverse',original_cash_id=original.id)
    reverse_batch=_batch(db,user,row,reversal,'correction_reverse',values['evidence_id'])
    for link in links:
        if remaining[link.id]:_allocate(db,user,reverse_batch,reversal,original_account,sources[link.case_id],remaining[link.id],values['evidence_id'],original=link)
    db.flush()
    for allocation in frozen['allocations']:
        _,current=source_details(db,user,allocation['source_case_id'],True,True)
        if allocation['amount_cents']>current['due_cents']:raise HTTPException(409,'正确重记金额超过该客户原单当前应收，请核对更正分配')
    corrected_batch=None
    if frozen['amount_cents']:
        corrected,account=_cash(db,user,row,{**frozen,'evidence_id':values['evidence_id']},frozen['amount_cents'],'in','business_finance_corrected',exclude_original=original.id,actual_date=date.fromisoformat(frozen['actual_business_date']))
        corrected_batch=_batch(db,user,row,corrected,'correction_record',values['evidence_id'])
        for allocation in frozen['allocations']:_allocate(db,user,corrected_batch,corrected,account,sources[allocation['source_case_id']],allocation['amount_cents'],values['evidence_id'])
    db.add(FinanceCorrection(case_id=row.id,original_cash_id=original.id,reversing_batch_id=reverse_batch.id,corrected_batch_id=corrected_batch.id if corrected_batch else None));_done(db,user,row,order);db.flush()
    for source in sources.values():sync_source(db,user,source,values['evidence_id'])

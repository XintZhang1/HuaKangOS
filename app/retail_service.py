"""Retail separates reservation, physical fulfillment, receivable and real cash."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .flow_models import Case,Item,Customer,StockMove,PaymentLink,Task
from .flow_documents import can_file
from .tenancy import single_store
from . import flow_engine as flow
from .retail_models import RetailOrder,RetailLine,RetailReservation,RetailDispatch,RetailReturn,RetailReturnLine,RetailReturnPosting,RetailPayment

READ_ROLES={'admin','manager','sales','service','technician','inventory','finance','auditor'}
MONEY_ROLES={'admin','manager','sales','service','finance','auditor'}
COST_ROLES={'admin','manager','finance','auditor'}
FRONT={'admin','sales','service'}
ROLES={'approve':{'admin','manager'},'authorize':FRONT,'cancel':{'admin','manager'},'dispatch':{'admin','inventory'},
    'install':{'admin','technician'},'accept':FRONT,'receive':{'admin','finance'},'return_request':FRONT|{'manager'},
    'return_approve':{'admin','manager'},'return_cancel':{'admin','manager'},'return_receive':{'admin','inventory'},
    'return_rectify':{'admin','technician'},'return_reject':{'admin','manager'},'return_handback':{'admin','inventory'},'refund':{'admin','finance'}}
ACTIVE_RETURNS={'requested','approved','rectification','reinspection','handback'}
LABELS={'approve':'主管批准精品报价','authorize':'确认客户认可报价','cancel':'取消未出库精品','dispatch':'确认精品实际出库','install':'确认实际安装',
    'accept':'确认客户接收','receive':'确认实际收款','return_request':'申请原单退货','return_approve':'批准退货及费用规则','return_cancel':'撤销未验收退货',
    'return_receive':'确认退货可售检查','return_rectify':'提交退货整改','return_reject':'决定拒收并交回客户','return_handback':'确认拒收商品实物交回','refund':'确认原款实际退款'}
def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def _one(db,model,key):
    value=db.scalar(select(model).where(model.id==key))
    if not value:raise HTTPException(404,'当前门店原始记录不存在')
    return value
def get_order(db,user,key):
    if user.role not in READ_ROLES:raise HTTPException(403,'当前岗位不能查看精品销售')
    row=flow.get_case(db,user,key)
    if row.kind!='retail' or row.flow_version!=2:raise HTTPException(404,'当前门店精品明细订单不存在')
    _one(db,RetailOrder,key);return row
def reserved_quantity(db,item_id,excluding_case_id=None):
    query=select(func.coalesce(func.sum(RetailReservation.quantity_milli),0)).where(RetailReservation.item_id==item_id)
    if excluding_case_id is not None:query=query.where(RetailReservation.case_id!=excluding_case_id)
    return int(db.scalar(query))
def _evidence(db,user,row,key,category=None):
    asset=flow.file_exists(db,row,key,category)
    if not can_file(user,row,asset):raise HTTPException(403,'当前岗位不能使用此类凭据')
    return asset
def totals(db,row):
    returns=_rows(db,RetailReturnPosting,case_id=row.id)
    links=_rows(db,PaymentLink,case_id=row.id)
    paid=sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in links)
    from .business_finance_sources import case_credit_amount
    advance_credit=case_credit_amount(db,row.id);cash_paid=paid;paid+=advance_credit
    reduction=sum(p.goods_cents+p.installation_cents-p.retained_cents for p in returns)
    charge=0 if row.data.get('cancelled') else row.amount_cents-reduction
    cost=sum(d.value_cents for d in _rows(db,RetailDispatch,case_id=row.id))-sum(p.value_cents for p in returns)
    result={'quoted_cents':row.amount_cents,'return_reduction_cents':reduction,'retained_installation_cents':sum(p.retained_cents for p in returns),
        'charge_cents':charge,'net_paid_cents':paid,'cash_paid_cents':cash_paid,'advance_credit_cents':advance_credit,
        'advance_return_due_cents':min(advance_credit,max(0,paid-charge)),
        'receivable_cents':max(0,charge-paid),'refund_due_cents':max(0,paid-charge-advance_credit),
        'revenue_cents':charge if row.data.get('accepted_date') else 0,'cost_cents':cost}
    from .retail_group_service import totals_adjustment
    group=totals_adjustment(db,row)
    result['net_price_cents']=charge
    if group is not None:
        # C settles the quoted debt; P is actual external consideration.
        # An accepted original return reduces C/P/S immediately, even when
        # restoration of an indivisible coupon must await later returns.
        paid+=group['group_paid_cents']
        result.update(group)
        result.update(net_paid_cents=paid,receivable_cents=max(0,charge-paid),
            refund_due_cents=group['cash_refund_due_cents'],advance_return_due_cents=0,
            net_price_cents=charge-group['group_external_discount_cents'])
        result['revenue_cents']=result['net_price_cents'] if row.data.get('accepted_date') else 0
    return result
def collectable_amount(db,row):
    from .business_finance_sources import case_reserved_amount
    amount=totals(db,row)
    return min(max(0,amount['receivable_cents']-case_reserved_amount(db,row.id)),
        amount.get('cash_collectable_cents',amount['receivable_cents']))
def _execute(db,user,key,operation,payload,callback):
    single_store(db);digest=flow.request_digest('retail_'+operation,payload)
    try:
        prior=flow.prior_request(db,user,key,digest)
        if prior:return describe(db,user,prior)
        row=callback();db.flush();flow.save_receipt(db,user,key,digest,row);db.commit();return describe(db,user,row)
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'记录冲突或其他员工正在办理，请刷新核对并保留原请求编号')
    except Exception:db.rollback();raise
def _distribute(total,weights):
    denominator=sum(weights)
    if not denominator:return [0]*len(weights)
    values=[total*w//denominator for w in weights]
    for idx in sorted(range(len(weights)),key=lambda n:(-(total*weights[n]%denominator),n))[:total-sum(values)]:values[idx]+=1
    return values
def _reserve(db,user,row,item,quantity,reason):
    item.updated_at=utcnow()
    db.add(RetailReservation(case_id=row.id,item_id=item.id,quantity_milli=quantity,reason=reason,actor_id=user.id));db.flush()
def _create_frozen_order(db,user,customer,related,prepared,net,discount_cents):
    """Internal transaction fragment; caller validates ordinary prices or a frozen bundle."""
    if len(net)!=2*len(prepared) or not prepared or min(net)<0 or sum(net)>1_000_000_000_000:
        raise HTTPException(422,'精品冻结清单或金额无效')
    row=Case(number='HKR'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='retail',flow_version=2,state='approval',
        title=customer.name+' · 精品销售',customer_id=customer.id,owner_id=user.id,created_by=user.id,business_date=today(),due_date=today(),
        amount_cents=sum(net),data={})
    db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);db.add(RetailOrder(id=row.id,customer_name=customer.name,related_repair_id=related,discount_cents=discount_cents))
    for n,(item,work,line) in enumerate(prepared):
        db.add(RetailLine(case_id=row.id,item_id=item.id,sku=line.get('sku',item.sku),name=line.get('name',item.name),unit=line.get('unit',item.unit),quantity_milli=line['quantity_milli'],
            unit_price_cents=line['unit_price_cents'],goods_cents=net[2*n],work_item_id=work.id if work else None,
            work_code=line.get('work_code',work.code if work else ''),work_name=line.get('work_name',work.name if work else ''),
            installation_unit_price_cents=line['installation_unit_price_cents'],installation_cents=net[2*n+1]))
        _reserve(db,user,row,item,line['quantity_milli'],'reserve')
    flow.ensure_task(db,row,'retail_approve','复核精品报价及价格授权','manager')
    flow.log_event(db,user,row,'retail_create','开单并占用商品',detail={'line_count':len(prepared),'revision':1})
    return row
def create(db,user,request_id,v):
    if v.get('member_pricing') is None:v={k:value for k,value in v.items() if k!='member_pricing'}
    if user.role not in FRONT:raise HTTPException(403,'销售或服务顾问才能开精品单')
    def operation():
        from .master_data import require_active
        from .inventory_availability import assert_can_issue
        customer=_one(db,Customer,v['customer_id'])
        if user.role=='sales' and customer.owner_id!=user.id:raise HTTPException(403,'此客户不在本人可读客户范围，请先由主管办理客户交接')
        related=v.get('related_repair_id')
        if related:
            repair=flow.get_case(db,user,related)
            if repair.kind!='repair' or repair.customer_id!=customer.id:raise HTTPException(422,'附带销售只能关联同店、同一客户的可读维修单')
        if len({l['item_id'] for l in v['lines']})!=len(v['lines']):raise HTTPException(422,'同一商品请合并为一行')
        prepared=[];weights=[]
        for line in v['lines']:
            item=_one(db,Item,line['item_id'])
            if not item.active:raise HTTPException(422,'商品已停用')
            assert_can_issue(db,item,line['quantity_milli'])
            work=require_active(db,'work_items',line['work_item_id']) if line['work_item_id'] else None
            goods=(line['quantity_milli']*line['unit_price_cents']+500)//1000
            installation=(line['quantity_milli']*line['installation_unit_price_cents']+500)//1000
            weights.extend([goods,installation]);prepared.append((item,work,line))
        gross=sum(weights)
        if gross>1_000_000_000_000 or v['discount_cents']>gross:raise HTTPException(422,'报价超出金额上限或优惠超过原价')
        from . import member_pricing_service as pricing
        contract=pricing.prepare_retail(db,user,customer,prepared,weights,v.get('member_pricing'),v['discount_cents'])
        net=[p['net_cents'] for p in contract['lines']] if contract else _distribute(gross-v['discount_cents'],weights)
        row=_create_frozen_order(db,user,customer,related,prepared,net,gross-sum(net))
        pricing.freeze_quote(db,user,row,'retail',row.id,contract);return row
    return _execute(db,user,request_id,'create',v,operation)
def _task(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or (task.assignee_id!=user.id and user.role not in {'admin','manager'}):raise HTTPException(409,'步骤待办已完成或已交给其他员工，请核对接手人')
def _active(db,row):return [r for r in _rows(db,RetailReturn,case_id=row.id) if r.status in ACTIVE_RETURNS]
def _sync(db,user,row):
    db.flush();amount=totals(db,row);row.cost_cents=amount['cost_cents']
    if row.data.get('cancelled'):
        row.state='settling' if amount['refund_due_cents'] else 'cancelled'
    elif row.data.get('accepted_date'):row.state='settling' if amount['receivable_cents'] or amount['refund_due_cents'] or _active(db,row) else 'completed'
    elif row.data.get('dispatched'):row.state='working'
    elif row.data.get('authorized'):row.state='pending'
    elif row.data.get('approved'):row.state='authorization'
    if row.data.get('approved'):
        if amount.get('cash_collectable_cents',amount['receivable_cents']) and not row.data.get('cancelled'):flow.ensure_task(db,row,'retail_receive','确认精品实际收款','finance',reopen=True)
        else:flow.finish_task(db,row,'retail_receive',user)
    if amount['refund_due_cents']:flow.ensure_task(db,row,'retail_refund','按原收款确认实际退款','finance',reopen=True)
    else:flow.finish_task(db,row,'retail_refund',user)
    from .retail_group_service import sync_tasks
    sync_tasks(db,user,row,amount)
def _portion(value,quantity,remaining):return value if quantity==remaining else (2*value*quantity+remaining)//(2*remaining)
def _stock(db,user,row,item,qty,value,purpose,original=None):
    if item.quantity_milli+qty<0 or item.inventory_value_cents+value<0:raise HTTPException(409,'库存数量或价值不足')
    item.quantity_milli+=qty;item.inventory_value_cents+=value
    if item.quantity_milli==0 and item.inventory_value_cents:raise HTTPException(409,'原单价值核对失败，不能留下无数量的库存价值')
    item.unit_cost_cents=(2*item.inventory_value_cents*1000+item.quantity_milli)//(2*item.quantity_milli) if item.quantity_milli else 0
    item.updated_at=utcnow();move=StockMove(case_id=row.id,item_id=item.id,quantity_milli=qty,value_cents=value,
        unit_cost_cents=abs(value)*1000//abs(qty),purpose=purpose,original_id=original,actor_id=user.id,business_date=today())
    db.add(move);db.flush()
    from .warehouse_stock import after_stock_move
    after_stock_move(db,user,row,item,move)
    return move
def _return(db,user,row,action,v):
    if action=='return_request':
        if not row.data.get('dispatched') or row.data.get('cancelled'):raise HTTPException(409,'只有实际出库的商品才能申请原单退货')
        _evidence(db,user,row,v['evidence_id'])
        if len({l['dispatch_id'] for l in v['lines']})!=len(v['lines']):raise HTTPException(422,'同一原出库行请合并数量')
        request=RetailReturn(case_id=row.id,reason=v['reason'],requested_by=user.id,evidence_id=v['evidence_id']);db.add(request);db.flush()
        for line in v['lines']:
            source=_one(db,RetailDispatch,line['dispatch_id'])
            if source.case_id!=row.id:raise HTTPException(404,'本单没有该原始出库行')
            returned=sum(p.quantity_milli for p in _rows(db,RetailReturnPosting,dispatch_id=source.id))
            if line['quantity_milli']>source.quantity_milli-returned:raise HTTPException(409,'退货数量超过原出库未退数量')
            db.add(RetailReturnLine(return_id=request.id,dispatch_id=source.id,quantity_milli=line['quantity_milli']))
        flow.ensure_task(db,row,'retail_return_review_'+str(request.id),'复核精品退货与安装保留费','manager');return
    request=_one(db,RetailReturn,v['return_id'])
    if request.case_id!=row.id:raise HTTPException(404,'本单没有该退货申请')
    if request.version!=v['return_version']:raise HTTPException(409,'退货申请已变化，请刷新后核对')
    request.updated_at=utcnow();lines=_rows(db,RetailReturnLine,return_id=request.id)
    if action=='return_approve':
        if request.status!='requested':raise HTTPException(409,'该退货已经复核或撤销')
        _task(db,user,row,'retail_return_review_'+str(request.id))
        if request.requested_by==user.id and user.role!='admin':raise HTTPException(403,'申请人不能批准自己的退货')
        for line in lines:
            source=_one(db,RetailDispatch,line.dispatch_id)
            held=db.scalar(select(func.coalesce(func.sum(RetailReturnLine.quantity_milli),0)).join(RetailReturn,RetailReturn.id==RetailReturnLine.return_id)
                .where(RetailReturnLine.dispatch_id==source.id,RetailReturn.status.in_(['approved','rectification','reinspection','handback','accepted'])))
            if line.quantity_milli>source.quantity_milli-held:raise HTTPException(409,'该原出库数量已被其他获批退货占用')
        request.status='approved';request.approved_by=user.id;request.retain_installation=bool(row.data.get('installed'))
        flow.finish_task(db,row,'retail_return_review_'+str(request.id),user)
        flow.ensure_task(db,row,'retail_return_receive_'+str(request.id),'实际检查退回商品是否可售','inventory')
    elif action=='return_cancel':
        if request.status not in {'requested','approved'}:raise HTTPException(409,'验收失败的待整改商品须完成整改和复检；不能跳过实物异常处理撤销')
        request.status='cancelled'
        for suffix in ('review','receive'):flow.finish_task(db,row,'retail_return_'+suffix+'_'+str(request.id),user,'cancelled')
    elif action=='return_reject':
        if request.status not in {'rectification','reinspection'}:raise HTTPException(409,'须有退货不合格事实，才能决定拒收并交回客户')
        request.status='handback'
        for suffix in ('rectify','receive'):flow.finish_task(db,row,'retail_return_'+suffix+'_'+str(request.id),user,'cancelled')
        flow.ensure_task(db,row,'retail_return_handback_'+str(request.id),'将拒收商品实际交回客户','inventory')
    elif action=='return_handback':
        if request.status!='handback':raise HTTPException(409,'主管决定拒收后才能确认实物交回')
        _task(db,user,row,'retail_return_handback_'+str(request.id));_evidence(db,user,row,v['evidence_id']);request.status='rejected'
        flow.finish_task(db,row,'retail_return_handback_'+str(request.id),user)
    elif action=='return_rectify':
        if request.status!='rectification':raise HTTPException(409,'只有验收不合格的退货才能提交整改')
        _task(db,user,row,'retail_return_rectify_'+str(request.id));_evidence(db,user,row,v['evidence_id']);request.status='reinspection'
        flow.finish_task(db,row,'retail_return_rectify_'+str(request.id),user);flow.ensure_task(db,row,'retail_return_receive_'+str(request.id),'整改后复检退货可售性','inventory',reopen=True)
    elif action=='return_receive':
        if request.status not in {'approved','reinspection'}:raise HTTPException(409,'退货尚未获批或须先完成整改')
        _task(db,user,row,'retail_return_receive_'+str(request.id));_evidence(db,user,row,v['evidence_id'])
        flow.finish_task(db,row,'retail_return_receive_'+str(request.id),user)
        if not v['passed']:
            request.status='rectification';flow.ensure_task(db,row,'retail_return_rectify_'+str(request.id),'处理退货缺陷并提交复检','technician',reopen=True);return
        for line in lines:
            source=_one(db,RetailDispatch,line.dispatch_id);sale=_one(db,RetailLine,source.line_id)
            prior=_rows(db,RetailReturnPosting,dispatch_id=source.id);remaining=source.quantity_milli-sum(p.quantity_milli for p in prior)
            if line.quantity_milli>remaining:raise HTTPException(409,'原单剩余可退数量不足')
            cost=_portion(source.value_cents-sum(p.value_cents for p in prior),line.quantity_milli,remaining)
            goods=_portion(sale.goods_cents-sum(p.goods_cents for p in prior),line.quantity_milli,remaining)
            install=_portion(sale.installation_cents-sum(p.installation_cents for p in prior),line.quantity_milli,remaining)
            move=_stock(db,user,row,_one(db,Item,sale.item_id),line.quantity_milli,cost,'retail_return',source.stock_move_id)
            db.add(RetailReturnPosting(case_id=row.id,return_line_id=line.id,dispatch_id=source.id,stock_move_id=move.id,quantity_milli=line.quantity_milli,
                value_cents=cost,goods_cents=goods,installation_cents=install,retained_cents=install if request.retain_installation else 0,evidence_id=v['evidence_id']))
        request.status='accepted'
        # Keep stock, original tender reduction and restoration liability atomic.
        db.flush()
        from .retail_group_service import record_actual_return
        line_ids={line.id for line in lines}
        for posting in _rows(db,RetailReturnPosting,case_id=row.id):
            if posting.return_line_id in line_ids:record_actual_return(db,user,row,posting)
    else:raise HTTPException(404,'退货动作不存在')
def command(db,user,key,request_id,version,action,v):
    if user.role not in ROLES.get(action,set()):raise HTTPException(403,'当前岗位不能办理此精品步骤')
    def operation():
        row=get_order(db,user,key)
        from . import retail_group_service as mixed
        if row.version!=version:raise HTTPException(409,'精品单已经变化，请刷新后核对')
        row.updated_at=utcnow();lines=_rows(db,RetailLine,case_id=row.id)
        if action.startswith('return_'):_return(db,user,row,action,v)
        elif action=='approve':
            if row.state!='approval':raise HTTPException(409,'报价已复核或取消')
            _task(db,user,row,'retail_approve')
            if row.created_by==user.id and user.role!='admin':raise HTTPException(403,'开单人不能批准自己的报价')
            if row.amount_cents<v['minimum_total_cents'] and not v['allow_below_minimum']:raise HTTPException(409,'报价低于明确最低价，须主管确认低价例外及原因')
            flow.set_data(row,approved=True);flow.finish_task(db,row,'retail_approve',user)
            flow.ensure_task(db,row,'retail_authorize','确认客户同意报价及安装退费约定','sales',assignee=row.owner_id)
        elif action=='authorize':
            if row.state!='authorization' or v['revision']!=1:raise HTTPException(409,'客户确认须关联当前已获批报价版本')
            _task(db,user,row,'retail_authorize');_evidence(db,user,row,v['evidence_id'],'authorization')
            from .member_pricing_service import record_authorization
            record_authorization(db,user,row,row.id,v['evidence_id']);flow.set_data(row,authorized=True)
            from .membership_service import freeze_points_rule
            freeze_points_rule(db,user,row)
            flow.finish_task(db,row,'retail_authorize',user);flow.ensure_task(db,row,'retail_dispatch','按已确认精品清单实际出库','inventory')
        elif action=='cancel':
            if row.data.get('dispatched') or row.data.get('cancelled'):raise HTTPException(409,'已出库商品须走原单退货，或本单已取消')
            for line in lines:_reserve(db,user,row,_one(db,Item,line.item_id),-line.quantity_milli,'cancel')
            flow.set_data(row,cancelled=True);flow.close_tasks(db,row,user)
        elif action=='dispatch':
            if row.state!='pending' or not row.data.get('authorized') or row.data.get('dispatched'):raise HTTPException(409,'报价需审批及客户确认，且只能实际出库一次')
            _task(db,user,row,'retail_dispatch');_evidence(db,user,row,v['evidence_id'])
            from .inventory_availability import assert_can_issue
            for line in lines:
                item=_one(db,Item,line.item_id);assert_can_issue(db,item,line.quantity_milli,excluding_retail_case_id=row.id)
                cost=_portion(item.inventory_value_cents,line.quantity_milli,item.quantity_milli)
                _reserve(db,user,row,item,-line.quantity_milli,'dispatch');move=_stock(db,user,row,item,-line.quantity_milli,-cost,'retail_dispatch')
                db.add(RetailDispatch(case_id=row.id,line_id=line.id,stock_move_id=move.id,quantity_milli=line.quantity_milli,value_cents=cost,evidence_id=v['evidence_id']))
            flow.set_data(row,dispatched=True);flow.finish_task(db,row,'retail_dispatch',user)
            if any(l.work_item_id for l in lines):flow.ensure_task(db,row,'retail_install','实际完成精品安装并说明结果','technician')
            flow.ensure_task(db,row,'retail_accept','客户确认接收精品及安装结果','sales',assignee=row.owner_id)
        elif action=='install':
            if not row.data.get('dispatched') or row.data.get('installed') or row.data.get('accepted_date') or _active(db,row):raise HTTPException(409,'须已出库、未安装且无待处理退货才可确认安装')
            if not any(l.work_item_id for l in lines):raise HTTPException(409,'本单无安装项目')
            original=_rows(db,RetailDispatch,case_id=row.id);returned=_rows(db,RetailReturnPosting,case_id=row.id)
            if not any(l.work_item_id and l.quantity_milli>sum(p.quantity_milli for p in returned if any(d.id==p.dispatch_id and d.line_id==l.id for d in original)) for l in lines):
                raise HTTPException(409,'需要安装的商品已全部验收退回，不能虚构安装事实')
            _task(db,user,row,'retail_install');_evidence(db,user,row,v['evidence_id']);flow.set_data(row,installed=True);flow.finish_task(db,row,'retail_install',user)
        elif action=='accept':
            if not row.data.get('dispatched') or row.data.get('accepted_date') or _active(db,row):raise HTTPException(409,'须已出库、无待处理退货且未接收才能办理')
            returned=_rows(db,RetailReturnPosting,case_id=row.id);dispatches=_rows(db,RetailDispatch,case_id=row.id)
            needs_install=any(l.work_item_id and l.quantity_milli>sum(p.quantity_milli for p in returned if any(d.id==p.dispatch_id and d.line_id==l.id for d in dispatches)) for l in lines)
            if needs_install and not row.data.get('installed'):raise HTTPException(409,'尚未由技师确认实际安装，不能确认交付')
            _task(db,user,row,'retail_accept');_evidence(db,user,row,v['evidence_id']);flow.set_data(row,accepted_date=today().isoformat());flow.finish_task(db,row,'retail_accept',user)
            if not needs_install:flow.finish_task(db,row,'retail_install',user,'cancelled')
        elif action in {'receive','refund'}:
            if not row.data.get('approved'):raise HTTPException(409,'未获批报价不能确认收退款')
            _evidence(db,user,row,v['evidence_id'],'receipt');amount=totals(db,row);original=None
            if action=='receive':
                if row.data.get('cancelled') or v['amount_cents']>amount['receivable_cents']:raise HTTPException(409,'超过当前精品可收金额')
                mixed.guard_cash_receive(db,user,row,v['amount_cents'])
                _task(db,user,row,'retail_receive')
            else:
                if v['amount_cents']>amount['refund_due_cents']:raise HTTPException(409,'超过验收退货或取消后的实际应退余额')
                _task(db,user,row,'retail_refund');original=_one(db,PaymentLink,v['original_payment_id'])
                if original.case_id!=row.id or original.direction!='in':raise HTTPException(404,'本单没有该笔原始收款')
                mixed.guard_cash_refund(db,user,row,original.id,v['amount_cents'])
            link=flow.add_payment(db,user,row,v,direction='in' if action=='receive' else 'out',original=original,amount=v['amount_cents'])
            db.add(RetailPayment(case_id=row.id,payment_link_id=link.id,evidence_id=v['evidence_id']))
            if action=='receive':mixed.attach_cash(db,user,row,link)
            else:mixed.attach_cash_refund(db,user,row,link,original.id)
        else:raise HTTPException(404,'精品动作不存在')
        flow.log_event(db,user,row,'retail_'+action,LABELS[action],detail=v);db.flush()
        if action in {'cancel','return_receive'}:
            from .business_finance_sources import return_retail_advance
            return_retail_advance(db,user,row,action,v.get('evidence_id'))
        _sync(db,user,row)
        from .membership_service import sync_consumption_points
        sync_consumption_points(db,user,row,evidence_id=v.get('evidence_id'))
        from .invoice_service import sync_source
        sync_source(db,user,row)
        return row
    return _execute(db,user,request_id,action,{'case_id':key,'version':version,'values':v},operation)
def describe(db,user,row):
    order=_one(db,RetailOrder,row.id);money=user.role in MONEY_ROLES;cost=user.role in COST_ROLES
    def fields(obj,names):return {k:getattr(obj,k) for k in names}
    result=fields(row,['id','number','version','flow_version','state','store_id','customer_id'])
    result.update(fields(order,['revision','related_repair_id','customer_name','installation_policy']),data=dict(row.data),business_date=row.business_date.isoformat())
    result['lines']=[]
    for line in _rows(db,RetailLine,case_id=row.id):
        d=fields(line,['id','item_id','sku','name','unit','quantity_milli','work_item_id','work_code','work_name'])
        if money:d.update(fields(line,['unit_price_cents','goods_cents','installation_unit_price_cents','installation_cents']))
        result['lines'].append(d)
    result['dispatches']=[]
    for source in _rows(db,RetailDispatch,case_id=row.id):
        prior=_rows(db,RetailReturnPosting,dispatch_id=source.id);d=fields(source,['id','line_id','quantity_milli','evidence_id'])
        d['returned_milli']=sum(p.quantity_milli for p in prior)
        if cost:d['value_cents']=source.value_cents
        result['dispatches'].append(d)
    result['returns']=[]
    for request in _rows(db,RetailReturn,case_id=row.id):
        d=fields(request,['id','version','status','reason','retain_installation'])
        d['lines']=[fields(l,['id','dispatch_id','quantity_milli']) for l in _rows(db,RetailReturnLine,return_id=request.id)]
        result['returns'].append(d)
    result['return_postings']=[]
    for p in _rows(db,RetailReturnPosting,case_id=row.id):
        d=fields(p,['id','return_line_id','dispatch_id','quantity_milli','evidence_id'])
        if money:d.update(fields(p,['goods_cents','installation_cents','retained_cents']))
        if cost:d['value_cents']=p.value_cents
        result['return_postings'].append(d)
    result['payments']=[]
    if money:
        result.update(amount_cents=row.amount_cents,discount_cents=order.discount_cents,totals=totals(db,row))
        from .member_pricing_service import describe_quote
        member_price=describe_quote(db,user,row,row.id)
        if member_price:result['member_pricing']=member_price
        if not cost:
            for field in ('cost_cents','group_external_discount_cents','group_internal_settlement_cents',
                    'group_recognized_cents','group_discount_borne_cents','service_discount_borne_cents'):
                result['totals'].pop(field,None)
            if 'group_paid_cents' in result['totals']:
                result['totals'].pop('net_price_cents',None);result['totals'].pop('revenue_cents',None)
        from .retail_group_service import exists,cash_refundable
        refund_caps={}
        if user.role in COST_ROLES and exists(db,row):
            for allocation,amount in cash_refundable(db,row):
                refund_caps[allocation.payment_link_id]=refund_caps.get(allocation.payment_link_id,0)+amount
        for p in _rows(db,PaymentLink,case_id=row.id):
            d=fields(p,['id','direction','amount_cents','original_id','business_date'])
            if user.role in COST_ROLES:d.update(fields(p,['cash_id','account_id','reference']))
            if p.direction=='in' and 'group_paid_cents' in result['totals'] and user.role in COST_ROLES:
                d['refundable_cents']=refund_caps.get(p.id,0)
            result['payments'].append(d)
    result['actions']=[k for k,roles in ROLES.items() if user.role in roles]
    from .retail_bundle_service import sale_info
    result['bundle']=sale_info(db,row,money)
    if result['bundle']:
        for line in result['lines']:
            line['pricing_mode']='frozen_bundle'
            line.pop('unit_price_cents',None);line.pop('installation_unit_price_cents',None)
    return result

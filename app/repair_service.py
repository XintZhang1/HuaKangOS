"""Explicit repair v3 commands; quotes, actual stock and payer facts commit once."""
import hashlib,json,uuid
from datetime import date
from importlib.util import find_spec
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .flow_models import Case,Customer,Item,StockMove,PaymentLink,Task,Reference,FileAsset
from .flow_documents import can_file
from .tenancy import single_store
from . import flow_engine as flow
from .repair_models import (RepairQuote,RepairLine,RepairPriceApproval,RepairAuthorization,RepairQuoteCancellation,
    RepairStock,RepairQuality,RepairSettlement,RepairAllocation,RepairPayment)

READ_ROLES={'admin','manager','service','technician','inventory','finance','auditor'}
MONEY_ROLES={'admin','manager','service','finance','auditor'}
COST_ROLES={'admin','manager','finance','auditor'}
ROLES={'quote':{'admin','service'},'quote_cancel':{'admin','manager','service'},'price_approve':{'admin','manager'},
    'authorize':{'admin','service'},'start':{'admin','technician'},'issue':{'admin','inventory'},
    'return_material':{'admin','inventory'},'finish':{'admin','technician'},'quality':{'admin','service'},
    'allocate':{'admin','manager'},'receive':{'admin','finance'},'release':{'admin','service'},'cancel':{'admin','manager','service'}}
LABELS={'quote':'提交维修报价版本','quote_cancel':'撤销待授权报价','price_approve':'主管价格授权','authorize':'记录客户当前报价授权',
    'start':'确认维修开工','issue':'按授权明细发料','return_material':'按原领料退回','finish':'完成本次施工','quality':'记录维修质检',
    'allocate':'冻结多方承担','receive':'登记承担方实际到账','release':'确认客户接车','cancel':'取消未开工维修'}


def is_detailed(row):return row.kind=='repair' and row.flow_version in {3,4}
def _rows(db,model,**filters):return list(db.scalars(select(model).filter_by(**filters).order_by(model.id)))
def _one(db,model,key):
    obj=db.scalar(select(model).where(model.id==key))
    if not obj:raise HTTPException(404,'当前门店记录不存在')
    return obj
def _quote(db,row,key=None):
    quote=_one(db,RepairQuote,key or row.data.get('quote_id',0))
    if quote.case_id!=row.id:raise HTTPException(404,'报价不属于本维修工单')
    return quote
def get_order(db,user,key):
    if user.role not in READ_ROLES:raise HTTPException(403,'当前岗位不能访问维修明细工单')
    row=flow.get_case(db,user,key)
    if not is_detailed(row):raise HTTPException(409,'本接口仅办理维修明细 v3／v4，历史维修单请使用原流程')
    if row.flow_version==4:
        from .service_intake_service import context
        context(db,row)
    return row
def _evidence(db,user,row,key):
    asset=flow.file_exists(db,row,key)
    if not can_file(user,row,asset):raise HTTPException(403,'当前岗位不能使用此类凭据')
    return asset
def _task(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or (task.assignee_id!=user.id and user.role!='admin'):
        raise HTTPException(409,'该步骤尚无待办或已转交其他员工，请核对接手人')
def _settlement(db,row):return db.scalar(select(RepairSettlement).where(RepairSettlement.case_id==row.id))
def _authorized(db,row):
    quote=_quote(db,row)
    if row.data.get('authorized_quote_id')!=quote.id:raise HTTPException(409,'当前报价或增项尚未获客户授权')
    return quote
def _extra_credit(db,row):
    from .repair_package_service import case_paid_amount as package_paid,case_reserved_amount as package_reserved
    if find_spec('app.group_benefits_service'):
        from .group_benefits_service import case_paid_amount,case_reserved_amount
        return case_paid_amount(db,row.id)+package_paid(db,row.id),case_reserved_amount(db,row.id)+package_reserved(db,row.id)
    return package_paid(db,row.id),package_reserved(db,row.id)
def _credits(db,row):
    from .group_service import case_paid_amount,case_reserved_amount
    extra,hold=_extra_credit(db,row)
    if find_spec('app.business_finance_service'):
        from .business_finance_service import case_credit_amount,case_reserved_amount as finance_reserved
        extra+=case_credit_amount(db,row.id);hold+=finance_reserved(db,row.id)
    return case_paid_amount(db,row.id)+extra,case_reserved_amount(db,row.id)+hold
def _cash_paid(db,allocation):
    return sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in db.scalars(select(PaymentLink).join(RepairPayment,RepairPayment.payment_link_id==PaymentLink.id)
        .where(RepairPayment.allocation_id==allocation.id)))
def allocation_amount(db,row,allocation):
    from .aftercare_service import net_charge
    from .claims_service import allocation_delta
    return net_charge(db,row,allocation.id)+allocation_delta(db,allocation.id)
def _allocation_due(db,row,allocation,include_reservations=False):
    paid=_cash_paid(db,allocation)
    if allocation.payer_type=='internal':return 0
    if allocation.payer_type=='customer':
        credit,hold=_credits(db,row);paid+=credit+(hold if include_reservations else 0)
    return max(0,allocation_amount(db,row,allocation)-paid)
def customer_due(db,row,include_reservations=True):
    if not is_detailed(row) or not _settlement(db,row) or row.state not in {'settling','credit_open','completed'}:
        raise HTTPException(409,'客户承担须在质检通过并冻结多方结算后使用权益')
    allocation=db.scalar(select(RepairAllocation).where(RepairAllocation.case_id==row.id,RepairAllocation.payer_type=='customer'))
    return _allocation_due(db,row,allocation,include_reservations) if allocation else 0
def eligible_benefit_units(db,row,service_code):
    customer_due(db,row)
    quote=_authorized(db,row)
    if quote.purpose=='stop':return 0
    from .rework_extension_service import customer_line
    from .repair_package_service import excluded_line_keys
    excluded=excluded_line_keys(db,row,quote.id)
    return sum(line.quantity_milli//1000 for line in _rows(db,RepairLine,quote_id=quote.id)
        if line.kind=='work' and line.code==service_code and line.unit=='job' and line.amount_cents>0 and customer_line(db,line) and line.line_key not in excluded)
def eligible_benefit_credit(db,row,service_code):
    customer_due(db,row)
    quote=_authorized(db,row)
    if quote.purpose=='stop':return 0
    from .rework_extension_service import customer_line
    from .repair_package_service import excluded_line_keys
    excluded=excluded_line_keys(db,row,quote.id)
    return sum(line.amount_cents for line in _rows(db,RepairLine,quote_id=quote.id)
        if line.kind=='work' and line.code==service_code and line.unit=='job' and line.amount_cents>0 and customer_line(db,line) and line.line_key not in excluded)
def gross_revenue_amount(db,row):
    return sum(a.amount_cents for a in _rows(db,RepairAllocation,case_id=row.id) if a.payer_type!='internal')
def revenue_amount(db,row):
    return sum(allocation_amount(db,row,a) for a in _rows(db,RepairAllocation,case_id=row.id) if a.payer_type!='internal')
def receivable_amount(db,row):
    return sum(_allocation_due(db,row,a) for a in _rows(db,RepairAllocation,case_id=row.id))
def receivable_rows(db,row):
    result=[]
    for allocation in _rows(db,RepairAllocation,case_id=row.id):
        if allocation.payer_type=='internal':continue
        due=_allocation_due(db,row,allocation)
        amount=allocation_amount(db,row,allocation)
        result.append({'payer_type':allocation.payer_type,'payer_name':allocation.payer_name,'amount_cents':amount,
            'paid_cents':amount-due,'due_cents':due,'due_date':allocation.due_date})
    return result
def _stock_net(db,row,line_key=None):
    rows=_rows(db,RepairStock,case_id=row.id)
    if line_key:rows=[r for r in rows if r.line_key==line_key]
    return sum(r.quantity_milli for r in rows),sum(r.value_cents for r in rows)
def _pending_parts(db,row):
    if not row.data.get('authorized_quote_id') or row.data.get('stopping'):return []
    return [line for line in _rows(db,RepairLine,quote_id=row.data['authorized_quote_id'])
        if line.kind=='part' and _stock_net(db,row,line.line_key)[0]<line.quantity_milli]


def sync_after_member(db,user,row,evidence_id=None):
    """Reconcile settlement only; never attest that the customer took a car."""
    db.flush()
    if not is_detailed(row) or not _settlement(db,row):return
    for allocation in _rows(db,RepairAllocation,case_id=row.id):
        key='repair_receive_'+str(allocation.id)
        if _allocation_due(db,row,allocation)>0:
            flow.ensure_task(db,row,key,'登记'+{'customer':'客户','insurer':'保险','manufacturer':'厂家','internal':'内部'}[allocation.payer_type]+'承担款到账','finance',due=allocation.due_date,reopen=True)
        else:flow.finish_task(db,row,key,user)
    if row.data.get('released_date'):
        row.state='credit_open' if receivable_amount(db,row)>0 else 'completed'
        row.completed_date=today() if row.state=='completed' else None
    else:row.state='settling'
    row.updated_at=utcnow();db.flush()
    from .membership_service import sync_consumption_points
    sync_consumption_points(db,user,row,evidence_id=evidence_id)
    from .claims_service import sync_source as sync_claims
    sync_claims(db,user,row)


def _execute(db,user,key,operation,payload,callback):
    single_store(db);digest=flow.request_digest('repair_v3_'+operation,payload)
    try:
        old=flow.prior_request(db,user,key,digest)
        if old:return describe(db,user,old)
        row=callback();db.flush();flow.save_receipt(db,user,key,digest,row);db.commit()
        return describe(db,user,row)
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'维修记录同时变化，请刷新核对，保留原请求编号确认结果')
    except Exception:db.rollback();raise


def create(db,user,key,values):
    if user.role not in {'admin','service'}:raise HTTPException(403,'维修明细开单由服务顾问办理')
    def run():
        customer=_one(db,Customer,values['customer_id'])
        row=Case(number='HKR'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='repair',flow_version=3,
            state='assessment',title=customer.name+' · 维修明细',owner_id=user.id,created_by=user.id,customer_id=customer.id,
            business_date=today(),due_date=date.fromisoformat(values['due_date']),data={'plate':values['plate'],'problem':values['problem']})
        db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);flow.ensure_task(db,row,'repair_quote','核对项目配件并报价','service',assignee=user.id)
        flow.log_event(db,user,row,'repair_v3_create','建立维修明细工单');return row
    return _execute(db,user,key,'create',values,run)


def _distribute(total,weights):
    """Largest remainder, stable line order, exact integer fen conservation."""
    weight=sum(weights)
    if not weight:
        if total:raise HTTPException(422,'零金额明细不能分摊折扣')
        return [0]*len(weights)
    portions=[total*w//weight for w in weights]
    for i in sorted(range(len(weights)),key=lambda i:(-(total*weights[i]%weight),i))[:total-sum(portions)]:portions[i]+=1
    return portions


def _new_quote(db,user,row,v):
    if row.state not in {'assessment','working','approval','authorization'} or _settlement(db,row):
        raise HTTPException(409,'当前阶段不能更改报价；已结算或已交车须走后续独立纠错业务')
    old=_quote(db,row,row.data['authorized_quote_id']) if row.data.get('authorized_quote_id') else None
    from . import rework_extension_service as rework
    rework_contract=rework.prepare_quote(db,row,v,old)
    from . import repair_package_service as packages
    package_contract=packages.prepare_quote(db,user,row,v,old)
    if row.data.get('quote_id') and row.data.get('quote_id')!=row.data.get('authorized_quote_id'):
        raise HTTPException(409,'已有待审批或授权版本，请先明确撤销，不能覆盖')
    carry={l.line_key:l for l in _rows(db,RepairLine,quote_id=old.id)} if old and (row.data.get('started') or rework_contract or package_contract) else {}
    if row.data.get('stopping'):raise HTTPException(409,'已授权停工，不能重新加项开工')
    stop=v['purpose']=='stop'
    if stop and (not carry or not row.data.get('started')):raise HTTPException(409,'未开工维修请取消；停工报价用于明确已履约保留费用')
    specs=[];seen=set();sources=set();increments=[];member_contract=None
    from . import member_pricing_service as pricing
    if stop and v.get('member_pricing'):raise HTTPException(409,'停工只按原已授权费用约定保留，不重新应用会员折扣')
    from .master_data import require_active
    if stop:
        if v['lines']:raise HTTPException(422,'停工版本保留原项目配件清单，只明确约定保留费')
        retained=v['retained_amount_cents']
        if retained is None or retained>old.amount_cents:raise HTTPException(422,'保留费不能超过已授权金额')
        allocations=_distribute(retained,[l.amount_cents for l in carry.values()])
        for line,amount in zip(carry.values(),allocations):
            gross=(line.quantity_milli*line.unit_price_cents+500)//1000
            specs.append({k:getattr(line,k) for k in ('line_key','kind','work_item_id','item_id','code','name','unit','standard_fee_cents','quantity_milli','unit_price_cents')}|
                {'amount_cents':amount,'discount_cents':gross-amount})
            if package_contract:specs[-1]['_original_amount']=line.amount_cents
        packages.stop_specs(package_contract,specs,retained,_distribute)
    else:
        if not v['lines'] or v['retained_amount_cents'] is not None:raise HTTPException(422,'正常报价需有项目配件，不填写停工保留费')
        for data in v['lines']:
            previous=carry.get(data.get('line_key'));kind=data['kind'];source=data['source_id'];qty=data['quantity_milli'];price=data['unit_price_cents']
            source_key=(kind,source,data.get('charge_scope'),data.get('source_line_id'),data.get('package_lot_id')) if rework_contract or package_contract else (kind,source)
            if source_key in sources:raise HTTPException(422,'相同责任类别的作业项目或配件请合并数量')
            sources.add(source_key);base_amount=0
            if previous:
                if kind!=previous.kind or source!=(previous.work_item_id if kind=='work' else previous.item_id) or price!=previous.unit_price_cents or qty<previous.quantity_milli:
                    raise HTTPException(409,'开工后已有授权行不能移除、减量或改价；停工需单独约定已履约费用')
                if qty>previous.quantity_milli:
                    active_source=require_active(db,'work_items',source) if kind=='work' else _one(db,Item,source)
                    if not active_source.active:raise HTTPException(422,'停用项目或配件不能追加数量')
                spec={k:getattr(previous,k) for k in ('line_key','kind','work_item_id','item_id','code','name','unit','standard_fee_cents')}
                base_amount=previous.amount_cents;increment=(qty*price+500)//1000-(previous.quantity_milli*price+500)//1000;seen.add(previous.line_key)
            else:
                if data.get('line_key'):raise HTTPException(422,'新增明细不能指定其他版本的行编号')
                source_row=require_active(db,'work_items',source) if kind=='work' else _one(db,Item,source)
                if not source_row.active:raise HTTPException(422,'项目或配件已停用')
                spec={'line_key':uuid.uuid4().hex,'kind':kind,'work_item_id':source if kind=='work' else None,'item_id':source if kind=='part' else None,
                    'code':source_row.code if kind=='work' else source_row.sku,'name':source_row.name,
                    'unit':source_row.billing_unit if kind=='work' else source_row.unit,'standard_fee_cents':source_row.standard_fee_cents if kind=='work' else 0}
                increment=(qty*price+500)//1000
            specs.append(spec|{'quantity_milli':qty,'unit_price_cents':price,'amount_cents':base_amount+increment});increments.append(increment)
        if set(carry)-seen:raise HTTPException(409,'增项版本必须保留全部已授权明细')
        parts=rework_contract['scopes'] if rework_contract else [{'charge_scope':'customer'} for _ in specs]
        components=[dict(line_key=s['line_key'],component=s['kind'],source_id=s['work_item_id'] if s['kind']=='work' else s['item_id'],basis_cents=increment,carry_cents=s['amount_cents']-increment,charge_scope=part['charge_scope']) for s,increment,part in zip(specs,increments,parts)]
        packages.quote_basis(package_contract,specs,components)
        member_contract=pricing.prepare_quote(db,user,row,v.get('member_pricing'),components,v['discount_cents'])
        if member_contract:
            for spec,priced in zip(specs,member_contract['lines']):spec['amount_cents']=priced['carry_cents']+priced['net_cents']
        else:
            discounts=[0 if c.get('price_source')=='package_contract' else increment for c,increment in zip(components,increments)]
            if v['discount_cents']>sum(discounts):raise HTTPException(422,'本次新增优惠不能超过未被已付套餐覆盖的新增项目配件金额')
            for spec,discount in zip(specs,_distribute(v['discount_cents'],discounts)):spec['amount_cents']-=discount
        for spec in specs:spec['discount_cents']=(spec['quantity_milli']*spec['unit_price_cents']+500)//1000-spec['amount_cents']
    amount=sum(s['amount_cents'] for s in specs)
    if amount>1_000_000_000_000:raise HTTPException(422,'报价金额超出允许范围')
    scopes=rework.quote_scopes(rework_contract,specs)
    digest_data={'purpose':v['purpose'],'reason':v['reason'],'lines':specs}
    if scopes is not None:digest_data['rework_scopes']=scopes
    if member_contract:digest_data['member_pricing']=pricing.canonical(member_contract)
    if package_contract:
        for p in package_contract['lines']:p['line_key']=specs[p['index']]['line_key']
        digest_data['repair_package']=packages.canonical(package_contract)
    digest=hashlib.sha256(json.dumps(digest_data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    revision=db.scalar(select(func.coalesce(func.max(RepairQuote.revision),0)).where(RepairQuote.case_id==row.id))+1
    quote=RepairQuote(case_id=row.id,revision=revision,purpose=v['purpose'],reason=v['reason'],amount_cents=amount,
        discount_cents=sum(s['discount_cents'] for s in specs),digest=digest,created_by=user.id)
    db.add(quote);db.flush()
    quote_lines=[RepairLine(quote_id=quote.id,**spec) for spec in specs]
    db.add_all(quote_lines);db.flush();rework.freeze_quote(db,quote,quote_lines,rework_contract,scopes)
    pricing.freeze_quote(db,user,row,'repair',quote.id,member_contract)
    packages.freeze_quote(db,user,row,quote,quote_lines,package_contract)
    flow.set_data(row,quote_id=quote.id);row.state='approval';flow.finish_task(db,row,'repair_quote',user)
    flow.ensure_task(db,row,'repair_price_'+str(quote.id),'确认当前报价价格权限','manager')


def _post_stock(db,user,row,item,qty,value,purpose,original=None):
    item.quantity_milli+=qty;item.inventory_value_cents+=value
    if item.quantity_milli<0 or item.inventory_value_cents<0 or (not item.quantity_milli and item.inventory_value_cents):
        raise HTTPException(409,'本店配件数量或库存价值不足／不一致，不能发料')
    item.unit_cost_cents=(2*item.inventory_value_cents*1000+item.quantity_milli)//(2*item.quantity_milli) if item.quantity_milli else 0
    item.updated_at=utcnow()
    move=StockMove(case_id=row.id,item_id=item.id,quantity_milli=qty,value_cents=value,unit_cost_cents=abs(value)*1000//abs(qty),
        purpose=purpose,actor_id=user.id,business_date=today(),original_id=original)
    db.add(move);db.flush()
    from .warehouse_stock import after_stock_move
    after_stock_move(db,user,row,item,move)
    return move


def _review(db,user,row,action,v):
    quote=_quote(db,row,v['quote_id'])
    if quote.id!=row.data.get('quote_id') or row.state not in {'approval','authorization'}:
        raise HTTPException(409,'该报价已结束或不是当前待授权版本')
    if action=='price_approve':
        if row.state!='approval':raise HTTPException(409,'价格已经复核')
        if quote.created_by==user.id and user.role!='admin':raise HTTPException(403,'报价人不能审批本人报价')
        if quote.amount_cents<v['minimum_total_cents'] and not v['allow_below_minimum']:
            raise HTTPException(409,'报价低于本次主管确认的最低金额，须明确低价授权及原因')
        db.add(RepairPriceApproval(quote_id=quote.id,minimum_total_cents=v['minimum_total_cents'],allow_below_minimum=v['allow_below_minimum'],reason=v['reason'],actor_id=user.id))
        row.state='authorization';flow.finish_task(db,row,'repair_price_'+str(quote.id),user)
        from .rework_extension_service import service_assignee
        flow.ensure_task(db,row,'repair_authorize_'+str(quote.id),'取得当前报价客户授权','service',assignee=service_assignee(db,row))
    elif action=='authorize':
        if row.state!='authorization':raise HTTPException(409,'当前报价须先完成主管价格授权')
        asset=_evidence(db,user,row,v['evidence_id'])
        if row.flow_version==4 and asset.category!='authorization':raise HTTPException(422,'本次客户报价授权必须使用客户授权类别文件，保护报价文件的岗位权限')
        if db.scalar(select(RepairAuthorization.id).join(FileAsset,FileAsset.id==RepairAuthorization.evidence_id)
            .join(RepairQuote,RepairQuote.id==RepairAuthorization.quote_id)
            .where(RepairQuote.case_id==row.id,FileAsset.sha256==asset.sha256)):
            raise HTTPException(409,'该客户授权内容已绑定本工单旧报价，重新上传相同内容也不能代替本次新授权')
        from .member_pricing_service import record_authorization
        from .repair_package_service import guard_authorization
        guard_authorization(db,user,row,quote.id)
        record_authorization(db,user,row,quote.id,v['evidence_id'])
        db.add(RepairAuthorization(quote_id=quote.id,evidence_id=v['evidence_id'],quote_digest=quote.digest,actor_id=user.id))
        from .membership_service import freeze_points_rule
        freeze_points_rule(db,user,row)
        flow.set_data(row,authorized_quote_id=quote.id,stopping=quote.purpose=='stop');row.amount_cents=quote.amount_cents;row.state='working'
        flow.finish_task(db,row,'repair_authorize_'+str(quote.id),user)
        flow.ensure_task(db,row,'repair_work','核对授权并完成施工' if quote.purpose=='service' else '记录停工时已完成施工与保留项目','technician',reopen=True)
    else:
        db.add(RepairQuoteCancellation(quote_id=quote.id,reason=v['reason'],actor_id=user.id))
        from .repair_package_service import release_quote
        release_quote(db,user,row,quote.id)
        for prefix in ('repair_price_','repair_authorize_'):flow.finish_task(db,row,prefix+str(quote.id),user,'cancelled')
        previous=row.data.get('authorized_quote_id');flow.set_data(row,quote_id=previous)
        row.state='working' if previous else 'assessment'
        if not previous:
            from .rework_extension_service import service_assignee
            flow.ensure_task(db,row,'repair_quote','重新核对并报价','service',assignee=service_assignee(db,row),reopen=True)


def _materials(db,user,row,action,v):
    if not row.data.get('started') or row.data.get('released_date') or _settlement(db,row):raise HTTPException(409,'开工后、冻结结算前才能按实际领退料')
    _evidence(db,user,row,v['evidence_id'])
    if action=='issue':
        quote=_authorized(db,row)
        if row.state!='working' or row.data.get('stopping'):raise HTTPException(409,'待授权、待质检或停工阶段不能新增领料')
        _task(db,user,row,'repair_issue')
        line=db.scalar(select(RepairLine).where(RepairLine.quote_id==quote.id,RepairLine.line_key==v['line_key'],RepairLine.kind=='part'))
        if not line:raise HTTPException(404,'当前授权报价中没有该配件行')
        if v['quantity_milli']>line.quantity_milli-_stock_net(db,row,line.line_key)[0]:raise HTTPException(409,'发料超过当前客户授权的尚未领取数量')
        item=_one(db,Item,line.item_id);qty=v['quantity_milli']
        from .inventory_availability import assert_can_issue
        assert_can_issue(db,item,qty)
        value=item.inventory_value_cents if qty==item.quantity_milli else (2*item.inventory_value_cents*qty+item.quantity_milli)//(2*item.quantity_milli)
        move=_post_stock(db,user,row,item,-qty,-value,'repair_issue_v3')
        db.add(RepairStock(case_id=row.id,quote_id=quote.id,line_key=line.line_key,stock_move_id=move.id,quantity_milli=qty,value_cents=value,evidence_id=v['evidence_id']))
    else:
        original=_one(db,RepairStock,v['original_id'])
        if original.case_id!=row.id or original.original_id:raise HTTPException(404,'请选择本工单实际原领料')
        returned=_rows(db,RepairStock,original_id=original.id);remaining=original.quantity_milli+sum(x.quantity_milli for x in returned)
        value_left=original.value_cents+sum(x.value_cents for x in returned);qty=v['quantity_milli']
        if qty>remaining:raise HTTPException(409,'退料超过原领料尚未退回数量')
        value=value_left if qty==remaining else (2*value_left*qty+remaining)//(2*remaining)
        source=_one(db,StockMove,original.stock_move_id);item=_one(db,Item,source.item_id)
        move=_post_stock(db,user,row,item,qty,value,'repair_return_v3',source.id)
        db.add(RepairStock(case_id=row.id,quote_id=original.quote_id,line_key=original.line_key,stock_move_id=move.id,
            original_id=original.id,quantity_milli=-qty,value_cents=-value,evidence_id=v['evidence_id']))
        if row.state=='settling':row.state='quality';flow.ensure_task(db,row,'repair_quality','退料后重新核对质检与明细','service',reopen=True)


def _allocate(db,user,row,v):
    quote=_authorized(db,row)
    if row.state!='settling' or _settlement(db,row):raise HTTPException(409,'通过质检后只冻结一次承担，不能覆盖既有结算')
    _evidence(db,user,row,v['evidence_id'])
    quality=db.scalar(select(RepairQuality).where(RepairQuality.case_id==row.id).order_by(RepairQuality.id.desc()))
    if not quality or not quality.passed or quality.quote_id!=quote.id:raise HTTPException(409,'当前报价尚未通过质检')
    allocations=v['allocations']
    if len({a['payer_type'] for a in allocations})!=len(allocations) or sum(a['amount_cents'] for a in allocations)!=row.amount_cents:
        raise HTTPException(422,'各承担方金额之和必须恰好等于当前授权应收，且同类承担只能一行')
    from .claims_service import validate_allocation,bind_after_allocation
    validate_allocation(db,row,allocations)
    settlement=RepairSettlement(case_id=row.id,quote_id=quote.id,labor_cost_cents=v['labor_cost_cents'],evidence_id=v['evidence_id'],actor_id=user.id)
    db.add(settlement);db.flush()
    from .master_data import require_active
    for data in allocations:
        kind=data['payer_type'];name='';insurer=None;manufacturer=None
        if kind=='customer':name=_one(db,Customer,row.customer_id).name
        elif kind=='insurer':insurer=require_active(db,'insurers',data['payer_id']);name=insurer.name
        elif kind=='manufacturer':
            manufacturer=_one(db,Reference,data['payer_id'])
            if manufacturer.category!='厂家' or not manufacturer.active:raise HTTPException(422,'请选择本店启用的厂家往来档案')
            name=manufacturer.name
        else:
            name=data['payer_name']
            if len(name)<2:raise HTTPException(422,'请明确内部费用承担方')
        db.add(RepairAllocation(case_id=row.id,settlement_id=settlement.id,payer_type=kind,payer_name=name,
            insurer_id=insurer.id if insurer else None,manufacturer_id=manufacturer.id if manufacturer else None,
            amount_cents=data['amount_cents'],due_date=date.fromisoformat(data['due_date'])))
    row.cost_cents=v['labor_cost_cents']+_stock_net(db,row)[1]
    flow.set_data(row,payer='多方承担');flow.finish_task(db,row,'repair_allocate',user)
    from .rework_extension_service import service_assignee
    flow.ensure_task(db,row,'repair_release','核对客户结清并确认接车','service',assignee=service_assignee(db,row))
    db.flush();bind_after_allocation(db,user,row)


def command(db,user,key,request_id,version,action,v):
    if v.get('member_pricing') is None:v={k:value for k,value in v.items() if k!='member_pricing'}
    if action not in ROLES:raise HTTPException(404,'维修动作不存在')
    if user.role not in ROLES[action]:raise HTTPException(403,'当前门店岗位不能办理本维修动作')
    def run():
        row=get_order(db,user,key)
        if row.version!=version:raise HTTPException(409,'工单已经变化，请刷新核对当前版本')
        from .aftercare_service import guard_source_action
        guard_source_action(db,user,row,action,v.get('allocation_id'))
        row.updated_at=utcnow();before=row.state
        if row.flow_version==4:
            from .service_intake_service import before_repair_command
            before_repair_command(db,user,row,action,v)
        if action=='quote':_new_quote(db,user,row,v)
        elif action in {'price_approve','authorize','quote_cancel'}:_review(db,user,row,action,v)
        elif action=='cancel':
            from .repair_package_service import release_quote
            if not row.data.get('started') and not _rows(db,RepairStock,case_id=row.id) and not _settlement(db,row):release_quote(db,user,row)
            credit,hold=_credits(db,row)
            if row.data.get('started') or _rows(db,RepairStock,case_id=row.id) or _settlement(db,row) or credit or hold or flow.paid_amount(db,row):
                raise HTTPException(409,'已有施工、领料或结算事实，不能取消；须约定停工保留费并按原领料退回')
            if row.state in {'cancelled','completed','credit_open'}:raise HTTPException(409,'当前维修不能取消')
            row.state='cancelled';row.completed_date=today();flow.close_tasks(db,row,user)
        elif action=='start':
            quote=_authorized(db,row);_task(db,user,row,'repair_work')
            if row.state!='working' or row.data.get('started') or quote.purpose=='stop':raise HTTPException(409,'当前报价不能重复开工')
            flow.set_data(row,started=True,start_result=v['result'])
        elif action in {'issue','return_material'}:_materials(db,user,row,action,v)
        elif action=='finish':
            _authorized(db,row);_task(db,user,row,'repair_work')
            if row.state!='working' or not row.data.get('started'):raise HTTPException(409,'须完成授权并实际开工后提交质检')
            if _pending_parts(db,row):raise HTTPException(409,'授权配件尚未领齐，请核对实际用料或约定停工保留费用')
            flow.set_data(row,finish_result=v['result']);row.state='quality';flow.finish_task(db,row,'repair_work',user)
            flow.ensure_task(db,row,'repair_quality','核对施工与安全交接条件','service',reopen=True)
        elif action=='quality':
            quote=_authorized(db,row);_task(db,user,row,'repair_quality')
            if row.state!='quality':raise HTTPException(409,'当前未提交质检')
            if _pending_parts(db,row):raise HTTPException(409,'授权配件与实际领用不一致，不能通过质检')
            _evidence(db,user,row,v['evidence_id'])
            db.add(RepairQuality(case_id=row.id,quote_id=quote.id,passed=v['passed'],result=v['result'],evidence_id=v['evidence_id'],actor_id=user.id))
            flow.finish_task(db,row,'repair_quality',user)
            if v['passed']:
                row.state='settling';flow.ensure_task(db,row,'repair_allocate','核对并冻结客户、保险、厂家和内部承担','manager',reopen=True)
            else:
                row.state='working';flow.ensure_task(db,row,'repair_work','处理质检缺陷并重新提交','technician',reopen=True)
        elif action=='allocate':_allocate(db,user,row,v)
        elif action=='receive':
            if row.state not in {'settling','credit_open'} or not _settlement(db,row):raise HTTPException(409,'冻结承担后才可登记实际到账')
            allocation=_one(db,RepairAllocation,v['allocation_id'])
            if allocation.case_id!=row.id or allocation.payer_type=='internal':raise HTTPException(404,'实际收款承担方不存在')
            from .claims_service import guard_receive
            guard_receive(db,row,allocation.id)
            _task(db,user,row,'repair_receive_'+str(allocation.id));_evidence(db,user,row,v['evidence_id'])
            if v['amount_cents']>_allocation_due(db,row,allocation,True):raise HTTPException(409,'本次到账超过该承担方扣除权益占额后的尚欠金额')
            link=flow.add_payment(db,user,row,v,amount=v['amount_cents'])
            db.add(RepairPayment(allocation_id=allocation.id,payment_link_id=link.id,evidence_id=v['evidence_id']))
        elif action=='release':
            if row.state!='settling' or not _settlement(db,row):raise HTTPException(409,'质检与多方承担冻结后才能交车')
            _task(db,user,row,'repair_release');_evidence(db,user,row,v['evidence_id'])
            from .repair_package_service import guard_release
            guard_release(db,row)
            if _credits(db,row)[1] or customer_due(db,row,False):raise HTTPException(409,'客户承担尚未结清或仍有权益占额，不能交车')
            flow.set_data(row,released_date=today().isoformat(),release_evidence_id=v['evidence_id']);flow.finish_task(db,row,'repair_release',user)
        db.flush()
        if row.state=='working' and row.data.get('started') and row.data.get('quote_id')==row.data.get('authorized_quote_id'):
            if _pending_parts(db,row):flow.ensure_task(db,row,'repair_issue','按当前授权明细发出配件','inventory',reopen=True)
            else:flow.finish_task(db,row,'repair_issue',user)
        sync_after_member(db,user,row)
        if row.flow_version==4:
            from .service_intake_service import after_repair_command
            after_repair_command(db,user,row,action)
        from .invoice_service import sync_source
        sync_source(db,user,row)
        flow.log_event(db,user,row,'repair_v'+str(row.flow_version)+'_'+action,LABELS[action],before,{'quote_id':row.data.get('quote_id'),'reason':v.get('reason','')})
        from .membership_service import sync_consumption_points
        sync_consumption_points(db,user,row,evidence_id=v.get('evidence_id'))
        return row
    return _execute(db,user,request_id,action,{'id':key,'version':version,'values':v},run)


def describe(db,user,row):
    money=user.role in MONEY_ROLES;cost=user.role in COST_ROLES
    result={k:getattr(row,k) for k in ('id','number','state','version','flow_version','store_id','customer_id','title')}
    result.update(data=flow.safe_data(row.data,user,row),due_date=row.due_date.isoformat(),actions=[k for k,roles in ROLES.items() if user.role in roles])
    result['quotes']=[]
    for quote in _rows(db,RepairQuote,case_id=row.id):
        from .rework_extension_service import quote_description
        from .rework_extension_models import ReworkLineScope
        q={k:getattr(quote,k) for k in ('id','revision','purpose','reason','digest')}
        q['price_approved']=bool(db.scalar(select(RepairPriceApproval.id).where(RepairPriceApproval.quote_id==quote.id)))
        q['authorized']=bool(db.scalar(select(RepairAuthorization.id).where(RepairAuthorization.quote_id==quote.id)))
        q['cancelled']=bool(db.scalar(select(RepairQuoteCancellation.id).where(RepairQuoteCancellation.quote_id==quote.id)))
        q['lines']=[]
        from .repair_package_service import quote_info
        package=quote_info(db,user,row,quote.id)
        if package:q['repair_package']=package
        if money:
            q.update(amount_cents=quote.amount_cents,discount_cents=quote.discount_cents)
            from .member_pricing_service import describe_quote
            member_price=describe_quote(db,user,row,quote.id)
            if member_price:q['member_pricing']=member_price
        if money:
            partition=quote_description(db,quote.id)
            if partition:q['rework_scope']=partition
        for line in _rows(db,RepairLine,quote_id=quote.id):
            data={k:getattr(line,k) for k in ('line_key','kind','work_item_id','item_id','code','name','unit','quantity_milli')};data['issued_milli']=_stock_net(db,row,line.line_key)[0]
            if money:data.update(unit_price_cents=line.unit_price_cents,amount_cents=line.amount_cents,discount_cents=line.discount_cents,standard_fee_cents=line.standard_fee_cents)
            partition=db.scalar(select(ReworkLineScope).where(ReworkLineScope.line_id==line.id))
            if partition:data.update(charge_scope=partition.charge_scope,source_line_id=partition.source_line_id)
            q['lines'].append(data)
        result['quotes'].append(q)
    result['stock']=[]
    for stock in _rows(db,RepairStock,case_id=row.id):
        data={k:getattr(stock,k) for k in ('id','quote_id','line_key','original_id','quantity_milli','stock_move_id','evidence_id')}
        if stock.original_id is None:data['returnable_milli']=stock.quantity_milli+sum(x.quantity_milli for x in _rows(db,RepairStock,original_id=stock.id))
        if cost:data['value_cents']=stock.value_cents
        result['stock'].append(data)
    result['quality']=[{k:getattr(q,k) for k in ('id','quote_id','passed','result','evidence_id')} for q in _rows(db,RepairQuality,case_id=row.id)]
    result['settled']=bool(_settlement(db,row));result['allocations']=[]
    if money:
        for a in _rows(db,RepairAllocation,case_id=row.id):
            d={k:getattr(a,k) for k in ('id','payer_type','payer_name','amount_cents')};d.update(due_date=a.due_date.isoformat(),due_cents=_allocation_due(db,row,a),net_cents=allocation_amount(db,row,a))
            d['payments']=[{'id':p.id,'payment_link_id':p.payment_link_id,'evidence_id':p.evidence_id,'amount_cents':_one(db,PaymentLink,p.payment_link_id).amount_cents,'direction':_one(db,PaymentLink,p.payment_link_id).direction} for p in _rows(db,RepairPayment,allocation_id=a.id)]
            result['allocations'].append(d)
        from .claims_models import ClaimResponsibility
        result['claims_internal_absorption']=[{'payer_name':r.payer_name,'amount_cents':r.amount_cents} for r in _rows(db,ClaimResponsibility,source_case_id=row.id,payer_type='internal')]
        result.update(amount_cents=row.amount_cents,receivable_cents=receivable_amount(db,row),revenue_cents=revenue_amount(db,row))
        if result['settled']:result['customer_due_cents']=customer_due(db,row)
    if cost:result['cost_cents']=row.cost_cents
    if row.flow_version==4:
        from .service_intake_service import repair_info
        result['service_intake']=repair_info(db,user,row)
    return result

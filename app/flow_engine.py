"""Deterministic state transitions. Callers commit once, after all effects succeed.
Public input never supplies a state, a task result, a cost snapshot, or an owner scope.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import uuid
from sqlalchemy import select, func, or_
from fastapi import HTTPException
from .db import utcnow, today
from .models import User, UserStore, Store, Vehicle, Sale, CashEntry, AppMetadata
from .flow_models import Case, Task, Customer, FlowEvent, RequestReceipt, VehicleHold, PaymentLink, Account, Item, StockMove, Member, MemberEntry, FileAsset
from .flow_specs import SPECS, STATES, TERMINAL, parse_fields, flow_spec, CURRENT_FLOW_VERSION, FLOW_CATALOGUES
from .tenancy import single_store, role_for_store, project_user
from .services import audit

MANAGEMENT={'admin','manager','auditor','finance'}
FINANCE_ACTIONS={'receive','late_receive','refund','topup_receive','member_refund_pay','apply_balance'}
READ_KINDS={
'reception':{'customer_care','lead','callback'}, 'sales':{'retail','customer_care','lead','order','addon','insurance','agency','callback','complaint'},
'inventory':{'retail','vehicle_procurement','order','repair','purchase','procurement','material_transfer','vehicle_transfer','material_issue','material_return','stock_count'},
'technician':{'retail','order','repair','addon','material_issue','material_return'},
'service':{'retail','customer_care','order','repair','insurance','addon','agency','material_issue','material_return','callback','complaint','member_topup','member_refund'},
'customer_service':{'customer_care','lead','callback','complaint','member_topup','member_refund'},
}
READ_KINDS['inventory'].update({'warehouse','opening_import','addon'})
for _role in ('sales','service'):READ_KINDS[_role].add('other_income')
READ_KINDS['service'].add('claim')
for _role in ('sales','service','reception','customer_service'):READ_KINDS[_role].add('recharge_bundle')
for _role in ('inventory','service','technician'):READ_KINDS[_role].add('vehicle_operations')
for _role in ('inventory','service','technician','sales'):READ_KINDS[_role].add('aftercare')
for _role in ('sales','service','reception','customer_service'):READ_KINDS[_role].add('business_finance')
for _role in ('service','reception','customer_service'):READ_KINDS[_role].add('service_intake')
for _role in ('service','reception','customer_service','sales'):READ_KINDS[_role].add('membership')
for _role in ('sales','service','reception','customer_service'):READ_KINDS[_role].add('observation_correction')
MONEY_HIDDEN={'amount','labor','parts','discount','unit_cost','commission','labor_cost','balance','cost'}


def scoped_get(db,model,pk):
    # Always execute a scoped SELECT (not identity-map-only get).
    return db.scalar(select(model).where(model.id==pk))


def eligible_users(db, role, store_id):
    ids=select(UserStore.user_id).where(UserStore.store_id==store_id)
    users=list(db.scalars(select(User).where(User.active.is_(True),or_(User.id.in_(ids),User.role=='admin')).order_by(User.id)))
    users=[project_user(u, role_for_store(db,u,store_id)) for u in users]
    matching=[u for u in users if u.role==role]
    if matching:return matching
    managers=[u for u in users if u.role=='manager']
    # A cashier task must not be assigned to a non-cashier fallback manager.
    return ([u for u in users if u.role=='admin'] if role=='finance' else managers or [u for u in users if u.role=='admin'])


def assignable(db,user_id,store_id,roles=None):
    user=db.get(User,user_id)
    role=role_for_store(db,user,store_id)
    allowed=user and user.active and role is not None
    if roles and 'finance' in roles and user and role not in {'admin','finance'}:
        raise HTTPException(422,'实际收退款任务只能交给财务或管理员')
    if not allowed or (roles and role not in set(roles)|{'admin','manager'}):
        raise HTTPException(422,'接手员工未启用、未获得当前门店权限，或岗位不匹配')
    return project_user(user,role)


def own_role(user, roles):
    return user.role=='admin' or user.role in roles or (user.role=='manager' and 'finance' not in roles)


def can_read(db,user,row):
    if row.kind=='member_pricing_rule':
        from .member_pricing_service import can_read as member_pricing_read
        return row.flow_version==1 and member_pricing_read(user,row)
    if row.kind=='vehicle_income':
        return row.flow_version==1 and not getattr(user,'_aggregate_scope',False) and user.role in MANAGEMENT
    if row.kind=='observation_correction':
        from .observation_corrections_service import can_read_case
        return can_read_case(db,user,row)
    if row.kind=='retail_group_rule':
        from .retail_group_rules import can_read_case
        return can_read_case(db,user,row)
    if row.kind=='business_entity':
        from .business_entity_service import can_read_case
        return can_read_case(db,user,row)
    if row.kind=='addon':
        if row.flow_version==3 and getattr(user,'_aggregate_scope',False):return False
        if row.flow_version!=3 and user.role=='inventory':return False
    if row.kind=='insurance' and row.flow_version==3:
        from .insurance_service import can_read as insurance_read
        return insurance_read(db,user,row)
    if (row.kind=='agency' and row.flow_version==3) or (row.kind=='other_income' and row.flow_version==2):
        if getattr(user,'_aggregate_scope',False) or user.role not in {'admin','manager','sales','service','finance','auditor'}:return False
        if user.role=='sales':
            parent=scoped_get(db,Case,row.parent_id) if row.parent_id else None
            return row.owner_id==user.id or row.created_by==user.id or bool(parent and parent.owner_id==user.id) or db.scalar(select(Task.id).where(Task.case_id==row.id,Task.assignee_id==user.id,Task.status=='open')) is not None
        return True
    if row.kind=='claim':return not getattr(user,'_aggregate_scope',False) and user.role in {'admin','manager','service','finance','auditor'}
    if row.kind=='opening_import':
        from .opening_import_service import can_read_case
        return can_read_case(db,user,row)
    if row.kind=='recharge_bundle':
        if getattr(user,'_aggregate_scope',False):return False
        from .recharge_bundle_service import can_read as bundle_read
        return bundle_read(user,row)
    if row.kind in {'aftercare','business_finance'}:
        if getattr(user,'_aggregate_scope',False):return False
        if row.kind=='business_finance':
            from .business_finance_service import can_read as finance_read
            return finance_read(user,row)
        if user.role=='technician':return db.scalar(select(Task.id).where(Task.case_id==row.id,Task.assignee_id==user.id)) is not None
        if user.role=='sales':return row.owner_id==user.id or row.created_by==user.id or db.scalar(select(Task.id).where(Task.case_id==row.id,Task.assignee_id==user.id,Task.status=='open')) is not None
        return user.role in MANAGEMENT|{'inventory','service'}
    if row.kind=='vehicle_operations':
        from .vehicle_operations_service import can_read_case
        return can_read_case(db,user,row)
    if row.kind=='membership':
        from .membership_service import can_read as can_membership
        return can_membership(user,row)
    if row.kind=='invoice' and row.flow_version==3:
        from .invoice_service import can_read as can_invoice
        return can_invoice(user,row)
    if row.kind in {'reconciliation','interstore_clearing'}:
        from .reconciliation_service import can_read as can_reconcile
        return can_reconcile(user,row)
    if row.kind=='customer_care':
        from .customer_service import can_read_case
        return can_read_case(db,user,row)
    if user.role in MANAGEMENT:return True
    if row.kind not in READ_KINDS.get(user.role,set()):return False
    if user.role=='inventory' and row.kind=='repair':return row.flow_version in {3,4}
    if user.role=='service' and row.kind=='order':
        return db.scalar(select(Task.id).where(Task.case_id==row.id,Task.assignee_id==user.id)) is not None
    if user.role in {'sales','reception'}:
        if row.owner_id==user.id or row.created_by==user.id:return True
        if db.scalar(select(Task.id).where(Task.case_id==row.id,Task.assignee_id==user.id,Task.status=='open')):return True
        parent=scoped_get(db,Case,row.parent_id) if row.parent_id else None
        return bool(parent and parent.owner_id==user.id)
    return True


def case_query(user):
    stmt=select(Case)
    if getattr(user,'_aggregate_scope',False):
        stmt=stmt.where(Case.kind.notin_(['vehicle_income','member_pricing_rule']))
        stmt=stmt.where(Case.kind.notin_(['observation_correction','retail_group_rule','business_entity','vehicle_operations','aftercare','business_finance','opening_import','recharge_bundle','claim','other_income']))
        stmt=stmt.where(or_(Case.kind!='agency',Case.flow_version!=3))
        stmt=stmt.where(or_(Case.kind!='insurance',Case.flow_version!=3))
        stmt=stmt.where(or_(Case.kind!='addon',Case.flow_version!=3))
    if user.role=='technician':stmt=stmt.where(or_(Case.kind!='aftercare',Case.id.in_(select(Task.case_id).where(Task.assignee_id==user.id))))
    if user.role in {'service','technician'}:
        from .vehicle_operations_models import VehicleOperation
        stmt=stmt.where(or_(Case.kind!='vehicle_operations',Case.id.in_(select(VehicleOperation.id).where(VehicleOperation.kind=='customer_return'))))
    if user.role=='finance' or getattr(user,'_aggregate_scope',False):stmt=stmt.where(Case.kind.notin_(['customer_care','observation_correction']))
    if user.role not in MANAGEMENT:
        stmt=stmt.where(Case.kind.in_(READ_KINDS.get(user.role,set())))
        if user.role=='inventory':
            stmt=stmt.where(or_(Case.kind!='repair',Case.flow_version.in_([3,4])))
            stmt=stmt.where(or_(Case.kind!='addon',Case.flow_version==3))
        if user.role=='service':
            stmt=stmt.where(or_(Case.kind!='order',Case.id.in_(select(Task.case_id).where(Task.assignee_id==user.id))))
        if user.role in {'sales','reception'}:
            # Related service tasks remain reachable through their parent detail.
            own_vehicle=Case.customer_id.in_(select(Customer.id).where(Customer.owner_id==user.id))
            generic=or_(Case.owner_id==user.id,Case.created_by==user.id,Case.id.in_(select(Task.case_id).where(Task.assignee_id==user.id,Task.status=='open')),Case.parent_id.in_(select(Case.id).where(Case.owner_id==user.id)))
            stmt=stmt.where(or_((Case.kind=='observation_correction') & own_vehicle,(Case.kind!='observation_correction') & generic))
    return stmt


def get_case(db,user,pk):
    row=scoped_get(db,Case,pk)
    if row is None or not can_read(db,user,row):raise HTTPException(404,'业务不存在或当前账号不可查看')
    return row


def money_visible(user,row):
    return user.role not in {'inventory','technician','reception','customer_service'}


def safe_data(data,user,row):
    if row.kind=='member_pricing_rule':
        return {k:v for k,v in data.items() if k in {'member_price_rule_id','rule_id','decision_id','status','task_id','from','to'} and not isinstance(v,(dict,list))}
    if row.kind=='vehicle_income':
        return {k:v for k,v in data.items() if k in {'revision_id','decision_id','cash_fact_id','status','task_id','from','to'} and not isinstance(v,(dict,list))}
    if user.role in MANAGEMENT:return dict(data)
    if row.kind=='vehicle_transfer':
        # A shared original timeline is not an alternative financial/file API.
        public={'vehicle_transfer_id','transfer_id','exception_id','plan_id','observation_id',
                'receipt_id','unavailable_id','vehicle_id','vin','kind','status','confirmed','actual_at',
                'source_observation_id','destination_observation_id','found_observation_id','location_id','task_id','from','to'}
        return {k:v for k,v in data.items() if k in public and not isinstance(v,(dict,list))}
    if row.kind=='opening_import':
        # The common timeline must respect the same separation as the opening
        # page: inventory staff do not receive frozen bank or customer mappings.
        return {k:v for k,v in data.items() if k not in {'account_context','owners','objects'}}
    if row.kind in {'addon','insurance'} and row.flow_version==3:
        # Raw action payloads also appear in the common event timeline. Their
        # nested quote/consent bodies are private; the dedicated domain view
        # separately projects the operational facts each employee can read.
        if not money_visible(user,row) or row.kind=='insurance':
            public={'flow_version','source_order_id','source_quote_id','sales_quote_id',
                    'quote_id','plan_id','resolution_id','tender_id','dispatch_id',
                    'acceptance_id','return_id','aftercare_case_id','new_vehicle_id',
                    'passed','stage','status','task_id','from','to'}
            return {k:v for k,v in data.items() if k in public and not isinstance(v,(dict,list))}
        def without_cost(value):
            if isinstance(value,dict):return {k:without_cost(v) for k,v in value.items() if 'cost' not in k and 'commission' not in k}
            if isinstance(value,list):return [without_cost(v) for v in value]
            return value
        return without_cost(data)
    result={k:v for k,v in data.items() if 'cost' not in k and k!='commission'}
    if not money_visible(user,row):
        result={k:v for k,v in result.items() if not any(x in k for x in MONEY_HIDDEN)}
        if row.kind=='order' and row.flow_version in {3,4}:result={k:v for k,v in result.items() if k not in {'reason','terms'}}
        if row.kind in {'procurement','vehicle_procurement','retail'} or (row.kind=='repair' and row.flow_version in {3,4}):
            result={k:v for k,v in result.items() if k not in {'account_id','reference','original_payment_id','evidence_id','minimum_total_cents','price_reason'}}
    return result


def customer_for(db,user,values,flow_version=2):
    if flow_version>=2:
        from .customer_choice import resolve_customer
        return resolve_customer(db,user,values)
    name=values.get('customer_name','').strip();phone=values.get('customer_phone','').strip()
    if not name:return None
    existing=list(db.scalars(select(Customer).where(Customer.phone==phone))) if phone else []
    exact=[c for c in existing if c.name==name]
    if exact:return exact[0]
    if existing:raise HTTPException(409,'此号码已有不同姓名的客户，请先到客户档案核对，不会自动合并')
    c=Customer(name=name,phone=phone,owner_id=user.id)
    db.add(c);db.flush();return c


def log_event(db,user,row,action,label,before='',detail=None):
    event=FlowEvent(case_id=row.id,actor_id=user.id,action=action,label=label,before_state=before,after_state=row.state,detail=detail or {})
    db.add(event)
    audit(db,user.id,'flow_'+action,'flow',row.id,reason=label,after={'store_id':row.store_id,'state':row.state,'number':row.number})
    from .config import settings
    if settings.assistant_runtime_enabled or settings.assistant_notifications_enabled:
        # The original caller still owns commit/rollback. Only persisted source
        # IDs enter the outbox; labels, customer details and event detail do not.
        from .assistant_runtime_outbox import emit_wake_event
        db.flush()
        emit_wake_event(db,'flow:'+str(event.id),'flow',{
            'store_id':row.store_id,'object_ref':{'type':'case','id':row.id},
            'source_ref':{'type':'flow_event','id':event.id,'version':None}})


def _emit_task_signal(db, task):
    """Append a real Task revision; the original business caller owns commit."""
    from .config import settings
    if not (settings.assistant_runtime_enabled or settings.assistant_notifications_enabled):
        return
    from .assistant_runtime_outbox import emit_wake_event
    emit_wake_event(db, f'task:{task.id}:{task.version}', 'task', {
        'store_id': task.store_id, 'task_id': task.id,
        'object_ref': {'type': 'case', 'id': task.case_id},
        'source_ref': {'type': 'task', 'id': task.id, 'version': task.version}})


def ensure_task(db,row,key,title,role,assignee=None,due=None,reopen=False):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key))
    if task and task.status=='done' and not reopen:return task
    if task and task.status=='open':
        previous=(task.assignee_id,task.due_date)
        # Synchronizing related facts must never silently undo a human handoff.
        if assignee is not None:
            assignable(db,assignee,row.store_id)
            task.assignee_id=assignee
        if due is not None:task.due_date=due
        db.flush()
        if previous!=(task.assignee_id,task.due_date):_emit_task_signal(db,task)
        return task
    if assignee is None:
        candidates=eligible_users(db,role,row.store_id)
        if not candidates:raise HTTPException(409,'当前门店缺少可接手此任务的岗位或管理员，请先配置账号')
        # Small-team default: least current open workload, then stable ID. No performance ranking.
        counts={uid:n for uid,n in db.execute(select(Task.assignee_id,func.count()).where(Task.status=='open').group_by(Task.assignee_id))}
        assignee=min(candidates,key=lambda u:(counts.get(u.id,0),u.id)).id
    else:assignable(db,assignee,row.store_id)
    if task is None:
        task=Task(case_id=row.id,key=key,title=title,role=role,assignee_id=assignee,due_date=due or today())
        db.add(task)
    else:
        task.status='open';task.assignee_id=assignee;task.due_date=due or today();task.done_at=None;task.done_by=None
    db.flush();_emit_task_signal(db,task);return task


def finish_task(db,row,key,user,status='done'):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key))
    if task and task.status=='open':task.status=status;task.done_by=user.id;task.done_at=utcnow()


def close_tasks(db,row,user):
    from .repair_package_service import close_unpaid_purchases
    close_unpaid_purchases(db,user,row)
    for t in db.scalars(select(Task).where(Task.case_id==row.id,Task.status=='open')):
        # A source case can finish before its independently approved group refund.
        # Only the group refund command releases its hold and closes its task.
        if t.key.startswith(('group_refund_review_','group_refund_pay_','benefit_refund_review_','benefit_refund_pay_','repair_package_refund_','transfer_recovery_','transfer_found_','retail_group_','gate_review_','vehicle_transport_claim_')) or t.key in {'invoice_adjust','gate_cancelled_repair_exit'}:continue
        t.status='cancelled';t.done_by=user.id;t.done_at=utcnow()


def task_done(db,row,key):
    return db.scalar(select(Task.id).where(Task.case_id==row.id,Task.key==key,Task.status=='done')) is not None


def set_data(row,**values):
    row.data={**row.data,**values};row.updated_at=utcnow()


def initial_tasks(db,row):
    mapping={'lead':('assign','分派接待','reception'), 'order':('approve','确认车辆订单','manager'),
    'repair':('quote','检查并报价','service'),'insurance':('service','确认保险方案','service'),
    'addon':('service','确认加装项目','sales'),'agency':('service','确认代办项目','service'),
    'purchase':('approve','复核物资采购','manager'),'stock_count':('approve','复核盘点差异','manager'),
    'material_issue':('issue','确认发料','inventory'),'material_return':('return_in','确认退料','inventory'),
    'callback':('callback','联系客户','customer_service'),'complaint':('plan','安排投诉处理','manager'),
    'member_topup':('topup_receive','核对充值到账','finance'),'member_refund':('approve','复核余额退款','manager'),
    'invoice':('invoice_issue','办理并登记发票','finance')}
    key,title,role=mapping[row.kind]
    ensure_task(db,row,key,title,role,due=row.due_date)


def new_case(db,user,kind,values,parent=None,customer=None,internal=False):
    single_store(db)
    if kind not in SPECS:raise HTTPException(403,'没有创建此业务的权限')
    from .config import settings
    if kind=='invoice' and settings.environment=='production':raise HTTPException(409,'正式业务请从开票与原票冲红申请，核对原单经营主体后办理')
    flow_version=parent.flow_version if internal and parent else CURRENT_FLOW_VERSION
    # V3 vehicle quote changes do not silently promote independent old service
    # or callback cases to a catalogue which they never used.
    if internal and parent and parent.kind=='order' and parent.flow_version in {3,4}:flow_version=2
    spec=flow_spec(kind,flow_version)
    if not internal and user.role not in spec['create_roles']:raise HTTPException(403,'没有创建此业务的权限')
    if not internal:values=parse_fields(spec['fields'],values)
    if customer is None:customer=customer_for(db,user,values,flow_version)
    if kind in {'member_topup','member_refund'}:
        member=scoped_get(db,Member,values['member_id'])
        if not member or not member.active:raise HTTPException(422,'会员不存在或已停用')
        customer=scoped_get(db,Customer,member.customer_id)
        if kind=='member_refund' and values['amount']>member_available(db,member):raise HTTPException(409,'退款金额超过可用储值余额')
    if kind in {'purchase','stock_count'}:
        item=scoped_get(db,Item,values['item_id'])
        if not item or not item.active:raise HTTPException(422,'物资不存在或已停用')
        if kind=='stock_count':values={**values,'book_quantity':item.quantity_milli,'item_version':item.version}
    if kind=='invoice':
        linked=get_case(db,user,values['related_case_id'])
        if linked.kind not in {'order','repair','addon','agency'} or linked.state in {'cancelled','rejected'}:raise HTTPException(422,'请选择有效的销售、维修或服务业务')
        from .invoice_service import balance
        if values['amount']>balance(db,linked)['available_cents']:raise HTTPException(409,'申请金额超过该业务已确认的外部承担且尚未登记开票的金额')
        linked.updated_at=utcnow()  # Version-lock the allocation of the invoiceable amount.
        parent=linked;customer=scoped_get(db,Customer,linked.customer_id) if linked.customer_id else None
    due=values.get('delivery_due') or values.get('due_date')
    row=Case(number='HK'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind=kind,flow_version=flow_version,state=spec['initial'],
        title=(customer.name+' · ' if customer else '')+spec['label'],owner_id=parent.owner_id if parent and kind=='order' else user.id,created_by=user.id,
        customer_id=customer.id if customer else None,parent_id=parent.id if parent else None,
        amount_cents=values.get('amount',0),business_date=today(),due_date=date.fromisoformat(due) if due else today(),data=values)
    db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);initial_tasks(db,row);log_event(db,user,row,'create','建立'+spec['label'],detail=values)
    if kind=='order':
        from .flow_documents import generate_document
        generate_document(db,user,row,'contract')
    return row


def paid_amount(db,row):
    from .business_finance_sources import case_credit_amount
    from .group_service import case_paid_amount
    from .group_benefits_service import case_paid_amount as benefit_paid
    from .repair_package_service import case_paid_amount as package_paid
    payments=list(db.scalars(select(PaymentLink).where(PaymentLink.case_id==row.id)))
    bank=sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in payments)
    wallet=-sum(e.amount_cents for e in db.scalars(select(MemberEntry).where(MemberEntry.case_id==row.id,MemberEntry.purpose=='consume')))
    return bank+wallet+case_paid_amount(db,row.id)+benefit_paid(db,row.id)+case_credit_amount(db,row.id)+package_paid(db,row.id)


def collectable_amount(db,row):
    """Committed settlement plus reserved group benefits cannot exceed the bill."""
    if row.kind=='retail' and row.flow_version==2:
        from .retail_service import collectable_amount as retail_collectable
        return retail_collectable(db,row)
    from .group_service import case_reserved_amount
    from .group_benefits_service import case_reserved_amount as benefit_reserved
    from .business_finance_sources import case_reserved_amount as finance_reserved
    from .repair_package_service import case_reserved_amount as package_reserved
    from .aftercare_service import net_charge
    return net_charge(db,row)-paid_amount(db,row)-case_reserved_amount(db,row.id)-benefit_reserved(db,row.id)-finance_reserved(db,row.id)-package_reserved(db,row.id)


def member_available(db,member):
    holds=sum(c.amount_cents for c in db.scalars(select(Case).where(Case.kind=='member_refund',Case.state=='refund_pending')) if c.data.get('member_id')==member.id)
    return member.balance_cents-holds


def category_requirement_message(actual,accepted,role=None):
    """凭据类别不符时的统一说明：写清“本次需要哪一类”，而不是笼统的“类型不匹配”。

    actual  = 上传文件实际归入的类别键（可能为 None）
    accepted= 该动作接受的类别键（None 表示“任一实际业务凭据都可以”）
    """
    from .flow_specs import category_label
    if not accepted:
        return ('本岗位不能使用“%s”作为本单凭据：请改用本单实际业务凭据或客户授权；'
                '资金与价格资料请交财务、店长岗位上传。') % category_label(actual)
    wanted='、'.join(category_label(key) for key in accepted)
    return ('本次需要“%s”类别的凭据，当前选择的是“%s”。请在上传弹窗的“文件类别”里改选后重新提交。'
            % (wanted,category_label(actual)))


def file_exists(db,row,file_id,category=None):
    asset=scoped_get(db,FileAsset,file_id)
    if not asset or asset.case_id!=row.id or asset.generated:raise HTTPException(422,'请选择本单实际上传的业务凭据，不可拿系统空白单代替')
    if category:
        accepted=category if isinstance(category,(list,tuple,set)) else (category,)
        if asset.category not in accepted:
            raise HTTPException(422,category_requirement_message(asset.category,tuple(accepted)))
    from .file_security import require_usable
    require_usable(db,asset)
    return asset


def children(db,row):return list(db.scalars(select(Case).where(Case.parent_id==row.id)))


def readiness(db,row):
    flow_spec(row.kind,row.flow_version)
    problems=[]
    if not row.vehicle_id:problems.append('尚未配车')
    required=[('sign','合同尚未签回')]
    if row.flow_version==1:required.append(('inspect','交车检查未完成'))
    elif row.data.get('inspection_status')!='passed' or row.data.get('inspection',{}).get('outcome')!='合格':
        problems.append('交车检查尚未合格，须处理缺陷并复检通过')
    for key,label in required:
        if not task_done(db,row,key):problems.append(label)
    if paid_amount(db,row)<row.amount_cents:problems.append('车辆款项尚未收齐')
    for child in children(db,row):
        if child.kind in {'agency','insurance','addon'} and child.flow_version==3:continue  # dedicated domains own explicit delivery guards
        if row.flow_version in {3,4} and child.state in {'cancelled','rejected'}:continue
        if child.kind in {'addon','insurance','agency'} and child.state!='completed':problems.append(flow_spec(child.kind,child.flow_version)['label']+'未完成')
    if row.flow_version in {3,4}:
        from .sales_quote_service import readiness as quote_readiness
        problems.extend(quote_readiness(db,row))
    return problems


def blocker(db,user,row,action):
    flow_spec(row.kind,row.flow_version)
    key=action.key
    if row.kind in {'lead','callback'} and key not in {'close','assign'} and row.customer_id:
        customer=scoped_get(db,Customer,row.customer_id)
        if customer and not customer.contact_allowed:return '客户已要求停止联系，请结束本次任务；重新联系需主管核对意愿'
    if row.parent_id:
        parent=scoped_get(db,Case,row.parent_id)
        if parent and parent.kind=='order' and parent.flow_version in {3,4} and row.kind in {'addon','insurance','agency'}:
            from .sales_quote_service import pending as pending_quote
            if pending_quote(db,parent):return '上游车辆报价正在变更，先完成或撤回新报价后再继续配套服务'
        if parent and parent.state in {'cancel_review','refund_pending','cancelled'} and row.kind in {'addon','insurance','agency','material_issue','material_return'}:
            return '上游业务正在取消或已取消，暂不能继续'
    if row.kind=='order':
        if row.flow_version in {3,4}:
            from .sales_quote_service import blocking_reason
            quote_reason=blocking_reason(db,user,row,key)
            if quote_reason:return quote_reason
        if row.flow_version==1 and key in {'inspect','dispatch','deliver'}:
            return '旧版本订单只有文本检查记录，暂停检查、出库和提车；请由管理员评审流程升级后重新检查，历史凭据保留'
        if key=='allocate' and row.vehicle_id:return '本单已经配车'
        if key in {'sign','inspect','rectify','reinspect'} and not row.vehicle_id:return '请先完成配车'
        if row.flow_version in {2,3,4}:
            if key in {'inspect','reinspect'} and row.data.get('inspection_status')=='passed':return '交车检查已合格，无需重复办理'
            if key=='inspect' and row.data.get('inspection_status'):return '首次检查已记录，请按缺陷处理和复检任务办理'
            if key=='rectify' and row.data.get('inspection_status')!='failed':return '当前没有待处理的交车检查缺陷'
            if key=='reinspect' and row.data.get('inspection_status')!='awaiting_reinspection':return '请先记录缺陷处理结果，再进行复检'
        if key=='dispatch':
            problems=readiness(db,row)
            if problems:return '；'.join(problems)
        if key=='deliver' and not task_done(db,row,'dispatch'):return '请先确认车辆出库'
        if key=='deliver' and row.flow_version in {3,4}:
            problems=readiness(db,row)
            if problems:return '；'.join(problems)
        if key in {'dispatch','deliver'}:
            from .service_orders_service import guard_order_delivery
            try:
                guard_order_delivery(db,row)
                from .insurance_service import guard_order_delivery as insurance_delivery
                insurance_delivery(db,row)
                from .addon_service import guard_order_delivery as addon_delivery
                addon_delivery(db,row)
            except HTTPException as exc:
                if exc.status_code!=409:raise
                return exc.detail
        if key=='cancel_request':
            if task_done(db,row,'dispatch'):return '已出库业务不能直接退订，需要人工核对退车及资金处理'
            if row.flow_version!=4 and any(c.kind in {'addon','insurance','agency'} and c.state!='pending' for c in children(db,row)):
                return '已有服务开始办理，请先由负责人处理服务终止及费用，本版不自动取消已执行服务'
        if row.flow_version==4 and key in {'cancel_request','cancel_approve','refund'}:
            if any(c.kind in {'addon','insurance','agency'} and c.state not in {'cancelled','rejected'} for c in children(db,row)):
                return '请先在每张加装、保险及代办单明确取消；已经执行或独立终止结清的服务须走原单售后，不能简单退订'
            if key=='cancel_approve':
                request=db.scalar(select(FlowEvent).where(FlowEvent.case_id==row.id,FlowEvent.action=='cancel_request').order_by(FlowEvent.id.desc()))
                if not request:return '退订缺少本次申请记录，请核对原操作留痕'
                if request.actor_id==user.id:return '本次退订申请须由另一位主管独立复核，管理员也不能审批本人申请'
    if row.kind=='repair':
        if key=='release':
            from .group_service import case_reserved_amount
            from .group_benefits_service import case_reserved_amount as benefit_reserved
            if case_reserved_amount(db,row.id) or benefit_reserved(db,row.id):return '集团会员权益尚在占用中，请财务确认核销或撤销后再交车'
        if key=='cancel':
            from .group_service import case_paid_amount,case_reserved_amount
            from .group_benefits_service import case_paid_amount as benefit_paid,case_reserved_amount as benefit_reserved
            if case_paid_amount(db,row.id) or case_reserved_amount(db,row.id) or benefit_paid(db,row.id) or benefit_reserved(db,row.id):return '请先撤销集团会员权益占用或处理已核销款项'
        if key in {'finish','quality'}:
            if any(c.kind in {'material_issue','material_return'} and c.state not in TERMINAL for c in children(db,row)):
                return '尚有未完成的领料或退料任务'
        if key=='finish' and not row.data.get('started'):return '请先接车开工'
        if key=='start' and row.data.get('started'):return '已经开工'
        if key=='internal_settle' and row.data.get('payer')!='内部':return '此单不是内部承担'
        if key=='credit' and row.data.get('payer')=='内部':return '内部承担请使用内部结算'
        if key=='release' and paid_amount(db,row)<row.amount_cents and not row.data.get('credit_approved') and not row.data.get('internal_settled'):
            return '款项未结清；需要财务收款或主管批准月结'
        if key=='receive' and row.data.get('payer')=='内部':return '内部承担不生成客户收款'
    if key in {'receive','late_receive'} and collectable_amount(db,row)<=0:return '本单金额已结清或已被集团会员权益占用'
    if row.flow_version==2 and key=='cancel':
        if row.kind=='purchase' and purchase_has_postings(db,row):return '已有实际到货或付款记录，不能取消；请办理对应退货退款'
        if row.kind=='member_refund' and member_refund_has_postings(db,row):return '已有实际退款记录，不能撤销或改写流水'
    if key in {'approve','count_approve','cancel_approve'} and row.created_by==user.id and user.role!='admin':
        return '需要另一位主管复核，不能审核自己创建的单据'
    if key=='refund' and paid_amount(db,row)<=0:return '本单已无待退金额'
    if not action.task and user.role in {'sales','reception'} and row.owner_id!=user.id:
        assigned=db.scalar(select(Task.id).where(Task.case_id==row.id,Task.assignee_id==user.id,Task.status=='open'))
        if not assigned:return '当前业务已交由其他员工负责，变更或取消请由负责人处理'
    if action.task:
        t=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==action.task))
        if t and t.status!='open':return '此步骤已经处理'
        if t and t.assignee_id!=user.id and user.role not in {'admin','manager'}:return '此任务由其他员工接手'
    return ''


def available_actions(db,user,row):
    result=[]
    for action in flow_spec(row.kind,row.flow_version)['actions']:
        if row.state not in action.states or not own_role(user,action.roles):continue
        reason=blocker(db,user,row,action)
        if not reason:
            from .aftercare_service import guard_source_action
            try:guard_source_action(db,user,row,action.key)
            except HTTPException as exc:
                if exc.status_code!=409:raise
                reason=exc.detail
        fields=action.fields
        if row.kind=='lead' and action.key=='remind':
            customer=scoped_get(db,Customer,row.customer_id) if row.customer_id else None
            if not customer or not customer.phone:
                # API clients and the employee page receive the same recovery
                # requirement. Never mutate the preserved process catalogue.
                fields=[{**field,'required':True} if field['key']=='customer_phone' else field for field in fields]
        result.append(dict(key=action.key,label=action.label,fields=fields,enabled=not reason,reason=reason,confirm=action.confirm))
    return result


def add_payment(db,user,row,values,direction='in',original=None,amount=None):
    amount=amount if amount is not None else values['amount']
    account=scoped_get(db,Account,values['account_id'])
    if not account or not account.active:raise HTTPException(422,'收付款账户不存在或已停用')
    file_exists(db,row,values['evidence_id'])
    if (db.scalar(select(PaymentLink.id).where(PaymentLink.account_id==account.id,PaymentLink.reference==values['reference'])) or
        db.scalar(select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==values['reference']))):
        raise HTTPException(409,'该账户的凭证号已经登记，请核对是否重复收退款')
    account.updated_at=utcnow()  # Serialize voucher reuse across workflow/group cash paths.
    if direction=='in' and row.kind not in {'member_topup'} and amount>collectable_amount(db,row):
        raise HTTPException(409,'金额超过本单可收金额，请核对已收款及集团会员权益占用')
    if original:
        refunded=sum(p.amount_cents for p in db.scalars(select(PaymentLink).where(PaymentLink.original_id==original.id)))
        from .aftercare_service import refund_reservation_amount
        if original.direction!='in' or original.case_id!=row.id or amount>original.amount_cents-refunded-refund_reservation_amount(db,original.id):
            raise HTTPException(409,'退款不能超过这笔原收款的尚未退回金额')
        if account.id!=original.account_id:raise HTTPException(409,'本版退款按原收款账户退回；跨账户退款请人工核对后另行设计')
    from .business_entity_service import require_account_entity,record_cash_entity
    require_account_entity(db,user,row,account.id,today(),original_cash_id=original.cash_id if original else None)
    cash=CashEntry(doc_no='WF-'+uuid.uuid4().hex[:20].upper(),business_date=today(),created_by=user.id,approval_state='approved',
        direction=direction,category='workflow_'+row.kind if direction=='in' else 'workflow_refund',amount_cents=amount,account=account.name,
        counterparty=row.title,payment_method='cash' if account.account_type=='cash' else 'bank',voucher_no=values['reference'],note='关联业务 '+row.number)
    db.add(cash);db.flush();record_cash_entity(db,user,row,cash,account.id,original_cash_id=original.cash_id if original else None)
    link=PaymentLink(case_id=row.id,cash_id=cash.id,original_id=original.id if original else None,account_id=account.id,direction=direction,
        amount_cents=amount,reference=values['reference'],business_date=today())
    db.add(link);db.flush()
    audit(db,user.id,'create','cash',cash.id,after={'store_id':row.store_id,'amount_cents':amount,'direction':direction},reason='流程确认实际到账：'+row.number)
    return link


def stock_move(db,user,row,item,quantity,unit_cost,purpose,original=None):
    # Fen conservation uses inventory value, not repeated rounded average prices.
    from decimal import Decimal
    old_quantity=item.quantity_milli
    old_value=item.inventory_value_cents
    if quantity<0:
        from .inventory_availability import assert_can_issue
        assert_can_issue(db,item,-quantity)
    if quantity>=0:
        value=int((Decimal(quantity)*unit_cost/1000).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        if original:
            returned=list(db.scalars(select(StockMove).where(StockMove.original_id==original.id)))
            available=-original.quantity_milli-sum(m.quantity_milli for m in returned)
            if quantity>available:raise HTTPException(409,'退料数量超过原领料尚未退回数量')
            remaining_value=-original.value_cents-sum(m.value_cents for m in returned)
            value=remaining_value if quantity==available else int((Decimal(remaining_value)*quantity/available).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    else:
        value=-old_value if -quantity==old_quantity else -int((Decimal(old_value)*(-quantity)/old_quantity).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    item.quantity_milli+=quantity;item.inventory_value_cents+=value
    item.unit_cost_cents=int((Decimal(item.inventory_value_cents)*1000/item.quantity_milli).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if item.quantity_milli else 0
    move=StockMove(case_id=row.id,item_id=item.id,quantity_milli=quantity,unit_cost_cents=unit_cost,value_cents=value,purpose=purpose,
        actor_id=user.id,business_date=today(),original_id=original.id if original else None)
    db.add(move);db.flush()
    from .warehouse_stock import after_stock_move
    after_stock_move(db,user,row,item,move)
    return move


def complete_case(db,user,row):
    row.state='completed';row.completed_date=today();close_tasks(db,row,user)


def make_callback(db,user,row,topic,days=3):
    customer=scoped_get(db,Customer,row.customer_id) if row.customer_id else None
    if customer and customer.contact_allowed:
        cb=new_case(db,user,'callback',{'topic':topic,'due_date':(today()+timedelta(days=days)).isoformat()},parent=row,customer=customer,internal=True)
        cb.due_date=today()+timedelta(days=days)
        return cb


def release_order(db,user,row):
    hold=db.scalar(select(VehicleHold).where(VehicleHold.case_id==row.id))
    if hold:db.delete(hold)
    row.state='cancelled';row.completed_date=today();close_tasks(db,row,user)
    for child in children(db,row):
        if child.kind in {'addon','insurance','agency'} and child.state=='pending':child.state='cancelled';close_tasks(db,child,user)


def process_action(db,user,row,key,raw,version):
    if row.kind=='order' and row.flow_version in {3,4}:
        from sqlalchemy.exc import OperationalError,IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        try:return _process_action(db,user,row,key,raw,version)
        except (OperationalError,IntegrityError,StaleDataError):
            db.rollback()
            raise HTTPException(409,'车辆或报价已被同时办理，请刷新核对；本次没有重复过账')
    return _process_action(db,user,row,key,raw,version)


def _process_action(db,user,row,key,raw,version):
    if row.version!=version:raise HTTPException(409,'内容已更新，请刷新后再操作；本次没有覆盖他人的记录')
    catalogue=flow_spec(row.kind,row.flow_version)
    handler=ACTION_HANDLERS.get((row.kind,row.flow_version))
    if handler is None:raise HTTPException(409,'此业务的流程版本尚未配置处理器，未执行操作')
    spec=next((a for a in catalogue['actions'] if a.key==key),None)
    if not spec:raise HTTPException(404,'此业务没有该操作')
    if not own_role(user,spec.roles):raise HTTPException(403,'当前岗位不能执行此操作')
    if row.state not in spec.states:raise HTTPException(409,'当前业务状态不能执行此操作')
    if row.kind=='order' and row.flow_version==4 and key in {'cancel_request','cancel_approve','refund'}:
        # Serialize the child-set check with every typed child create/command.
        # A concurrently changed parent version fails before any refund fact.
        db.scalar(select(Case).where(Case.id==row.id).with_for_update())
        row.updated_at=utcnow();db.flush()
    reason=blocker(db,user,row,spec)
    if reason:raise HTTPException(409,reason)
    v=parse_fields(spec.fields,raw);before=row.state;row.updated_at=utcnow()
    from .aftercare_service import guard_source_action
    guard_source_action(db,user,row,key)
    handler(db,user,row,key,v)
    from .invoice_service import sync_source
    sync_source(db,user,row)
    db.flush();log_event(db,user,row,key,spec.label,before,{**v,'flow_version':row.flow_version});return row


def _apply_action_v1(db,user,row,key,v):
    """Preserved version 1 actions; version 2 delegates only unchanged branches."""
    if row.kind=='lead':
        customer=scoped_get(db,Customer,row.customer_id)
        if key=='assign':
            target=assignable(db,v['assignee_id'],row.store_id,{'sales','reception'})
            row.owner_id=target.id
            if customer and customer.owner_id==row.created_by:customer.owner_id=target.id
            row.state='contacting';finish_task(db,row,'assign',user)
            ensure_task(db,row,'contact','记录接待结果','sales',target.id)
        elif key in {'intent','remind','follow','reopen'}:
            if customer and not customer.contact_allowed:raise HTTPException(409,'客户已要求停止联系；请先由主管核对并更新联系意愿')
            if key=='remind':
                if not customer:raise HTTPException(409,'未找到客户，请刷新后重试')
                phone=v.get('customer_phone','').strip()
                if customer.phone and phone and phone!=customer.phone:
                    raise HTTPException(409,'联系电话已变更，请刷新后重新安排')
                if not customer.phone:
                    if not phone:raise HTTPException(409,'请填写联系电话后安排回访')
                    customer.phone=phone

            close_tasks(db,row,user)
            row.state='reminder' if key=='remind' else 'intent';row.due_date=date.fromisoformat(v['due_date'])
            if key=='reopen':row.completed_date=None
            taskkey='contact' if row.state=='reminder' else 'follow'
            ensure_task(db,row,taskkey,'接待回访' if row.state=='reminder' else '意向跟进','sales',row.owner_id,row.due_date,reopen=True)
            set_data(row,**v)
        elif key=='reserve':
            new_case(db,user,'order',v,parent=row,customer=customer,internal=True)
            row.state='converted';close_tasks(db,row,user)
        elif key=='close':
            row.state='closed';row.completed_date=today();close_tasks(db,row,user)
            if v['no_contact'] and customer:customer.contact_allowed=False
    elif row.kind=='order':
        if key=='revise':
            row.amount_cents=v['amount'];set_data(row,model=v['model'],amount=v['amount'])
            from .flow_documents import generate_document
            generate_document(db,user,row,'contract')
        elif key=='approve':
            row.state='executing';finish_task(db,row,'approve',user)
            for k,title,role in [('allocate','选择配车','inventory'),('sign','合同签回','sales'),('receive','登记车辆款到账','finance'),('inspect','交车检查','service'),('dispatch','车辆出库','inventory'),('deliver','客户提车','sales')]:
                ensure_task(db,row,k,title,role,row.owner_id if role=='sales' else None,row.due_date)
            for kind in ('addon','insurance','agency'):
                if row.data.get(kind):new_case(db,user,kind,{},row,scoped_get(db,Customer,row.customer_id),internal=True)
        elif key=='allocate':
            vehicle=db.scalar(select(Vehicle).where(Vehicle.id==v['vehicle_id']).with_for_update())
            if not vehicle or vehicle.approval_state!='approved':raise HTTPException(422,'请选择本店已审核入库车辆')
            from .vehicle_transfer_service import assert_vehicle_available
            assert_vehicle_available(db,user,vehicle)
            if db.scalar(select(Sale.id).where(Sale.active_vehicle_id==vehicle.id)) or db.scalar(select(VehicleHold).where(VehicleHold.vehicle_id==vehicle.id)):
                raise HTTPException(409,'该车已被其他订单占用')
            if row.data['model'].strip()!=vehicle.model.strip():raise HTTPException(409,'配车车型与订单不一致，请核对；本版不允许直接换车型')
            vehicle.updated_at=utcnow()  # Serialize reservations across legacy and workflow tables.
            db.add(VehicleHold(vehicle_id=vehicle.id,case_id=row.id));row.vehicle_id=vehicle.id;row.cost_cents=vehicle.purchase_cost_cents
            finish_task(db,row,'allocate',user)
            from .flow_documents import generate_document
            generate_document(db,user,row,'contract')
        elif key=='sign':
            from .flow_documents import verify_signed
            verify_signed(db,row,v['evidence_id'],'contract',user=user);set_data(row,signed_file=v['evidence_id']);finish_task(db,row,'sign',user)
        elif key=='inspect':file_exists(db,row,v['evidence_id']);set_data(row,inspection=v);finish_task(db,row,'inspect',user)
        elif key=='receive':
            add_payment(db,user,row,v)
            if paid_amount(db,row)>=row.amount_cents:finish_task(db,row,'receive',user)
        elif key=='dispatch':
            file_exists(db,row,v['evidence_id'])
            from .vehicle_operations_service import record_exit_position
            record_exit_position(db,user,row,scoped_get(db,Vehicle,row.vehicle_id),v['evidence_id'],'sale_dispatch',handover=True)
            finish_task(db,row,'dispatch',user);set_data(row,dispatched_at=utcnow().isoformat()+'Z')
        elif key=='deliver':
            from .flow_documents import verify_signed
            verify_signed(db,row,v['evidence_id'],'handover',user=user)
            from .vehicle_operations_service import record_exit_position
            record_exit_position(db,user,row,scoped_get(db,Vehicle,row.vehicle_id),v['evidence_id'],'sale_deliver')
            row.state='delivered';row.completed_date=today();finish_task(db,row,'deliver',user)
            hold=db.scalar(select(VehicleHold).where(VehicleHold.case_id==row.id));hold.delivered=True
            set_data(row,handover_file=v['evidence_id']);make_callback(db,user,row,'车辆交付回访')
        elif key=='cancel_request':
            set_data(row,previous_state=row.state,cancel_reason=v['reason']);row.state='cancel_review'
            ensure_task(db,row,'cancel_approve','复核退订申请','manager',reopen=True)
        elif key=='cancel_reject':row.state=row.data['previous_state'];finish_task(db,row,'cancel_approve',user)
        elif key=='cancel_approve':
            close_tasks(db,row,user)
            if paid_amount(db,row)>0:
                row.state='refund_pending';ensure_task(db,row,'refund','按原收款办理退款','finance')
            else:release_order(db,user,row)
        elif key=='refund':
            original=scoped_get(db,PaymentLink,v['original_id'])
            if not original:raise HTTPException(422,'原收款不存在')
            add_payment(db,user,row,v,'out',original)
            if paid_amount(db,row)==0:release_order(db,user,row)
    elif row.kind=='repair':
        if key=='quote':
            amount=v['labor']+v['parts']-v['discount']
            if amount<0:raise HTTPException(422,'优惠不得超过工时与配件金额之和')
            row.amount_cents=amount;row.cost_cents=v.get('labor_cost',0);set_data(row,**v)
            row.state='authorization';finish_task(db,row,'quote',user);ensure_task(db,row,'authorize','确认客户授权','service')
        elif key=='authorize':
            file_exists(db,row,v['evidence_id']);set_data(row,authorization_file=v['evidence_id']);row.state='working'
            finish_task(db,row,'authorize',user);ensure_task(db,row,'work','完成维修施工','technician')
        elif key=='start':set_data(row,started=True,started_at=utcnow().isoformat()+'Z')
        elif key in {'material','return_material'}:material_request(db,user,row,key,v)
        elif key=='finish':row.state='quality';finish_task(db,row,'work',user);ensure_task(db,row,'quality','核对施工质量','service',reopen=True)
        elif key=='rework':row.state='working';finish_task(db,row,'quality',user);ensure_task(db,row,'work','返工处理','technician',reopen=True)
        elif key=='quality':
            file_exists(db,row,v['evidence_id']);row.state='settling';finish_task(db,row,'quality',user)
            if row.data.get('payer')=='内部':ensure_task(db,row,'internal_settle','确认内部承担','manager')
            elif paid_amount(db,row)<row.amount_cents:ensure_task(db,row,'receive','登记维修款到账','finance')
            ensure_task(db,row,'release','确认客户接车','service')
        elif key in {'receive','late_receive'}:
            add_payment(db,user,row,v)
            if paid_amount(db,row)>=row.amount_cents:
                finish_task(db,row,'receive',user)
                if row.state=='credit_open':complete_case(db,user,row)
        elif key=='internal_settle':set_data(row,internal_settled=True);finish_task(db,row,'internal_settle',user)
        elif key=='credit':
            set_data(row,credit_approved=True,credit_due=v['due_date']);row.due_date=date.fromisoformat(v['due_date'])
            for t in db.scalars(select(Task).where(Task.case_id==row.id,Task.status=='open',Task.role=='finance')):t.due_date=row.due_date
        elif key=='release':
            file_exists(db,row,v['evidence_id']);finish_task(db,row,'release',user);set_data(row,released_date=today().isoformat())
            if paid_amount(db,row)<row.amount_cents and not row.data.get('internal_settled'):row.state='credit_open'
            else:complete_case(db,user,row)
            make_callback(db,user,row,'维修服务回访')
        elif key=='cancel':row.state='cancelled';close_tasks(db,row,user)
        elif key=='apply_balance':apply_member_balance(db,user,row,v)
    elif row.kind in {'addon','insurance','agency'}:
        if key=='service_quote':
            row.amount_cents=v['amount'];set_data(row,**v);row.state='working';finish_task(db,row,'service',user)
            ensure_task(db,row,'work','办理'+flow_spec(row.kind,row.flow_version)['label'],'technician' if row.kind=='addon' else 'service')
        elif key=='material':material_request(db,user,row,key,v)
        elif key in {'service_finish','policy_issue'}:
            file_exists(db,row,v['evidence_id'])
            if any(c.kind=='material_issue' and c.state not in TERMINAL for c in children(db,row)):raise HTTPException(409,'尚有未处理领料申请')
            if key=='policy_issue':
                if v['end_date']<v['start_date']:raise HTTPException(422,'保单到期日早于生效日')
                for c in db.scalars(select(Case).where(Case.kind=='insurance',Case.id!=row.id)):
                    if c.data.get('policy_number')==v['policy_number']:raise HTTPException(409,'保单号已登记')
            set_data(row,**v);finish_task(db,row,'work',user)
            if row.amount_cents>0:row.state='settling';ensure_task(db,row,'receive','登记'+('保费代收' if row.kind=='insurance' else '服务收款'),'finance')
            else:complete_case(db,user,row)
            if key=='policy_issue':make_callback(db,user,row,'保险到期续保联系',max(0,(date.fromisoformat(v['end_date'])-today()).days-30))
        elif key=='receive':
            add_payment(db,user,row,v)
            if paid_amount(db,row)>=row.amount_cents:complete_case(db,user,row)
    elif row.kind in {'purchase','material_issue','material_return','stock_count'}:
        process_stock_action(db,user,row,key,v)
    elif row.kind=='callback':
        if key in {'callback_done','close'}:complete_case(db,user,row)
        elif key=='callback_later':
            row.due_date=date.fromisoformat(v['due_date']);ensure_task(db,row,'callback','联系客户','customer_service',due=row.due_date,reopen=True)
        elif key in {'new_intent','new_complaint'}:
            customer=scoped_get(db,Customer,row.customer_id)
            child=new_case(db,user,'lead' if key=='new_intent' else 'complaint',v,parent=row,customer=customer,internal=True)
            if key=='new_intent':
                close_tasks(db,child,user);child.state='intent';t=ensure_task(db,child,'follow','意向跟进','sales',due=date.fromisoformat(v['due_date']));child.owner_id=t.assignee_id
                log_event(db,user,child,'callback_intent','原回访产生新意向','unassigned',{'callback_case_id':row.id,'need':v.get('need',''),'due_date':v['due_date']})
            complete_case(db,user,row)
    elif row.kind=='complaint':
        if key=='plan':row.state='resolving';set_data(row,**v);finish_task(db,row,'plan',user);ensure_task(db,row,'resolve','落实投诉处理方案','customer_service',due=date.fromisoformat(v['due_date']))
        elif key=='resolve':file_exists(db,row,v['evidence_id']);set_data(row,**v);complete_case(db,user,row)
        elif key=='reopen':row.state='pending';row.completed_date=None;ensure_task(db,row,'plan','重新安排投诉处理','manager',reopen=True)
    elif row.kind in {'member_topup','member_refund'}:process_member_action(db,user,row,key,v)
    elif row.kind=='invoice':
        if key=='invoice_issue':
            file_exists(db,row,v['evidence_id'])
            if any(c.data.get('invoice_number')==v['invoice_number'] for c in db.scalars(select(Case).where(Case.kind=='invoice',Case.id!=row.id))):raise HTTPException(409,'发票号码已登记')
            set_data(row,**v);complete_case(db,user,row)
        elif key=='cancel':row.state='cancelled';close_tasks(db,row,user)
    else:raise HTTPException(409,'该业务尚未配置此操作')


def purchase_has_postings(db,row):
    return bool(db.scalar(select(StockMove.id).where(StockMove.case_id==row.id)) or
                db.scalar(select(PaymentLink.id).where(PaymentLink.case_id==row.id)))


def member_refund_has_postings(db,row):
    return bool(db.scalar(select(PaymentLink.id).where(PaymentLink.case_id==row.id,PaymentLink.direction=='out')) or
                db.scalar(select(MemberEntry.id).where(MemberEntry.case_id==row.id,MemberEntry.purpose=='refund')))


def _apply_action_v2(db,user,row,key,v):
    if row.kind=='order' and key in {'inspect','reinspect'}:
        file_exists(db,row,v['evidence_id'],'inspection')
        round_number=row.data.get('inspection',{}).get('round',0)+1
        passed=v['outcome']=='合格'
        set_data(row,inspection={**v,'round':round_number,'vehicle_id':row.vehicle_id},
                 inspection_status='passed' if passed else 'failed')
        finish_task(db,row,key,user)
        if not passed:
            ensure_task(db,row,'rectify','处理交车检查缺陷','technician',due=row.due_date,reopen=True)
    elif row.kind=='order' and key=='rectify':
        file_exists(db,row,v['evidence_id'])
        set_data(row,rectification={**v,'inspection_round':row.data['inspection']['round']},
                 inspection_status='awaiting_reinspection')
        finish_task(db,row,'rectify',user)
        ensure_task(db,row,'reinspect','复检交车条件','service',due=row.due_date,reopen=True)
    elif row.kind=='purchase' and key=='cancel':
        if purchase_has_postings(db,row):raise HTTPException(409,'已有实际到货或付款记录，不能取消')
        set_data(row,cancel_reason=v['reason']);row.state='cancelled';row.completed_date=today();close_tasks(db,row,user)
    elif row.kind=='member_refund' and key=='cancel':
        member=db.scalar(select(Member).where(Member.id==row.data['member_id']).with_for_update())
        if not member:raise HTTPException(422,'会员不存在')
        if member_refund_has_postings(db,row):raise HTTPException(409,'已有实际退款记录，不能撤销或改写流水')
        # Removing this pending case from member_available releases the hold. Touch
        # the member version to serialize cancellation against spending/approval.
        member.updated_at=utcnow()
        set_data(row,cancel_reason=v['reason']);row.state='cancelled';row.completed_date=today();close_tasks(db,row,user)
    else:
        _apply_action_v1(db,user,row,key,v)


ACTION_HANDLERS={(kind,version):handler for version,handler in [(1,_apply_action_v1),(2,_apply_action_v2)]
                 for kind in FLOW_CATALOGUES[version]}

def _apply_order_v3(db,user,row,key,values):
    from .sales_quote_service import apply_action
    return apply_action(db,user,row,key,values)

ACTION_HANDLERS[('order',3)]=_apply_order_v3
ACTION_HANDLERS[('order',4)]=_apply_order_v3


def material_request(db,user,parent,key,v):
    if key=='material':
        item=scoped_get(db,Item,v['item_id'])
        if not item or not item.active:raise HTTPException(422,'物资不存在或已停用')
        new_case(db,user,'material_issue',v,parent=parent,internal=True)
    else:
        original=scoped_get(db,StockMove,v['move_id'])
        origin_case=scoped_get(db,Case,original.case_id) if original else None
        if not original or original.purpose!='issue' or not origin_case or origin_case.parent_id!=parent.id:raise HTTPException(422,'请选择本工单已确认的领料记录')
        new_case(db,user,'material_return',{**v,'item_id':original.item_id},parent=parent,internal=True)


def process_stock_action(db,user,row,key,v):
    item=scoped_get(db,Item,row.data['item_id'])
    if not item:raise HTTPException(422,'物资不存在')
    if key=='approve':row.state='receiving';finish_task(db,row,'approve',user);ensure_task(db,row,'stock_in','确认到货验收','inventory')
    elif key=='reject':row.state='rejected';close_tasks(db,row,user)
    elif key=='stock_in':
        file_exists(db,row,v['evidence_id']);stock_move(db,user,row,item,row.data['quantity'],row.data['unit_cost'],'purchase');complete_case(db,user,row)
    elif key in {'issue','return_in'}:
        file_exists(db,row,v['evidence_id']);parent=scoped_get(db,Case,row.parent_id)
        if not parent or parent.state not in {'working','quality'}:raise HTTPException(409,'上游施工已结束或暂停，不能再改变领退料')
        if key=='issue':
            move=stock_move(db,user,row,item,-row.data['quantity'],item.unit_cost_cents,'issue')
            parent.cost_cents=(parent.cost_cents or 0)-move.value_cents
        else:
            original=scoped_get(db,StockMove,row.data['move_id'])
            move=stock_move(db,user,row,item,row.data['quantity'],original.unit_cost_cents,'return',original)
            parent.cost_cents=(parent.cost_cents or 0)-move.value_cents
        parent.updated_at=utcnow();complete_case(db,user,row)
    elif key=='count_approve':
        file_exists(db,row,v['evidence_id'])
        if item.version!=row.data['item_version']:raise HTTPException(409,'盘点期间库存已有变化，请退回后重新盘点，不能用旧数量覆盖新库存')
        delta=row.data['counted']-item.quantity_milli
        if delta:stock_move(db,user,row,item,delta,item.unit_cost_cents,'count')
        complete_case(db,user,row)


def process_member_action(db,user,row,key,v):
    member=scoped_get(db,Member,row.data['member_id'])
    if not member or not member.active:raise HTTPException(422,'会员不存在或已停用')
    if key=='topup_receive':
        add_payment(db,user,row,v,amount=row.amount_cents);member.balance_cents+=row.amount_cents
        db.add(MemberEntry(member_id=member.id,case_id=row.id,amount_cents=row.amount_cents,purpose='topup',actor_id=user.id));complete_case(db,user,row)
    elif key=='approve':
        if row.amount_cents>member_available(db,member):raise HTTPException(409,'退款金额超过会员可用余额')
        # Touch member version to serialize simultaneous approvals and spending.
        member.updated_at=utcnow();row.state='refund_pending';finish_task(db,row,'approve',user);ensure_task(db,row,'member_refund_pay','执行会员余额退款','finance')
    elif key=='member_refund_pay':
        if row.amount_cents>member.balance_cents:raise HTTPException(409,'储值余额不足')
        add_payment(db,user,row,v,'out',amount=row.amount_cents);member.balance_cents-=row.amount_cents
        db.add(MemberEntry(member_id=member.id,case_id=row.id,amount_cents=-row.amount_cents,purpose='refund',actor_id=user.id));complete_case(db,user,row)
    elif key in {'reject','cancel'}:row.state='rejected' if key=='reject' else 'cancelled';close_tasks(db,row,user)


def apply_member_balance(db,user,row,v):
    file_exists(db,row,v['evidence_id'])
    member=scoped_get(db,Member,v['member_id'])
    if not member or not member.active or member.customer_id!=row.customer_id:raise HTTPException(422,'只能使用本客户本人在本店的储值余额')
    if row.data.get('payer')!='客户':raise HTTPException(409,'非客户承担的费用不能扣会员余额')
    if v['amount']>member_available(db,member) or v['amount']>collectable_amount(db,row):raise HTTPException(409,'超过会员可用余额或本单可收金额（含集团会员权益占用）')
    member.balance_cents-=v['amount']
    db.add(MemberEntry(member_id=member.id,case_id=row.id,amount_cents=-v['amount'],purpose='consume',actor_id=user.id));db.flush()
    if paid_amount(db,row)>=row.amount_cents:finish_task(db,row,'receive',user)


def request_digest(operation,payload):
    return hashlib.sha256(json.dumps({'operation':operation,'payload':payload},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def prior_request(db,user,key,digest):
    old=db.scalar(select(RequestReceipt).where(RequestReceipt.request_key==key))
    if old:
        if old.actor_id!=user.id or old.digest!=digest:raise HTTPException(409,'此操作编号已用于不同内容，请刷新页面后重试')
        return get_case(db,user,old.case_id)
    return None


def save_receipt(db,user,key,digest,row):
    db.add(RequestReceipt(request_key=key,actor_id=user.id,digest=digest,case_id=row.id))

"""Explicit customer reuse. Phone matches suggest; they never merge identities."""
import re
from fastapi import HTTPException
from sqlalchemy import select,or_
from .flow_models import Customer
from .tenancy import single_store,role_for_store

ROLES={'admin','manager','sales','reception','service','customer_service'}


def visible_customers(db,user):
    sid=single_store(db)
    role=role_for_store(db,user,sid)
    if role not in ROLES:raise HTTPException(403,'当前门店岗位不能选择或建立客户档案')
    query=select(Customer).where(Customer.store_id==sid)
    if role in {'sales','reception'}:query=query.where(Customer.owner_id==user.id)
    return query


def normalized_phone(phone):
    phone=(phone or '').strip()
    if phone and not re.fullmatch(r'[0-9+() \-]{3,30}',phone):raise HTTPException(422,'联系电话填写不正确，请核对格式')
    return phone


def matches(db,user,phone='',query=''):
    stmt=visible_customers(db,user);phone=normalized_phone(phone)
    if phone:stmt=stmt.where(Customer.phone==phone)
    elif query:
        query=query.strip()
        stmt=stmt.where(or_(Customer.name.contains(query,autoescape=True),Customer.phone.contains(query,autoescape=True)))
    else:return {'items':[],'has_more':False}
    rows=list(db.scalars(stmt.order_by(Customer.id.desc()).limit(21)))
    return {'items':[{'id':r.id,'name':r.name,'phone':r.phone} for r in rows[:20]],'has_more':len(rows)>20}


def resolve_customer(db,user,values):
    """v2 only. Called before case/task creation, under the caller's transaction."""
    if not any(k in values for k in ('customer_name','customer_phone','customer_id')):return None
    stmt=visible_customers(db,user)
    name=(values.get('customer_name') or '').strip();phone=normalized_phone(values.get('customer_phone'))
    customer_id=values.get('customer_id');confirmed=values.get('confirm_new_customer',False)
    if not isinstance(confirmed,bool):raise HTTPException(422,'另建客户确认须是明确的是或否')
    if customer_id:
        if isinstance(customer_id,bool) or not isinstance(customer_id,int):raise HTTPException(422,'请选择明确的客户档案')
        if confirmed:raise HTTPException(422,'已选择客户档案，不能同时确认另建')
        customer=db.scalar(stmt.where(Customer.id==customer_id).with_for_update())
        if not customer:raise HTTPException(404,'客户档案不存在或当前岗位不可选择')
        if (name and name!=customer.name) or (phone and phone!=customer.phone):raise HTTPException(422,'姓名或电话与已选择的客户档案不一致，请核对选择；本操作不修改客户资料')
        return customer
    if not name or len(name)>100:raise HTTPException(422,'请选择已有客户，或填写不超过100字的客户姓名')
    if phone and db.scalar(stmt.where(Customer.phone==phone).limit(1)) and not confirmed:
        raise HTTPException(409,'此联系电话有当前获权的客户档案，请明确选择复用，或核对后确认另建独立档案；不会自动合并')
    customer=Customer(name=name,phone=phone,owner_id=user.id)
    db.add(customer);db.flush();return customer


def create_master_customer(db,user,values):
    """A create endpoint must never overwrite an existing customer's preferences."""
    if values.get('customer_id'):raise HTTPException(422,'新增客户只能建立新档案；复用已有客户请在业务单选择，修改资料请打开原档案')
    row=resolve_customer(db,user,{'customer_name':values['name'],'customer_phone':values.get('phone',''),
        'confirm_new_customer':values.get('confirm_new_customer',False)})
    row.contact_allowed=values.get('contact_allowed',False);row.note=values.get('note','')
    return row

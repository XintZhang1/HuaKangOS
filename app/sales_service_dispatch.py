"""Order v4 creates typed child tasks in the same transaction as signed consent."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from .db import today
from .flow_models import Case,Customer
from .models import Vehicle
from . import flow_engine as flow


def guard_quote_change(db,row,old,quote):
    for child in flow.children(db,row):
        if child.kind not in {'addon','insurance','agency'} or child.state in {'cancelled','rejected'}:continue
        if not quote.services[child.kind]:raise HTTPException(409,'先在原明细服务单办理取消或终止，再从车辆报价移除该服务')
        if old and old.model_id!=quote.model_id:raise HTTPException(409,'原配车已有明确关联服务，须先处理原加装、保单及代办后才能换车型')


def _agency(db,user,source,quote):
    from .service_orders_models import ServiceOrder
    from .service_orders_service import _sync
    customer=flow.scoped_get(db,Customer,source.customer_id);car=flow.scoped_get(db,Vehicle,source.vehicle_id)
    row=Case(number='HKS'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='agency',flow_version=3,state='pending',
        title=customer.name+' · 代办服务',parent_id=source.id,customer_id=source.customer_id,owner_id=source.owner_id,created_by=user.id,
        business_date=today(),due_date=source.due_date,data={})
    db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row)
    db.add(ServiceOrder(id=row.id,subtype='agency',source_order_id=source.id,delivery_blocking=True,customer_name=customer.name,
        vehicle_snapshot={'vin':car.vin,'stock_vehicle_id':car.id,'model_name':car.model,'sales_quote_id':quote.id},reason='客户车辆报价第 '+str(quote.revision)+' 版另单代办约定',created_by=user.id))
    db.flush();_sync(db,user,row);flow.log_event(db,user,row,'serviceorder_create','按客户本版车辆约定建立代办待办',detail={'source_order_id':source.id,'sales_quote_id':quote.id})
    return row


def synchronize(db,user,source,quote):
    from .sales_quote_models import SalesQuoteConsent
    if source.kind!='order' or source.flow_version!=4 or source.data.get('active_quote_id')!=quote.id or quote.case_id!=source.id or not source.vehicle_id:
        raise HTTPException(409,'新明细服务须来自已配车的本版销售约定')
    if not db.scalar(select(SalesQuoteConsent.id).where(SalesQuoteConsent.quote_id==quote.id,SalesQuoteConsent.vehicle_id==source.vehicle_id)):
        raise HTTPException(409,'客户尚未签回本版车辆及配套服务约定')
    for kind in ('addon','insurance','agency'):
        live=[c for c in flow.children(db,source) if c.kind==kind and c.state not in {'cancelled','rejected'}]
        if not quote.services[kind]:
            if live:raise HTTPException(409,'配套服务仍在原单办理，不能由车辆签回自动抹去')
        elif not live:
            if kind=='agency':create=_agency
            elif kind=='insurance':
                from .insurance_service import create_for_sales_quote as create
            else:
                from .addon_service import create_for_sales_quote as create
            create(db,user,source,quote)
    db.flush()

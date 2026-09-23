"""Sales accessory agreements, actual work, and original physical dispositions."""
from datetime import datetime,date
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,Boolean,ForeignKey,JSON,Date,DateTime,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned

class AddonOrder(StoreScoped,Base):
    __tablename__='addon_orders'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    source_order_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    customer_id:Mapped[int]=mapped_column(ForeignKey('flow_customers.id'))
    source_snapshot:Mapped[dict]=mapped_column(JSON)
    delivery_blocking:Mapped[bool]=mapped_column(Boolean)
    reason:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))

class AddonTarget(StoreScoped,Base):
    __tablename__='addon_targets'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('addon_orders.id'),unique=True)
    vehicle_id:Mapped[int]=mapped_column(ForeignKey('vehicles.id'))
    vin:Mapped[str]=mapped_column(String(17))
    source_version:Mapped[int]=mapped_column(Integer)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class AddonQuote(StoreScoped,Base):
    __tablename__='addon_quotes'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('addon_orders.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    goods_cents:Mapped[int]=mapped_column(BigInteger)
    installation_cents:Mapped[int]=mapped_column(BigInteger)
    discount_cents:Mapped[int]=mapped_column(BigInteger)
    pricing_version:Mapped[int]=mapped_column(Integer,default=1,server_default='1')
    gift_terms:Mapped[dict]=mapped_column(JSON,default=dict,server_default='{}')
    digest:Mapped[str]=mapped_column(String(64))
    reason:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_addon_quote_revision'),CheckConstraint('goods_cents>=0 AND installation_cents>=0 AND discount_cents>=0 AND (pricing_version=2 OR (pricing_version=1 AND goods_cents+installation_cents>0))',name='ck_addon_quote_money'))

class AddonLine(StoreScoped,Base):
    __tablename__='addon_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('addon_quotes.id'),index=True)
    line_key:Mapped[str]=mapped_column(String(40))
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'))
    work_item_id:Mapped[int]=mapped_column(ForeignKey('master_work_items.id'))
    sku:Mapped[str]=mapped_column(String(60))
    name:Mapped[str]=mapped_column(String(120))
    unit:Mapped[str]=mapped_column(String(20))
    work_code:Mapped[str]=mapped_column(String(60))
    work_name:Mapped[str]=mapped_column(String(120))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    goods_unit_cents:Mapped[int]=mapped_column(BigInteger)
    installation_unit_cents:Mapped[int]=mapped_column(BigInteger)
    goods_cents:Mapped[int]=mapped_column(BigInteger)
    installation_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('quote_id','line_key',name='uq_addon_quote_line'),CheckConstraint('quantity_milli>0 AND goods_unit_cents>=0 AND installation_unit_cents>=0 AND goods_cents>=0 AND installation_cents>=0',name='ck_addon_line_values'))

class AddonApproval(StoreScoped,Base):
    __tablename__='addon_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('addon_quotes.id'),unique=True)
    minimum_cents:Mapped[int]=mapped_column(BigInteger)
    allow_below_minimum:Mapped[bool]=mapped_column(Boolean)
    gift_confirmed:Mapped[bool]=mapped_column(Boolean,default=False,server_default='0')
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class AddonAuthorization(StoreScoped,Base):
    __tablename__='addon_authorizations'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('addon_quotes.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class AddonReservation(StoreScoped,Base):
    __tablename__='addon_reservations'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('addon_orders.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('addon_lines.id'))
    line_key:Mapped[str]=mapped_column(String(40))
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'),index=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    purpose:Mapped[str]=mapped_column(String(20))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("(quantity_milli>0 AND purpose='reserve') OR (quantity_milli<0 AND purpose IN ('dispatch','cancel'))",name='ck_addon_reservation'),)

class AddonDispatch(StoreScoped,Base):
    __tablename__='addon_dispatches'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('addon_orders.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('addon_lines.id'))
    line_key:Mapped[str]=mapped_column(String(40))
    target_id:Mapped[int]=mapped_column(ForeignKey('addon_targets.id'))
    stock_move_id:Mapped[int]=mapped_column(ForeignKey('flow_stock_moves.id'),unique=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    goods_cents:Mapped[int]=mapped_column(BigInteger)
    installation_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('quantity_milli>0 AND value_cents>=0 AND goods_cents>=0 AND installation_cents>=0',name='ck_addon_dispatch'),)

class AddonInstallation(StoreScoped,Base):
    __tablename__='addon_installations'
    id:Mapped[int]=mapped_column(primary_key=True)
    dispatch_id:Mapped[int]=mapped_column(ForeignKey('addon_dispatches.id'),index=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    result:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('quantity_milli>0',name='ck_addon_installation'),)

class AddonInspection(StoreScoped,Base):
    __tablename__='addon_inspections'
    id:Mapped[int]=mapped_column(primary_key=True)
    installation_id:Mapped[int]=mapped_column(ForeignKey('addon_installations.id'),index=True)
    passed:Mapped[bool]=mapped_column(Boolean)
    result:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class AddonRectification(StoreScoped,Base):
    __tablename__='addon_rectifications'
    id:Mapped[int]=mapped_column(primary_key=True)
    inspection_id:Mapped[int]=mapped_column(ForeignKey('addon_inspections.id'),unique=True)
    result:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class AddonAcceptance(StoreScoped,Base):
    __tablename__='addon_acceptances'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('addon_orders.id'),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('addon_quotes.id'),unique=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    business_date:Mapped[date]=mapped_column(Date)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class AddonResolution(Versioned,Base):
    __tablename__='addon_resolutions'
    case_id:Mapped[int]=mapped_column(ForeignKey('addon_orders.id'),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('addon_quotes.id'))
    kind:Mapped[str]=mapped_column(String(20))
    status:Mapped[str]=mapped_column(String(25),default='requested')
    lines:Mapped[list]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(String(1000))
    digest:Mapped[str]=mapped_column(String(64))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("kind IN ('return','cancel','vehicle_gift')",name='ck_addon_resolution_kind'),CheckConstraint("status IN ('requested','approved','consented','rectification','reinspection','handback','rejected','completed','cancelled')",name='ck_addon_resolution_status'))

class AddonResolutionFact(StoreScoped,Base):
    __tablename__='addon_resolution_facts'
    id:Mapped[int]=mapped_column(primary_key=True)
    resolution_id:Mapped[int]=mapped_column(ForeignKey('addon_resolutions.id'),index=True)
    action:Mapped[str]=mapped_column(String(30))
    result:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class AddonReturnPosting(StoreScoped,Base):
    __tablename__='addon_return_postings'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('addon_orders.id'),index=True)
    resolution_id:Mapped[int]=mapped_column(ForeignKey('addon_resolutions.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('addon_lines.id'))
    line_key:Mapped[str]=mapped_column(String(40))
    dispatch_id:Mapped[int|None]=mapped_column(ForeignKey('addon_dispatches.id'),nullable=True)
    installation_id:Mapped[int|None]=mapped_column(ForeignKey('addon_installations.id'),nullable=True)
    stock_move_id:Mapped[int|None]=mapped_column(ForeignKey('flow_stock_moves.id'),nullable=True,unique=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    goods_cents:Mapped[int]=mapped_column(BigInteger)
    installation_cents:Mapped[int]=mapped_column(BigInteger)
    retained_cents:Mapped[int]=mapped_column(BigInteger)
    acceptance_id:Mapped[int|None]=mapped_column(ForeignKey('addon_acceptances.id'),nullable=True)
    business_date:Mapped[date]=mapped_column(Date)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint('quantity_milli>0 AND value_cents>=0 AND goods_cents>=0 AND installation_cents>=0 AND retained_cents>=0 AND retained_cents<=installation_cents',name='ck_addon_return_posting'),)

class AddonVehicleHandover(StoreScoped,Base):
    __tablename__='addon_vehicle_handovers'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('addon_orders.id'),index=True)
    resolution_id:Mapped[int]=mapped_column(ForeignKey('addon_resolutions.id'),unique=True)
    aftercare_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    vehicle_operation_id:Mapped[int]=mapped_column(ForeignKey('vehicle_operations.id'))
    new_vehicle_id:Mapped[int]=mapped_column(ForeignKey('vehicles.id'))
    vin:Mapped[str]=mapped_column(String(17))
    attachments:Mapped[list]=mapped_column(JSON)
    incremental_value_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('incremental_value_cents=0',name='ck_addon_gift_no_invented_value'),)

class AddonPayment(StoreScoped,Base):
    __tablename__='addon_payments'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('addon_orders.id'),index=True)
    payment_link_id:Mapped[int|None]=mapped_column(ForeignKey('flow_payment_links.id'),nullable=True,unique=True)
    credit_link_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_credit_links.id'),nullable=True,unique=True)
    resolution_id:Mapped[int|None]=mapped_column(ForeignKey('addon_resolutions.id'),nullable=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint('(payment_link_id IS NOT NULL AND credit_link_id IS NULL) OR (payment_link_id IS NULL AND credit_link_id IS NOT NULL)',name='ck_addon_payment_source'),)

class AddonReceipt(StoreScoped,Base):
    __tablename__='addon_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80))
    digest:Mapped[str]=mapped_column(String(64))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_addon_request'),)

IMMUTABLE=(AddonOrder,AddonTarget,AddonQuote,AddonLine,AddonApproval,AddonAuthorization,AddonReservation,AddonDispatch,
    AddonInstallation,AddonInspection,AddonRectification,AddonAcceptance,AddonResolutionFact,AddonReturnPosting,AddonVehicleHandover,AddonPayment,AddonReceipt)
@event.listens_for(Session,'before_flush')
def immutable_addon(db,*_):
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,IMMUTABLE):raise HTTPException(409,'加装报价、真实施工、库存及资金事实不可覆盖，请追加原单处置')
        if isinstance(row,AddonResolution) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('case_id','quote_id','kind','lines','reason','digest','evidence_id','requested_by'))):raise HTTPException(409,'加装处置申请原始内容不可修改')

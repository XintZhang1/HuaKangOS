"""Store-owned vehicle purchase facts; vehicle identity/custody remains central."""
from datetime import date
from sqlalchemy import String,Integer,BigInteger,Date,ForeignKey,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from fastapi import HTTPException
from .db import Base
from .models import StoreScoped
from .flow_models import Versioned


class VehiclePurchaseOrder(StoreScoped,Base):
    __tablename__='vehicle_purchase_orders'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    supplier_id:Mapped[int]=mapped_column(ForeignKey('master_suppliers.id'))
    supplier_name:Mapped[str]=mapped_column(String(120))
    supplier_code:Mapped[str]=mapped_column(String(40))
    payment_terms_days:Mapped[int]=mapped_column(Integer)
    contracting_party:Mapped[str]=mapped_column(String(180))
    reason:Mapped[str]=mapped_column(String(500))


class VehiclePurchaseLine(StoreScoped,Base):
    __tablename__='vehicle_purchase_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    model_id:Mapped[int]=mapped_column(ForeignKey('master_vehicle_models.id'))
    model_code:Mapped[str]=mapped_column(String(40))
    model_name:Mapped[str]=mapped_column(String(120))
    brand:Mapped[str]=mapped_column(String(80))
    model_year:Mapped[int]=mapped_column(Integer)
    fuel_type:Mapped[str]=mapped_column(String(20))
    color:Mapped[str]=mapped_column(String(40))
    quantity:Mapped[int]=mapped_column(Integer)
    __table_args__=(CheckConstraint('quantity BETWEEN 1 AND 1000',name='ck_vpurchase_line_qty'),UniqueConstraint('case_id','model_id','color',name='uq_vpurchase_model_color'))


class VehiclePurchasePrice(StoreScoped,Base):
    __tablename__='vehicle_purchase_prices'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('vehicle_purchase_lines.id'),unique=True)
    unit_cost_cents:Mapped[int]=mapped_column(BigInteger)
    list_price_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    approved_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint('unit_cost_cents > 0 AND list_price_cents >= 0',name='ck_vpurchase_price'),)


class VehiclePurchaseShipment(Versioned,Base):
    __tablename__='vehicle_purchase_shipments'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('vehicle_purchase_lines.id'))
    vin:Mapped[str]=mapped_column(String(17),index=True)
    # Global uniqueness coordinates competing stores without exposing their data.
    active_vin:Mapped[str|None]=mapped_column(String(17),unique=True,nullable=True)
    status:Mapped[str]=mapped_column(String(20),default='transit')
    shipped_date:Mapped[date]=mapped_column(Date)
    expected_date:Mapped[date]=mapped_column(Date)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("status IN ('transit','received','returned')",name='ck_vpurchase_shipment_state'),
        CheckConstraint("(status='transit' AND active_vin=vin) OR (status!='transit' AND active_vin IS NULL)",name='ck_vpurchase_vin_claim'))


class VehiclePurchaseReceipt(StoreScoped,Base):
    __tablename__='vehicle_purchase_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    shipment_id:Mapped[int]=mapped_column(ForeignKey('vehicle_purchase_shipments.id'),unique=True)
    vehicle_id:Mapped[int]=mapped_column(ForeignKey('vehicles.id'),unique=True)
    location_id:Mapped[int]=mapped_column(ForeignKey('master_locations.id'))
    value_cents:Mapped[int]=mapped_column(BigInteger)
    due_date:Mapped[date]=mapped_column(Date)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    business_date:Mapped[date]=mapped_column(Date)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint('value_cents > 0',name='ck_vpurchase_receipt_value'),)


class VehiclePurchaseReturn(Versioned,Base):
    __tablename__='vehicle_purchase_returns'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    shipment_id:Mapped[int]=mapped_column(ForeignKey('vehicle_purchase_shipments.id'))
    active_shipment_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_purchase_shipments.id'),unique=True,nullable=True)
    status:Mapped[str]=mapped_column(String(20),default='requested')
    reason:Mapped[str]=mapped_column(String(500))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    approved_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    __table_args__=(CheckConstraint("status IN ('requested','approved','dispatched','cancelled')",name='ck_vpurchase_return_state'),
        CheckConstraint("status NOT IN ('approved','dispatched') OR approved_by IS NOT NULL",name='ck_vpurchase_return_approval'))


class VehiclePurchaseCancellation(StoreScoped,Base):
    __tablename__='vehicle_purchase_cancellations'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('vehicle_purchase_lines.id'),unique=True)
    quantity:Mapped[int]=mapped_column(Integer)
    reason:Mapped[str]=mapped_column(String(500))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(CheckConstraint('quantity > 0',name='ck_vpurchase_cancel_qty'),)


class VehiclePurchaseFundsRequest(Versioned,Base):
    __tablename__='vehicle_purchase_funds_requests'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    status:Mapped[str]=mapped_column(String(20),default='open')
    reason:Mapped[str]=mapped_column(String(500))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("amount_cents > 0 AND status IN ('open','closed','cancelled')",name='ck_vpurchase_funds'),)


class VehiclePurchasePayment(StoreScoped,Base):
    __tablename__='vehicle_purchase_payments'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    funds_request_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_purchase_funds_requests.id'),nullable=True)
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_purchase_payments.id'),nullable=True)
    direction:Mapped[str]=mapped_column(String(3))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    reference:Mapped[str]=mapped_column(String(100))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(UniqueConstraint('store_id','account_id','reference',name='uq_vpurchase_cash_reference'),
        CheckConstraint("amount_cents > 0 AND ((direction='out' AND original_id IS NULL AND funds_request_id IS NOT NULL) OR (direction='in' AND original_id IS NOT NULL AND funds_request_id IS NULL))",name='ck_vpurchase_payment'))


class VehiclePurchaseMovement(StoreScoped,Base):
    __tablename__='vehicle_purchase_movements'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    shipment_id:Mapped[int]=mapped_column(ForeignKey('vehicle_purchase_shipments.id'),index=True)
    vehicle_id:Mapped[int|None]=mapped_column(ForeignKey('vehicles.id'),nullable=True)
    return_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_purchase_returns.id'),nullable=True,unique=True)
    original_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_purchase_movements.id'),nullable=True)
    kind:Mapped[str]=mapped_column(String(20))
    quantity:Mapped[int]=mapped_column(Integer)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    business_date:Mapped[date]=mapped_column(Date)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('shipment_id','kind',name='uq_vpurchase_movement'),
        CheckConstraint("(kind='receive' AND quantity=1 AND value_cents>0 AND vehicle_id IS NOT NULL) OR (kind='return' AND quantity=-1 AND value_cents<0 AND vehicle_id IS NOT NULL) OR (kind='transit_return' AND quantity=0 AND value_cents=0)",name='ck_vpurchase_movement_sign'))


IMMUTABLE=(VehiclePurchaseOrder,VehiclePurchaseLine,VehiclePurchasePrice,VehiclePurchaseReceipt,
    VehiclePurchaseCancellation,VehiclePurchasePayment,VehiclePurchaseMovement)
@event.listens_for(Session,'before_flush')
def protect_vehicle_purchase(db,*_):
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,IMMUTABLE):raise HTTPException(409,'整车采购约定与实物资金事实不可覆盖，请追加对应业务记录')
        frozen=()
        if isinstance(row,VehiclePurchaseShipment):frozen=('case_id','line_id','vin','shipped_date','expected_date','evidence_id','actor_id')
        if isinstance(row,VehiclePurchaseReturn):frozen=('case_id','shipment_id','reason','evidence_id','requested_by')
        if isinstance(row,VehiclePurchaseFundsRequest):frozen=('case_id','amount_cents','reason','evidence_id','requested_by')
        if frozen and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in frozen)):
            raise HTTPException(409,'原始申请与发运来源不可覆盖，请撤销或追加对应事实')

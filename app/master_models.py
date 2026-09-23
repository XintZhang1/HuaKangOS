"""Typed store masters and immutable evidence for opening inventory."""
from datetime import date, datetime
from sqlalchemy import (String, Integer, BigInteger, Boolean, Date, DateTime, Text,
                        ForeignKey, UniqueConstraint, CheckConstraint, JSON, event, inspect)
from sqlalchemy.orm import Mapped, mapped_column, declared_attr, Session
from fastapi import HTTPException
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned


class MasterRecord(Versioned):
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    @declared_attr.directive
    def __table_args__(cls):
        return (UniqueConstraint('store_id','code',name='uq_'+cls.__tablename__+'_code'),)


class Supplier(MasterRecord, Base):
    __tablename__ = 'master_suppliers'
    tax_identifier: Mapped[str] = mapped_column(String(40), default='')
    contact_name: Mapped[str] = mapped_column(String(80), default='')
    phone: Mapped[str] = mapped_column(String(30), default='')
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint('store_id','code',name='uq_master_suppliers_code'),
                     CheckConstraint('payment_terms_days BETWEEN 0 AND 365',name='ck_master_supplier_terms'))


class Insurer(MasterRecord, Base):
    __tablename__ = 'master_insurers'
    license_number: Mapped[str] = mapped_column(String(60), default='')
    claims_phone: Mapped[str] = mapped_column(String(30), default='')
    settlement_days: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint('store_id','code',name='uq_master_insurers_code'),
                     CheckConstraint('settlement_days BETWEEN 0 AND 365',name='ck_master_insurer_terms'))


class Warehouse(MasterRecord, Base):
    __tablename__ = 'master_warehouses'
    warehouse_type: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(String(200), default='')
    __table_args__ = (UniqueConstraint('store_id','code',name='uq_master_warehouses_code'),
                     CheckConstraint("warehouse_type IN ('vehicles','materials','mixed')",name='ck_master_warehouse_type'))


class StorageLocation(MasterRecord, Base):
    __tablename__ = 'master_locations'
    warehouse_id: Mapped[int] = mapped_column(ForeignKey('master_warehouses.id'),index=True)


class MaterialCategory(MasterRecord, Base):
    __tablename__ = 'master_material_categories'
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('master_material_categories.id'),nullable=True)


class MaterialBrand(MasterRecord, Base):
    __tablename__ = 'master_material_brands'


class WorkItem(MasterRecord, Base):
    __tablename__ = 'master_work_items'
    billing_unit: Mapped[str] = mapped_column(String(10))
    standard_minutes: Mapped[int] = mapped_column(Integer, default=0)
    standard_fee_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    warranty_days: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint('store_id','code',name='uq_master_work_items_code'),
        CheckConstraint("billing_unit IN ('job','hour') AND standard_minutes BETWEEN 0 AND 100000 AND standard_fee_cents >= 0 AND warranty_days BETWEEN 0 AND 3650",name='ck_master_work_values'))


class Team(MasterRecord, Base):
    __tablename__ = 'master_teams'
    leader_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True)


class AgencyProject(MasterRecord, Base):
    __tablename__ = 'master_agency_projects'
    service_fee_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    expected_days: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint('store_id','code',name='uq_master_agency_projects_code'),
        CheckConstraint('service_fee_cents >= 0 AND expected_days BETWEEN 0 AND 365',name='ck_master_agency_values'))


class VehicleModel(MasterRecord, Base):
    __tablename__ = 'master_vehicle_models'
    brand: Mapped[str] = mapped_column(String(80))
    model_year: Mapped[int] = mapped_column(Integer)
    fuel_type: Mapped[str] = mapped_column(String(20))
    seats: Mapped[int] = mapped_column(Integer)
    displacement_ml: Mapped[int] = mapped_column(Integer,default=0)
    battery_wh: Mapped[int] = mapped_column(Integer,default=0)
    guide_price_cents: Mapped[int] = mapped_column(BigInteger,default=0)
    __table_args__ = (UniqueConstraint('store_id','code',name='uq_master_vehicle_models_code'),
        CheckConstraint("fuel_type IN ('petrol','diesel','electric','hybrid','plugin_hybrid') AND model_year BETWEEN 1990 AND 2100 AND seats BETWEEN 1 AND 60 AND displacement_ml BETWEEN 0 AND 20000 AND battery_wh BETWEEN 0 AND 2000000 AND guide_price_cents >= 0",name='ck_master_model_values'))


class MemberTier(MasterRecord, Base):
    __tablename__ = 'master_member_tiers'
    annual_fee_cents: Mapped[int] = mapped_column(BigInteger,default=0)
    validity_months: Mapped[int] = mapped_column(Integer,default=12)
    discount_basis_points: Mapped[int] = mapped_column(Integer,default=10000)
    __table_args__ = (UniqueConstraint('store_id','code',name='uq_master_member_tiers_code'),
        CheckConstraint('annual_fee_cents >= 0 AND validity_months BETWEEN 1 AND 120 AND discount_basis_points BETWEEN 0 AND 10000',name='ck_master_tier_values'))


class ItemProfile(Versioned, Base):
    __tablename__ = 'master_item_profiles'
    item_id: Mapped[int] = mapped_column(ForeignKey('flow_items.id'),unique=True)
    category_id: Mapped[int] = mapped_column(ForeignKey('master_material_categories.id'),index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey('master_locations.id'),index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey('master_suppliers.id'),nullable=True,index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey('master_material_brands.id'),nullable=True,index=True)
    active: Mapped[bool] = mapped_column(Boolean,default=True)


class MasterReceipt(StoreScoped, Base):
    __tablename__ = 'master_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_key: Mapped[str] = mapped_column(String(80))
    digest: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow)
    __table_args__ = (UniqueConstraint('store_id','request_key',name='uq_master_request_key'),)


class OpeningBatch(Versioned, Base):
    __tablename__ = 'opening_batches'
    source_text: Mapped[str] = mapped_column(Text)
    source_digest: Mapped[str] = mapped_column(String(64))
    source_reference: Mapped[str] = mapped_column(String(160))
    opening_date: Mapped[date] = mapped_column(Date)
    totals: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20),default='prepared')
    prepared_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime,nullable=True)
    # A store can commit opening data only once, including competing batches.
    confirmed_store_key: Mapped[int | None] = mapped_column(Integer,nullable=True,unique=True)
    __table_args__ = (CheckConstraint("status IN ('prepared','trial_passed','confirmed')",name='ck_opening_status'),)


class OpeningStockEntry(StoreScoped, Base):
    __tablename__ = 'opening_stock_entries'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('opening_batches.id'))
    item_id: Mapped[int] = mapped_column(ForeignKey('flow_items.id'),unique=True)
    quantity_milli: Mapped[int] = mapped_column(BigInteger)
    value_cents: Mapped[int] = mapped_column(BigInteger)
    business_date: Mapped[date] = mapped_column(Date)
    source_reference: Mapped[str] = mapped_column(String(160))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow)
    __table_args__ = (CheckConstraint('quantity_milli > 0 AND value_cents >= 0',name='ck_opening_stock_values'),)


@event.listens_for(Session,'before_flush')
def preserve_master_evidence(db,*_):
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,(MasterReceipt,OpeningStockEntry)):
            raise HTTPException(409,'期初来源与操作回执不可覆盖；请通过后续业务更正')
        if isinstance(row,OpeningBatch):
            if row in db.deleted or any(inspect(row).attrs[key].history.has_changes() for key in
                ('source_text','source_digest','source_reference','opening_date','totals','prepared_by')):
                raise HTTPException(409,'期初原资料、摘要和汇总不可覆盖；请重新预检另一份资料')

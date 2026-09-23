"""Reviewed opening facts. Opening cash is a balance, never a receipt."""
from datetime import date, datetime
from sqlalchemy import String, Integer, BigInteger, Date, DateTime, ForeignKey, JSON, CheckConstraint, UniqueConstraint, event, inspect, select
from sqlalchemy.orm import Mapped, mapped_column, Session
from fastapi import HTTPException
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned


class OpeningImport(Versioned, Base):
    __tablename__='opening_imports'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('opening_batches.id'),unique=True)
    status:Mapped[str]=mapped_column(String(20),default='prepared')
    __table_args__=(CheckConstraint("status IN ('prepared','trial_passed','approved','confirmed','cancelled')",name='ck_opening_import_status'),)


class OpeningAttestation(StoreScoped, Base):
    __tablename__='opening_attestations'
    id:Mapped[int]=mapped_column(primary_key=True)
    import_id:Mapped[int]=mapped_column(ForeignKey('opening_imports.id'),index=True)
    kind:Mapped[str]=mapped_column(String(20))
    source_digest:Mapped[str]=mapped_column(String(64))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    reason:Mapped[str]=mapped_column(String(500))
    observed:Mapped[dict]=mapped_column(JSON)
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('import_id','kind',name='uq_opening_attestation_kind'),
        CheckConstraint("kind IN ('approve','inventory','finance')",name='ck_opening_attestation_kind'))


class OpeningAccountEntry(StoreScoped, Base):
    __tablename__='opening_account_entries'
    id:Mapped[int]=mapped_column(primary_key=True)
    import_id:Mapped[int]=mapped_column(ForeignKey('opening_imports.id'),index=True)
    row_number:Mapped[int]=mapped_column(Integer)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'),unique=True)
    account_name:Mapped[str]=mapped_column(String(100))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    business_date:Mapped[date]=mapped_column(Date)
    source_reference:Mapped[str]=mapped_column(String(160))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('import_id','row_number',name='uq_opening_account_row'),CheckConstraint('amount_cents>=0 AND row_number>0',name='ck_opening_account_value'))


class OpeningVehicleEntry(StoreScoped, Base):
    __tablename__='opening_vehicle_entries'
    id:Mapped[int]=mapped_column(primary_key=True)
    import_id:Mapped[int]=mapped_column(ForeignKey('opening_imports.id'),index=True)
    row_number:Mapped[int]=mapped_column(Integer)
    vehicle_id:Mapped[int]=mapped_column(ForeignKey('vehicles.id'),unique=True)
    identity_id:Mapped[int]=mapped_column(ForeignKey('group_identities.id'))
    model_id:Mapped[int]=mapped_column(ForeignKey('master_vehicle_models.id'))
    location_id:Mapped[int]=mapped_column(ForeignKey('master_locations.id'))
    vin:Mapped[str]=mapped_column(String(17))
    value_cents:Mapped[int]=mapped_column(BigInteger)
    business_date:Mapped[date]=mapped_column(Date)
    source_reference:Mapped[str]=mapped_column(String(160))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('import_id','row_number',name='uq_opening_vehicle_row'),CheckConstraint('value_cents>=0 AND row_number>0',name='ck_opening_vehicle_value'))


IMMUTABLE=(OpeningAttestation,OpeningAccountEntry,OpeningVehicleEntry)


@event.listens_for(Session,'before_flush')
def protect_opening(db,*_):
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if not isinstance(row,(*IMMUTABLE,OpeningImport)):continue
        if not db.info.get('_opening_authority'):raise HTTPException(403,'期初资料只能通过三岗核验流程办理')
        if row in db.new:continue
        if isinstance(row,IMMUTABLE) or row in db.deleted:raise HTTPException(409,'期初余额、车辆来源和核验凭据不可改写')
        if any(inspect(row).attrs[k].history.has_changes() for k in ('case_id','batch_id')):raise HTTPException(409,'期初批次来源不可更换')
    from .models import CashEntry
    from .flow_models import Account
    for row in db.new:
        if not isinstance(row,CashEntry):continue
        sid=row.store_id if row.store_id is not None else db.info.get('write_store',1)
        # Explicit SQL store criteria plus tenant loader filtering; no identity-map fallback.
        entry=db.scalar(select(OpeningAccountEntry).where(OpeningAccountEntry.store_id==sid,OpeningAccountEntry.account_name==row.account))
        if entry and row.business_date<entry.business_date:raise HTTPException(409,'实际流水日期不能早于该账户期初基准日')
    for row in db.dirty:
        if not isinstance(row,Account) or not any(inspect(row).attrs[k].history.has_changes() for k in ('name','account_type')):continue
        if db.scalar(select(OpeningAccountEntry.id).where(OpeningAccountEntry.store_id==row.store_id,OpeningAccountEntry.account_id==row.id)):
            raise HTTPException(409,'已有期初余额来源的账户不能改名或改变账户类型')

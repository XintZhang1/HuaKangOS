"""Frozen CSV sources and links to existing purchase facts; no second stock/cash ledger."""
from datetime import datetime
from sqlalchemy import String,Integer,BigInteger,ForeignKey,JSON,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from fastapi import HTTPException
from .db import Base
from .models import StoreScoped
from .flow_models import Versioned


class VehicleImportBatch(Versioned,Base):
    __tablename__='vehicle_import_batches'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    kind:Mapped[str]=mapped_column(String(12))
    status:Mapped[str]=mapped_column(String(20),default='prepared')
    source_file_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    source_digest:Mapped[str]=mapped_column(String(64))
    source_reference:Mapped[str]=mapped_column(String(100))
    source_case_version:Mapped[int]=mapped_column(Integer)
    replacement_batch_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_import_batches.id'),nullable=True)
    prepared_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    reviewed_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    confirmed_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    row_count:Mapped[int]=mapped_column(Integer)
    amount_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    errors:Mapped[list]=mapped_column(JSON,default=list)
    __table_args__=(CheckConstraint("kind IN ('funds','ship','receive') AND status IN ('invalid','prepared','trial_passed','reviewed','confirmed','cancelled')",name='ck_vimport_state'),CheckConstraint('row_count BETWEEN 1 AND 200 AND amount_cents >= 0',name='ck_vimport_totals'))


class VehicleImportRow(StoreScoped,Base):
    __tablename__='vehicle_import_rows'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('vehicle_import_batches.id'),index=True)
    row_number:Mapped[int]=mapped_column(Integer)
    source_row:Mapped[str]=mapped_column(String(80))
    vin:Mapped[str]=mapped_column(String(17))
    line_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_purchase_lines.id'),nullable=True)
    manifest_row_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_import_rows.id'),nullable=True)
    origin_key:Mapped[str]=mapped_column(String(64),index=True)
    vehicle_key:Mapped[str]=mapped_column(String(64),index=True)
    values:Mapped[dict]=mapped_column(JSON)
    errors:Mapped[list]=mapped_column(JSON,default=list)
    __table_args__=(UniqueConstraint('batch_id','row_number',name='uq_vimport_row'),CheckConstraint('row_number BETWEEN 2 AND 201',name='ck_vimport_row_number'))


class VehicleImportClaim(StoreScoped,Base):
    """Temporary holds are released only when an entirely unposted batch is cancelled."""
    __tablename__='vehicle_import_claims'
    key:Mapped[str]=mapped_column(String(64),primary_key=True)
    row_id:Mapped[int]=mapped_column(ForeignKey('vehicle_import_rows.id'),index=True)


class VehicleImportResult(StoreScoped,Base):
    __tablename__='vehicle_import_results'
    id:Mapped[int]=mapped_column(primary_key=True)
    row_id:Mapped[int]=mapped_column(ForeignKey('vehicle_import_rows.id'),unique=True)
    funds_request_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_purchase_funds_requests.id'),nullable=True,unique=True)
    shipment_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_purchase_shipments.id'),nullable=True,unique=True)
    receipt_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_purchase_receipts.id'),nullable=True,unique=True)
    __table_args__=(CheckConstraint('(CASE WHEN funds_request_id IS NULL THEN 0 ELSE 1 END + CASE WHEN shipment_id IS NULL THEN 0 ELSE 1 END + CASE WHEN receipt_id IS NULL THEN 0 ELSE 1 END)=1',name='ck_vimport_result_kind'),)


class VehicleImportRequest(StoreScoped,Base):
    __tablename__='vehicle_import_requests'
    id:Mapped[int]=mapped_column(primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    request_key:Mapped[str]=mapped_column(String(80))
    digest:Mapped[str]=mapped_column(String(64))
    batch_id:Mapped[int]=mapped_column(ForeignKey('vehicle_import_batches.id'))
    __table_args__=(UniqueConstraint('store_id','actor_id','request_key',name='uq_vimport_request'),)


@event.listens_for(Session,'before_flush')
def protect_vehicle_imports(db,*_):
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if isinstance(row,(VehicleImportBatch,VehicleImportRow,VehicleImportClaim,VehicleImportResult,VehicleImportRequest)) and not db.info.get('_vehicle_import_authority'):
            raise HTTPException(403,'车辆导入须通过批次核验办理')
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,(VehicleImportRow,VehicleImportResult,VehicleImportRequest)):
            raise HTTPException(409,'车辆导入来源与结果不可覆盖')
        if isinstance(row,VehicleImportBatch):
            frozen=('case_id','kind','source_file_id','source_digest','source_reference','source_case_version','replacement_batch_id','prepared_by','row_count','amount_cents','errors')
            if row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in frozen):raise HTTPException(409,'批次来源已冻结，请取消未执行批次并关联替代资料')

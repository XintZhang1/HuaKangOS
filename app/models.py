"""All monetary values are integer CNY fen. No floating point is persisted."""
from datetime import date, datetime
from sqlalchemy import String, Text, Integer, BigInteger, Boolean, Date, DateTime, ForeignKey, JSON, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, declared_attr
from .db import Base, utcnow


class AppMetadata(Base):
    __tablename__ = 'app_metadata'
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class Store(Base):
    __tablename__ = 'stores'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StoreScoped:
    # Ownership is immutable. The migration validates existing rows before applying.
    store_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)


class UserStore(Base):
    __tablename__ = 'user_stores'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), primary_key=True)
    # NULL is an explicit compatibility mode for existing global-role accounts.
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    __table_args__ = (CheckConstraint("role IS NULL OR role IN ('manager','sales','inventory','service','finance','auditor','reception','technician','customer_service')", name='ck_user_store_role'),)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))
    can_group_summary: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
    access_version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint("role IN ('admin','manager','sales','inventory','service','finance','auditor','reception','technician','customer_service')", name='ck_user_role'), CheckConstraint('access_version >= 1', name='ck_user_access_version'))


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA256, never plaintext
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), index=True)
    ip: Mapped[str] = mapped_column(String(100), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class DocumentMixin(StoreScoped):
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_no: Mapped[str] = mapped_column(String(60))
    business_date: Mapped[date] = mapped_column(Date, index=True)
    approval_state: Mapped[str] = mapped_column(String(15), default='draft', index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    note: Mapped[str] = mapped_column(Text, default='')
    @declared_attr.directive
    def __mapper_args__(cls):
        return {'version_id_col': cls.version}


class Vehicle(DocumentMixin, Base):
    __tablename__ = 'vehicles'
    vin: Mapped[str] = mapped_column(String(17))
    # Each physical receipt has its own immutable store owner. Generation 0
    # preserves the original global VIN uniqueness for legacy creation paths.
    inventory_generation: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    brand: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    color: Mapped[str] = mapped_column(String(40), default='')
    supplier: Mapped[str] = mapped_column(String(120), default='')
    location: Mapped[str] = mapped_column(String(120), default='')
    purchase_cost_cents: Mapped[int] = mapped_column(BigInteger)
    list_price_cents: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (
        UniqueConstraint('vin', 'inventory_generation', name='uq_vehicle_vin_generation'),
        CheckConstraint('inventory_generation >= 0', name='ck_vehicle_generation'),
        UniqueConstraint('store_id', 'doc_no', name='uq_vehicle_store_doc'),
        CheckConstraint('purchase_cost_cents >= 0 AND list_price_cents >= 0', name='ck_vehicle_money'),
        CheckConstraint("approval_state IN ('draft','submitted','approved','rejected','void')", name='ck_vehicle_approval'),
    )


class Sale(DocumentMixin, Base):
    __tablename__ = 'sales'
    vehicle_id: Mapped[int] = mapped_column(ForeignKey('vehicles.id'), index=True)
    # Only an APPROVED sale occupies a car. Database UNIQUE prevents concurrent double allocation.
    active_vehicle_id: Mapped[int | None] = mapped_column(ForeignKey('vehicles.id'), unique=True, nullable=True)
    customer_name: Mapped[str] = mapped_column(String(100))
    customer_phone: Mapped[str] = mapped_column(String(30), default='')
    salesperson: Mapped[str] = mapped_column(String(80))
    sale_stage: Mapped[str] = mapped_column(String(15), default='ordered')
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    contract_amount_cents: Mapped[int] = mapped_column(BigInteger)
    purchase_cost_snapshot_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    __table_args__ = (
        UniqueConstraint('store_id', 'doc_no', name='uq_sale_store_doc'),
        CheckConstraint('contract_amount_cents > 0', name='ck_sale_money'),
        CheckConstraint("sale_stage IN ('ordered','delivered')", name='ck_sale_stage'),
        CheckConstraint("approval_state IN ('draft','submitted','approved','rejected','void')", name='ck_sale_approval'),
        CheckConstraint("(approval_state = 'approved' AND active_vehicle_id IS NOT NULL AND active_vehicle_id = vehicle_id) OR (approval_state != 'approved' AND active_vehicle_id IS NULL)", name='ck_sale_allocation'),
        CheckConstraint("(sale_stage = 'ordered' AND delivery_date IS NULL) OR (sale_stage = 'delivered' AND delivery_date IS NOT NULL AND delivery_date >= business_date)", name='ck_sale_delivery'),
    )


class Repair(DocumentMixin, Base):
    __tablename__ = 'repairs'
    plate_number: Mapped[str] = mapped_column(String(30))
    customer_name: Mapped[str] = mapped_column(String(100))
    customer_phone: Mapped[str] = mapped_column(String(30), default='')
    service_advisor: Mapped[str] = mapped_column(String(80))
    repair_type: Mapped[str] = mapped_column(String(20), default='maintenance')
    repair_stage: Mapped[str] = mapped_column(String(20), default='open')
    policy_id: Mapped[int | None] = mapped_column(ForeignKey('policies.id'), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    labor_amount_cents: Mapped[int] = mapped_column(BigInteger)
    parts_amount_cents: Mapped[int] = mapped_column(BigInteger)
    discount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (
        UniqueConstraint('store_id', 'doc_no', name='uq_repair_store_doc'),
        CheckConstraint('labor_amount_cents >= 0 AND parts_amount_cents >= 0 AND discount_cents >= 0 AND cost_amount_cents >= 0 AND discount_cents <= labor_amount_cents + parts_amount_cents', name='ck_repair_money'),
        CheckConstraint("repair_stage IN ('open','completed')", name='ck_repair_stage'),
        CheckConstraint("approval_state IN ('draft','submitted','approved','rejected','void')", name='ck_repair_approval'),
        CheckConstraint("(repair_stage = 'open' AND completion_date IS NULL) OR (repair_stage = 'completed' AND completion_date IS NOT NULL AND completion_date >= business_date)", name='ck_repair_completion'),
    )


class Policy(DocumentMixin, Base):
    __tablename__ = 'policies'
    policy_number: Mapped[str] = mapped_column(String(80), unique=True)
    insurer: Mapped[str] = mapped_column(String(100))
    plate_number: Mapped[str] = mapped_column(String(30))
    customer_name: Mapped[str] = mapped_column(String(100))
    customer_phone: Mapped[str] = mapped_column(String(30), default='')
    policy_type: Mapped[str] = mapped_column(String(20), default='commercial')
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    premium_cents: Mapped[int] = mapped_column(BigInteger)
    commission_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (
        UniqueConstraint('store_id', 'doc_no', name='uq_policy_store_doc'),
        CheckConstraint('premium_cents > 0 AND commission_cents >= 0 AND end_date >= start_date', name='ck_policy_values'),
        CheckConstraint("approval_state IN ('draft','submitted','approved','rejected','void')", name='ck_policy_approval'),
    )


class CashEntry(DocumentMixin, Base):
    __tablename__ = 'cash_entries'
    direction: Mapped[str] = mapped_column(String(5))
    category: Mapped[str] = mapped_column(String(30))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    account: Mapped[str] = mapped_column(String(100))
    counter_account: Mapped[str] = mapped_column(String(100), default='')
    counterparty: Mapped[str] = mapped_column(String(120), default='')
    payment_method: Mapped[str] = mapped_column(String(20), default='bank')
    voucher_no: Mapped[str] = mapped_column(String(100))
    sale_id: Mapped[int | None] = mapped_column(ForeignKey('sales.id'), nullable=True, index=True)
    repair_id: Mapped[int | None] = mapped_column(ForeignKey('repairs.id'), nullable=True, index=True)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey('policies.id'), nullable=True, index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey('vehicles.id'), nullable=True, index=True)
    __table_args__ = (
        UniqueConstraint('store_id', 'doc_no', name='uq_cash_store_doc'),
        CheckConstraint('amount_cents > 0', name='ck_cash_money'),
        CheckConstraint("direction IN ('in','out')", name='ck_cash_direction'),
        CheckConstraint("approval_state IN ('draft','submitted','approved','rejected','void')", name='ck_cash_approval'),
        CheckConstraint('(CASE WHEN sale_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN repair_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN policy_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN vehicle_id IS NOT NULL THEN 1 ELSE 0 END) <= 1', name='ck_cash_one_link'),
    )


class AuditLog(StoreScoped, Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(30), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    reason: Mapped[str] = mapped_column(Text, default='')
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Finding(StoreScoped, Base):
    __tablename__ = 'findings'
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    rule_code: Mapped[str] = mapped_column(String(60), index=True)
    severity: Mapped[str] = mapped_column(String(10))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    evidence: Mapped[dict] = mapped_column(JSON)
    suggested_action: Mapped[str] = mapped_column(Text)
    first_seen: Mapped[date] = mapped_column(Date)
    last_seen: Mapped[date] = mapped_column(Date)
    review_status: Mapped[str] = mapped_column(String(20), default='open')
    review_note: Mapped[str] = mapped_column(Text, default='')
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {'version_id_col': version}


class DailyReport(StoreScoped, Base):
    __tablename__ = 'daily_reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    source_revision: Mapped[int] = mapped_column(Integer)
    config_hash: Mapped[str] = mapped_column(String(64))
    ai_requested: Mapped[bool] = mapped_column(Boolean)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    snapshot: Mapped[dict] = mapped_column(JSON)
    deterministic_summary: Mapped[str] = mapped_column(Text)
    finding_ids: Mapped[list] = mapped_column(JSON)
    ai_status: Mapped[str] = mapped_column(String(30))
    ai_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_error: Mapped[str] = mapped_column(String(250), default='')
    model: Mapped[str] = mapped_column(String(100), default='')
    __table_args__ = (UniqueConstraint('store_id', 'business_date', 'source_revision', 'config_hash', 'ai_requested', name='uq_report_input'),)


class JobLease(Base):
    __tablename__ = 'job_leases'
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


MODULES = {'vehicles': Vehicle, 'sales': Sale, 'repairs': Repair, 'policies': Policy, 'cash': CashEntry}


class Feedback(StoreScoped, Base):
    __tablename__ = 'feedback'
    id: Mapped[int] = mapped_column(primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default='improvement')
    status: Mapped[str] = mapped_column(String(30), default='new', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    base_sha: Mapped[str] = mapped_column(String(40), default='')
    head_sha: Mapped[str] = mapped_column(String(40), default='')
    branch: Mapped[str] = mapped_column(String(120), default='')
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    test_result: Mapped[dict] = mapped_column(JSON, default=dict)
    review_url: Mapped[str] = mapped_column(String(500), default='')
    approval_token_hash: Mapped[str] = mapped_column(String(64), default='')
    approval_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str] = mapped_column(String(100), default='')
    approved_sha: Mapped[str] = mapped_column(String(40), default='')
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str] = mapped_column(String(500), default='')
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {'version_id_col': version}


class MaintenanceEvent(Base):
    __tablename__ = 'maintenance_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    feedback_id: Mapped[int] = mapped_column(ForeignKey('feedback.id'), index=True)
    action: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text, default='')
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Deployment(Base):
    __tablename__ = 'deployments'
    id: Mapped[int] = mapped_column(primary_key=True)
    feedback_id: Mapped[int] = mapped_column(ForeignKey('feedback.id'), unique=True)
    sha: Mapped[str] = mapped_column(String(40))
    previous_sha: Mapped[str] = mapped_column(String(40))
    previous_path: Mapped[str] = mapped_column(Text)
    release_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='pending')
    backup_path: Mapped[str] = mapped_column(Text, default='')
    error: Mapped[str] = mapped_column(String(500), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BotReceipt(Base):
    __tablename__ = 'bot_receipts'
    event_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

# Register the independently versioned workflow tables.
from . import flow_models  # noqa: E402,F401
from . import vehicle_transfer_models  # noqa: E402,F401
from . import vehicle_procurement_models  # noqa: E402,F401
from . import reconciliation_models  # noqa: E402,F401
from . import retail_models  # noqa: E402,F401
from . import repair_models  # noqa: E402,F401
from . import customer_service_models  # noqa: E402,F401
from . import group_benefits_models  # noqa: E402,F401
from . import group_models  # noqa: E402,F401
from . import transfer_models  # noqa: E402,F401
from . import transfer_exception_models  # noqa: E402,F401
from . import file_security_models  # noqa: E402,F401
from . import master_models  # noqa: E402,F401
from . import procurement_models  # noqa: E402,F401
from . import invoice_models  # noqa: E402,F401
from . import warehouse_models  # noqa: E402,F401
from . import membership_models  # noqa: E402,F401
from . import membership_fee_correction_models  # noqa: E402,F401
from . import service_intake_models  # noqa: E402,F401
from . import aftercare_models  # noqa: E402,F401
from . import group_aftercare_models  # noqa: E402,F401
from . import vehicle_operations_models  # noqa: E402,F401
from . import business_finance_models  # noqa: E402,F401
from . import private_file_models  # noqa: E402,F401
from . import opening_import_models  # noqa: E402,F401
from . import recharge_bundle_models  # noqa: E402,F401
from . import claims_models  # noqa: E402,F401
from . import vehicle_imports_models  # noqa: E402,F401
from . import retail_bundle_models  # noqa: E402,F401

from . import vehicle_catalog_models  # explicit model hierarchy, no text inference

from . import service_orders_models  # noqa: E402,F401

from . import sales_quote_models  # noqa: E402,F401

from . import procurement_cost_models  # noqa: E402,F401

from . import addon_models  # noqa: E402,F401
from . import user_access_models as _user_access_models

from . import insurance_models  # register immutable insurance facts
from . import business_entity_models  # approved legal identities and source attribution

from . import retail_group_models, observation_corrections_models, transfer_goods_recovery_models  # n46a explicit domain registration

from . import transfer_goods_search_models  # o57b append-only original return-transit tracing

from . import questionnaire_models  # p68c immutable issued questionnaire versions
from . import gate_visit_models  # noqa: E402,F401

from .vehicle_transport_models import *  # noqa: F401,F403

from . import dossier_grant_models  # explicit read-only original-record/file grants
from . import vehicle_income_models  # original supplier vehicle income, separate from customer receipts
from . import rework_extension_models  # explicit original responsibility grants and local quote classification
from . import member_pricing_models  # independently approved local membership price provenance
from . import repair_package_models  # explicit prepaid work/material components and original-source returns

from . import business_assistant_models  # owner/store-scoped confirmed business assistant

"""Frozen store-owned vehicle procurement, receipts, funds and original reversals."""
from alembic import op
import sqlalchemy as sa
revision='o915_vehicle_procurement'
down_revision='n814_vehicle_transfer'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('vehicle_purchase_lines',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('model_id',sa.Integer(),sa.ForeignKey('master_vehicle_models.id'),nullable=False),
        sa.Column('model_code',sa.String(length=40),nullable=False),
        sa.Column('model_name',sa.String(length=120),nullable=False),
        sa.Column('brand',sa.String(length=80),nullable=False),
        sa.Column('model_year',sa.Integer(),nullable=False),
        sa.Column('fuel_type',sa.String(length=20),nullable=False),
        sa.Column('color',sa.String(length=40),nullable=False),
        sa.Column('quantity',sa.Integer(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint('quantity BETWEEN 1 AND 1000',name='ck_vpurchase_line_qty'),
        sa.UniqueConstraint('case_id','model_id','color',name='uq_vpurchase_model_color'))
    op.create_index('ix_vehicle_purchase_lines_case_id','vehicle_purchase_lines',['case_id'],unique=False)
    op.create_index('ix_vehicle_purchase_lines_store_id','vehicle_purchase_lines',['store_id'],unique=False)
    op.create_table('vehicle_purchase_orders',
        sa.Column('id',sa.Integer(),sa.ForeignKey('flow_cases.id'),primary_key=True,nullable=False),
        sa.Column('supplier_id',sa.Integer(),sa.ForeignKey('master_suppliers.id'),nullable=False),
        sa.Column('supplier_name',sa.String(length=120),nullable=False),
        sa.Column('supplier_code',sa.String(length=40),nullable=False),
        sa.Column('payment_terms_days',sa.Integer(),nullable=False),
        sa.Column('contracting_party',sa.String(length=180),nullable=False),
        sa.Column('reason',sa.String(length=500),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False))
    op.create_index('ix_vehicle_purchase_orders_store_id','vehicle_purchase_orders',['store_id'],unique=False)
    op.create_table('vehicle_purchase_cancellations',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('line_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_lines.id'),nullable=False),
        sa.Column('quantity',sa.Integer(),nullable=False),
        sa.Column('reason',sa.String(length=500),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('line_id',name=None),
        sa.CheckConstraint('quantity > 0',name='ck_vpurchase_cancel_qty'))
    op.create_index('ix_vehicle_purchase_cancellations_case_id','vehicle_purchase_cancellations',['case_id'],unique=False)
    op.create_index('ix_vehicle_purchase_cancellations_store_id','vehicle_purchase_cancellations',['store_id'],unique=False)
    op.create_table('vehicle_purchase_funds_requests',
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('status',sa.String(length=20),nullable=False),
        sa.Column('reason',sa.String(length=500),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('requested_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint("amount_cents > 0 AND status IN ('open','closed','cancelled')",name='ck_vpurchase_funds'))
    op.create_index('ix_vehicle_purchase_funds_requests_case_id','vehicle_purchase_funds_requests',['case_id'],unique=False)
    op.create_index('ix_vehicle_purchase_funds_requests_store_id','vehicle_purchase_funds_requests',['store_id'],unique=False)
    op.create_table('vehicle_purchase_prices',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('line_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_lines.id'),nullable=False),
        sa.Column('unit_cost_cents',sa.BigInteger(),nullable=False),
        sa.Column('list_price_cents',sa.BigInteger(),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('approved_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('line_id',name=None),
        sa.CheckConstraint('unit_cost_cents > 0 AND list_price_cents >= 0',name='ck_vpurchase_price'))
    op.create_index('ix_vehicle_purchase_prices_case_id','vehicle_purchase_prices',['case_id'],unique=False)
    op.create_index('ix_vehicle_purchase_prices_store_id','vehicle_purchase_prices',['store_id'],unique=False)
    op.create_table('vehicle_purchase_shipments',
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('line_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_lines.id'),nullable=False),
        sa.Column('vin',sa.String(length=17),nullable=False),
        sa.Column('active_vin',sa.String(length=17),nullable=True),
        sa.Column('status',sa.String(length=20),nullable=False),
        sa.Column('shipped_date',sa.Date(),nullable=False),
        sa.Column('expected_date',sa.Date(),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('active_vin',name=None),
        sa.CheckConstraint("status IN ('transit','received','returned')",name='ck_vpurchase_shipment_state'),
        sa.CheckConstraint("(status='transit' AND active_vin=vin) OR (status!='transit' AND active_vin IS NULL)",name='ck_vpurchase_vin_claim'))
    op.create_index('ix_vehicle_purchase_shipments_case_id','vehicle_purchase_shipments',['case_id'],unique=False)
    op.create_index('ix_vehicle_purchase_shipments_store_id','vehicle_purchase_shipments',['store_id'],unique=False)
    op.create_index('ix_vehicle_purchase_shipments_vin','vehicle_purchase_shipments',['vin'],unique=False)
    op.create_table('vehicle_purchase_payments',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('funds_request_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_funds_requests.id'),nullable=True),
        sa.Column('cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('flow_accounts.id'),nullable=False),
        sa.Column('original_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_payments.id'),nullable=True),
        sa.Column('direction',sa.String(length=3),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('reference',sa.String(length=100),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('cash_id',name=None),
        sa.CheckConstraint("amount_cents > 0 AND ((direction='out' AND original_id IS NULL AND funds_request_id IS NOT NULL) OR (direction='in' AND original_id IS NOT NULL AND funds_request_id IS NULL))",name='ck_vpurchase_payment'),
        sa.UniqueConstraint('store_id','account_id','reference',name='uq_vpurchase_cash_reference'))
    op.create_index('ix_vehicle_purchase_payments_case_id','vehicle_purchase_payments',['case_id'],unique=False)
    op.create_index('ix_vehicle_purchase_payments_store_id','vehicle_purchase_payments',['store_id'],unique=False)
    op.create_table('vehicle_purchase_receipts',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('shipment_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_shipments.id'),nullable=False),
        sa.Column('vehicle_id',sa.Integer(),sa.ForeignKey('vehicles.id'),nullable=False),
        sa.Column('location_id',sa.Integer(),sa.ForeignKey('master_locations.id'),nullable=False),
        sa.Column('value_cents',sa.BigInteger(),nullable=False),
        sa.Column('due_date',sa.Date(),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('business_date',sa.Date(),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('vehicle_id',name=None),
        sa.UniqueConstraint('shipment_id',name=None),
        sa.CheckConstraint('value_cents > 0',name='ck_vpurchase_receipt_value'))
    op.create_index('ix_vehicle_purchase_receipts_case_id','vehicle_purchase_receipts',['case_id'],unique=False)
    op.create_index('ix_vehicle_purchase_receipts_store_id','vehicle_purchase_receipts',['store_id'],unique=False)
    op.create_table('vehicle_purchase_returns',
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('shipment_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_shipments.id'),nullable=False),
        sa.Column('active_shipment_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_shipments.id'),nullable=True),
        sa.Column('status',sa.String(length=20),nullable=False),
        sa.Column('reason',sa.String(length=500),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('requested_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('approved_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=True),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('active_shipment_id',name=None),
        sa.CheckConstraint("status NOT IN ('approved','dispatched') OR approved_by IS NOT NULL",name='ck_vpurchase_return_approval'),
        sa.CheckConstraint("status IN ('requested','approved','dispatched','cancelled')",name='ck_vpurchase_return_state'))
    op.create_index('ix_vehicle_purchase_returns_case_id','vehicle_purchase_returns',['case_id'],unique=False)
    op.create_index('ix_vehicle_purchase_returns_store_id','vehicle_purchase_returns',['store_id'],unique=False)
    op.create_table('vehicle_purchase_movements',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('shipment_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_shipments.id'),nullable=False),
        sa.Column('vehicle_id',sa.Integer(),sa.ForeignKey('vehicles.id'),nullable=True),
        sa.Column('return_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_returns.id'),nullable=True),
        sa.Column('original_id',sa.Integer(),sa.ForeignKey('vehicle_purchase_movements.id'),nullable=True),
        sa.Column('kind',sa.String(length=20),nullable=False),
        sa.Column('quantity',sa.Integer(),nullable=False),
        sa.Column('value_cents',sa.BigInteger(),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('business_date',sa.Date(),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('return_id',name=None),
        sa.CheckConstraint("(kind='receive' AND quantity=1 AND value_cents>0 AND vehicle_id IS NOT NULL) OR (kind='return' AND quantity=-1 AND value_cents<0 AND vehicle_id IS NOT NULL) OR (kind='transit_return' AND quantity=0 AND value_cents=0)",name='ck_vpurchase_movement_sign'),
        sa.UniqueConstraint('shipment_id','kind',name='uq_vpurchase_movement'))
    op.create_index('ix_vehicle_purchase_movements_case_id','vehicle_purchase_movements',['case_id'],unique=False)
    op.create_index('ix_vehicle_purchase_movements_shipment_id','vehicle_purchase_movements',['shipment_id'],unique=False)
    op.create_index('ix_vehicle_purchase_movements_store_id','vehicle_purchase_movements',['store_id'],unique=False)

def downgrade():
    raise RuntimeError('请从一致备份恢复；整车采购事实不可破坏性降级')

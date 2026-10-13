"""Append-only employee responsibility handovers, without changing old facts."""
from alembic import op
import sqlalchemy as sa

revision = 'h68z_employee_handover'
down_revision = 'h67y_user_archive'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('employee_handovers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('successor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('successor_role', sa.String(30), nullable=False),
        sa.Column('successor_access_version', sa.Integer(), nullable=False),
        sa.Column('receipt_id', sa.Integer(), sa.ForeignKey('user_access_receipts.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('receipt_id', 'store_id', name='uq_employee_handover_store'),
        sa.CheckConstraint('source_id != successor_id', name='ck_employee_handover_distinct'),
        sa.CheckConstraint('successor_access_version >= 1', name='ck_employee_handover_version'))
    for name in ('store_id', 'source_id', 'successor_id', 'receipt_id'):
        op.create_index('ix_employee_handovers_' + name, 'employee_handovers', [name])
    op.create_table('employee_handover_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('handover_id', sa.Integer(), sa.ForeignKey('employee_handovers.id'), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('business_record_customers.id'), nullable=True),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=True),
        sa.Column('can_continue', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('handover_id', 'customer_id', name='uq_employee_handover_customer'),
        sa.UniqueConstraint('handover_id', 'contract_id', name='uq_employee_handover_contract'),
        sa.CheckConstraint('(customer_id IS NULL) != (contract_id IS NULL)', name='ck_employee_handover_one_record'))
    for name in ('handover_id', 'customer_id', 'contract_id'):
        op.create_index('ix_employee_handover_records_' + name, 'employee_handover_records', [name])


def downgrade():
    raise RuntimeError('员工交接与历史责任必须保留，请使用已核对的备份恢复')

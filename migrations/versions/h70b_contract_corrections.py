"""Append contract corrections and reversible list archival; no old fact changes."""
from alembic import op
import sqlalchemy as sa

revision = 'h70b_contract_corrections'
down_revision = 'h69a_wholesale_catalog'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('business_record_contracts', sa.Column('archived_at', sa.DateTime(), nullable=True))
    op.add_column('business_record_contracts', sa.Column('archived_by', sa.Integer(), nullable=True))
    op.add_column('business_record_contracts', sa.Column('archive_reason', sa.Text(), nullable=True))
    op.create_table('business_record_contract_corrections',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False),
        sa.Column('previous_id', sa.Integer(), sa.ForeignKey('business_record_contract_corrections.id'), nullable=True),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('assigned_to', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('assigned_role', sa.String(30), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('previous_snapshot', sa.JSON(), nullable=False),
        sa.Column('draft', sa.JSON(), nullable=False),
        sa.Column('approved_snapshot', sa.JSON(none_as_null=True), nullable=True),
        *[sa.Column(name + '_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True)
          for name in ('submitted', 'manager_approved', 'general_manager_approved', 'deputy_approved')],
        *[sa.Column(name + '_at', sa.DateTime(), nullable=True)
          for name in ('submitted', 'manager_approved', 'general_manager_approved', 'deputy_approved')],
        sa.Column('approved_on', sa.Date(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('sale_delta_cents', sa.BigInteger(), nullable=False),
        sa.Column('cash_delta_cents', sa.BigInteger(), nullable=True),
        sa.Column('events', sa.JSON(), nullable=False),
        sa.CheckConstraint("status IN ('draft','submitted','manager_approved','deputy_pending','approved','cancelled')", name='ck_record_correction_status'),
        sa.CheckConstraint("assigned_role IN ('sales','manager')", name='ck_record_correction_assignee'),
        sa.CheckConstraint("status != 'approved' OR (approved_snapshot IS NOT NULL AND approved_at IS NOT NULL AND approved_on IS NOT NULL)", name='ck_record_correction_approved'))
    for name in ('store_id', 'contract_id', 'approved_on'):
        op.create_index('ix_business_record_contract_corrections_' + name, 'business_record_contract_corrections', [name])


def downgrade():
    raise RuntimeError('合同更正及历史依据不可删除，请使用已核对的恢复方案')

"""Append gift and maintenance redemption facts without altering contracts."""
from alembic import op
import sqlalchemy as sa

revision = 'h74f_record_benefit_redemptions'
down_revision = 'h73e_record_signed_documents'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('business_record_benefit_redemptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False),
        sa.Column('source_key', sa.String(80), nullable=False),
        sa.Column('source_snapshot', sa.JSON(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('reverses_id', sa.Integer(), sa.ForeignKey('business_record_benefit_redemptions.id'), nullable=True),
        sa.Column('redeemed_on', sa.Date(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('reverses_id', name='uq_record_benefit_reversal'),
        sa.CheckConstraint('(quantity = 1 AND reverses_id IS NULL) OR (quantity = -1 AND reverses_id IS NOT NULL)', name='ck_record_benefit_event'))
    op.create_index('ix_business_record_benefit_redemptions_store_id', 'business_record_benefit_redemptions', ['store_id'])
    op.create_index('ix_business_record_benefit_redemptions_contract_id', 'business_record_benefit_redemptions', ['contract_id'])


def downgrade():
    raise RuntimeError('兑换历史必须保留，请使用经核对的恢复方案')

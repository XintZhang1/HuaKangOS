"""Append clerk-confirmed daily reports; retain all historical business data."""
from alembic import op
import sqlalchemy as sa

revision = 'h59q_record_daily_reports'
down_revision = 'h58p_record_invoices'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('business_record_daily_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('report_key', sa.String(80), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('confirmed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('source_digest', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.UniqueConstraint('store_id', 'day', 'report_key', 'version', name='uq_record_daily_report_version'))
    op.create_index('ix_business_record_daily_reports_store_id', 'business_record_daily_reports', ['store_id'])
    op.create_index('ix_business_record_daily_reports_day', 'business_record_daily_reports', ['day'])
    op.create_index('ix_business_record_daily_reports_report_key', 'business_record_daily_reports', ['report_key'])


def downgrade():
    raise RuntimeError('Clerk-confirmed daily reports are retained; restore a verified backup instead')

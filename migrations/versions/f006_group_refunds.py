"""Group principal refund approval and reserved execution, frozen schema."""
from alembic import op
import sqlalchemy as sa

revision = 'f006_group_refunds'
down_revision = 'e905_group'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('group_refund_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('member_id', sa.Integer(), sa.ForeignKey('group_members.id'), nullable=False),
        sa.Column('original_id', sa.Integer(), sa.ForeignKey('group_entries.id'), nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('closed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('executed_entry_id', sa.Integer(), sa.ForeignKey('group_entries.id'), nullable=True, unique=True),
        sa.CheckConstraint("amount_cents > 0 AND status IN ('requested','approved','rejected','cancelled','executed')", name='ck_group_refund_status'),
        sa.CheckConstraint("status NOT IN ('approved','executed') OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)", name='ck_group_refund_approved'),
        sa.CheckConstraint("(status = 'executed' AND executed_entry_id IS NOT NULL AND closed_by IS NOT NULL) OR "
                           "(status != 'executed' AND executed_entry_id IS NULL)", name='ck_group_refund_executed'))
    for column in ('store_id', 'member_id', 'original_id', 'case_id'):
        op.create_index('ix_group_refund_requests_'+column, 'group_refund_requests', [column])


def downgrade():
    raise RuntimeError('集团退款审核与执行记录不可删除降级，请恢复经验证的一致备份')

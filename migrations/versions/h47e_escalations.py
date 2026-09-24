"""向相关上级提交评审：请求与处理轨迹两张表。只记录请求，不改变权限、不执行业务动作。"""
from alembic import op
import sqlalchemy as sa

revision = 'h47e_escalations'
down_revision = 'g35t_assistant_thinking'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'escalations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False, index=True),
        sa.Column('requester_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('requester_role', sa.String(30), nullable=False),
        sa.Column('target_role', sa.String(30), nullable=False),
        sa.Column('subject', sa.String(160), nullable=False),
        sa.Column('case_reference', sa.String(80), nullable=False, server_default=''),
        sa.Column('operation_id', sa.String(200), nullable=False, server_default=''),
        sa.Column('blocked_message', sa.Text(), nullable=False, server_default=''),
        sa.Column('reason_category', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('claimed_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
        sa.Column('decided_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decision_note', sa.Text(), nullable=False, server_default=''),
        sa.CheckConstraint("status in ('open','claimed','done','rejected','cancelled')",
                           name='ck_escalation_status'),
        sa.CheckConstraint("reason_category in ('authority','amount')", name='ck_escalation_category'),
        sa.CheckConstraint("target_role in ('manager','admin')", name='ck_escalation_target'),
    )
    op.create_index('ix_escalations_store_status', 'escalations', ['store_id', 'status'])
    op.create_table(
        'escalation_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False, index=True),
        sa.Column('escalation_id', sa.Integer(), sa.ForeignKey('escalations.id'), nullable=False, index=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False, index=True),
    )


def downgrade():
    raise RuntimeError('评审申请是已提交请求的处理痕迹，请通过核验备份恢复')

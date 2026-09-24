"""评审申请的依据：系统自己记下的被挡记录（escalation_refusals）。

评审只能引用真实发生过的拒绝，不能只凭申请人自述类别，否则业务规则冲突会被改写成
“岗位权限不足”。本迁移只新增一张表，不回改 h47e 及更早的迁移。
"""
from alembic import op
import sqlalchemy as sa

revision = 'h48f_escalation_refusals'
down_revision = 'h47e_escalations'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'escalation_refusals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('role', sa.String(30), nullable=False),
        sa.Column('method', sa.String(10), nullable=False),
        sa.Column('path', sa.String(240), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False, server_default=''),
        sa.Column('category', sa.String(20), nullable=False),
        sa.Column('source', sa.String(20), nullable=False, server_default='page'),
        sa.Column('created_at', sa.DateTime(), nullable=False, index=True),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.Column('consumed_by_id', sa.Integer(), sa.ForeignKey('escalations.id'), nullable=True),
        sa.CheckConstraint("category in ('authority','amount','rule')",
                           name='ck_escalation_refusal_category'),
        sa.CheckConstraint("source in ('page','assistant')", name='ck_escalation_refusal_source'),
    )
    op.create_index('ix_escalation_refusals_user', 'escalation_refusals',
                    ['user_id', 'store_id', 'consumed_at'])


def downgrade():
    raise RuntimeError('被挡记录是已提交评审的依据，请通过核验备份恢复')

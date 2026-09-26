"""卡片带"流程步骤"：business_assistant_proposals.step_order / step_label。

业主 2026-09-25 说明："连续批量确认"是指员工说一个中间流程（例如"章先生看完车要直接订车，
把流程补上再打印订单合同"）时，助手应当**在同一轮里把整条前序链按顺序准备成卡片组**，
员工挨个/分组确认，确认完直接进入下一轮生成订单合同——而不是一步一轮地中断对话。
页面上要按"第 1 步 / 第 2 步…"分组展示，所以步骤序号必须由服务端存下来。
本迁移只加两列并给旧行回填空值/0，不回改 h49g 及更早的迁移。
"""
from alembic import op
import sqlalchemy as sa

revision = 'h50h_proposal_step'
down_revision = 'h49g_proposal_turn'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('business_assistant_proposals') as batch:
        batch.add_column(sa.Column('step_order', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('step_label', sa.String(120), nullable=False, server_default=''))


def downgrade():
    raise RuntimeError('卡片分组是已确认界面的依据，请通过核验备份恢复')

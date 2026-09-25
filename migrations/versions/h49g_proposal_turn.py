"""待确认卡记录它属于哪一轮对话（business_assistant_proposals.request_id）。

业主 2026-09-25 试用反馈：一轮对话生成的几十张卡在页面上是"一张一张铺开"的，
既看不出它们属于同一轮，也没法翻页（他要的是 < 5/10 > 这种）。分组只能靠服务端
给出的事实，不能靠前端猜时间——所以把本轮的消息编号落到卡片上。
本迁移只加一列并回填旧行为空串，不回改 h48f 及更早的迁移。
"""
from alembic import op
import sqlalchemy as sa

revision = 'h49g_proposal_turn'
down_revision = 'h48f_escalation_refusals'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('business_assistant_proposals') as batch:
        batch.add_column(sa.Column('request_id', sa.String(100), nullable=False, server_default=''))


def downgrade():
    raise RuntimeError('卡片分组是已确认界面的依据，请通过核验备份恢复')

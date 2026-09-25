"""卡片上的必填项：business_assistant_proposals.questions。

业主 2026-09-25："需要员工回答的部分，你能不能在分组卡片的单张里把这些选项列为必填项，
只有确认过后才能继续点下一张。"——需要员工决定的事实（分派给谁、选哪台车、交车日期…）
不再靠聊天里问一句，而是作为这张卡的必填项由员工在卡片上填，填完才能确认。
本迁移只加一列（JSON，可为空），不回改 h50h 及更早的迁移。
"""
from alembic import op
import sqlalchemy as sa

revision = 'h51i_proposal_questions'
down_revision = 'h50h_proposal_step'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('business_assistant_proposals') as batch:
        batch.add_column(sa.Column('questions', sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError('卡片必填项是已确认界面的依据，请通过核验备份恢复')

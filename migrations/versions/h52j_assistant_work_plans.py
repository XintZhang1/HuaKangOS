"""Persist assistant work plans without changing any native business state."""
from alembic import op
import sqlalchemy as sa
revision='h52j_assistant_work_plans'
down_revision='h51i_proposal_questions'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('business_assistant_work_plans',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('store_id',sa.Integer(),sa.ForeignKey('stores.id'),nullable=False),
        sa.Column('session_id',sa.String(36),sa.ForeignKey('business_assistant_sessions.id'),nullable=False),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('request_id',sa.String(100),nullable=False),
        sa.Column('goal',sa.String(300),nullable=False),sa.Column('steps',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.UniqueConstraint('session_id','request_id',name='uq_assistant_work_plan_turn'))
    for col in ('store_id','session_id','owner_id'):
        op.create_index('ix_business_assistant_work_plans_'+col,'business_assistant_work_plans',[col])

def downgrade():
    raise RuntimeError('办事计划关联员工已确认的业务，请通过核验备份恢复，不直接删除记录')

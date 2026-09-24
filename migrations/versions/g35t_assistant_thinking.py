"""Bind the per-message thinking option to its durable request identity."""
from alembic import op
import sqlalchemy as sa

revision='g35t_assistant_thinking'
down_revision='f24s_business_assistant'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('business_assistant_messages',sa.Column('thinking',sa.Boolean(),nullable=False,server_default=sa.false()))


def downgrade():
    raise RuntimeError('思考开关属于已发送请求的核对记录，请通过核验备份恢复')

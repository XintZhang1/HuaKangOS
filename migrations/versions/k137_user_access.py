"""Account authorization CAS and immutable request receipts. Frozen schema."""
from alembic import op
import sqlalchemy as sa

revision = 'k137_user_access'
down_revision = 'j036_addon_lines'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('access_version', sa.Integer(),
        sa.CheckConstraint('access_version >= 1', name='ck_user_access_version'),
        nullable=False, server_default='1'))
    op.create_table('user_access_receipts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('target_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_key', sa.String(80), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.Column('request_data', sa.JSON(), nullable=False),
        sa.Column('previous_version', sa.Integer(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('audit_id', sa.Integer(), sa.ForeignKey('audit_logs.id'), nullable=False, unique=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('actor_id', 'request_key', name='uq_user_access_request'),
        sa.UniqueConstraint('target_id', 'previous_version', name='uq_user_access_target_version'),
        sa.CheckConstraint('previous_version >= 1', name='ck_user_access_previous'))
    op.create_index('ix_user_access_receipts_actor_id', 'user_access_receipts', ['actor_id'])
    op.create_index('ix_user_access_receipts_target_id', 'user_access_receipts', ['target_id'])


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text('SELECT COUNT(*) FROM user_access_receipts')) or bind.scalar(sa.text('SELECT COUNT(*) FROM users WHERE access_version > 1')):
        raise RuntimeError('账号授权版本已使用，不能丢弃审计回执直接降级')
    op.drop_table('user_access_receipts')
    op.drop_column('users', 'access_version')

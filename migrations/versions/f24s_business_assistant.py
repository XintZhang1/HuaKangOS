"""Private conversations, user-confirmed operation envelopes and issue reports."""
from alembic import op
import sqlalchemy as sa

revision = 'f24s_business_assistant'
down_revision = 'e13r_member_fee_corrections'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('business_assistant_sessions',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('owner_role', sa.String(20), nullable=False),sa.Column('access_version',sa.Integer(),nullable=False),
        sa.Column('recent_operation_ids',sa.JSON(),nullable=False),
        sa.Column('title', sa.String(100), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False), sa.Column('busy_token', sa.String(80)),
        sa.Column('busy_until', sa.DateTime()), sa.Column('version', sa.Integer(), nullable=False))
    op.create_table('business_assistant_messages',
        sa.Column('id', sa.Integer(), primary_key=True), sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('business_assistant_sessions.id'), nullable=False),
        sa.Column('request_id', sa.String(100), nullable=False), sa.Column('role', sa.String(12), nullable=False),
        sa.Column('content', sa.Text(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('session_id','request_id',name='uq_assistant_message_request'),
        sa.CheckConstraint("role IN ('user','assistant')",name='ck_assistant_message_role'))
    op.create_table('business_assistant_proposals',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('session_id',sa.String(36),sa.ForeignKey('business_assistant_sessions.id'),nullable=False),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('owner_role',sa.String(20),nullable=False),
        sa.Column('access_version',sa.Integer(),nullable=False),sa.Column('operation_id',sa.String(180),nullable=False),
        sa.Column('label',sa.String(160),nullable=False),sa.Column('summary',sa.String(600),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),sa.Column('digest',sa.String(64),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('idempotent',sa.Boolean(),nullable=False),
        sa.Column('result',sa.JSON()),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('expires_at',sa.DateTime(),nullable=False),
        sa.Column('started_at',sa.DateTime()),sa.Column('finished_at',sa.DateTime()),sa.Column('version',sa.Integer(),nullable=False),
        sa.CheckConstraint("status IN ('pending','executing','succeeded','failed','uncertain','cancelled','expired')",name='ck_assistant_proposal_status'))
    op.create_table('business_assistant_issues',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('session_id',sa.String(36),sa.ForeignKey('business_assistant_sessions.id'),nullable=False),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('category',sa.String(20),nullable=False),
        sa.Column('summary',sa.String(1200),nullable=False),sa.Column('operation_id',sa.String(180),nullable=False),
        sa.Column('status_code',sa.Integer()),sa.Column('synthetic',sa.Boolean(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint("category IN ('input','rule','system','model','unsupported')",name='ck_assistant_issue_category'))
    for table, columns in {
        'business_assistant_sessions':['store_id','owner_id'],
        'business_assistant_messages':['store_id','session_id'],
        'business_assistant_proposals':['store_id','session_id'],
        'business_assistant_issues':['store_id','session_id','owner_id'],
    }.items():
        for column in columns: op.create_index(f'ix_{table}_{column}',table,[column])


def downgrade():
    raise RuntimeError('问答、操作确认及问题记录不可自动删除，请从核验备份恢复')

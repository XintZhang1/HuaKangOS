"""Attachment quarantine and immutable scan history, frozen schema."""
from alembic import op
import sqlalchemy as sa

revision = 'g107_file_security'
down_revision = 'f006_group_refunds'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('file_scan_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('request_key', sa.String(80), nullable=True),
        sa.Column('request_digest', sa.String(64), nullable=True),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('engine', sa.String(30), nullable=False),
        sa.Column('engine_version', sa.String(200), nullable=False),
        sa.Column('code', sa.String(40), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('store_id', 'request_key', name='uq_file_scan_request'),
        sa.CheckConstraint("state IN ('quarantined','clean','structure_only','infected','error','rejected')", name='ck_file_scan_state'),
        sa.CheckConstraint("action IN ('initial','rescan') AND size >= 0", name='ck_file_scan_action'))
    op.create_index('ix_file_scan_events_store_id', 'file_scan_events', ['store_id'])
    op.create_index('ix_file_scan_events_file_id', 'file_scan_events', ['file_id'])
    op.create_table('file_security',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('file_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False, unique=True),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('last_scan_id', sa.Integer(), sa.ForeignKey('file_scan_events.id'), nullable=True),
        sa.CheckConstraint("state IN ('quarantined','clean','structure_only','infected','error','rejected')", name='ck_file_security_state'))
    op.create_index('ix_file_security_store_id', 'file_security', ['store_id'])
    # Historical files deliberately have no status row: reads interpret them as
    # unscanned and blocked until a real authorized scan is recorded.


def downgrade():
    raise RuntimeError('附件扫描审计不可删除降级，请恢复经验证的一致备份')

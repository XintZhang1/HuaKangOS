"""Recoverable staff archival; keep accounts, memberships and business history."""
from alembic import op
import sqlalchemy as sa

revision = 'h67y_user_archive'
down_revision = 'h66x_vehicle_gift_policy'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('archived_at', sa.DateTime(), nullable=True))


def downgrade():
    raise RuntimeError('员工删除和恢复历史须保留，请恢复经过核对的备份')

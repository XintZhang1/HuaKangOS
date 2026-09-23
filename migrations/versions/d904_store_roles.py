"""Store-specific employee roles and explicit aggregate reporting grants.

Frozen migration; account roles and existing business records are unchanged.
"""
from alembic import op
import sqlalchemy as sa

revision = 'd904_store_roles'
down_revision = 'c803_workflow'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('can_group_summary', sa.Boolean(), nullable=False, server_default=sa.false()))
    # Preserve existing read access, without granting summaries to operational roles.
    op.execute(sa.text("UPDATE users SET can_group_summary = TRUE WHERE role IN ('admin','manager','finance','auditor')"))
    with op.batch_alter_table('user_stores') as batch:
        batch.add_column(sa.Column('role', sa.String(20), nullable=True))
        batch.create_check_constraint('ck_user_store_role', "role IS NULL OR role IN ('manager','sales','inventory','service','finance','auditor','reception','technician','customer_service')")


def downgrade():
    # Silent downgrade would turn explicit local roles back into broader global roles.
    bind = op.get_bind()
    if bind.scalar(sa.text('SELECT COUNT(*) FROM user_stores WHERE role IS NOT NULL')):
        raise RuntimeError('门店岗位已启用；必须先审阅并处理权限映射，不能直接降级')
    with op.batch_alter_table('user_stores') as batch:
        batch.drop_constraint('ck_user_store_role', type_='check')
        batch.drop_column('role')
    op.drop_column('users', 'can_group_summary')

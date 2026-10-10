"""Add an independent store administrator; never reassign an existing account."""
from alembic import op

revision = 'h61s_store_administration'
down_revision = 'h60r_record_deputy_approval'
branch_labels = None
depends_on = None


def upgrade():
    roles = "'manager','sales','inventory','service','finance','auditor','reception','technician','customer_service','clerk','general_manager','chairman','group_deputy_manager','store_admin'"
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint('ck_user_role', type_='check')
        batch.create_check_constraint('ck_user_role', "role IN ('admin'," + roles + ')')
        batch.create_check_constraint('ck_store_admin_no_summary', "role != 'store_admin' OR NOT can_group_summary")
    with op.batch_alter_table('user_stores') as batch:
        batch.drop_constraint('ck_user_store_role', type_='check')
        batch.create_check_constraint('ck_user_store_role', 'role IS NULL OR role IN (' + roles + ')')


def downgrade():
    raise RuntimeError('Account authorization history is retained; restore a verified backup instead')

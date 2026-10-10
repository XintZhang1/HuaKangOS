"""Append explicit deputy approval for new contracts; historical workflows stay intact."""
from alembic import op
import sqlalchemy as sa

revision = 'h60r_record_deputy_approval'
down_revision = 'h59q_record_daily_reports'
branch_labels = None
depends_on = None


def upgrade():
    roles = "'manager','sales','inventory','service','finance','auditor','reception','technician','customer_service','clerk','general_manager','chairman','group_deputy_manager'"
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint('ck_user_role', type_='check')
        batch.create_check_constraint('ck_user_role', "role IN ('admin'," + roles + ')')
    with op.batch_alter_table('user_stores') as batch:
        batch.drop_constraint('ck_user_store_role', type_='check')
        batch.create_check_constraint('ck_user_store_role', 'role IS NULL OR role IN (' + roles + ')')
    with op.batch_alter_table('business_record_contracts') as batch:
        batch.add_column(sa.Column('approval_limits', sa.JSON(none_as_null=True), nullable=True))
        batch.add_column(sa.Column('general_manager_approved_by', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('general_manager_approved_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('general_manager_approval_note', sa.Text(), nullable=False, server_default=''))
        batch.add_column(sa.Column('deputy_approved_by', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('deputy_approved_at', sa.DateTime(), nullable=True))
        for field in ('general_manager_approved_by', 'deputy_approved_by'):
            batch.create_foreign_key('fk_record_contract_' + field, 'users', [field], ['id'])
        for field in ('status', 'workflow', 'priced'):
            batch.drop_constraint('ck_record_contract_' + field, type_='check')
        batch.create_check_constraint('ck_record_contract_status', "status IN ('submitted','manager_approved','deputy_pending','priced','approved','rejected')")
        batch.create_check_constraint('ck_record_contract_workflow', "workflow_version IN ('legacy-v2','trial-v29','trial-v30')")
        batch.create_check_constraint('ck_record_contract_priced', "workflow_version IN ('trial-v29','trial-v30') OR status NOT IN ('priced','approved') OR (expected_amount_cents IS NOT NULL AND cost_cents IS NOT NULL AND profit_cents IS NOT NULL AND gift_cost_cents IS NOT NULL AND priced_by IS NOT NULL)")
        batch.create_check_constraint('ck_record_contract_limits', "workflow_version != 'trial-v30' OR status NOT IN ('manager_approved','deputy_pending','approved') OR (manager_approved_by IS NOT NULL AND approval_limits IS NOT NULL)")
        batch.create_check_constraint('ck_record_contract_deputy', "status != 'deputy_pending' OR (workflow_version = 'trial-v30' AND general_manager_approved_by IS NOT NULL)")
        batch.create_check_constraint('ck_record_contract_general', "workflow_version != 'trial-v30' OR status != 'approved' OR general_manager_approved_by IS NOT NULL")


def downgrade():
    raise RuntimeError('Deputy approval history is retained; restore a verified backup instead')

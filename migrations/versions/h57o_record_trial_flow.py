"""Append trial contract and office approvals, retaining all historical facts."""
from alembic import op
import sqlalchemy as sa

revision = 'h57o_record_trial_flow'
down_revision = 'h56n_record_report_sources'
branch_labels = None
depends_on = None


def upgrade():
    table = 'business_record_contracts'
    with op.batch_alter_table(table) as batch:
        batch.add_column(sa.Column('workflow_version', sa.String(20), nullable=False, server_default='legacy-v2'))
        batch.add_column(sa.Column('manager_approved_by', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('manager_approved_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('manager_approval_note', sa.Text(), nullable=False, server_default=''))
        batch.add_column(sa.Column('office_status', sa.String(20), nullable=False, server_default='not_started'))
        batch.add_column(sa.Column('office_revision', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('office_data', sa.JSON(none_as_null=True), nullable=True))
        batch.add_column(sa.Column('office_approved_data', sa.JSON(none_as_null=True), nullable=True))
        batch.add_column(sa.Column('office_submitted_by', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('office_submitted_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('office_approved_by', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('office_approved_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('office_approval_note', sa.Text(), nullable=False, server_default=''))
        for field in ('manager_approved_by', 'office_submitted_by', 'office_approved_by'):
            batch.create_foreign_key('fk_record_contract_' + field, 'users', [field], ['id'])
        batch.drop_constraint('ck_record_contract_status', type_='check')
        batch.drop_constraint('ck_record_contract_priced', type_='check')
        batch.create_check_constraint('ck_record_contract_status', "status IN ('submitted','manager_approved','priced','approved','rejected')")
        batch.create_check_constraint('ck_record_contract_workflow', "workflow_version IN ('legacy-v2','trial-v29')")
        batch.create_check_constraint('ck_record_contract_office', "office_status IN ('not_started','draft','submitted','approved','rejected')")
        batch.create_check_constraint('ck_record_contract_priced', "workflow_version = 'trial-v29' OR status NOT IN ('priced','approved') OR (expected_amount_cents IS NOT NULL AND cost_cents IS NOT NULL AND profit_cents IS NOT NULL AND gift_cost_cents IS NOT NULL AND priced_by IS NOT NULL)")
    op.create_table('business_record_standard_prices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('sale_price_cents', sa.BigInteger(), nullable=True),
        sa.Column('cost_cents', sa.BigInteger(), nullable=True),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('store_id', 'name', name='uq_record_price_name'),
        sa.CheckConstraint('sale_price_cents IS NULL OR sale_price_cents >= 0', name='ck_record_standard_sale'),
        sa.CheckConstraint('cost_cents IS NULL OR cost_cents >= 0', name='ck_record_standard_cost'))
    op.create_index('ix_business_record_standard_prices_store_id', 'business_record_standard_prices', ['store_id'])


def downgrade():
    raise RuntimeError('Trial approval history is retained; restore a verified backup instead')

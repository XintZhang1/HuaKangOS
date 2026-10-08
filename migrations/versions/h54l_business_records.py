"""Append independent customer V2 records and explicit V2 staff roles.

No legacy business row is changed. Fixed schema definitions intentionally do not
import the application models, so historical upgrades remain reproducible.
"""
from alembic import op
import sqlalchemy as sa

revision = 'h54l_business_records'
down_revision = 'h53k_assistant_runtime'
branch_labels = None
depends_on = None


def _columns(versioned=True):
    columns = [sa.Column('id', sa.Integer(), primary_key=True),
               sa.Column('store_id', sa.Integer(), nullable=False),
               sa.Column('created_at', sa.DateTime(), nullable=False)]
    if versioned:
        columns += [sa.Column('version', sa.Integer(), nullable=False),
                    sa.Column('updated_at', sa.DateTime(), nullable=False)]
    return columns


def _index(table, fields):
    for field in ('store_id', *fields):
        op.create_index('ix_' + table + '_' + field, table, [field])


def upgrade():
    old_roles = "'manager','sales','inventory','service','finance','auditor','reception','technician','customer_service'"
    v2_roles = old_roles + ",'clerk','general_manager','chairman'"
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint('ck_user_role', type_='check')
        batch.create_check_constraint('ck_user_role', "role IN ('admin'," + v2_roles + ')')
    with op.batch_alter_table('user_stores') as batch:
        batch.drop_constraint('ck_user_store_role', type_='check')
        batch.create_check_constraint('ck_user_store_role', 'role IS NULL OR role IN (' + v2_roles + ')')

    op.create_table('business_record_customers', *_columns(),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('phone', sa.String(40), nullable=False),
        sa.Column('note', sa.Text(), nullable=False))
    _index('business_record_customers', ['owner_id'])

    op.create_table('business_record_contracts', *_columns(),
        sa.Column('number', sa.String(60), nullable=False, unique=True),
        sa.Column('salesperson_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('customer_name', sa.String(100), nullable=False),
        sa.Column('customer_phone', sa.String(40), nullable=False),
        sa.Column('brand', sa.String(100), nullable=False),
        sa.Column('model', sa.String(160), nullable=False),
        sa.Column('vin', sa.String(40), nullable=False),
        sa.Column('contract_date', sa.Date(), nullable=False),
        sa.Column('sale_price_cents', sa.BigInteger(), nullable=False),
        sa.Column('form_data', sa.JSON(), nullable=False),
        sa.Column('gift_description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('expected_amount_cents', sa.BigInteger(), nullable=True),
        sa.Column('cost_cents', sa.BigInteger(), nullable=True),
        sa.Column('profit_cents', sa.BigInteger(), nullable=True),
        sa.Column('gift_cost_cents', sa.BigInteger(), nullable=True),
        sa.Column('price_note', sa.Text(), nullable=False),
        sa.Column('priced_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('priced_at', sa.DateTime(), nullable=True),
        sa.Column('approval_note', sa.Text(), nullable=False),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('approved_snapshot', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('template_version', sa.String(100), nullable=False),
        sa.CheckConstraint("status IN ('submitted','priced','approved','rejected')", name='ck_record_contract_status'),
        sa.CheckConstraint('sale_price_cents > 0', name='ck_record_contract_price'),
        sa.CheckConstraint('expected_amount_cents IS NULL OR expected_amount_cents >= 0', name='ck_record_contract_expected'),
        sa.CheckConstraint('cost_cents IS NULL OR cost_cents >= 0', name='ck_record_contract_cost'),
        sa.CheckConstraint('gift_cost_cents IS NULL OR gift_cost_cents >= 0', name='ck_record_contract_gift'),
        sa.CheckConstraint("status NOT IN ('priced','approved') OR (expected_amount_cents IS NOT NULL AND cost_cents IS NOT NULL AND profit_cents IS NOT NULL AND gift_cost_cents IS NOT NULL AND priced_by IS NOT NULL)", name='ck_record_contract_priced'),
        sa.CheckConstraint("status != 'approved' OR (approved_by IS NOT NULL AND approved_snapshot IS NOT NULL)", name='ck_record_contract_approved'))
    _index('business_record_contracts', ['salesperson_id', 'brand', 'contract_date', 'status'])

    op.create_table('business_record_receipts', *_columns(False),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False, unique=True),
        sa.Column('actual_amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('received_on', sa.Date(), nullable=False),
        sa.Column('confirmed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.CheckConstraint('actual_amount_cents > 0', name='ck_record_receipt_amount'))
    _index('business_record_receipts', ['received_on'])

    op.create_table('business_record_after_sales', *_columns(),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('number', sa.String(60), nullable=False, unique=True),
        sa.Column('service_type', sa.String(30), nullable=False),
        sa.Column('customer_name', sa.String(100), nullable=False),
        sa.Column('customer_phone', sa.String(40), nullable=False),
        sa.Column('vehicle', sa.String(160), nullable=False),
        sa.Column('brand', sa.String(100), nullable=False),
        sa.Column('service_items', sa.Text(), nullable=False),
        sa.Column('materials_cents', sa.BigInteger(), nullable=False),
        sa.Column('labor_cents', sa.BigInteger(), nullable=False),
        sa.Column('cost_cents', sa.BigInteger(), nullable=True),
        sa.Column('handler_name', sa.String(100), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.CheckConstraint("service_type IN ('repair','maintenance','accident','renewal','extended_warranty','accessories')", name='ck_record_service_type'),
        sa.CheckConstraint('materials_cents >= 0 AND labor_cents >= 0 AND (cost_cents IS NULL OR cost_cents >= 0)', name='ck_record_service_money'))
    _index('business_record_after_sales', ['owner_id', 'service_type', 'brand', 'business_date'])

    op.create_table('business_record_manual_reports', *_columns(),
        sa.Column('report_key', sa.String(80), nullable=False),
        sa.Column('period', sa.Date(), nullable=False),
        sa.Column('brand', sa.String(100), nullable=False),
        sa.Column('salesperson_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('values', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False))
    _index('business_record_manual_reports', ['report_key', 'period', 'salesperson_id'])

    op.create_table('business_record_settings', *_columns(),
        sa.Column('approval_mode', sa.String(15), nullable=False),
        sa.Column('threshold_amount_cents', sa.BigInteger(), nullable=True),
        sa.Column('threshold_basis_points', sa.Integer(), nullable=True),
        sa.UniqueConstraint('store_id', name='uq_record_settings_store'),
        sa.CheckConstraint("approval_mode IN ('all','fixed','ratio')", name='ck_record_settings_mode'),
        sa.CheckConstraint('threshold_amount_cents IS NULL OR threshold_amount_cents >= 0', name='ck_record_settings_amount'),
        sa.CheckConstraint('threshold_basis_points IS NULL OR (threshold_basis_points >= 0 AND threshold_basis_points <= 10000)', name='ck_record_settings_ratio'))
    _index('business_record_settings', [])

    op.create_table('business_record_commands', *_columns(False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_id', sa.String(80), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.UniqueConstraint('store_id', 'actor_id', 'request_id', name='uq_record_command'))
    _index('business_record_commands', [])


def downgrade():
    raise RuntimeError('业务记录迁移不删除已录数据；请使用发布前一致性备份恢复。')

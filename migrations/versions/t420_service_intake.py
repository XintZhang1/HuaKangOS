"""Frozen service intake, customer vehicle proof, and rework responsibility."""
from alembic import op
import sqlalchemy as sa

revision="t420_service_intake"
down_revision="s319_membership"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('intake_command_receipts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('request_key', sa.String(length=80), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('store_id', 'request_key', name='uq_intake_request_key')
    )
    op.create_index(op.f('ix_intake_command_receipts_store_id'), 'intake_command_receipts', ['store_id'], unique=False)
    op.create_table('intake_presets',
    sa.Column('code', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('profile', sa.String(length=20), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("profile IN ('wash','quick')", name='ck_intake_preset_profile'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('store_id', 'code', name='uq_intake_preset_code')
    )
    op.create_index(op.f('ix_intake_presets_store_id'), 'intake_presets', ['store_id'], unique=False)
    op.create_table('intake_preset_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('preset_id', sa.Integer(), nullable=False),
    sa.Column('work_item_id', sa.Integer(), nullable=False),
    sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('quantity_milli>0', name='ck_intake_preset_quantity'),
    sa.ForeignKeyConstraint(['preset_id'], ['intake_presets.id'], ),
    sa.ForeignKeyConstraint(['work_item_id'], ['master_work_items.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('preset_id', 'work_item_id', name='uq_intake_preset_work')
    )
    op.create_index(op.f('ix_intake_preset_lines_preset_id'), 'intake_preset_lines', ['preset_id'], unique=False)
    op.create_index(op.f('ix_intake_preset_lines_store_id'), 'intake_preset_lines', ['store_id'], unique=False)
    op.create_table('intake_resources',
    sa.Column('code', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('resource_type', sa.String(length=20), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('active_case_id', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("resource_type IN ('repair','wash')", name='ck_intake_resource_type'),
    sa.ForeignKeyConstraint(['active_case_id'], ['flow_cases.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('active_case_id'),
    sa.UniqueConstraint('store_id', 'code', name='uq_intake_resource_code')
    )
    op.create_index(op.f('ix_intake_resources_store_id'), 'intake_resources', ['store_id'], unique=False)
    op.create_table('intake_appointments',
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('customer_vehicle_id', sa.Integer(), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=False),
    sa.Column('starts_at', sa.DateTime(), nullable=False),
    sa.Column('ends_at', sa.DateTime(), nullable=False),
    sa.Column('mode', sa.String(length=15), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('problem', sa.String(length=1000), nullable=False),
    sa.Column('preset_id', sa.Integer(), nullable=True),
    sa.Column('repair_case_id', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("mode IN ('appointment','walk_in') AND status IN ('scheduled','arrived','converted','cancelled','no_show') AND ends_at>starts_at", name='ck_intake_appointment'),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['customer_vehicle_id'], ['care_customer_vehicles.id'], ),
    sa.ForeignKeyConstraint(['preset_id'], ['intake_presets.id'], ),
    sa.ForeignKeyConstraint(['repair_case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['resource_id'], ['intake_resources.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id'),
    sa.UniqueConstraint('repair_case_id')
    )
    op.create_index(op.f('ix_intake_appointments_resource_id'), 'intake_appointments', ['resource_id'], unique=False)
    op.create_index(op.f('ix_intake_appointments_store_id'), 'intake_appointments', ['store_id'], unique=False)
    op.create_table('intake_resource_uses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=10), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('occurred_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("action IN ('acquire','release')", name='ck_intake_resource_use'),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['resource_id'], ['intake_resources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_intake_resource_uses_case_id'), 'intake_resource_uses', ['case_id'], unique=False)
    op.create_index(op.f('ix_intake_resource_uses_resource_id'), 'intake_resource_uses', ['resource_id'], unique=False)
    op.create_index(op.f('ix_intake_resource_uses_store_id'), 'intake_resource_uses', ['store_id'], unique=False)
    op.create_table('intake_rework_requests',
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('source_case_id', sa.Integer(), nullable=False),
    sa.Column('source_quote_id', sa.Integer(), nullable=False),
    sa.Column('customer_vehicle_id', sa.Integer(), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('active_source_id', sa.Integer(), nullable=True),
    sa.Column('requested_by', sa.Integer(), nullable=False),
    sa.Column('approved_by', sa.Integer(), nullable=True),
    sa.Column('repair_case_id', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("status IN ('requested','approved','rejected','cancelled','converted','completed')", name='ck_intake_rework_status'),
    sa.ForeignKeyConstraint(['active_source_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['customer_vehicle_id'], ['care_customer_vehicles.id'], ),
    sa.ForeignKeyConstraint(['repair_case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['resource_id'], ['intake_resources.id'], ),
    sa.ForeignKeyConstraint(['source_case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['source_quote_id'], ['repair_quotes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('active_source_id'),
    sa.UniqueConstraint('case_id'),
    sa.UniqueConstraint('repair_case_id')
    )
    op.create_index(op.f('ix_intake_rework_requests_source_case_id'), 'intake_rework_requests', ['source_case_id'], unique=False)
    op.create_index(op.f('ix_intake_rework_requests_store_id'), 'intake_rework_requests', ['store_id'], unique=False)
    op.create_table('intake_vehicle_bindings',
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('customer_vehicle_id', sa.Integer(), nullable=False),
    sa.Column('customer_identity_id', sa.Integer(), nullable=False),
    sa.Column('vehicle_identity_id', sa.Integer(), nullable=False),
    sa.Column('vin', sa.String(length=17), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('source_reference', sa.String(length=500), nullable=False),
    sa.Column('reviewed_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['customer_identity_id'], ['group_identities.id'], ),
    sa.ForeignKeyConstraint(['customer_vehicle_id'], ['care_customer_vehicles.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['vehicle_identity_id'], ['group_identities.id'], ),
    sa.PrimaryKeyConstraint('case_id')
    )
    op.create_index(op.f('ix_intake_vehicle_bindings_store_id'), 'intake_vehicle_bindings', ['store_id'], unique=False)
    op.create_table('intake_arrivals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=False),
    sa.Column('customer_vehicle_id', sa.Integer(), nullable=False),
    sa.Column('checked_vin', sa.String(length=17), nullable=False),
    sa.Column('odometer_km', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('odometer_km BETWEEN 0 AND 3000000', name='ck_intake_arrival_mileage'),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['appointment_id'], ['intake_appointments.id'], ),
    sa.ForeignKeyConstraint(['customer_vehicle_id'], ['care_customer_vehicles.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('appointment_id')
    )
    op.create_index(op.f('ix_intake_arrivals_store_id'), 'intake_arrivals', ['store_id'], unique=False)
    op.create_table('intake_repair_contexts',
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('profile', sa.String(length=20), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=True),
    sa.Column('rework_id', sa.Integer(), nullable=True),
    sa.Column('preset_id', sa.Integer(), nullable=True),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("profile IN ('regular','wash','quick','rework') AND ((rework_id IS NOT NULL AND appointment_id IS NULL AND profile='rework') OR (appointment_id IS NOT NULL AND rework_id IS NULL AND profile!='rework'))", name='ck_intake_context'),
    sa.ForeignKeyConstraint(['appointment_id'], ['intake_appointments.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['preset_id'], ['intake_presets.id'], ),
    sa.ForeignKeyConstraint(['resource_id'], ['intake_resources.id'], ),
    sa.ForeignKeyConstraint(['rework_id'], ['intake_rework_requests.id'], ),
    sa.PrimaryKeyConstraint('case_id'),
    sa.UniqueConstraint('appointment_id'),
    sa.UniqueConstraint('rework_id')
    )
    op.create_index(op.f('ix_intake_repair_contexts_store_id'), 'intake_repair_contexts', ['store_id'], unique=False)
    op.create_table('intake_rework_liabilities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('request_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('internal_name', sa.String(length=120), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('approved_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['request_id'], ['intake_rework_requests.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('request_id')
    )
    op.create_index(op.f('ix_intake_rework_liabilities_store_id'), 'intake_rework_liabilities', ['store_id'], unique=False)
    op.create_table('intake_rework_source_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('request_id', sa.Integer(), nullable=False),
    sa.Column('source_line_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['request_id'], ['intake_rework_requests.id'], ),
    sa.ForeignKeyConstraint(['source_line_id'], ['repair_lines.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('request_id', 'source_line_id', name='uq_intake_rework_line')
    )
    op.create_index(op.f('ix_intake_rework_source_lines_request_id'), 'intake_rework_source_lines', ['request_id'], unique=False)
    op.create_index(op.f('ix_intake_rework_source_lines_store_id'), 'intake_rework_source_lines', ['store_id'], unique=False)

def downgrade():
    op.drop_table('intake_rework_source_lines')
    op.drop_table('intake_rework_liabilities')
    op.drop_table('intake_repair_contexts')
    op.drop_table('intake_arrivals')
    op.drop_table('intake_vehicle_bindings')
    op.drop_table('intake_rework_requests')
    op.drop_table('intake_resource_uses')
    op.drop_table('intake_appointments')
    op.drop_table('intake_resources')
    op.drop_table('intake_preset_lines')
    op.drop_table('intake_presets')
    op.drop_table('intake_command_receipts')

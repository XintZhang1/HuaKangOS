"""Frozen vehicle location, local movement, disposal and original physical returns."""
from alembic import op
import sqlalchemy as sa
revision='v622_vehicle_operations'
down_revision='u521_invoice'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('vehicle_positions',
        sa.Column('vehicle_id',sa.Integer(),sa.ForeignKey('vehicles.id'),nullable=False),
        sa.Column('location_id',sa.Integer(),sa.ForeignKey('master_locations.id'),nullable=True),
        sa.Column('status',sa.String(length=20),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('vehicle_id',name=None),
        sa.CheckConstraint("(status='stored' AND location_id IS NOT NULL) OR (status!='stored' AND location_id IS NULL)",name='ck_vposition_location'),
        sa.CheckConstraint("status IN ('stored','transit','handover','exited')",name='ck_vposition_status'))
    op.create_index('ix_vehicle_positions_store_id','vehicle_positions',['store_id'],unique=False)
    op.create_table('vehicle_operations',
        sa.Column('id',sa.Integer(),sa.ForeignKey('flow_cases.id'),primary_key=True,nullable=False),
        sa.Column('kind',sa.String(length=25),nullable=False),
        sa.Column('status',sa.String(length=30),nullable=False),
        sa.Column('source_vehicle_id',sa.Integer(),sa.ForeignKey('vehicles.id'),nullable=False),
        sa.Column('source_generation',sa.Integer(),nullable=False),
        sa.Column('vin',sa.String(length=17),nullable=False),
        sa.Column('source_location_id',sa.Integer(),sa.ForeignKey('master_locations.id'),nullable=True),
        sa.Column('destination_location_id',sa.Integer(),sa.ForeignKey('master_locations.id'),nullable=True),
        sa.Column('original_operation_id',sa.Integer(),sa.ForeignKey('vehicle_operations.id'),nullable=True),
        sa.Column('aftercare_case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=True),
        sa.Column('source_order_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=True),
        sa.Column('authorization_evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=True),
        sa.Column('received_vehicle_id',sa.Integer(),sa.ForeignKey('vehicles.id'),nullable=True),
        sa.Column('cost_cents',sa.BigInteger(),nullable=False),
        sa.Column('reason',sa.String(length=500),nullable=False),
        sa.Column('recipient',sa.String(length=180),nullable=False),
        sa.Column('requested_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('aftercare_case_id',name=None),
        sa.UniqueConstraint('received_vehicle_id',name=None),
        sa.CheckConstraint("kind IN ('locate','local_move','other_out','other_return','customer_return')",name='ck_voperation_kind'),
        sa.CheckConstraint("status IN ('requested','approved','transit','returning','completed','cancelled','rejected','awaiting_receipt','quarantined','inspected','rectifying','release_approved','return_to_customer','accepted','returned_to_customer')",name='ck_voperation_status'),
        sa.CheckConstraint('source_generation >= 0 AND cost_cents >= 0',name='ck_voperation_value'))
    op.create_index('ix_vehicle_operations_source_vehicle_id','vehicle_operations',['source_vehicle_id'],unique=False)
    op.create_index('ix_vehicle_operations_store_id','vehicle_operations',['store_id'],unique=False)
    op.create_index('ix_vehicle_operations_vin','vehicle_operations',['vin'],unique=False)
    op.create_table('vehicle_operation_claims',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('vehicle_operations.id'),nullable=False),
        sa.Column('store_id',sa.Integer(),sa.ForeignKey('stores.id'),nullable=False),
        sa.Column('vin',sa.String(length=17),nullable=False),
        sa.Column('active_vin',sa.String(length=17),nullable=True),
        sa.UniqueConstraint('case_id',name=None),
        sa.UniqueConstraint('active_vin',name=None),
        sa.CheckConstraint('active_vin IS NULL OR active_vin=vin',name='ck_voperation_claim'))
    op.create_table('vehicle_position_entries',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('operation_id',sa.Integer(),sa.ForeignKey('vehicle_operations.id'),nullable=True),
        sa.Column('vehicle_id',sa.Integer(),sa.ForeignKey('vehicles.id'),nullable=False),
        sa.Column('location_id',sa.Integer(),sa.ForeignKey('master_locations.id'),nullable=True),
        sa.Column('kind',sa.String(length=35),nullable=False),
        sa.Column('quantity',sa.Integer(),nullable=False),
        sa.Column('inventory_delta',sa.Integer(),nullable=False),
        sa.Column('value_cents',sa.BigInteger(),nullable=False),
        sa.Column('original_id',sa.Integer(),sa.ForeignKey('vehicle_position_entries.id'),nullable=True),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('business_date',sa.Date(),nullable=False),
        sa.Column('reason',sa.String(length=500),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint('quantity BETWEEN -1 AND 1 AND inventory_delta BETWEEN -1 AND 1',name='ck_vposition_entry_qty'),
        sa.CheckConstraint('(quantity=1 AND value_cents>=0) OR (quantity=-1 AND value_cents<=0) OR (quantity=0 AND value_cents=0)',name='ck_vposition_entry_value'),
        sa.UniqueConstraint('case_id','vehicle_id','kind',name='uq_vposition_entry_once'))
    op.create_index('ix_vehicle_position_entries_case_id','vehicle_position_entries',['case_id'],unique=False)
    op.create_index('ix_vehicle_position_entries_operation_id','vehicle_position_entries',['operation_id'],unique=False)
    op.create_index('ix_vehicle_position_entries_store_id','vehicle_position_entries',['store_id'],unique=False)
    op.create_index('ix_vehicle_position_entries_vehicle_id','vehicle_position_entries',['vehicle_id'],unique=False)
    op.create_table('vehicle_return_inspections',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('operation_id',sa.Integer(),sa.ForeignKey('vehicle_operations.id'),nullable=False),
        sa.Column('outcome',sa.String(length=10),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('findings',sa.String(length=1000),nullable=False),
        sa.Column('business_date',sa.Date(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint("outcome IN ('pass','fail')",name='ck_vreturn_inspection'))
    op.create_index('ix_vehicle_return_inspections_operation_id','vehicle_return_inspections',['operation_id'],unique=False)
    op.create_index('ix_vehicle_return_inspections_store_id','vehicle_return_inspections',['store_id'],unique=False)
    op.create_table('vehicle_operation_reviews',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('operation_id',sa.Integer(),sa.ForeignKey('vehicle_operations.id'),nullable=False),
        sa.Column('decision',sa.String(length=25),nullable=False),
        sa.Column('inspection_id',sa.Integer(),sa.ForeignKey('vehicle_return_inspections.id'),nullable=True),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('reason',sa.String(length=500),nullable=False),
        sa.Column('business_date',sa.Date(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint("decision IN ('approve','reject','release','rectify','return_to_customer')",name='ck_voperation_review'))
    op.create_index('ix_vehicle_operation_reviews_operation_id','vehicle_operation_reviews',['operation_id'],unique=False)
    op.create_index('ix_vehicle_operation_reviews_store_id','vehicle_operation_reviews',['store_id'],unique=False)
    op.create_table('vehicle_quarantine_facts',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('operation_id',sa.Integer(),sa.ForeignKey('vehicle_operations.id'),nullable=False),
        sa.Column('kind',sa.String(length=25),nullable=False),
        sa.Column('location_id',sa.Integer(),sa.ForeignKey('master_locations.id'),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('reason',sa.String(length=500),nullable=False),
        sa.Column('business_date',sa.Date(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint("kind IN ('intake','release','return_to_customer')",name='ck_vquarantine_kind'),
        sa.UniqueConstraint('operation_id','kind',name='uq_vquarantine_fact'))
    op.create_index('ix_vehicle_quarantine_facts_operation_id','vehicle_quarantine_facts',['operation_id'],unique=False)
    op.create_index('ix_vehicle_quarantine_facts_store_id','vehicle_quarantine_facts',['store_id'],unique=False)
    op.create_table('vehicle_order_hold_releases',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('source_case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('aftercare_case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('vehicle_id',sa.Integer(),sa.ForeignKey('vehicles.id'),nullable=False),
        sa.Column('reason',sa.String(length=500),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('business_date',sa.Date(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('source_case_id',name=None),
        sa.UniqueConstraint('aftercare_case_id',name=None))
    op.create_index('ix_vehicle_order_hold_releases_store_id','vehicle_order_hold_releases',['store_id'],unique=False)

def downgrade():
    op.drop_table('vehicle_order_hold_releases')
    op.drop_table('vehicle_quarantine_facts')
    op.drop_table('vehicle_operation_reviews')
    op.drop_table('vehicle_return_inspections')
    op.drop_table('vehicle_position_entries')
    op.drop_table('vehicle_operation_claims')
    op.drop_table('vehicle_operations')
    op.drop_table('vehicle_positions')

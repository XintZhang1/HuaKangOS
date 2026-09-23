"""Actual gate attendance and reviewed corrections; no fabricated historic facts."""
from alembic import op
import sqlalchemy as sa
revision = 'q79d_gate_visits'
down_revision = 'p68c_questionnaire_versions'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('gate_visits',
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('customer_vehicle_id', sa.Integer(), sa.ForeignKey('care_customer_vehicles.id'), nullable=False),
        sa.Column('vin', sa.String(length=17), nullable=False),
        sa.Column('purpose', sa.String(length=24), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("purpose IN ('consultation','inspection','accessory','delivery','other') AND status IN ('planned','inside','departed','cancelled','voided','handed_over')", name='ck_gate_visit_state'),
        sa.UniqueConstraint('case_id', name=None),
    )
    op.create_index('ix_gate_visits_store_id', 'gate_visits', ['store_id'], unique=False)
    op.create_index('ix_gate_visits_vin', 'gate_visits', ['vin'], unique=False)
    op.create_table('gate_facts',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('visit_id', sa.Integer(), sa.ForeignKey('gate_visits.id'), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('actual_at', sa.DateTime(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("direction IN ('arrive','leave') AND actual_at<=created_at", name='ck_gate_fact'),
        sa.UniqueConstraint('visit_id', 'direction', name='uq_gate_visit_direction'),
    )
    op.create_index('ix_gate_facts_store_id', 'gate_facts', ['store_id'], unique=False)
    op.create_index('ix_gate_facts_visit_id', 'gate_facts', ['visit_id'], unique=False)
    op.create_table('gate_corrections',
        sa.Column('visit_id', sa.Integer(), sa.ForeignKey('gate_visits.id'), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('actual_at', sa.DateTime(), nullable=True),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('origin_digest', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('active_visit_id', sa.Integer(), sa.ForeignKey('gate_visits.id'), nullable=True),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("kind IN ('arrive_time','leave_time','void_visit') AND status IN ('pending','approved','rejected','cancelled') AND ((kind='void_visit' AND actual_at IS NULL) OR (kind!='void_visit' AND actual_at IS NOT NULL)) AND ((status='pending' AND active_visit_id IS NOT NULL AND active_visit_id=visit_id) OR (status!='pending' AND active_visit_id IS NULL))", name='ck_gate_correction'),
        sa.UniqueConstraint('active_visit_id', name=None),
    )
    op.create_index('ix_gate_corrections_store_id', 'gate_corrections', ['store_id'], unique=False)
    op.create_index('ix_gate_corrections_visit_id', 'gate_corrections', ['visit_id'], unique=False)
    op.create_table('gate_reviews',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('correction_id', sa.Integer(), sa.ForeignKey('gate_corrections.id'), nullable=False),
        sa.Column('decision', sa.String(length=12), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("decision IN ('approved','rejected')", name='ck_gate_review'),
        sa.UniqueConstraint('correction_id', name=None),
    )
    op.create_index('ix_gate_reviews_store_id', 'gate_reviews', ['store_id'], unique=False)
    op.create_table('gate_handoffs',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('visit_id', sa.Integer(), sa.ForeignKey('gate_visits.id'), nullable=False),
        sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('intake_appointments.id'), nullable=False),
        sa.Column('arrival_fact_id', sa.Integer(), sa.ForeignKey('intake_arrivals.id'), nullable=False),
        sa.Column('origin_fact_id', sa.Integer(), sa.ForeignKey('gate_facts.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('origin_digest', sa.String(length=64), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('appointment_id', name=None),
        sa.UniqueConstraint('arrival_fact_id', name=None),
        sa.UniqueConstraint('visit_id', name=None),
        sa.UniqueConstraint('origin_fact_id', name=None),
    )
    op.create_index('ix_gate_handoffs_store_id', 'gate_handoffs', ['store_id'], unique=False)
    op.create_table('gate_repair_exits',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('actual_at', sa.DateTime(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('actual_at<=created_at', name='ck_gate_repair_exit'),
        sa.UniqueConstraint('case_id', name=None),
    )
    op.create_index('ix_gate_repair_exits_store_id', 'gate_repair_exits', ['store_id'], unique=False)

def downgrade():
    raise RuntimeError('Actual gate origins require a reviewed consistent backup restore; no destructive downgrade')

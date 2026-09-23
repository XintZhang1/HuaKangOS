"""Explicit original liability and new customer work; old rework unchanged."""
from alembic import op
import sqlalchemy as sa
revision='z68m_rework_extensions'
down_revision='y57l_vehicle_income'
branch_labels=None
depends_on=None

def fk(name,target,**kw):return sa.Column(name,sa.Integer(),sa.ForeignKey(target),nullable=False,**kw)
def local():return sa.Column('store_id',sa.Integer(),nullable=False)
def upgrade():
    op.create_table('rework_source_grants',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('definition_version',sa.Integer(),nullable=False),
        fk('from_store_id','stores.id'),fk('to_store_id','stores.id'),fk('source_case_id','flow_cases.id'),
        sa.Column('source_case_version',sa.Integer(),nullable=False),fk('source_quote_id','repair_quotes.id'),
        fk('from_vehicle_id','care_customer_vehicles.id'),fk('to_vehicle_id','care_customer_vehicles.id'),
        fk('customer_identity_id','group_identities.id'),fk('vehicle_identity_id','group_identities.id'),
        sa.Column('vin',sa.String(17),nullable=False),sa.Column('source_number',sa.String(80),nullable=False),sa.Column('source_lines',sa.JSON(),nullable=False),
        sa.Column('original_liability_limit_cents',sa.BigInteger(),nullable=False),sa.Column('responsible_name',sa.String(120),nullable=False),
        fk('recipient_id','users.id'),sa.Column('recipient_role',sa.String(20),nullable=False),sa.Column('recipient_access_version',sa.Integer(),nullable=False),
        fk('requested_by','users.id'),sa.Column('requester_role',sa.String(20),nullable=False),sa.Column('requester_access_version',sa.Integer(),nullable=False),
        fk('evidence_id','flow_files.id'),sa.Column('reason',sa.String(1000),nullable=False),sa.Column('expires_at',sa.DateTime(),nullable=False),
        sa.Column('status',sa.String(12),nullable=False),sa.Column('scope_digest',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint("definition_version=1 AND version>0 AND source_case_version>0 AND original_liability_limit_cents>=0 AND recipient_access_version>0 AND requester_access_version>0 AND expires_at>created_at AND status IN ('pending','approved','rejected','cancelled','revoked','consumed')",name='ck_rework_source_grant'))
    for name in ('from_store_id','to_store_id','source_case_id'):op.create_index('ix_rework_source_grants_'+name,'rework_source_grants',[name])
    op.create_table('rework_grant_decisions',sa.Column('id',sa.Integer(),primary_key=True),fk('grant_id','rework_source_grants.id'),
        sa.Column('previous_version',sa.Integer(),nullable=False),sa.Column('action',sa.String(12),nullable=False),fk('actor_id','users.id'),
        sa.Column('actor_role',sa.String(20),nullable=False),sa.Column('actor_access_version',sa.Integer(),nullable=False),fk('store_id','stores.id'),
        sa.Column('scope_digest',sa.String(64),nullable=False),sa.Column('reason',sa.String(1000),nullable=False),sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('grant_id','previous_version',name='uq_rework_grant_decision'),
        sa.CheckConstraint("previous_version>0 AND actor_access_version>0 AND action IN ('approve','reject','cancel','revoke','consume')",name='ck_rework_grant_decision'))
    op.create_index('ix_rework_grant_decisions_grant_id','rework_grant_decisions',['grant_id'])
    op.create_table('rework_grant_receipts',local(),sa.Column('id',sa.Integer(),primary_key=True),sa.Column('request_key',sa.String(80),nullable=False),
        fk('actor_id','users.id'),sa.Column('digest',sa.String(64),nullable=False),fk('grant_id','rework_source_grants.id'),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('store_id','request_key',name='uq_rework_grant_receipt'))
    op.create_table('rework_extensions',local(),fk('request_id','intake_rework_requests.id',primary_key=True),sa.Column('definition_version',sa.Integer(),nullable=False),
        fk('grant_id','rework_source_grants.id',unique=True),sa.Column('grant_digest',sa.String(64),nullable=False),fk('actor_id','users.id'),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint('definition_version=1',name='ck_rework_extension_definition'))
    op.create_table('rework_quote_scopes',local(),fk('quote_id','repair_quotes.id',primary_key=True),fk('request_id','rework_extensions.request_id'),
        sa.Column('original_liability_cents',sa.BigInteger(),nullable=False),sa.Column('customer_extra_cents',sa.BigInteger(),nullable=False),sa.Column('digest',sa.String(64),nullable=False),
        sa.CheckConstraint('original_liability_cents>=0 AND customer_extra_cents>=0',name='ck_rework_quote_scope_amounts'))
    op.create_index('ix_rework_quote_scopes_request_id','rework_quote_scopes',['request_id'])
    op.create_table('rework_line_scopes',local(),fk('line_id','repair_lines.id',primary_key=True),fk('quote_id','rework_quote_scopes.quote_id'),
        sa.Column('charge_scope',sa.String(24),nullable=False),sa.Column('source_line_id',sa.Integer(),sa.ForeignKey('repair_lines.id'),nullable=True),
        sa.CheckConstraint("(charge_scope='original_liability' AND source_line_id IS NOT NULL) OR (charge_scope='customer_extra' AND source_line_id IS NULL)",name='ck_rework_line_scope'))
    op.create_index('ix_rework_line_scopes_quote_id','rework_line_scopes',['quote_id'])
    for table in ('rework_grant_receipts','rework_extensions','rework_quote_scopes','rework_line_scopes'):op.create_index('ix_'+table+'_store_id',table,['store_id'])

def downgrade():
    for table in ('rework_line_scopes','rework_quote_scopes','rework_extensions','rework_grant_receipts','rework_grant_decisions','rework_source_grants'):op.drop_table(table)

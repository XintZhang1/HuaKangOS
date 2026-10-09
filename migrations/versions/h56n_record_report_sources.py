"""Append report sources and correction links without rewriting saved facts."""
from alembic import op
import sqlalchemy as sa

revision = 'h56n_record_report_sources'
down_revision = 'h55m_record_customer_links'
branch_labels = None
depends_on = None


def upgrade():
    table = 'business_record_manual_reports'
    with op.batch_alter_table(table) as batch:
        batch.add_column(sa.Column('contract_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('contract_version', sa.Integer(), nullable=True))
        # Existing independent rows keep their historical interpretation.
        batch.add_column(sa.Column('entry_mode', sa.String(20), nullable=False, server_default='legacy'))
        batch.add_column(sa.Column('supersedes_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('supersedes_version', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('source_key', sa.String(160), nullable=True))
        batch.add_column(sa.Column('note', sa.Text(), nullable=False, server_default=''))
        batch.create_foreign_key('fk_record_report_contract', 'business_record_contracts', ['contract_id'], ['id'])
        batch.create_foreign_key('fk_record_report_predecessor', table, ['supersedes_id'], ['id'])
        batch.create_index('ix_business_record_manual_reports_contract_id', ['contract_id'])
        batch.create_unique_constraint('uq_record_report_predecessor', ['supersedes_id'])
        batch.create_unique_constraint('uq_record_report_source_key', ['source_key'])


def downgrade():
    raise RuntimeError('Report sources and correction history are retained; restore a verified backup instead')

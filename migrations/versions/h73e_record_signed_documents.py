"""Append signed contract and delivery originals without changing delivery gates."""
from alembic import op
import sqlalchemy as sa

revision = 'h73e_record_signed_documents'
down_revision = 'h72d_accessory_sale_evidence'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('business_record_signed_documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('contract_version', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(180), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('object_key', sa.String(200), nullable=False),
        sa.Column('scan_state', sa.String(30), nullable=False),
        sa.Column('scan_code', sa.String(50), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('signed_contract','signed_delivery')", name='ck_record_signed_document_kind'))
    for column in ('store_id', 'contract_id'):
        op.create_index('ix_business_record_signed_documents_' + column, 'business_record_signed_documents', [column])


def downgrade():
    raise RuntimeError('签字材料原件不可删除；请恢复经过核对的备份')

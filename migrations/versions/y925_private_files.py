"""Immutable private local attachment references; historical BLOBs remain intact."""
from alembic import op
import sqlalchemy as sa
revision='y925_private_files'
down_revision='x824_business_finance'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('private_file_objects',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('store_id',sa.Integer(),sa.ForeignKey('stores.id'),nullable=False),
        sa.Column('file_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('object_key',sa.String(100),nullable=False),
        sa.Column('sha256',sa.String(64),nullable=False),
        sa.Column('size',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('file_id'),sa.UniqueConstraint('object_key'),
        sa.CheckConstraint('size > 0 AND size <= 10485760',name='ck_private_file_size'))
    op.create_index('ix_private_file_objects_store_id','private_file_objects',['store_id'])


def downgrade():
    raise RuntimeError('私有对象与原附件历史不可自动降级删除；请按已验证整套备份恢复')

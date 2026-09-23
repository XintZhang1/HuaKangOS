"""Material brand references; no inferred labels or changes to historic business rows."""
from alembic import op
import sqlalchemy as sa
revision='t02g_master_completion'
down_revision='s91f_dossier_grants'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('master_material_brands',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('code',sa.String(40),nullable=False),
        sa.Column('name',sa.String(120),nullable=False),
        sa.Column('active',sa.Boolean(),nullable=False),
        sa.UniqueConstraint('store_id','code',name='uq_master_material_brands_code'))
    op.create_index('ix_master_material_brands_store_id','master_material_brands',['store_id'])
    with op.batch_alter_table('master_item_profiles') as batch:
        batch.add_column(sa.Column('brand_id',sa.Integer(),nullable=True))
        batch.create_foreign_key('fk_item_profile_brand','master_material_brands',['brand_id'],['id'])
        batch.create_index('ix_master_item_profiles_brand_id',['brand_id'])


def downgrade():
    raise RuntimeError('物资品牌及原引用不可自动降级；请用已核验的整库备份恢复')

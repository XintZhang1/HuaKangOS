"""Explicit brand/series and confirmed model/inventory classification."""
from alembic import op
import sqlalchemy as sa

revision='f632_vehicle_catalog'
down_revision='e531_service_orders'
branch_labels=None
depends_on=None


def version_columns():
    return [sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False)]


def upgrade():
    for table,extra in [
        ('catalog_vehicle_brands',[]),
        ('catalog_vehicle_series',[sa.Column('brand_id',sa.Integer(),sa.ForeignKey('catalog_vehicle_brands.id'),nullable=False)])]:
        op.create_table(table,*version_columns(),sa.Column('code',sa.String(40),nullable=False),
            sa.Column('name',sa.String(120),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),*extra,
            sa.UniqueConstraint('store_id','code',name='uq_'+table+'_code'))
        op.create_index('ix_'+table+'_store_id',table,['store_id'])
    op.create_index('ix_catalog_vehicle_series_brand_id','catalog_vehicle_series',['brand_id'])
    op.create_table('catalog_model_classifications',*version_columns(),
        sa.Column('model_id',sa.Integer(),sa.ForeignKey('master_vehicle_models.id'),nullable=False),
        sa.Column('series_id',sa.Integer(),sa.ForeignKey('catalog_vehicle_series.id'),nullable=False),
        sa.UniqueConstraint('model_id',name='uq_catalog_model_classification'))
    op.create_index('ix_catalog_model_classifications_store_id','catalog_model_classifications',['store_id'])
    op.create_table('catalog_vehicle_classifications',*version_columns(),
        sa.Column('vehicle_id',sa.Integer(),sa.ForeignKey('vehicles.id'),nullable=False),
        sa.Column('model_id',sa.Integer(),sa.ForeignKey('master_vehicle_models.id'),nullable=False),
        sa.UniqueConstraint('vehicle_id',name='uq_catalog_vehicle_classification'))
    op.create_index('ix_catalog_vehicle_classifications_store_id','catalog_vehicle_classifications',['store_id'])


def downgrade():
    for name in ('catalog_vehicle_classifications','catalog_model_classifications','catalog_vehicle_series','catalog_vehicle_brands'):
        op.drop_table(name)

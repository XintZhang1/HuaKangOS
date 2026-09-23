"""Frozen typed store masters and reviewed opening inventory.

No historical business state or quantity is inferred.
"""
from alembic import op
import sqlalchemy as sa

revision='h208_master_data'
down_revision='g107_file_security'
branch_labels=None
depends_on=None


def master(name,*columns,constraints=()):
    op.create_table(name,
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),sa.Column('code',sa.String(40),nullable=False),
        sa.Column('name',sa.String(120),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),
        *columns,sa.UniqueConstraint('store_id','code',name='uq_'+name+'_code'),*constraints)
    op.create_index('ix_'+name+'_store_id',name,['store_id'])


def upgrade():
    master('master_suppliers',sa.Column('tax_identifier',sa.String(40),nullable=False),
        sa.Column('contact_name',sa.String(80),nullable=False),sa.Column('phone',sa.String(30),nullable=False),
        sa.Column('payment_terms_days',sa.Integer(),nullable=False),constraints=[
            sa.CheckConstraint('payment_terms_days BETWEEN 0 AND 365',name='ck_master_supplier_terms')])
    master('master_insurers',sa.Column('license_number',sa.String(60),nullable=False),
        sa.Column('claims_phone',sa.String(30),nullable=False),sa.Column('settlement_days',sa.Integer(),nullable=False),
        constraints=[sa.CheckConstraint('settlement_days BETWEEN 0 AND 365',name='ck_master_insurer_terms')])
    master('master_warehouses',sa.Column('warehouse_type',sa.String(20),nullable=False),
        sa.Column('address',sa.String(200),nullable=False),constraints=[
            sa.CheckConstraint("warehouse_type IN ('vehicles','materials','mixed')",name='ck_master_warehouse_type')])
    master('master_locations',sa.Column('warehouse_id',sa.Integer(),sa.ForeignKey('master_warehouses.id'),nullable=False))
    op.create_index('ix_master_locations_warehouse_id','master_locations',['warehouse_id'])
    master('master_material_categories',sa.Column('parent_id',sa.Integer(),sa.ForeignKey('master_material_categories.id'),nullable=True))
    master('master_work_items',sa.Column('billing_unit',sa.String(10),nullable=False),
        sa.Column('standard_minutes',sa.Integer(),nullable=False),sa.Column('standard_fee_cents',sa.BigInteger(),nullable=False),
        sa.Column('warranty_days',sa.Integer(),nullable=False),constraints=[sa.CheckConstraint(
            "billing_unit IN ('job','hour') AND standard_minutes BETWEEN 0 AND 100000 AND standard_fee_cents >= 0 AND warranty_days BETWEEN 0 AND 3650",name='ck_master_work_values')])
    master('master_teams',sa.Column('leader_user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=True))
    master('master_agency_projects',sa.Column('service_fee_cents',sa.BigInteger(),nullable=False),
        sa.Column('expected_days',sa.Integer(),nullable=False),constraints=[
            sa.CheckConstraint('service_fee_cents >= 0 AND expected_days BETWEEN 0 AND 365',name='ck_master_agency_values')])
    master('master_vehicle_models',sa.Column('brand',sa.String(80),nullable=False),
        sa.Column('model_year',sa.Integer(),nullable=False),sa.Column('fuel_type',sa.String(20),nullable=False),
        sa.Column('seats',sa.Integer(),nullable=False),sa.Column('displacement_ml',sa.Integer(),nullable=False),
        sa.Column('battery_wh',sa.Integer(),nullable=False),sa.Column('guide_price_cents',sa.BigInteger(),nullable=False),
        constraints=[sa.CheckConstraint("fuel_type IN ('petrol','diesel','electric','hybrid','plugin_hybrid') AND model_year BETWEEN 1990 AND 2100 AND seats BETWEEN 1 AND 60 AND displacement_ml BETWEEN 0 AND 20000 AND battery_wh BETWEEN 0 AND 2000000 AND guide_price_cents >= 0",name='ck_master_model_values')])
    master('master_member_tiers',sa.Column('annual_fee_cents',sa.BigInteger(),nullable=False),
        sa.Column('validity_months',sa.Integer(),nullable=False),sa.Column('discount_basis_points',sa.Integer(),nullable=False),
        constraints=[sa.CheckConstraint('annual_fee_cents >= 0 AND validity_months BETWEEN 1 AND 120 AND discount_basis_points BETWEEN 0 AND 10000',name='ck_master_tier_values')])
    op.create_table('master_item_profiles',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('store_id',sa.Integer(),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('active',sa.Boolean(),nullable=False),sa.Column('item_id',sa.Integer(),sa.ForeignKey('flow_items.id'),nullable=False,unique=True),
        sa.Column('category_id',sa.Integer(),sa.ForeignKey('master_material_categories.id'),nullable=False),
        sa.Column('location_id',sa.Integer(),sa.ForeignKey('master_locations.id'),nullable=False),
        sa.Column('supplier_id',sa.Integer(),sa.ForeignKey('master_suppliers.id'),nullable=True))
    for col in ('store_id','category_id','location_id','supplier_id'):
        op.create_index('ix_master_item_profiles_'+col,'master_item_profiles',[col])
    op.create_table('master_receipts',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('store_id',sa.Integer(),nullable=False),sa.Column('request_key',sa.String(80),nullable=False),
        sa.Column('digest',sa.String(64),nullable=False),sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('result',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('store_id','request_key',name='uq_master_request_key'))
    op.create_index('ix_master_receipts_store_id','master_receipts',['store_id'])
    op.create_table('opening_batches',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('store_id',sa.Integer(),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('source_text',sa.Text(),nullable=False),sa.Column('source_digest',sa.String(64),nullable=False),
        sa.Column('source_reference',sa.String(160),nullable=False),sa.Column('opening_date',sa.Date(),nullable=False),
        sa.Column('totals',sa.JSON(),nullable=False),sa.Column('status',sa.String(20),nullable=False),
        sa.Column('prepared_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('confirmed_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=True),sa.Column('confirmed_at',sa.DateTime(),nullable=True),
        sa.Column('confirmed_store_key',sa.Integer(),nullable=True,unique=True),
        sa.CheckConstraint("status IN ('prepared','trial_passed','confirmed')",name='ck_opening_status'))
    op.create_index('ix_opening_batches_store_id','opening_batches',['store_id'])
    op.create_table('opening_stock_entries',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('store_id',sa.Integer(),nullable=False),sa.Column('batch_id',sa.Integer(),sa.ForeignKey('opening_batches.id'),nullable=False),
        sa.Column('item_id',sa.Integer(),sa.ForeignKey('flow_items.id'),nullable=False,unique=True),
        sa.Column('quantity_milli',sa.BigInteger(),nullable=False),sa.Column('value_cents',sa.BigInteger(),nullable=False),
        sa.Column('business_date',sa.Date(),nullable=False),sa.Column('source_reference',sa.String(160),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint('quantity_milli > 0 AND value_cents >= 0',name='ck_opening_stock_values'))
    op.create_index('ix_opening_stock_entries_store_id','opening_stock_entries',['store_id'])


def downgrade():
    raise RuntimeError('主数据与期初账本迁移不可自动降级；请使用已验证的一致备份恢复')

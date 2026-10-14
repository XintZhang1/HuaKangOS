"""Append a distinct kind for cashier paid-accessory evidence."""
from alembic import op

revision = 'h72d_accessory_sale_evidence'
down_revision = 'h71c_record_inventory'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('business_record_pricing_files') as batch:
        batch.drop_constraint('ck_record_pricing_file_kind', type_='check')
        batch.create_check_constraint('ck_record_pricing_file_kind',
            "kind IN ('vehicle','gift','contract_attachment','accessory_sale')")


def downgrade():
    raise RuntimeError('有偿精品原件与审批依据必须保留，请使用已核对的恢复方案')

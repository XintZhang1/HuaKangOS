"""Separate actual gift costs from sale values without rewriting old contracts."""
from alembic import op
import sqlalchemy as sa

revision = 'h64v_record_gift_costs'
down_revision = 'h63u_record_delivery_returns'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('business_record_gift_prices') as batch:
        batch.alter_column('unit_price_cents', existing_type=sa.BigInteger(), nullable=True)
        batch.add_column(sa.Column('unit_cost_cents', sa.BigInteger(), nullable=True))
        for name, size in (('brand', 100), ('unit', 40), ('applicable_models', 300), ('source_ref', 300)):
            batch.add_column(sa.Column(name, sa.String(size), nullable=False, server_default=''))
        batch.create_check_constraint('ck_record_gift_cost_nonnegative', 'unit_cost_cents IS NULL OR unit_cost_cents >= 0')
    with op.batch_alter_table('business_record_contract_terms') as batch:
        batch.alter_column('gift_total_cents', existing_type=sa.BigInteger(), nullable=True)
        batch.add_column(sa.Column('gift_cost_total_cents', sa.BigInteger(), nullable=True))
        # Existing records explicitly retain their original accounting basis.
        # No historical amount is copied or presented as a newly supplied cost.
        batch.add_column(sa.Column('gift_pricing_basis', sa.String(40), nullable=False,
                                   server_default='legacy-single-price'))
        batch.create_check_constraint('ck_record_terms_gift_cost', 'gift_cost_total_cents IS NULL OR gift_cost_total_cents >= 0')
        batch.create_check_constraint('ck_record_terms_gift_basis', "gift_pricing_basis IN ('legacy-single-price','separate-cost-v1')")


def downgrade():
    raise RuntimeError('赠品成本及历史核价依据不可删除；请恢复经过核对的备份')

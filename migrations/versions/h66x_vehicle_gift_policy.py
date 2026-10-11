"""Confirmed vehicle gift-cost policies; existing publications stay unchanged."""
from alembic import op
import sqlalchemy as sa

revision = 'h66x_vehicle_gift_policy'
down_revision = 'h65w_record_brand_catalogs'
branch_labels = None
depends_on = None


def upgrade():
    # No inference from old notes and no retroactive contract/policy updates.
    op.add_column('business_record_vehicle_prices',
        sa.Column('gift_policy', sa.JSON(none_as_null=True), nullable=True))


def downgrade():
    raise RuntimeError('已确认赠品政策是冻结依据，不可删除；请恢复经过核对的备份')

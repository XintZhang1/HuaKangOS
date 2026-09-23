"""Frozen zero-price sales gifts; preserve original addon/v3 quote digests."""
from alembic import op
import sqlalchemy as sa

revision='w35j_addon_gifts'
down_revision='v24i_procurement_prepayments'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('addon_quotes') as batch:
        batch.add_column(sa.Column('pricing_version',sa.Integer(),nullable=False,server_default='1'))
        batch.add_column(sa.Column('gift_terms',sa.JSON(),nullable=False,server_default='{}'))
        batch.drop_constraint('ck_addon_quote_money',type_='check')
        batch.create_check_constraint('ck_addon_quote_money','goods_cents>=0 AND installation_cents>=0 AND discount_cents>=0 AND (pricing_version=2 OR (pricing_version=1 AND goods_cents+installation_cents>0))')
    with op.batch_alter_table('addon_approvals') as batch:
        batch.add_column(sa.Column('gift_confirmed',sa.Boolean(),nullable=False,server_default=sa.false()))


def downgrade():
    raise RuntimeError('赠送核价与原实物事实不可自动删除；请使用经过验证的完整备份恢复')

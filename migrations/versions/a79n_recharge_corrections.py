"""Original bundle cash corrections append the original benefit unit changes."""
from alembic import op
import sqlalchemy as sa

revision='a79n_recharge_corrections'
down_revision='z68m_rework_extensions'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('benefit_wallets') as b:
        b.add_column(sa.Column('correction_units',sa.BigInteger(),nullable=False,server_default='0'))
        b.drop_constraint('ck_benefit_wallet_units',type_='check')
        b.create_check_constraint('ck_benefit_wallet_units','initial_units>0 AND initial_units+correction_units>=0 AND balance_units>=0 AND reserved_units>=0 AND reserved_units<=balance_units AND balance_units<=initial_units+correction_units')
    with op.batch_alter_table('benefit_entries') as b:
        b.drop_constraint('ck_benefit_entry_sign',type_='check')
        b.create_check_constraint('ck_benefit_entry_sign',"(purpose IN ('purchase','grant','exchange_in','reverse') AND units>0) OR (purpose IN ('capture','refund','adjust','exchange_out') AND units<0) OR (purpose='correction' AND units!=0)")
    op.create_table('business_finance_bundle_corrections',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('request_id',sa.Integer(),sa.ForeignKey('business_finance_stored_correction_requests.id'),nullable=False,unique=True),
        sa.Column('purchase_id',sa.Integer(),sa.ForeignKey('recharge_bundle_purchases.id'),nullable=False),
        sa.Column('rule_id',sa.Integer(),sa.ForeignKey('recharge_bundle_rules.id'),nullable=False),
        sa.Column('original_shares',sa.BigInteger(),nullable=False),sa.Column('corrected_shares',sa.BigInteger(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint('original_shares>0 AND corrected_shares>=0',name='ck_finance_bundle_correction_shares'))
    for column in ('store_id','purchase_id'):op.create_index('ix_business_finance_bundle_corrections_'+column,'business_finance_bundle_corrections',[column])
    op.create_table('business_finance_bundle_correction_components',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('correction_id',sa.Integer(),sa.ForeignKey('business_finance_bundle_corrections.id'),nullable=False),
        sa.Column('component_id',sa.Integer(),sa.ForeignKey('recharge_bundle_components.id'),nullable=False),
        sa.Column('wallet_id',sa.Integer(),sa.ForeignKey('benefit_wallets.id'),nullable=False),
        sa.Column('grant_entry_id',sa.Integer(),sa.ForeignKey('benefit_entries.id'),nullable=False),
        sa.Column('units_per_share',sa.BigInteger(),nullable=False),sa.Column('delta_units',sa.BigInteger(),nullable=False),
        sa.Column('expires_on',sa.Date(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('correction_id','component_id',name='uq_finance_bundle_correction_component'),
        sa.CheckConstraint('units_per_share>0',name='ck_finance_bundle_correction_units'))
    for column in ('store_id','correction_id'):op.create_index('ix_business_finance_bundle_correction_components_'+column,'business_finance_bundle_correction_components',[column])
    op.create_table('business_finance_bundle_correction_postings',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('component_id',sa.Integer(),sa.ForeignKey('business_finance_bundle_correction_components.id'),nullable=False,unique=True),
        sa.Column('benefit_entry_id',sa.Integer(),sa.ForeignKey('benefit_entries.id'),nullable=False,unique=True),
        sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_business_finance_bundle_correction_postings_store_id','business_finance_bundle_correction_postings',['store_id'])


def downgrade():raise RuntimeError('原组合本金与权益误记更正不可自动抹除；请使用核验备份恢复')

"""Frozen multi-line procurement, batch returns and supplier settlement schema."""
from alembic import op
import sqlalchemy as sa

revision='i309_procurement'
down_revision='h208_master_data'
branch_labels=None
depends_on=None


def scoped():return [sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False)]
def fk(name,target,nullable=False,unique=False):return sa.Column(name,sa.Integer(),sa.ForeignKey(target),nullable=nullable,unique=unique)
def integer(name):return sa.Column(name,sa.BigInteger(),nullable=False)


def upgrade():
    op.create_table('procurement_orders',sa.Column('id',sa.Integer(),sa.ForeignKey('flow_cases.id'),primary_key=True),
        sa.Column('store_id',sa.Integer(),nullable=False),fk('supplier_id','master_suppliers.id'),
        sa.Column('supplier_name',sa.String(120),nullable=False),sa.Column('supplier_code',sa.String(60),nullable=False),
        sa.Column('supplier_tax_identifier',sa.String(100),nullable=False),sa.Column('payment_terms_days',sa.Integer(),nullable=False))
    op.create_table('procurement_lines',*scoped(),fk('case_id','flow_cases.id'),fk('item_id','flow_items.id'),
        sa.Column('sku',sa.String(60),nullable=False),sa.Column('item_name',sa.String(120),nullable=False),sa.Column('unit',sa.String(20),nullable=False),
        integer('quantity_milli'),integer('unit_cost_cents'),integer('amount_cents'),
        sa.UniqueConstraint('case_id','item_id',name='uq_procurement_line_item'),
        sa.CheckConstraint('quantity_milli > 0 AND unit_cost_cents >= 0 AND amount_cents >= 0',name='ck_procurement_line_value'))
    op.create_table('procurement_receipts',*scoped(),fk('case_id','flow_cases.id'),fk('line_id','procurement_lines.id'),
        fk('stock_move_id','flow_stock_moves.id',unique=True),integer('quantity_milli'),integer('value_cents'),fk('evidence_id','flow_files.id'),
        sa.Column('due_date',sa.Date(),nullable=False),sa.CheckConstraint('quantity_milli > 0 AND value_cents >= 0',name='ck_procurement_receipt'))
    op.create_table('procurement_returns',*scoped(),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),fk('case_id','flow_cases.id'),
        sa.Column('status',sa.String(20),nullable=False),fk('requested_by','users.id'),fk('approved_by','users.id',nullable=True),
        sa.Column('reason',sa.String(500),nullable=False),fk('evidence_id','flow_files.id'),
        sa.CheckConstraint("status IN ('requested','approved','dispatched','cancelled')",name='ck_procurement_return_state'),
        sa.CheckConstraint("status NOT IN ('approved','dispatched') OR approved_by IS NOT NULL",name='ck_procurement_return_approval'))
    op.create_table('procurement_return_lines',*scoped(),fk('return_id','procurement_returns.id'),fk('receipt_id','procurement_receipts.id'),integer('quantity_milli'),
        sa.UniqueConstraint('return_id','receipt_id',name='uq_procurement_return_receipt'),
        sa.CheckConstraint('quantity_milli > 0',name='ck_procurement_return_quantity'))
    op.create_table('procurement_return_postings',*scoped(),fk('case_id','flow_cases.id'),fk('return_line_id','procurement_return_lines.id',unique=True),
        fk('receipt_id','procurement_receipts.id'),fk('stock_move_id','flow_stock_moves.id',unique=True),integer('quantity_milli'),integer('value_cents'),fk('evidence_id','flow_files.id'),
        sa.CheckConstraint('quantity_milli > 0 AND value_cents >= 0',name='ck_procurement_return_posting'))
    op.create_table('procurement_payments',*scoped(),fk('case_id','flow_cases.id'),fk('cash_id','cash_entries.id',unique=True),fk('account_id','flow_accounts.id'),
        fk('original_id','procurement_payments.id',nullable=True),sa.Column('direction',sa.String(3),nullable=False),integer('amount_cents'),
        sa.Column('reference',sa.String(100),nullable=False),fk('evidence_id','flow_files.id'),
        sa.UniqueConstraint('store_id','account_id','reference',name='uq_procurement_cash_reference'),
        sa.CheckConstraint("amount_cents > 0 AND ((direction='out' AND original_id IS NULL) OR (direction='in' AND original_id IS NOT NULL))",name='ck_procurement_payment'))
    indexes={'orders':['supplier_id'],'lines':['case_id'],'receipts':['case_id','line_id'],'returns':['case_id'],
        'return_lines':['return_id'],'return_postings':['case_id','receipt_id'],'payments':['case_id']}
    for suffix,columns in indexes.items():
        table='procurement_'+suffix
        for column in ['store_id']+columns:op.create_index('ix_'+table+'_'+column,table,[column])


def downgrade():
    raise RuntimeError('采购、库存和供应商结算事实不可删除降级；请恢复已验证的一致备份')

"""Multi-store ownership and the approval-gated maintenance ledger.

Revision ID: b702_multistore_feedback
Revises: 59100965745a
"""
from alembic import op
import sqlalchemy as sa

revision = 'b702_multistore_feedback'
down_revision = '59100965745a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('stores',
        sa.Column('id',sa.Integer(),primary_key=True), sa.Column('code',sa.String(30),nullable=False,unique=True),
        sa.Column('name',sa.String(100),nullable=False), sa.Column('active',sa.Boolean(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_table('user_stores',sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),primary_key=True),
        sa.Column('store_id',sa.Integer(),sa.ForeignKey('stores.id'),primary_key=True))
    db=op.get_bind()
    if db.scalar(sa.text('SELECT COUNT(*) FROM users')):
        db.execute(sa.text("INSERT INTO stores(id,code,name,active,created_at) VALUES(1,'MAIN','默认门店',:active,CURRENT_TIMESTAMP)"),{'active':True})
        db.execute(sa.text('INSERT INTO user_stores(user_id,store_id) SELECT id,1 FROM users'))
    table_names=['vehicles','sales','repairs','policies','cash_entries','audit_logs','findings','daily_reports']
    short={'vehicles':'vehicle','sales':'sale','repairs':'repair','policies':'policy','cash_entries':'cash'}
    for table in table_names:
        # Existing v0.1 data remains owned by the default store, never duplicated.
        op.add_column(table,sa.Column('store_id',sa.Integer(),nullable=False,server_default='1'))
        op.create_index('ix_'+table+'_store_id',table,['store_id'])
        if table in short:
            old=next(u for u in sa.inspect(db).get_unique_constraints(table) if u['column_names']==['doc_no'])
            naming={'uq':'uq_%(table_name)s_%(column_0_name)s'}
            with op.batch_alter_table(table,naming_convention=naming) as batch:
                batch.drop_constraint(old['name'] or 'uq_'+table+'_doc_no',type_='unique')
                batch.create_unique_constraint('uq_'+short[table]+'_store_doc',['store_id','doc_no'])
        if table=='daily_reports':
            with op.batch_alter_table(table) as batch:
                batch.drop_constraint('uq_report_input',type_='unique')
                batch.create_unique_constraint('uq_report_input',['store_id','business_date','source_revision','config_hash','ai_requested'])
    op.create_table('feedback',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('created_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('title',sa.String(160),nullable=False),sa.Column('description',sa.Text(),nullable=False),
        sa.Column('category',sa.String(30),nullable=False),sa.Column('status',sa.String(30),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('base_sha',sa.String(40),nullable=False),
        sa.Column('head_sha',sa.String(40),nullable=False),sa.Column('branch',sa.String(120),nullable=False),
        sa.Column('proposal',sa.JSON(),nullable=False),sa.Column('test_result',sa.JSON(),nullable=False),
        sa.Column('review_url',sa.String(500),nullable=False),sa.Column('approval_token_hash',sa.String(64),nullable=False),
        sa.Column('approval_expires_at',sa.DateTime(),nullable=True),sa.Column('approved_by',sa.String(100),nullable=False),
        sa.Column('approved_sha',sa.String(40),nullable=False),sa.Column('approved_at',sa.DateTime(),nullable=True),
        sa.Column('notification_sent',sa.Boolean(),nullable=False),sa.Column('last_error',sa.String(500),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False))
    op.create_index('ix_feedback_store_id','feedback',['store_id'])
    op.create_index('ix_feedback_status','feedback',['status'])
    op.create_table('maintenance_events',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('feedback_id',sa.Integer(),sa.ForeignKey('feedback.id'),nullable=False),
        sa.Column('action',sa.String(40),nullable=False),sa.Column('actor',sa.String(100),nullable=False),
        sa.Column('detail',sa.Text(),nullable=False),sa.Column('occurred_at',sa.DateTime(),nullable=False))
    op.create_index('ix_maintenance_events_feedback_id','maintenance_events',['feedback_id'])
    op.create_table('deployments',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('feedback_id',sa.Integer(),sa.ForeignKey('feedback.id'),unique=True,nullable=False),
        sa.Column('sha',sa.String(40),nullable=False),sa.Column('previous_sha',sa.String(40),nullable=False),
        sa.Column('previous_path',sa.Text(),nullable=False),sa.Column('release_path',sa.Text(),nullable=False),
        sa.Column('status',sa.String(30),nullable=False),sa.Column('backup_path',sa.Text(),nullable=False),
        sa.Column('error',sa.String(500),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_table('bot_receipts',sa.Column('event_id',sa.String(160),primary_key=True),sa.Column('occurred_at',sa.DateTime(),nullable=False))
    if db.dialect.name=='postgresql':
        # Explicit id=1 backfill must not leave the sequence pointing at 1.
        db.execute(sa.text("SELECT setval(pg_get_serial_sequence('stores','id'), COALESCE(MAX(id),1), MAX(id) IS NOT NULL) FROM stores"))


def downgrade():
    raise RuntimeError('Multi-store migration is not reversible by merging stores. Restore a verified pre-upgrade backup instead.')

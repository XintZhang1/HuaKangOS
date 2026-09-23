"""Original found-goods return searches; append-only, no second loss posting."""
from alembic import op
import sqlalchemy as sa

revision = 'o57b_found_transit_searches'
down_revision = 'n46a_operations_extensions'
branch_labels = None
depends_on = None


def _local_columns():
    return [sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False)]


def _dates():
    return [sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False)]


def upgrade():
    with op.batch_alter_table('transfer_goods_recoveries') as batch:
        batch.drop_constraint('ck_found_state', type_='check')
        batch.drop_constraint('ck_found_active', type_='check')
        batch.create_check_constraint('ck_found_state', "status IN ('preparing','transit','review','approved','financial','closed','cancelled','unlocated')")
        batch.create_check_constraint('ck_found_active', "(status IN ('closed','cancelled','unlocated') AND active_transfer_id IS NULL) OR (status NOT IN ('closed','cancelled','unlocated') AND active_transfer_id=transfer_id AND active_transfer_id IS NOT NULL)")
    op.create_table('transfer_goods_searches',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('recovery_id', sa.Integer(), sa.ForeignKey('transfer_goods_recoveries.id'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False), *_local_columns(),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('reason', sa.String(1000), nullable=False), *_dates(),
        sa.UniqueConstraint('recovery_id', 'revision', name='uq_found_search_revision'),
        sa.CheckConstraint('revision>0', name='ck_found_search_revision'))
    op.create_table('transfer_goods_search_reviews',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('search_id', sa.Integer(), sa.ForeignKey('transfer_goods_searches.id'), nullable=False),
        *_local_columns(), sa.Column('decision', sa.String(20), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('reason', sa.String(1000), nullable=False), *_dates(),
        sa.UniqueConstraint('search_id', 'store_id', name='uq_found_search_review_store'),
        sa.UniqueConstraint('search_id', 'actor_id', name='uq_found_search_review_actor'),
        sa.CheckConstraint("decision IN ('end_search','keep_searching')", name='ck_found_search_review'))
    op.create_table('transfer_goods_search_outcomes',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('search_id', sa.Integer(), sa.ForeignKey('transfer_goods_searches.id'), nullable=False),
        *_local_columns(), sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('review_id', sa.Integer(), sa.ForeignKey('transfer_goods_search_reviews.id'), nullable=True),
        sa.Column('receive_fact_id', sa.Integer(), sa.ForeignKey('transfer_goods_facts.id'), nullable=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False), *_dates(),
        sa.UniqueConstraint('search_id'), sa.UniqueConstraint('receive_fact_id'),
        sa.CheckConstraint("(kind='arrived' AND receive_fact_id IS NOT NULL AND review_id IS NULL) OR (kind IN ('unlocated','rejected') AND review_id IS NOT NULL AND receive_fact_id IS NULL)", name='ck_found_search_outcome'))
    op.create_table('transfer_goods_reappearances',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('previous_recovery_id', sa.Integer(), sa.ForeignKey('transfer_goods_recoveries.id'), nullable=False),
        sa.Column('search_id', sa.Integer(), sa.ForeignKey('transfer_goods_searches.id'), nullable=False),
        sa.Column('recovery_id', sa.Integer(), sa.ForeignKey('transfer_goods_recoveries.id'), nullable=False),
        *_local_columns(), sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False), *_dates(),
        sa.UniqueConstraint('recovery_id'),
        sa.CheckConstraint('quantity_milli>0 AND previous_recovery_id!=recovery_id', name='ck_found_reappearance'))
    for table, columns in {
        'transfer_goods_searches': ('recovery_id', 'store_id'),
        'transfer_goods_search_reviews': ('search_id', 'store_id'),
        'transfer_goods_search_outcomes': ('store_id',),
        'transfer_goods_reappearances': ('previous_recovery_id', 'search_id', 'store_id'),
    }.items():
        for column in columns:
            op.create_index('ix_' + table + '_' + column, table, [column], unique=False)


def downgrade():
    raise RuntimeError('Immutable search and reappearance facts require a reviewed consistent backup restore; no destructive downgrade')

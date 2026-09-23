"""Shared identities and group principal ledger, frozen schema.

Revision ID: e905_group
Revises: d904_store_roles
"""
from alembic import op
import sqlalchemy as sa

revision = 'e905_group'
down_revision = 'd904_store_roles'
branch_labels = None
depends_on = None


def identity():
    return sa.Column('id', sa.Integer(), primary_key=True)


def versioned():
    return [identity(), sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False)]


def fk(name, table, nullable=False, unique=False):
    return sa.Column(name, sa.Integer(), sa.ForeignKey(table+'.id'), nullable=nullable, unique=unique)


def store():
    return sa.Column('store_id', sa.Integer(), nullable=False)


def upgrade():
    op.create_table('group_identities', *versioned(),
        sa.Column('kind', sa.String(20), nullable=False), sa.Column('name', sa.String(120), nullable=False),
        sa.Column('canonical_key', sa.String(80), nullable=False), sa.Column('search_key', sa.String(100), nullable=False),
        fk('created_by', 'users'), sa.UniqueConstraint('kind', 'canonical_key', name='uq_group_identity_key'),
        sa.CheckConstraint("kind IN ('customer','vehicle','counterparty')", name='ck_group_identity_kind'))
    op.create_index('ix_group_identities_search_key', 'group_identities', ['search_key'])
    op.create_table('group_identity_links', identity(), store(), fk('identity_id', 'group_identities'),
        sa.Column('local_kind', sa.String(20), nullable=False), sa.Column('local_id', sa.Integer(), nullable=False),
        fk('confirmed_by', 'users'), sa.Column('confirmed_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('store_id', 'local_kind', 'local_id', name='uq_group_local_identity'),
        sa.CheckConstraint("local_kind IN ('customer','vehicle','counterparty')", name='ck_group_link_kind'))
    op.create_table('group_members', *versioned(), fk('identity_id', 'group_identities', unique=True),
        sa.Column('number', sa.String(40), nullable=False, unique=True),
        sa.Column('balance_cents', sa.BigInteger(), nullable=False), sa.Column('reserved_cents', sa.BigInteger(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.CheckConstraint('balance_cents >= 0 AND reserved_cents >= 0 AND reserved_cents <= balance_cents',
                           name='ck_group_member_available'))
    op.create_table('group_entries', identity(), fk('member_id', 'group_members'), fk('store_id', 'stores'),
        fk('case_id', 'flow_cases'), sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False), fk('original_id', 'group_entries', nullable=True),
        fk('cash_id', 'cash_entries', nullable=True, unique=True), fk('account_id', 'flow_accounts', nullable=True),
        sa.Column('reference', sa.String(100), nullable=True), fk('evidence_id', 'flow_files'), fk('actor_id', 'users'),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('store_id', 'account_id', 'reference', name='uq_group_cash_reference'),
        sa.CheckConstraint("(purpose IN ('topup','reverse') AND amount_cents > 0) OR "
                           "(purpose IN ('capture','refund') AND amount_cents < 0)", name='ck_group_entry_sign'),
        sa.CheckConstraint("(purpose IN ('topup','refund') AND cash_id IS NOT NULL AND account_id IS NOT NULL "
                           "AND reference IS NOT NULL) OR (purpose IN ('capture','reverse') AND cash_id IS NULL "
                           "AND account_id IS NULL AND reference IS NULL)", name='ck_group_entry_cash'),
        sa.CheckConstraint("(purpose = 'topup' AND original_id IS NULL) OR purpose = 'capture' OR "
                           "(purpose IN ('refund','reverse') AND original_id IS NOT NULL)", name='ck_group_entry_original'))
    op.create_table('group_reservations', *versioned(), store(), fk('member_id', 'group_members'),
        fk('case_id', 'flow_cases'), sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False), fk('evidence_id', 'flow_files'), fk('actor_id', 'users'),
        sa.CheckConstraint("amount_cents > 0 AND status IN ('reserved','captured','released')", name='ck_group_reservation'))
    op.create_table('group_payment_links', identity(), store(), fk('case_id', 'flow_cases'),
        fk('entry_id', 'group_entries', unique=True), fk('reservation_id', 'group_reservations'),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('amount_cents != 0', name='ck_group_payment_amount'))
    op.create_table('group_settlement_entries', identity(), store(), fk('entry_id', 'group_entries'),
        sa.Column('side', sa.String(10), nullable=False), sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('entry_id', 'side', name='uq_group_settlement_side'),
        sa.CheckConstraint("side IN ('center','store') AND amount_cents != 0", name='ck_group_settlement'))
    op.create_table('group_events', identity(), store(), fk('member_id', 'group_members', nullable=True),
        fk('actor_id', 'users'), sa.Column('action', sa.String(30), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False), sa.Column('occurred_at', sa.DateTime(), nullable=False))
    op.create_table('group_receipts', identity(), store(), sa.Column('request_key', sa.String(80), nullable=False),
        fk('actor_id', 'users'), sa.Column('digest', sa.String(64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('store_id', 'request_key', name='uq_group_request'))
    indexes = {'group_identity_links': ['store_id', 'identity_id'], 'group_entries': ['store_id', 'member_id'],
        'group_reservations': ['store_id', 'member_id', 'case_id'], 'group_payment_links': ['store_id', 'case_id'],
        'group_settlement_entries': ['store_id', 'entry_id'], 'group_events': ['store_id'], 'group_receipts': ['store_id']}
    for table, columns in indexes.items():
        for column in columns:
            op.create_index('ix_'+table+'_'+column, table, [column])


def downgrade():
    raise RuntimeError('集团身份与会员账本包含不可丢失的业务历史，请恢复经验证的一致备份，禁止删除账本降级')

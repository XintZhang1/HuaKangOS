"""M8.1 item 2: preparing must leave every original business row untouched.

The existing case checks four models. This one proves the stronger claim a
reviewer actually needs: across the whole isolated synthetic database, not one
row is added, removed or rewritten outside the assistant's own control tables
before an employee clicks confirm. A per-table row digest over the real sqlite
file is used rather than a hand-picked model list, so a table nobody thought of
is covered too.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import hashlib
import sqlite3
import unittest
from contextlib import closing
from sqlalchemy import func, select
# Import the shared baseline first: it loads app.main, which initialises the
# model modules in the order the application itself uses. Importing flow_models
# directly first trips a real circular import.
import test_runtime_integration as baseline
from app.db import SessionLocal, engine
from app.flow_models import Customer
from app.business_assistant_models import AssistantProposal
from app.assistant_runtime_models import RunItem
from fake_provider import Provider, customer_steps

# The assistant's own durable state. It is expected to change while a Run
# prepares; nothing else may. `app_metadata` is a shared table, so its assistant
# rows are excluded by primary key rather than by table name - the worker's own
# liveness heartbeat lives there and must not be mistaken for a business write.
CONTROL_PREFIXES = ('business_assistant_', 'assistant_runtime_')


def business_tables(connection):
    """Original business tables only, read straight from the real file schema."""
    rows = connection.execute("select name from sqlite_master where type='table' "
                              "and name not like 'sqlite_%'").fetchall()
    return sorted(name for (name,) in rows if not name.startswith(CONTROL_PREFIXES))


def assistant_owned(key):
    return type(key) is str and key.startswith(CONTROL_PREFIXES)


NULL = b'\x00null'


def cell(value):
    """A byte form for any stored type, including the binary attachment blobs."""
    if value is None:
        return NULL
    if type(value) is bytes:
        return value
    if type(value) is str:
        return value.encode('utf-8')
    return repr(value).encode('utf-8')


def table_digest(connection, name):
    """Order-independent content digest, so it does not depend on write order."""
    quoted = '"' + name.replace('"', '""') + '"'
    columns = [row[1] for row in connection.execute('pragma table_info(' + quoted + ')')]
    if not columns:
        return 'no-columns'
    select_list = ','.join('"' + column.replace('"', '""') + '"' for column in columns)
    rows = connection.execute('select ' + select_list + ' from ' + quoted).fetchall()
    rows = [row for row in rows if not assistant_owned(row[0])]
    digest = hashlib.sha256()
    for values in sorted(b'\x01'.join(cell(value) for value in row) for row in rows):
        digest.update(values + b'\x02')
    return str(len(rows)) + ':' + digest.hexdigest()


class PrepareZeroWrite(unittest.TestCase):
    setUp = baseline.RuntimeIntegration.setUp
    login = baseline.RuntimeIntegration.login
    count = baseline.RuntimeIntegration.count
    new_run = baseline.RuntimeIntegration.new_run
    tick = baseline.RuntimeIntegration.tick

    def snapshot(self):
        engine.dispose()
        with closing(sqlite3.connect(str(fixture_env.RUNTIME / 'synthetic.sqlite'))) as db:
            return {name: table_digest(db, name) for name in business_tables(db)}

    def metadata_rows(self):
        with closing(sqlite3.connect(str(fixture_env.RUNTIME / 'synthetic.sqlite'))) as db:
            return sorted((row[0], str(row[1])[:80]) for row in
                          db.execute('select key, value from app_metadata'))

    def test_preparation_changes_no_original_business_row(self):
        before = self.snapshot()
        metadata_before = self.metadata_rows()
        self.assertGreaterEqual(len(before), 40, 'the synthetic schema must be present')
        self.assertTrue(any(value.split(':')[0] != '0' for value in before.values()),
                        'the synthetic database must already hold original rows')
        name = '合成零写入' + str(id(self))[-6:]
        sid, _, _ = self.new_run('新建客户' + name + '，暂不允许联系。')
        result = self.tick(Provider(customer_steps(name)))
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['status'], 'succeeded', result)
        after = self.snapshot()
        metadata_after = self.metadata_rows()
        self.assertEqual(sorted(after), sorted(before), 'no business table may appear or vanish')
        changed = {table: (before[table], after[table])
                   for table in before if before[table] != after[table]}
        self.assertEqual(changed, {}, 'preparing must not touch any original business row: '
                         + repr({'metadata_before': metadata_before, 'metadata_after': metadata_after}))
        # The empty delta must not be because nothing was prepared.
        with SessionLocal() as db:
            proposals = db.scalar(select(func.count()).select_from(AssistantProposal))
            confirmations = db.scalar(select(func.count()).select_from(RunItem)
                                      .where(RunItem.kind == 'confirmation'))
        self.assertGreaterEqual(proposals, 1, 'a card must exist for the delta to mean anything')
        self.assertEqual(confirmations, 0, 'nothing may be frozen before the employee clicks')

    def test_the_refusal_to_confirm_without_a_click_is_what_keeps_it_zero(self):
        before = self.snapshot()
        name = '合成零写入点' + str(id(self))[-6:]
        before_customers = self.count(Customer)
        sid, _, _ = self.new_run('新建客户' + name + '，暂不允许联系。')
        self.assertEqual(self.tick(Provider(customer_steps(name)))['status'], 'succeeded')
        with SessionLocal() as db:
            card = db.scalar(select(AssistantProposal))
            self.assertIsNotNone(card)
            card_id, digest = card.id, card.digest
        # A wrong digest is refused before any original write, so the row delta
        # stays empty even though the request was sent.
        refused = self.client.post(baseline.BASE + '/sessions/' + sid + '/proposals/'
                                   + card_id + '/confirm', json={'digest': '0' * 64})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(self.count(Customer), before_customers)
        self.assertEqual(self.snapshot(), before)
        # The correct digest is the employee's click and does write, exactly once.
        accepted = self.client.post(baseline.BASE + '/sessions/' + sid + '/proposals/'
                                    + card_id + '/confirm', json={'digest': digest})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(self.count(Customer), before_customers + 1)
        after = self.snapshot()
        changed = [table for table in before if before[table] != after[table]]
        self.assertTrue(changed, 'the employee click must change original business rows')


if __name__ == '__main__':
    unittest.main()
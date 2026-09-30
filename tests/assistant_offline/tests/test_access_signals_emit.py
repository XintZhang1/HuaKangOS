"""M8.1 item 3, second half: the real access-change path emits its durable signal.

Nothing is simulated. An administrator edits a synthetic employee through the
original route, which writes the immutable `UserAccessReceipt` and its audit
record and - when the runtime switch is on - consumes that same receipt inside
the same transaction and writes the transactional wake outbox. The emitted rows
are then read back from the database.

Calling the emitter afterwards with an already committed receipt is refused by
design (`state.pending` is required), and these cases keep that refusal as
evidence: a signal may only be emitted from the transaction that created its
source, never reconstructed from a stored row.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import unittest
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
import test_runtime_integration as baseline
from app.db import SessionLocal
from app.models import AuditLog, User, UserStore
from app.user_access_models import UserAccessReceipt
from app.assistant_runtime_models import WakeEvent
from app.assistant_runtime_access_signals import emit_user_access_changed


class AccessSignalEmission(unittest.TestCase):
    setUp = baseline.RuntimeIntegration.setUp
    login = baseline.RuntimeIntegration.login
    count = baseline.RuntimeIntegration.count

    def new_employee(self, role='sales'):
        password = fixture_env.PASSWORD.read_text() + 'Initial'
        username = 'signal_' + role + '_' + uuid4().hex[:8]
        created = self.client.post('/api/users', json={
            'username': username, 'display_name': '合成信号员工', 'role': role,
            'password': password, 'store_ids': [1],
            'store_roles': [{'store_id': 1, 'role': role}]})
        self.assertEqual(created.status_code, 201, created.text)
        return created.json()

    def edit(self, account, *, active=True, role=None, request_id=None):
        """One real administrator edit; returns its receipt and the new signals."""
        request_id = request_id or ('sig' + uuid4().hex)
        body = {'request_id': request_id, 'access_version': account['access_version'],
                'store_ids': [1],
                'store_roles': [{'store_id': 1, 'role': role or account['role']}],
                'role': role or account['role'], 'display_name': account['display_name'],
                'active': active}
        with SessionLocal() as db:
            before = {row for row in db.scalars(select(WakeEvent.signal_key))}
        response = self.client.put('/api/users/' + str(account['id']), json=body)
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            after = {row for row in db.scalars(select(WakeEvent.signal_key))}
            receipt = db.scalar(select(UserAccessReceipt)
                                .where(UserAccessReceipt.request_key == request_id))
            self.assertIsNotNone(receipt, 'the original route must write its receipt')
            rows = list(db.scalars(select(WakeEvent).where(
                WakeEvent.signal_key.in_(after - before))))
            return receipt, rows

    def current(self, user_id):
        """The committed account row, as the next edit's precondition."""
        with SessionLocal() as db:
            row = db.get(User, user_id)
            self.assertIsNotNone(row)
            return {'id': row.id, 'role': row.role, 'display_name': row.display_name,
                    'access_version': row.access_version}

    def test_a_real_access_edit_emits_its_durable_signal(self):
        account = self.new_employee()
        receipt, rows = self.edit(account, active=False)
        self.assertTrue(rows, 'a real access change must emit at least one signal')
        self.assertTrue(all(row.topic == 'access.changed' for row in rows), rows)
        self.assertTrue(all(row.source_ref.get('type') == 'user_access_receipt'
                            and row.source_ref.get('id') == receipt.id for row in rows), rows)
        self.assertTrue(all(row.signal_key.startswith('user_access_receipt:' + str(receipt.id))
                            for row in rows), rows)
        with SessionLocal() as db:
            self.assertEqual(db.get(User, account['id']).access_version,
                             account['access_version'] + 1)
            self.assertEqual(db.get(UserAccessReceipt, receipt.id).previous_version,
                             account['access_version'])
        # A second distinct edit must not reuse the first receipt's keys. Its
        # precondition is the version the first edit just committed.
        _, again = self.edit(self.current(account['id']), active=True)
        self.assertTrue(again)
        self.assertFalse({row.signal_key for row in rows} & {row.signal_key for row in again})

    def test_a_committed_receipt_cannot_be_re_emitted_afterwards(self):
        account = self.new_employee()
        receipt, rows = self.edit(account, active=False)
        self.assertTrue(rows)
        with SessionLocal() as db:
            stored = db.get(UserAccessReceipt, receipt.id)
            self.assertIsNotNone(stored)
            # Reconstructing a signal outside its own transaction is refused.
            with self.assertRaises(HTTPException) as refused:
                emit_user_access_changed(db, stored)
        self.assertEqual(refused.exception.status_code, 409)
        with SessionLocal() as db:
            keys = set(db.scalars(select(WakeEvent.signal_key)))
        self.assertEqual(keys & {row.signal_key for row in rows},
                         {row.signal_key for row in rows},
                         'the refusal must not remove or duplicate the real signal')

    def test_a_state_mismatch_is_refused_instead_of_emitting(self):
        account = self.new_employee()
        receipt, _ = self.edit(account, active=False)
        with SessionLocal() as db:
            target = db.get(User, account['id'])
            target.access_version += 1
            db.commit()
        with SessionLocal() as db:
            with self.assertRaises(HTTPException) as refused:
                emit_user_access_changed(db, db.get(UserAccessReceipt, receipt.id))
        self.assertEqual(refused.exception.status_code, 409, 'stale receipts must not emit')

    def test_the_signal_chain_keeps_the_audit_it_was_built_from(self):
        account = self.new_employee()
        receipt, rows = self.edit(account, active=False, role='manager')
        self.assertTrue(rows)
        with SessionLocal() as db:
            audit = db.get(AuditLog, receipt.audit_id)
            self.assertIsNotNone(audit, 'the receipt must point at a real audit record')
            self.assertEqual(audit.action, 'update_user')
            self.assertEqual(audit.entity_id, account['id'])
            self.assertEqual(audit.before_data.get('access_version'), receipt.previous_version)
            self.assertEqual(audit.after_data.get('access_version'), receipt.previous_version + 1)
            self.assertEqual(audit.after_data.get('role'), 'manager')
            self.assertTrue(all(row.source_ref['id'] == receipt.id for row in rows))


if __name__ == '__main__':
    unittest.main()
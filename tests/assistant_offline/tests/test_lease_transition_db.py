"""M8.1 item 3: an expired lease must not overwrite state already committed.

`_append_queue_transition` proves the committed prior state through an
independent reader session, so these cases must arrange that ordering for real:
the old status is committed first, the new state is committed in another
transaction, and only then does the stale writer call the guard. A run row is
built from a real login session because `ck_assistant_run_login_ref` ties
`login_session_ref` to that session's hash, which is what makes the lease
identity verifiable rather than asserted.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import unittest
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import func, select
from app.db import SessionLocal
from app.models import LoginSession, User
from app.assistant_runtime_models import Run, RunEvent
from app.tenancy import set_scope
from app import assistant_runtime_queue as queue
from app.assistant_runtime_events import _append_queue_transition
import test_runtime_integration as baseline

BASE = '/api/business-assistant'


class LeaseTransitionGuard(unittest.TestCase):
    setUp = baseline.RuntimeIntegration.setUp
    login = baseline.RuntimeIntegration.login
    count = baseline.RuntimeIntegration.count

    def real_login_session(self, user_id):
        """The hash the original login wrote; the run row must carry exactly it."""
        with SessionLocal() as db:
            row = db.scalar(select(LoginSession).where(LoginSession.user_id == user_id)
                            .order_by(LoginSession.expires_at.desc()))
            self.assertIsNotNone(row, 'a real login session is required')
            return row.id

    def open_run(self, client):
        """One real conversation and one real Run through the original routes."""
        session = client.post(BASE + '/sessions', json={'title': '合成租约会话'})
        self.assertEqual(session.status_code, 201, session.text)
        run = client.post(BASE + '/sessions/' + session.json()['id'] + '/runs',
                          json={'request_id': 'lease_' + uuid4().hex, 'content': '合成租约演练'})
        self.assertEqual(run.status_code, 202, run.text)
        return run.json()

    def events(self, run_id, event_type=None):
        with SessionLocal() as db:
            query = select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run_id)
            if event_type is not None:
                query = query.where(RunEvent.type == event_type)
            return db.scalar(query)

    def advance(self, run_id, *, status):
        """Commit a newer state in its own transaction, as a later lease would.

        The new version is derived from the committed row (enqueueing already
        advanced it), so the case never depends on a hand-counted number.
        """
        with SessionLocal() as db:
            row = db.get(Run, run_id)
            self.assertIsNotNone(row)
            committed = row.version
            row.status = status
            row.version = committed + 1
            db.commit()
            return committed, committed + 1

    def guard(self, run_id, previous_status, mutate=None):
        """Call the private guard from a fresh session holding that run."""
        with SessionLocal() as db:
            row = db.get(Run, run_id)
            self.assertIsNotNone(row)
            if mutate is not None:
                mutate(row)
            set_scope(db, [row.store_id], row.store_id)
            return _append_queue_transition(db, row, previous_status=previous_status)

    def test_stale_lease_cannot_advance_a_state_committed_by_a_later_lease(self):
        client = self.client
        user_id = client.get('/api/auth/me').json()['id']
        self.real_login_session(user_id)
        run = self.open_run(client)
        # A later lease records 'running' as the committed state.
        committed_version = self.advance(run['id'], status='running')[1]
        events_before = self.events(run['id'])
        # The stale lease still believes 'queued' and asks to finish the run.
        with self.assertRaises(HTTPException) as stale:
            self.guard(run['id'], 'queued', lambda row: setattr(row, 'status', 'succeeded'))
        self.assertEqual(stale.exception.status_code, 409)
        with SessionLocal() as db:
            row = db.get(Run, run['id'])
            self.assertEqual(row.status, 'running', 'the stale write must not land')
            self.assertEqual(row.version, committed_version)
        self.assertEqual(self.events(run['id']), events_before,
                         'a refused transition must not append a lifecycle event')

    def test_a_version_that_did_not_advance_is_refused(self):
        client = self.client
        run = self.open_run(client)
        self.advance(run['id'], status='running')
        # Same status as committed, but the writer's version did not move past it.
        with self.assertRaises(HTTPException) as refused:
            self.guard(run['id'], 'running', lambda row: (setattr(row, 'status', 'succeeded'),
                                                          setattr(row, 'version', 1)))
        self.assertEqual(refused.exception.status_code, 409)
        with SessionLocal() as db:
            self.assertEqual(db.get(Run, run['id']).status, 'running')

    def test_a_repeated_target_state_emits_no_second_event(self):
        client = self.client
        run = self.open_run(client)
        self.advance(run['id'], status='running')
        with SessionLocal() as db:
            row = db.get(Run, run['id'])
            set_scope(db, [row.store_id], row.store_id)
            before = self.events(run['id'])
            # heartbeat and stop requests must not produce a lifecycle event
            self.assertIsNone(_append_queue_transition(db, row, previous_status='running'))
            db.rollback()
        self.assertEqual(self.events(run['id']), before)

    def test_identity_drift_on_the_run_row_is_refused(self):
        client = self.client
        run = self.open_run(client)
        self.advance(run['id'], status='running')
        for field, value in (('owner_id', 999999), ('store_id', 424242),
                             ('session_id', str(uuid4()))):
            with self.subTest(field=field):
                with self.assertRaises(HTTPException) as drifted:
                    self.guard(run['id'], 'queued',
                               lambda row, field=field, value=value: (setattr(row, 'status', 'succeeded'),
                                                                      setattr(row, field, value)))
                self.assertEqual(drifted.exception.status_code, 409)

    def test_the_real_queue_refuses_a_release_from_the_previous_lease(self):
        """The same invariant through the queue's own lease verbs, not the guard."""
        client = self.client
        run = self.open_run(client)
        from datetime import timedelta
        from app.db import utcnow
        now = utcnow()
        with SessionLocal() as db:
            old = queue.claim_next(db, 'old-lease', clock=lambda: now)
        self.assertIsNotNone(old, 'the queue must hand out the queued run')
        later = now + timedelta(seconds=queue.LEASE_SECONDS + 1)
        with SessionLocal() as db:
            self.assertEqual(queue.reclaim_expired(db, clock=lambda: later).status, 'queued')
        latest = later + timedelta(seconds=queue.RETRY_DELAYS[0] + 1)
        with SessionLocal() as db:
            new = queue.claim_next(db, 'new-lease', clock=lambda: latest)
        self.assertIsNotNone(new)
        self.assertGreater(new.fence, old.fence)
        with SessionLocal() as db:
            with self.assertRaises(HTTPException) as refused:
                queue.release(db, old, outcome='succeeded', clock=lambda: latest)
        self.assertEqual(refused.exception.status_code, 409)
        with SessionLocal() as db:
            row = db.get(Run, run['id'])
            self.assertEqual(row.status, 'running')
            self.assertEqual(row.lease_owner, 'new-lease')
            self.assertEqual(row.fence, new.fence)


if __name__ == '__main__':
    unittest.main()
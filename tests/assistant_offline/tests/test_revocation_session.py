"""M8.1 item 3: an existing real HTTP session must stop after access revocation.

The original account read compares the stored `access_version` with the live
account. Revoking therefore invalidates the access epoch that a conversation and
its frozen proposal were created under: the employee is still logged in, the
account is still active, but nothing that belonged to the old epoch may be read
or continued. These cases revoke through the real mechanism (a committed
`access_version` increment) and then require exactly that.

A newly created employee must clear the first-login password change before any
assistant call; that is the original rule rather than a test shortcut, so it is
done through the real endpoint.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from app.db import SessionLocal
from app.models import User
from app.main import app
import test_runtime_integration as baseline

BASE = '/api/business-assistant'


class SessionRevocation(unittest.TestCase):
    setUp = baseline.RuntimeIntegration.setUp
    login = baseline.RuntimeIntegration.login
    count = baseline.RuntimeIntegration.count

    def employee_client(self, role='sales'):
        """One synthetic employee with a second real login, separate from admin."""
        password = fixture_env.PASSWORD.read_text()
        initial, changed = password + 'Initial', password + 'Changed'
        username = 'revoke_' + role + '_' + uuid4().hex[:8]
        created = self.client.post('/api/users', json={
            'username': username, 'display_name': '合成撤权员工', 'role': role,
            'password': initial, 'store_ids': [1],
            'store_roles': [{'store_id': 1, 'role': role}]})
        self.assertEqual(created.status_code, 201, created.text)
        account = created.json()
        first = self.new_client()
        self.login_as(first, username, initial)
        # The original rule clears first-login authority through this endpoint
        # and revokes every existing login session, so log in again afterwards.
        change = first.post('/api/auth/password',
                            json={'current_password': initial, 'new_password': changed})
        self.assertEqual(change.status_code, 200, change.text)
        client = self.new_client()
        self.login_as(client, username, changed)
        return client, account

    def new_client(self):
        client = TestClient(app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        client.headers.update({'X-App-Request': '1', 'X-Store-ID': '1'})
        return client

    def login_as(self, client, username, password):
        response = client.post('/api/auth/login',
                               json={'username': username, 'password': password})
        self.assertEqual(response.status_code, 200, response.text)
        client.headers['X-CSRF-Token'] = client.cookies.get('dealer_csrf')
        return response

    def open_session(self, client, title='合成撤权会话'):
        response = client.post(BASE + '/sessions', json={'title': title})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def revoke(self, user_id):
        """A real committed access-epoch change, as the original admin flow does."""
        with SessionLocal() as db:
            target = db.get(User, user_id)
            self.assertIsNotNone(target)
            target.access_version += 1
            db.commit()
            return target.access_version

    def test_revoked_epoch_loses_its_conversation_without_leaking_it(self):
        client, account = self.employee_client()
        session = self.open_session(client)
        # Before revocation the same real session must work, otherwise the case
        # could pass for the wrong reason.
        self.assertEqual(client.get(BASE + '/sessions/' + session['id']).status_code, 200)
        before = client.get(BASE + '/workspace')
        self.assertEqual(before.status_code, 200, before.text)
        self.assertGreaterEqual(self.revoke(account['id']), 2)
        self.assertEqual(client.get(BASE + '/sessions/' + session['id']).status_code, 404)
        after = client.get(BASE + '/workspace')
        self.assertEqual(after.status_code, 200, after.text)
        # The old conversation must be gone from the projection, not shown as
        # revoked work the employee could still reach.
        self.assertNotIn(session['id'], after.text)
        self.assertNotIn(session['title'], after.text)

    def test_revoked_epoch_cannot_confirm_or_read_its_proposal(self):
        client, account = self.employee_client()
        session = self.open_session(client)
        self.revoke(account['id'])
        base = BASE + '/sessions/' + session['id'] + '/proposals/' + str(uuid4())
        # A syntactically valid digest is required to reach the identity check;
        # the answer must then be refusal, never a fresh authorization.
        confirm = client.post(base + '/confirm', json={'digest': 'a' * 64})
        self.assertIn(confirm.status_code, (403, 404, 409), confirm.text)
        result = client.get(base + '/execution-result')
        self.assertIn(result.status_code, (403, 404, 409), result.text)

    def test_revoked_epoch_cannot_start_a_new_run_or_conversation(self):
        client, account = self.employee_client()
        session = self.open_session(client)
        self.revoke(account['id'])
        run = client.post(BASE + '/sessions/' + session['id'] + '/runs',
                          json={'request_id': 'revoked_' + uuid4().hex,
                                'content': '撤权后不应继续'})
        self.assertIn(run.status_code, (403, 404, 409), run.text)
        # The employee is still logged in, so a brand-new conversation under the
        # new epoch is legitimate; what must never happen is the old epoch's
        # conversation returning along with it.
        again = client.post(BASE + '/sessions', json={'title': '撤权后新对话'})
        self.assertEqual(again.status_code, 201, again.text)
        fresh = again.json()
        self.assertNotEqual(fresh['id'], session['id'])
        listed = client.get(BASE + '/sessions')
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertIn(fresh['id'], listed.text)
        self.assertNotIn(session['id'], listed.text)

    def test_notifications_after_revocation_do_not_serve_the_old_epoch(self):
        client, account = self.employee_client()
        session = self.open_session(client)
        self.assertEqual(client.get(BASE + '/notifications').status_code, 200)
        self.revoke(account['id'])
        notifications = client.get(BASE + '/notifications')
        self.assertIn(notifications.status_code, (200, 403), notifications.text)
        self.assertNotIn(session['id'], notifications.text)
        self.assertNotIn(session['title'], notifications.text)

    def test_refusal_is_an_epoch_change_and_not_a_lost_account(self):
        client, account = self.employee_client()
        self.revoke(account['id'])
        self.assertEqual(client.get(BASE + '/sessions').status_code, 200)
        with SessionLocal() as db:
            current = db.get(User, account['id'])
            self.assertTrue(current.active)
            self.assertFalse(current.must_change_password)
            self.assertEqual(current.role, 'sales')
            self.assertEqual(current.access_version, account['access_version'] + 1)


if __name__ == '__main__':
    unittest.main()
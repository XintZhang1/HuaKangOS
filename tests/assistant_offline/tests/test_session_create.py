"""New assistant conversations must not promote an obsolete authentication snapshot."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import sqlite3
import unittest
from uuid import uuid4
from unittest.mock import patch
from fastapi import Depends, HTTPException, Request
from sqlalchemy import event, func, select
from app.main import app
from app.db import SessionLocal, engine, get_db
from app.security import get_user
from app.models import AppMetadata, User, Store, UserStore, LoginSession, CashEntry
from app.flow_models import Customer, Case, StockMove
from app.business_assistant_models import AssistantSession
from app import business_assistant_service as service
import test_runtime_integration as baseline
import test_procurement_repair_facts as shared


class SessionCreation(unittest.TestCase):
    setUp = baseline.RuntimeIntegration.setUp
    login = baseline.RuntimeIntegration.login
    count = baseline.RuntimeIntegration.count
    _baseline = baseline
    login_employee = shared.ProcurementNativeFlow.login_employee

    @contextmanager
    def after_auth_commit(self, mutation=None):
        """A separate real WAL commit after the request's original auth reads."""
        calls = []
        def authenticate_then_commit(request: Request, db=Depends(get_db)):
            user = get_user(request, db)
            if request.method == 'POST' and request.url.path == '/api/business-assistant/sessions':
                calls.append(user.id)
                with SessionLocal() as writer:
                    writer.add(AppMetadata(key='offline_session_'+uuid4().hex, value={'synthetic':True}))
                    if mutation:
                        mutation(writer, user, request.state.session_hash)
                    writer.commit()
            return user
        self.assertNotIn(get_user, app.dependency_overrides)
        app.dependency_overrides[get_user] = authenticate_then_commit
        try:
            yield calls
        finally:
            app.dependency_overrides.pop(get_user, None)

    def post(self, client=None):
        return (client or self.client).post('/api/business-assistant/sessions', json={'title':'合成并发新对话'})

    def test_concurrent_commit_does_not_turn_new_conversation_into_conflict(self):
        codes = []
        def capture(context):
            codes.append(getattr(context.original_exception, 'sqlite_errorcode', None))
        before = self.count(AssistantSession)
        business = [self.count(model) for model in (Customer, Case, CashEntry, StockMove)]
        event.listen(engine, 'handle_error', capture)
        try:
            with self.after_auth_commit() as calls:
                response = self.post()
        finally:
            event.remove(engine, 'handle_error', capture)
        self.assertEqual(response.status_code, 201, {'status':response.status_code, 'sqlite_codes':codes})
        self.assertEqual(len(calls), 1)
        self.assertEqual(codes, [])
        self.assertEqual(self.count(AssistantSession), before + 1)
        self.assertEqual([self.count(model) for model in (Customer, Case, CashEntry, StockMove)], business)
        self.assertEqual(response.json()['messages'], [])
        self.assertEqual(response.json()['proposals'], [])

    def revoked(self, mutation, status, client=None):
        before = self.count(AssistantSession)
        with self.after_auth_commit(mutation):
            response = self.post(client)
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(self.count(AssistantSession), before)
        self.assertNotIn('set-cookie', response.headers)

    def test_logout_between_authentication_and_creation_is_rechecked(self):
        self.revoked(lambda db,user,login: db.delete(db.get(LoginSession, login)), 401)

    def test_account_disable_between_authentication_and_creation_is_rechecked(self):
        self.revoked(lambda db,user,login: setattr(db.get(User, user.id), 'active', False), 401)

    def test_store_disable_between_authentication_and_creation_is_rechecked(self):
        self.revoked(lambda db,user,login: setattr(db.get(Store, 1), 'active', False), 409)

    def test_forced_password_change_cannot_reuse_original_authentication(self):
        self.revoked(lambda db,user,login: setattr(db.get(User, user.id), 'must_change_password', True), 403)

    def test_access_epoch_change_rejects_instead_of_reinterpreting_employee_intent(self):
        def mutate(db, user, login):
            account = db.get(User, user.id)
            account.access_version += 1
        self.revoked(mutate, 409)

    def test_changed_store_role_cannot_create_under_a_new_role_implicitly(self):
        client = self.login_employee('sales')
        def mutate(db, user, login):
            membership = db.scalar(select(UserStore).where(UserStore.user_id == user.id, UserStore.store_id == 1))
            membership.role = 'manager'
            db.get(User, user.id).access_version += 1
        self.revoked(mutate, 409, client)

    def test_membership_removed_cannot_create_under_old_store_authority(self):
        client = self.login_employee('sales')
        def mutate(db, user, login):
            membership = db.scalar(select(UserStore).where(UserStore.user_id == user.id, UserStore.store_id == 1))
            db.delete(membership)
        self.revoked(mutate, 403, client)

    def test_parallel_new_conversations_each_create_only_their_own_record(self):
        before = self.count(AssistantSession)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.post(), range(8)))
        self.assertEqual([r.status_code for r in results], [201] * 8, [r.text for r in results if r.status_code != 201])
        self.assertEqual(len({r.json()['id'] for r in results}), 8)
        self.assertEqual(self.count(AssistantSession), before + 8)

    def test_response_failure_after_commit_never_repeats_creation(self):
        before = self.count(AssistantSession)
        with patch.object(service, 'session_view', side_effect=HTTPException(503, '合成提交后读取失败')) as view:
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(view.call_count, 1)
        self.assertEqual(self.count(AssistantSession), before + 1)

    def test_bad_csrf_is_still_rejected_before_creation(self):
        before = self.count(AssistantSession)
        self.client.headers['X-CSRF-Token'] = 'INVALID-SYNTHETIC-CSRF'
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(self.count(AssistantSession), before)

    def test_group_summary_is_not_a_session_creation_scope(self):
        before = self.count(AssistantSession)
        self.client.headers['X-Store-ID'] = 'all'
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(self.count(AssistantSession), before)


if __name__ == '__main__':
    unittest.main()

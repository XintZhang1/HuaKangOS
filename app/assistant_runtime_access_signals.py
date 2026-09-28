"""Fixed wake producers for original global permission transactions.

Only a new receipt/audit object in the caller's own Session is accepted. The
original administrator route owns authorization and commit. These helpers
neither change tenant scope nor write a business row: the sole Core write is a
minimal WakeEvent for stores derived from the real permission source.
"""
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from uuid import uuid4

from .config import settings
from .db import utcnow
from .models import AuditLog, Store, User, UserStore
from .user_access_models import UserAccessReceipt
from .assistant_runtime_models import FollowupGrant, Run, WakeEvent


def _invalid():
    raise HTTPException(409, '权限变更唤醒来源不完整，请核对原事务') from None


def _pending(db, source, model):
    if type(source) is not model:
        _invalid()
    state = inspect(source)
    if state.session is not db or not state.pending or db.info.get('aggregate_scope'):
        _invalid()


def _actor(db, actor_id):
    actor = db.scalar(select(User).where(User.id == actor_id))
    if actor is None or not actor.active or actor.role != 'admin' or actor.must_change_password:
        _invalid()


def _audit(db, audit_id, actor_id, action, family, target_id):
    table = AuditLog.__table__
    value = db.execute(select(table).where(table.c.id == audit_id)).mappings().one_or_none()
    if (value is None or value['store_id'] != 0 or value['actor_id'] != actor_id
            or value['action'] != action or value['entity_type'] != family
            or value['entity_id'] != target_id):
        _invalid()
    _actor(db, actor_id)
    return value


def _membership_ids(value):
    if (type(value) is not list
            or any(type(ident) is not int or ident < 1 for ident in value)
            or len(set(value)) != len(value)):
        _invalid()
    return set(value)


def _user_stores(db, target, *, before=None, after=None):
    """Global permission metadata only; never load private plans or payloads."""
    stores = set(db.scalars(select(UserStore.store_id).where(UserStore.user_id == target.id)))
    for snapshot in (before, after):
        if snapshot is not None:
            if type(snapshot) is not dict:
                _invalid()
            stores.update(_membership_ids(snapshot.get('store_ids')))
    if target.role == 'admin' or any(snapshot and snapshot.get('role') == 'admin'
                                    for snapshot in (before, after)):
        stores.update(db.scalars(select(Store.id)))
    # Revocation must also reach a former store after its membership was removed.
    # These fixed Core reads inspect only target-owned runtime routing metadata.
    for model in (FollowupGrant, Run):
        table = model.__table__
        stores.update(db.scalars(select(table.c.store_id).where(table.c.owner_id == target.id)))
    existing = set(db.scalars(select(Store.id).where(Store.id.in_(stores))))
    if existing != stores:
        _invalid()
    return sorted(stores)


def _emit(db, stores, *, key_prefix, topic, source_ref):
    """The fixed cross-store write surface; scope and business tables are intact."""
    table = WakeEvent.__table__
    emitted = []
    for store_id in stores:
        values = {'signal_key': key_prefix + ':store:' + str(store_id), 'topic': topic,
                  'store_id': store_id, 'object_ref': None, 'proposal_id': None,
                  'task_id': None, 'plan_id': None, 'source_ref': dict(source_ref)}

        def existing():
            row = db.execute(select(table).where(table.c.signal_key == values['signal_key'])).mappings().one_or_none()
            if row is not None and any(row[key] != value for key, value in values.items()):
                _invalid()
            return row

        prior = existing()
        if prior is not None:
            emitted.append(prior['id'])
            continue
        ident, now = str(uuid4()), utcnow()
        try:
            with db.begin_nested():
                db.execute(table.insert().values(id=ident, **values, state='pending', attempt=0,
                    next_attempt_at=now, created_at=now, dispatched_at=None))
        except IntegrityError:
            prior = existing()
            if prior is None:
                _invalid()
            ident = prior['id']
        emitted.append(ident)
    return tuple(emitted)


def emit_user_access_changed(db, receipt):
    """Consume the new immutable access receipt before its owner's commit."""
    if not settings.assistant_runtime_enabled:
        return ()
    _pending(db, receipt, UserAccessReceipt)
    db.flush()
    target = db.scalar(select(User).where(User.id == receipt.target_id))
    audit = _audit(db, receipt.audit_id, receipt.actor_id, 'update_user', 'users', receipt.target_id)
    before, after = audit['before_data'], audit['after_data']
    if (target is None or type(before) is not dict or type(after) is not dict
            or receipt.result != after or before.get('id') != target.id or after.get('id') != target.id
            or before.get('access_version') != receipt.previous_version
            or after.get('access_version') != receipt.previous_version + 1
            or target.access_version != after['access_version']
            or target.role != after.get('role') or target.active is not after.get('active')):
        _invalid()
    current_stores = set(db.scalars(select(UserStore.store_id).where(UserStore.user_id == target.id)))
    if _membership_ids(after.get('store_ids')) != current_stores:
        _invalid()
    return _emit(db, _user_stores(db, target, before=before, after=after),
        key_prefix='user_access_receipt:' + str(receipt.id), topic='access.changed',
        source_ref={'type': 'user_access_receipt', 'id': receipt.id, 'version': target.access_version})


def emit_user_security_changed(db, audit_record):
    """A real administrator password reset invalidates first-password authority."""
    if not settings.assistant_runtime_enabled:
        return ()
    _pending(db, audit_record, AuditLog)
    db.flush()
    audit = _audit(db, audit_record.id, audit_record.actor_id, 'reset_password', 'users', audit_record.entity_id)
    target = db.scalar(select(User).where(User.id == audit['entity_id']))
    if target is None or not target.must_change_password or target.id == audit['actor_id']:
        _invalid()
    return _emit(db, _user_stores(db, target),
        key_prefix='audit_log:' + str(audit['id']) + ':access', topic='access.changed',
        source_ref={'type': 'audit_log', 'id': audit['id'], 'version': None})


def emit_store_access_changed(db, audit_record):
    """Store has no version column; its actual update audit is the source ID."""
    if not settings.assistant_runtime_enabled:
        return ()
    _pending(db, audit_record, AuditLog)
    db.flush()
    audit = _audit(db, audit_record.id, audit_record.actor_id, 'update_store', 'stores', audit_record.entity_id)
    target = db.scalar(select(Store).where(Store.id == audit['entity_id']))
    before, after = audit['before_data'], audit['after_data']
    if (target is None or type(before) is not dict or type(after) is not dict
            or before.get('id') != target.id or after.get('id') != target.id
            or type(before.get('active')) is not bool or type(after.get('active')) is not bool
            or before['active'] is after['active'] or target.active is not after['active']):
        _invalid()
    return _emit(db, [target.id], key_prefix='audit_log:' + str(audit['id']), topic='store.access_changed',
        source_ref={'type': 'audit_log', 'id': audit['id'], 'version': None})

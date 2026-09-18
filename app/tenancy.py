"""Request-scoped ownership. Internal jobs must explicitly set a single-store scope.
Do not use raw SQL for business queries: ORM SELECT criteria enforce store boundaries.
"""
from sqlalchemy import select, event, inspect
from sqlalchemy.orm import Session, with_loader_criteria
from fastapi import HTTPException
from .models import Store, StoreScoped, UserStore, AuditLog


def accessible_stores(db, user):
    stmt = select(Store).where(Store.active.is_(True)).order_by(Store.id)
    if user.role != 'admin':
        stmt = stmt.join(UserStore, UserStore.store_id == Store.id).where(UserStore.user_id == user.id)
    return list(db.scalars(stmt))


def set_scope(db, store_ids, write_store=None, global_audit=False):
    db.info['store_scope'] = tuple(sorted(set(store_ids))) + ((0,) if global_audit else ())
    db.info['write_store'] = write_store


def single_store(db):
    store = db.info.get('write_store')
    if not store:
        raise HTTPException(409, '请先选择一家门店，再录入、修改或生成日报')
    return store


def attach_scope(request, db, user):
    stores = accessible_stores(db, user)
    requested = request.headers.get('X-Store-ID', '')
    ids = [s.id for s in stores]
    if requested == 'all':
        if user.role not in {'admin','manager','finance','auditor'}:
            raise HTTPException(403, '该角色不能访问跨门店汇总')
        active = None
    elif requested:
        try: active = int(requested)
        except ValueError: raise HTTPException(422, '门店参数无效')
        if active not in ids: raise HTTPException(403, '没有该门店的访问权限，或门店已停用')
    else:
        active = ids[0] if ids else None
    if not ids and not request.url.path.startswith(('/api/auth/', '/api/users', '/api/stores')):
        raise HTTPException(403, '账号尚未分配可用门店，请联系管理员')
    set_scope(db, ids if active is None else [active], active, user.role == 'admin')
    user._store_ids = ids
    user._stores = [{'id':s.id,'code':s.code,'name':s.name} for s in stores]
    user._active_store_id = active


@event.listens_for(Session, 'do_orm_execute')
def scoped_select(execute_state):
    ids = execute_state.session.info.get('store_scope')
    if ids is not None and execute_state.is_select:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(StoreScoped, lambda row: row.store_id.in_(ids), include_aliases=True))
    if ids is not None and (execute_state.is_update or execute_state.is_delete):
        # Business state transitions must go through versioned ORM objects, not bulk writes.
        mapper = execute_state.bind_mapper
        if mapper and issubclass(mapper.class_, StoreScoped):
            raise HTTPException(409, '不允许绕过门店与版本校验批量写业务记录')


@event.listens_for(Session, 'before_flush')
def enforce_ownership(db, flush_context, instances):
    scope = db.info.get('store_scope')
    for row in list(db.new) + list(db.dirty) + list(db.deleted):
        if not isinstance(row, StoreScoped): continue
        if row in db.new and row.store_id is None:
            row.store_id = single_store(db) if scope is not None else 1
        if row not in db.new and inspect(row).attrs.store_id.history.has_changes():
            raise HTTPException(409, '业务归属门店不可直接修改；调拨须使用独立流程')
        if scope is not None and row.store_id not in scope and not (isinstance(row, AuditLog) and row.store_id == 0):
            raise HTTPException(403, '禁止跨门店写入')
        if scope is not None and not isinstance(row, AuditLog) and row.store_id != db.info.get('write_store'):
            raise HTTPException(409, '跨门店汇总为只读；请切换到具体门店')

"""Request-scoped ownership. Internal jobs must explicitly set a single-store scope.
Do not use raw SQL for business queries: ORM SELECT criteria enforce store boundaries.
"""
from sqlalchemy import select, event, inspect
from sqlalchemy.orm import Session, with_loader_criteria
from fastapi import HTTPException
from .models import Store, StoreScoped, UserStore, AuditLog


SUMMARY_ROLES = {'admin', 'manager', 'finance', 'auditor', 'general_manager', 'deputy_general_manager', 'chairman'}


class RequestPrincipal:
    """Request-only role projection. Never assign an active role to the ORM User."""
    def __init__(self, user, role, **context):
        self._account = user._account if isinstance(user, RequestPrincipal) else user
        self.role = role
        self.__dict__.update(context)

    @property
    def account_role(self):
        return self._account.role

    def __getattr__(self, name):
        return getattr(self._account, name)


def account_role(user):
    return getattr(user, 'account_role', user.role)


def role_for_store(db, user, store_id):
    if not user or not user.active:
        return None
    if account_role(user) == 'admin':
        return 'admin'
    membership = db.scalar(select(UserStore).where(UserStore.user_id == user.id, UserStore.store_id == store_id))
    return (membership.role or account_role(user)) if membership else None


def project_user(user, role):
    return RequestPrincipal(user, role)


def accessible_stores(db, user):
    stmt = select(Store).where(Store.active.is_(True)).order_by(Store.id)
    if account_role(user) != 'admin':
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
    roles = {s.id: role_for_store(db, user, s.id) for s in stores}
    group_ids = [sid for sid in ids if roles[sid] in SUMMARY_ROLES]
    can_summary = account_role(user) == 'admin' or bool(user.can_group_summary)
    if requested == 'all':
        if not can_summary or not group_ids:
            raise HTTPException(403, '账号未获集团汇总权限，或没有可汇总的管理岗位门店')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.url.path not in {'/api/auth/password', '/api/auth/logout', '/api/auth/login'}:
            raise HTTPException(409, '跨门店汇总为只读；请切换到具体门店')
        active = None
    elif requested:
        try: active = int(requested)
        except ValueError: raise HTTPException(422, '门店参数无效')
        if active not in ids:
            # Deactivating the store the employee is currently in must not look like a permission
            # problem: the page has to tell them to pick another store. Only reveal that state for
            # a store this account is actually assigned to (or for an administrator, who sees every
            # store); any other id keeps the uniform permission error so an unrelated store's
            # existence or active flag cannot be probed.
            is_admin = account_role(user) == 'admin'
            assigned = db.scalar(select(UserStore).where(UserStore.user_id == user.id,
                                                         UserStore.store_id == active))
            store = db.get(Store, active) if (is_admin or assigned) else None
            if is_admin or (store is not None and not store.active):
                raise HTTPException(409, '当前门店已停用或不存在，请重新选择门店后再办理')
            raise HTTPException(403, '没有该门店的访问权限')
    else:
        active = ids[0] if ids else None
    if not ids and not request.url.path.startswith(('/api/auth/', '/api/users', '/api/stores')):
        raise HTTPException(403, '账号尚未分配可用门店，请联系管理员')
    set_scope(db, group_ids if requested == 'all' else ([active] if active else []), active, account_role(user) == 'admin')
    db.info['aggregate_scope'] = requested == 'all'
    return RequestPrincipal(user, 'auditor' if requested == 'all' else roles.get(active, account_role(user)),
        _store_ids=ids, _stores=[{'id':s.id,'code':s.code,'name':s.name,'role':roles[s.id]} for s in stores],
        _active_store_id=active, _aggregate_scope=requested == 'all',
        _group_store_ids=group_ids if can_summary else [], _can_group_summary=can_summary and bool(group_ids))


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

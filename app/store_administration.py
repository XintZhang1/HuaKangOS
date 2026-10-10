"""Explicit current-store account administration; never a global admin alias."""
import re
from fastapi import HTTPException
from sqlalchemy import select, func, or_
from .models import User, UserStore, Store
from .tenancy import single_store, account_role
from .services import audit

STAFF_ROLES = frozenset({'sales', 'manager', 'clerk', 'finance'})
# A new role must opt into a reviewed API surface. In particular, legacy routes
# derive some role sets dynamically and must not become accessible by accident.
_RECORD_READS = re.compile(r'/api/business-records/(?:'
    r'catalog|contracts(?:/[1-9]\d*(?:/print|/invoice(?:/files/[1-9]\d*/download)?)?)?'
    r'|standard-prices|customers(?:/[1-9]\d*)?|after-sales'
    r'|manual-reports(?:/[1-9]\d*)?|report-prefill|settings|reports(?:/export)?'
    r'|report-periods|monthly-targets|daily-vehicle-reports(?:/export)?'
    r'|daily-reports(?:/(?:preview|export|trend(?:/export)?))?)')


def is_store_admin(user):
    return account_role(user) == 'store_admin' or user.role == 'store_admin'


def guard_request(request, user):
    if not is_store_admin(user):
        return
    method, path = request.method, request.url.path
    allowed = (
        method == 'GET' and (path in {'/api/auth/me', '/api/users', '/api/stores', '/api/audit'}
                            or _RECORD_READS.fullmatch(path))
        or method == 'POST' and (path in {'/api/auth/password', '/api/auth/logout', '/api/users',
            '/api/users/batch'}
            or re.fullmatch(r'/api/users/[1-9]\d*/password', path))
        or method == 'PUT' and re.fullmatch(r'/api/users/[1-9]\d*', path))
    if not allowed or (getattr(user, '_aggregate_scope', False)):
        raise HTTPException(403, '门店管理员仅可读取当前授权门店资料及维护本店普通员工账号，不可办理业务或全局运维')
    if '_huakang_runtime' in request.scope and method in {'POST', 'PUT'}:
        raise HTTPException(403, '员工账号维护须由门店管理员在页面核对办理，助手不能提交')


def validate_role_assignment(body, db=None, target=None):
    """Keep the store administrator an independent identity, including fallbacks."""
    role = body.role
    summary = body.can_group_summary if body.can_group_summary is not None else bool(target and target.can_group_summary)
    existing = {} if target is None else {m.store_id: m.role for m in db.scalars(
        select(UserStore).where(UserStore.user_id == target.id))}
    explicit = getattr(body, 'store_roles', None)
    ids = getattr(body, 'store_ids', None)
    if explicit is not None:
        effective = [m.role for m in explicit]
    elif ids is not None:
        effective = [existing.get(key) or role for key in ids]
    else:
        effective = [value or role for value in existing.values()]
    if (role == 'store_admin' and (summary or len(effective) != 1 or any(value != 'store_admin' for value in effective))
            or role != 'store_admin' and 'store_admin' in effective):
        raise HTTPException(422, '门店管理员须使用独立账号，仅可授权一家门店、岗位为门店管理员且不能授予集团汇总')


def validate_staff_payload(body, store_id, *, create=False):
    if body.role not in STAFF_ROLES or getattr(body, 'can_group_summary', False):
        raise HTTPException(403, '门店管理员只能维护销售、销售经理、销售内勤、收银账号，不能授予管理或集团权限')
    ids, roles = getattr(body, 'store_ids', None), getattr(body, 'store_roles', None)
    if ids is not None and (len(ids) != 1 or ids[0] != store_id):
        raise HTTPException(403, '员工账号只能归属当前门店，不能新增或移除其它门店授权')
    if roles is not None and (len(roles) != 1 or roles[0].store_id != store_id or roles[0].role not in STAFF_ROLES):
        raise HTTPException(403, '员工岗位只能分配给当前门店的普通岗位')
    if create and ids is None and roles is None:
        raise HTTPException(403, '请明确选择当前门店及普通岗位')


def revalidate_actor(db, principal, actor=None):
    store_id = single_store(db)
    actor = actor or db.scalar(select(User).where(User.id == principal.id).with_for_update()
                              .execution_options(populate_existing=True))
    membership = db.scalar(select(UserStore).where(UserStore.user_id == principal.id,
        UserStore.store_id == store_id).with_for_update().execution_options(populate_existing=True))
    store = db.scalar(select(Store).where(Store.id == store_id).with_for_update()
                      .execution_options(populate_existing=True))
    all_memberships = list(db.scalars(select(UserStore).where(UserStore.user_id == principal.id)
        .with_for_update().execution_options(populate_existing=True)))
    if (len(all_memberships) != 1 or not actor or not actor.active or actor.must_change_password or actor.role != 'store_admin'
            or actor.can_group_summary or not membership or membership.role != 'store_admin'
            or not store or not store.active):
        raise HTTPException(403, '门店管理员或当前门店授权已变化，请重新登录核对权限')
    return store_id


def manageable_query(principal):
    store_id = getattr(principal, '_active_store_id', None)
    memberships = select(func.count()).select_from(UserStore).where(UserStore.user_id == User.id).correlate(User).scalar_subquery()
    return (select(User).join(UserStore, UserStore.user_id == User.id).where(
        User.id != principal.id, User.role.in_(STAFF_ROLES), User.can_group_summary.is_(False),
        UserStore.store_id == store_id, memberships == 1,
        or_(UserStore.role.is_(None), UserStore.role.in_(STAFF_ROLES))))


def require_target(db, principal, target, *, lock=True):
    store_id = single_store(db)
    query = select(UserStore).where(UserStore.user_id == target.id).order_by(UserStore.store_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    memberships = list(db.scalars(query))
    if (target.id == principal.id or target.role not in STAFF_ROLES or target.can_group_summary
            or len(memberships) != 1 or memberships[0].store_id != store_id
            or (memberships[0].role or target.role) not in STAFF_ROLES):
        raise HTTPException(404, '本店可维护员工账号不存在')


def lock_target(db, principal, target_id):
    rows = list(db.scalars(select(User).where(User.id.in_({principal.id, target_id}))
        .order_by(User.id).with_for_update().execution_options(populate_existing=True)))
    actor = next((row for row in rows if row.id == principal.id), None)
    revalidate_actor(db, principal, actor)
    target = next((row for row in rows if row.id == target_id), None)
    if target is None:
        raise HTTPException(404, '本店可维护员工账号不存在')
    require_target(db, principal, target)
    return target


def account_event(db, principal, action, target, *, reason='', before=None, after=None):
    """Only local, credential-free account facts; no global users audit payload."""
    if after is None:
        store_id = single_store(db)
        member = db.scalar(select(UserStore).where(UserStore.user_id == target.id, UserStore.store_id == store_id))
        after = {key: getattr(target, key) for key in ('id', 'username', 'display_name', 'role', 'active', 'access_version')}
        after.update(account_role=target.role, store_ids=[store_id], can_group_summary=False,
            store_roles=[{'store_id': store_id, 'role': member.role or target.role, 'legacy_fallback': member.role is None}])
    after = dict(after, store_id=single_store(db))
    if before is not None:
        before = dict(before, store_id=single_store(db))
    audit(db, principal.id, action, 'store_account', target.id, before=before, after=after, reason=reason)
    return after


def capabilities(principal, roles):
    scoped = is_store_admin(principal)
    return {'scope': 'store' if scoped else 'global',
        'store_id': getattr(principal, '_active_store_id', None) if scoped else None,
        'assignable_roles': sorted(STAFF_ROLES if scoped else roles),
        'create': True, 'edit': True, 'reset_password': True, 'batch': True}


def account_snapshot(value, store_id):
    # This target has already passed the single-store ordinary-account check.
    keys = {'id','username','display_name','role','role_label','account_role','active',
            'access_version','store_ids','store_roles','stores','can_group_summary'}
    return dict({key: val for key, val in value.items() if key in keys}, store_id=store_id)

"""Serialized global administrator changes with optimistic access versions."""
from fastapi import HTTPException
from sqlalchemy import select, update, delete, or_
from sqlalchemy.exc import OperationalError, IntegrityError
from .models import User, UserStore, Store, LoginSession, AuditLog
from .user_access_models import UserAccessReceipt
from .services import audit
from . import store_administration as store_admin_service
from .user_access_integrity import receipt_digest


CONFLICT = '账号授权已被其他管理员修改，请关闭编辑窗口、刷新员工列表并核对最新岗位后重新办理'


def change_access(db, principal, target_id, body, account_info, assign_stores):
    if getattr(principal, '_aggregate_scope', False):
        raise HTTPException(409, '跨门店汇总为只读；请切换到具体门店')
    scoped = store_admin_service.is_store_admin(principal)
    if not scoped and getattr(principal, 'account_role', principal.role) != 'admin':
        raise HTTPException(403, '仅系统管理员可以管理账号')
    values = body.model_dump(exclude={'request_id'}, mode='json')
    scope_id = getattr(principal, '_active_store_id', None) if scoped else 0
    digest = receipt_digest(target_id, values, scope_id)
    try:
        # Lock administrator rows in a shared order: mutual revocations cannot
        # both act on an earlier permission snapshot or remove the final admin.
        locked = list(db.scalars(select(User).where(or_(User.role == 'admin',
            User.id.in_([principal.id, target_id]))).order_by(User.id).with_for_update()
            .execution_options(populate_existing=True)))
        actor = next((u for u in locked if u.id == principal.id), None)
        if scoped:
            store_admin_service.revalidate_actor(db, principal, actor)
        elif not actor or not actor.active or actor.role != 'admin':
            raise HTTPException(403, '管理员权限已变化，请重新登录后核对可用权限')
        if actor.must_change_password:
            raise HTTPException(403, '首次登录必须修改密码')
        target = next((u for u in locked if u.id == target_id), None)
        if scoped:
            if target is None:
                raise HTTPException(404, '本店可维护员工账号不存在')
            store_admin_service.require_target(db, principal, target)
            store_admin_service.validate_staff_payload(body, scope_id)
        prior = db.scalar(select(UserAccessReceipt).where(UserAccessReceipt.actor_id == actor.id,
                                                       UserAccessReceipt.request_key == body.request_id))
        if prior:
            if prior.digest != digest:
                raise HTTPException(409, '此请求号已用于不同的账号修改，请刷新后重新办理')
            return prior.result
        target = next((u for u in locked if u.id == target_id), None)
        if not target:
            raise HTTPException(404, '用户不存在')
        store_admin_service.validate_role_assignment(body, db, target)
        if target.access_version != body.access_version:
            raise HTTPException(409, CONFLICT)
        if target.id == actor.id and (body.role != 'admin' or not body.active):
            raise HTTPException(409, '不能降权或停用当前管理员自身')
        if target.role == 'admin' and target.active and (body.role != 'admin' or not body.active):
            if sum(u.active and u.role == 'admin' and u.id != target.id for u in locked) < 1:
                raise HTTPException(409, '至少保留一名启用的系统管理员')
        before = account_info(db, target)
        if scoped:
            before = store_admin_service.account_snapshot(before, scope_id)
        changes = body.model_dump(exclude={'store_ids', 'store_roles', 'access_version', 'request_id'},
                                  exclude_none=True)
        result = db.execute(update(User).where(User.id == target.id,
            User.access_version == body.access_version).values(**changes,
            access_version=User.access_version + 1).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(409, CONFLICT)
        db.refresh(target)
        if body.store_ids is not None or body.store_roles is not None:
            assign_stores(db, target, body.store_ids, body.store_roles)
        if target.role != 'admin' and target.active and not db.scalar(select(UserStore.user_id)
            .join(Store, Store.id == UserStore.store_id).where(UserStore.user_id == target.id,
                Store.active.is_(True)).limit(1)):
            raise HTTPException(422, '启用的非管理员账号至少分配一家在用门店及对应岗位')
        db.execute(delete(LoginSession).where(LoginSession.user_id == target.id))
        db.flush()
        after = account_info(db, target)
        family = 'store_account' if scoped else 'users'
        if scoped:
            store_admin_service.require_target(db, principal, target)
            after = store_admin_service.account_snapshot(after, scope_id)
            store_admin_service.account_event(db, principal, 'update_user', target, before=before, after=after,
                reason='核对本店账号授权版本后修改；原登录会话全部失效')
        else:
            audit(db, actor.id, 'update_user', 'users', target.id, before, after,
                  reason='核对账号授权版本后修改；原登录会话全部失效')
        db.flush()
        record = db.scalar(select(AuditLog).where(AuditLog.actor_id == actor.id,
            AuditLog.entity_type == family, AuditLog.entity_id == target.id,
            AuditLog.action == 'update_user').order_by(AuditLog.id.desc()))
        receipt = UserAccessReceipt(actor_id=actor.id, target_id=target.id,
            request_key=body.request_id, digest=digest, previous_version=body.access_version,
            request_data=values, result=after, audit_id=record.id)
        db.add(receipt)
        from .config import settings
        if settings.assistant_runtime_enabled:
            from .assistant_runtime_access_signals import emit_user_access_changed
            emit_user_access_changed(db, receipt)
        db.commit()
        return after
    except HTTPException:
        db.rollback()
        raise
    except OperationalError as exc:
        db.rollback()
        code = getattr(exc.orig, 'sqlstate', None) or getattr(exc.orig, 'pgcode', None)
        if code in {'40001', '40P01'} or getattr(exc.orig, 'sqlite_errorcode', 0) & 255 in {5, 6}:
            raise HTTPException(409, CONFLICT) from exc
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, '账号修改发生并发冲突；请保留本次请求号刷新核对，勿重复授权') from exc

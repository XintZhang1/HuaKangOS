"""评审申请的创建、查看与处理。只记录请求和结果，不改变权限、也不执行业务动作。"""
import re

from fastapi import HTTPException
from sqlalchemy import select

from .db import utcnow
from .escalation_models import (CATEGORY_LABELS, Escalation, EscalationEvent, STATUS_LABELS,
                                TARGET_LABELS, STATUSES)
from .security import ROLES
from .services import audit, plain
from .tenancy import single_store

OPERATION_PATTERN = re.compile(r'^(GET|POST|PUT) /api/[A-Za-z0-9_/{}.-]{2,180}$')
REVIEWER_ROLES = {'manager', 'admin'}
MAX_ROWS = 200


def account_role(user):
    return getattr(user, 'account_role', user.role)


def target_role_for(user):
    """本店店长；店长本人或管理员提出时转集团管理员（由服务端判定，模型与前端不能指定）。"""
    return 'admin' if account_role(user) in {'admin', 'manager'} else 'manager'


def is_reviewer(user):
    return account_role(user) in REVIEWER_ROLES


def view(db, row):
    """只暴露申请本身与处理轨迹；不含任何业务数据的越权投影。"""
    events = db.scalars(select(EscalationEvent).where(EscalationEvent.escalation_id == row.id)
                        .order_by(EscalationEvent.id)).all()
    return {**plain(row),
            'requester_role_label': ROLES.get(row.requester_role, row.requester_role),
            'target_label': TARGET_LABELS.get(row.target_role, row.target_role),
            'status_label': STATUS_LABELS.get(row.status, row.status),
            'category_label': CATEGORY_LABELS.get(row.reason_category, row.reason_category),
            'events': [plain(event) for event in events]}


def create(db, user, payload):
    store = single_store(db)
    if payload.reason_category == 'rule':
        # 规则不允许的事项不能靠评审绕过：这正是“模型或上级自造审批”的边界。
        raise HTTPException(422, '业务规则明确不允许的事项不能通过评审绕过，请按页面提示处理')
    subject = (payload.subject or '').strip()
    blocked = (payload.blocked_message or '').strip()
    case_reference = (payload.case_reference or '').strip()
    operation_id = (payload.operation_id or '').strip()
    if len(subject) < 5:
        raise HTTPException(422, '请写清要办的事（至少 5 个字），例如“给这张单批准 5% 折扣”')
    if len(blocked) < 8:
        raise HTTPException(422, '请把系统提示的原文填进来，上级要按它核对是哪一步被挡住')
    if operation_id and not OPERATION_PATTERN.fullmatch(operation_id):
        raise HTTPException(422, '操作编号格式不正确，例如 POST /api/flow/cases/{case_id}/actions/{action}')
    duplicate = db.scalar(select(Escalation).where(
        Escalation.store_id == store, Escalation.requester_id == user.id, Escalation.subject == subject,
        Escalation.case_reference == case_reference, Escalation.status.in_(('open', 'claimed'))))
    if duplicate:
        raise HTTPException(409, '同一件事已经提交过评审，请等待处理或先撤回')
    row = Escalation(store_id=store, requester_id=user.id, requester_role=user.role,
                     target_role=target_role_for(user), subject=subject, case_reference=case_reference,
                     operation_id=operation_id, blocked_message=blocked, reason_category=payload.reason_category,
                     status='open')
    db.add(row)
    db.flush()
    db.add(EscalationEvent(store_id=store, escalation_id=row.id, actor_id=user.id, action='submit', note=subject))
    audit(db, user.id, 'escalation_submit', 'escalations', row.id, reason='提交评审申请：' + subject[:60])
    db.commit()
    return view(db, row)


def listing(db, user, scope='mine', status=''):
    if scope not in {'mine', 'to_review'}:
        raise HTTPException(422, '查询范围不正确')
    if scope == 'to_review':
        if not is_reviewer(user):
            raise HTTPException(403, '只有店长或管理员可以查看待评审')
        # 不能看到自己提交的申请，也不能自己批准自己——与“管理员不能自己申请自己批准”一致。
        statement = select(Escalation).where(Escalation.requester_id != user.id,
                                             Escalation.status.in_(('open', 'claimed')))
        if account_role(user) != 'admin':
            statement = statement.where(Escalation.target_role == account_role(user))
    else:
        statement = select(Escalation).where(Escalation.requester_id == user.id)
    if status:
        if status not in STATUSES:
            raise HTTPException(422, '状态不正确')
        statement = statement.where(Escalation.status == status)
    rows = list(db.scalars(statement.order_by(Escalation.id.desc()).limit(MAX_ROWS)))
    return {'items': [view(db, row) for row in rows], 'scope': scope,
            'targets': TARGET_LABELS, 'statuses': STATUS_LABELS}


def act(db, user, escalation_id, action, version, note=''):
    store = single_store(db)
    # scoped select (not get): a request from another store must not be reachable here.
    row = db.scalar(select(Escalation).where(Escalation.id == escalation_id, Escalation.store_id == store))
    if not row:
        raise HTTPException(404, '评审申请不存在')
    if row.version != version:
        raise HTTPException(409, '这条申请已被其他人处理，请刷新后核对')
    note = (note or '').strip()
    role = account_role(user)
    if action == 'cancel':
        if row.requester_id != user.id and role != 'admin':
            raise HTTPException(403, '只有申请人本人或管理员可以撤回')
        if row.status not in {'open', 'claimed'}:
            raise HTTPException(409, '这条申请已经处理完，不能撤回')
        row.status = 'cancelled'
    else:
        if not is_reviewer(user):
            raise HTTPException(403, '只有店长或管理员可以处理评审申请')
        if row.requester_id == user.id:
            raise HTTPException(403, '不能自己批准自己提交的评审，请交给另一位有权限的同事')
        if role != 'admin' and row.target_role != role:
            raise HTTPException(403, '这条申请不属于你的岗位')
        if action == 'claim':
            if row.status != 'open':
                raise HTTPException(409, '这条申请已被接手或处理完')
            row.status, row.claimed_by_id, row.claimed_at = 'claimed', user.id, utcnow()
        elif action in {'done', 'reject'}:
            if row.status not in {'open', 'claimed'}:
                raise HTTPException(409, '这条申请已经处理完')
            if row.claimed_by_id not in (None, user.id) and role != 'admin':
                raise HTTPException(403, '这条申请已由其他人接手')
            if len(note) < 3:
                raise HTTPException(422, '请写明处理结果或驳回原因（至少 3 个字）')
            row.status = 'done' if action == 'done' else 'rejected'
            row.decided_by_id, row.decided_at, row.decision_note = user.id, utcnow(), note
        else:
            raise HTTPException(404, '不支持的评审操作')
    db.add(EscalationEvent(store_id=store, escalation_id=row.id, actor_id=user.id, action=action,
                           note=row.decision_note if action in {'done', 'reject'} else note))
    audit(db, user.id, 'escalation_' + action, 'escalations', row.id,
          reason=('评审申请：' + (row.decision_note or row.subject))[:200])
    db.commit()
    return view(db, row)

"""评审申请的创建、查看与处理。只记录请求和结果，不改变权限、也不执行业务动作。

评审只能引用**系统自己记下的被挡记录**（escalation_refusals）：申请人自述的类别不作数，
否则"业务规则不允许"的事会被改写成"岗位权限不足"绕过规则。岗位判定一律用当前门店的
实际岗位（请求主体已按门店投影），不是账号级岗位。
"""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select

from .db import utcnow
from .escalation_models import (CATEGORY_LABELS, Escalation, EscalationEvent, Refusal, STATUS_LABELS,
                                TARGET_LABELS, STATUSES)
from .security import ROLES
from .services import audit, plain
from .tenancy import single_store

REVIEWER_ROLES = {'manager', 'admin'}
MAX_ROWS = 200
MAX_REFUSALS = 12
REFUSAL_HOURS = 24
AUTHORITY_HINTS = ('权限', '岗位', '无权', '只有', '仅限', '不属于', '未获')
AMOUNT_HINTS = ('额度', '限额', '上限', '授权金额', '超出授权')
REFUSAL_CATEGORIES = ('authority', 'amount', 'rule')


def account_role(user):
    return getattr(user, 'account_role', user.role)


def store_role(user):
    """当前门店的实际岗位。请求主体已按门店投影，权限判定必须用它。"""
    return getattr(user, 'role', None) or 'unknown'


def classify_refusal(status_code, message):
    """把系统自己的拒绝分类；分不出权限/额度的一律算业务规则，不能走评审。"""
    text = str(message or '')
    if any(hint in text for hint in AMOUNT_HINTS):
        return 'amount'
    if any(hint in text for hint in AUTHORITY_HINTS):
        return 'authority'
    return 'rule'


def record_refusal(db, *, store_id, user, method, path, status_code, message, source='page'):
    """记下被挡住的一步（系统自己的事实），供评审申请引用。

    只记 403，以及确实带权限/额度语义的 422；表单校验、登录过期、评审接口自身和助手
    自己的策略拒绝都不记录：那些不是"岗位不够"。
    """
    if not store_id or not path.startswith('/api/'):
        return None
    if path.startswith(('/api/escalations', '/api/auth', '/api/business-assistant')):
        return None
    if status_code not in (403, 422):
        return None
    category = classify_refusal(status_code, message)
    if status_code == 422 and category == 'rule':
        return None
    row = Refusal(store_id=store_id, user_id=user.id, role=store_role(user), method=method,
                  path=path[:240], status_code=status_code, message=str(message or '')[:2000],
                  category=category, source=source)
    db.add(row)
    db.flush()
    cutoff = utcnow() - timedelta(days=7)
    for stale in db.scalars(select(Refusal).where(Refusal.user_id == user.id, Refusal.created_at < cutoff)):
        db.delete(stale)
    return row


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


def refusal_view(row):
    return {'id': row.id, 'method': row.method, 'path': row.path,
            'operation_id': '%s %s' % (row.method, row.path), 'status_code': row.status_code,
            'message': row.message, 'category': row.category,
            'category_label': CATEGORY_LABELS.get(row.category, row.category),
            'created_at': row.created_at}


def refusals(db, user):
    """本店最近被系统挡住、还没有用于评审申请的记录。"""
    store = single_store(db)
    rows = db.scalars(select(Refusal).where(Refusal.user_id == user.id, Refusal.store_id == store,
                                            Refusal.consumed_at.is_(None))
                      .order_by(Refusal.id.desc()).limit(MAX_REFUSALS)).all()
    return {'items': [refusal_view(row) for row in rows],
            'categories': CATEGORY_LABELS,
            'notice': '这里只显示系统确实拒绝过你的操作。业务规则不允许的事项会标成“业务规则”，不能提交评审。'}


def create(db, user, payload):
    store = single_store(db)
    receipt = db.scalar(select(Refusal).where(Refusal.id == payload.refusal_id,
                                              Refusal.user_id == user.id, Refusal.store_id == store))
    if not receipt:
        raise HTTPException(404, '找不到这条被挡记录：请先在原页面按提示办理一次，被系统挡住后再回来提交')
    if receipt.consumed_at is not None:
        raise HTTPException(409, '这条被挡记录已经用过了，请重新在页面办理一次')
    if receipt.created_at < utcnow() - timedelta(hours=REFUSAL_HOURS):
        raise HTTPException(409, '这条被挡记录已超过 %d 小时，请重新在页面办理一次' % REFUSAL_HOURS)
    if receipt.category == 'rule':
        raise HTTPException(422, '系统挡住这一步的原因是业务规则（%s），不能通过评审绕过，请按页面提示处理'
                            % receipt.message[:60])
    if payload.reason_category and payload.reason_category != receipt.category:
        raise HTTPException(422, '系统记录的原因属于“%s”，请按系统记录提交'
                            % CATEGORY_LABELS.get(receipt.category, receipt.category))
    subject = (payload.subject or '').strip()
    case_reference = (payload.case_reference or '').strip()
    if len(subject) < 5:
        raise HTTPException(422, '请写清要办的事（至少 5 个字），例如“给这张单批准 5% 折扣”')
    duplicate = db.scalar(select(Escalation).where(
        Escalation.store_id == store, Escalation.requester_id == user.id, Escalation.subject == subject,
        Escalation.case_reference == case_reference, Escalation.status.in_(('open', 'claimed'))))
    if duplicate:
        raise HTTPException(409, '同一件事已经提交过评审，请等待处理或先撤回')
    row = Escalation(store_id=store, requester_id=user.id, requester_role=store_role(user),
                     target_role='admin' if store_role(user) in {'admin', 'manager'} else 'manager',
                     subject=subject, case_reference=case_reference,
                     operation_id='%s %s' % (receipt.method, receipt.path), blocked_message=receipt.message,
                     reason_category=receipt.category, status='open')
    db.add(row)
    db.flush()
    receipt.consumed_at, receipt.consumed_by_id = utcnow(), row.id
    db.add(EscalationEvent(store_id=store, escalation_id=row.id, actor_id=user.id, action='submit', note=subject))
    audit(db, user.id, 'escalation_submit', 'escalations', row.id, reason='提交评审申请：' + subject[:60])
    db.commit()
    return view(db, row)


def listing(db, user, scope='mine', status=''):
    if scope not in {'mine', 'to_review'}:
        raise HTTPException(422, '查询范围不正确')
    role = store_role(user)
    if scope == 'to_review':
        if role not in REVIEWER_ROLES:
            raise HTTPException(403, '只有本店店长或管理员可以查看待评审')
        # 不能看到自己提交的申请，也不能自己批准自己——与“管理员不能自己申请自己批准”一致。
        statement = select(Escalation).where(Escalation.requester_id != user.id,
                                             Escalation.status.in_(('open', 'claimed')))
        # 收件人由服务端指定：店长只看发给店长的，集团管理员只看发给集团管理员的。
        statement = statement.where(Escalation.target_role == role)
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
    role = store_role(user)
    if action == 'cancel':
        if row.requester_id != user.id and account_role(user) != 'admin':
            raise HTTPException(403, '只有申请人本人或管理员可以撤回')
        if row.status not in {'open', 'claimed'}:
            raise HTTPException(409, '这条申请已经处理完，不能撤回')
        row.status = 'cancelled'
    else:
        if role not in REVIEWER_ROLES:
            raise HTTPException(403, '只有本店店长或管理员可以处理评审申请')
        if row.requester_id == user.id:
            raise HTTPException(403, '不能自己批准自己提交的评审，请交给另一位有权限的同事')
        if row.target_role != role:
            raise HTTPException(403, '这条申请不属于你的岗位')
        if action == 'claim':
            if row.status != 'open':
                raise HTTPException(409, '这条申请已被接手或处理完')
            row.status, row.claimed_by_id, row.claimed_at = 'claimed', user.id, utcnow()
        elif action in {'done', 'reject'}:
            if row.status not in {'open', 'claimed'}:
                raise HTTPException(409, '这条申请已经处理完')
            if row.claimed_by_id not in (None, user.id):
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

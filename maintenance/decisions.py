"""Short, durable card-action handler. No Git, AI, tests or restarts in callbacks."""
from datetime import timedelta
import hashlib
import hmac
import secrets
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.db import SessionLocal, utcnow
from app.models import Feedback, MaintenanceEvent, BotReceipt
from .config import GateError
from .gitops import SHA


def token_digest(token): return hashlib.sha256(token.encode()).hexdigest()


def event(db,job_id,action,actor='controller',detail=''):
    db.add(MaintenanceEvent(feedback_id=job_id,action=action,actor=actor,detail=detail[:4000]))


def issue_token(job_id,cfg,rollback=False):
    raw=secrets.token_urlsafe(32)
    with SessionLocal() as db:
        row=db.get(Feedback,job_id)
        if not row or row.status!=('deployed' if rollback else 'awaiting_approval'): raise GateError('审批对象状态已变化')
        row.approval_token_hash=token_digest(raw)
        row.approval_expires_at=utcnow()+timedelta(hours=cfg.approval_hours)
        row.notification_sent=False
        db.commit()
    return raw


def decide(cfg,operator,job_id,sha,token,decision,event_id,tenant_key=''):
    if operator not in cfg.approvers: raise GateError('你不在此应用配置的审批人白名单中')
    if cfg.tenant_key and tenant_key!=cfg.tenant_key: raise GateError('审批租户不匹配')
    if decision not in {'approve','reject','rollback'} or not SHA.fullmatch(sha) or not token or len(token)>100:
        raise GateError('无效审批请求')
    if not event_id or len(event_id)>160: raise GateError('缺少有效回调事件ID')
    with SessionLocal() as db:
        if db.get(BotReceipt,event_id): return '该操作已接收，不会重复发布'
        row=db.get(Feedback,job_id)
        if not row: raise GateError('改进任务不存在')
        if row.head_sha!=sha or not hmac.compare_digest(row.approval_token_hash,token_digest(token)):
            raise GateError('卡片已失效或提交不匹配，请使用最新卡片')
        if not row.approval_expires_at or row.approval_expires_at<=utcnow(): raise GateError('卡片审批已过期，须重新测试或重新发送')
        expected='deployed' if decision=='rollback' else 'awaiting_approval'
        if row.status!=expected: raise GateError('任务已处理，不能重复审批')
        if not row.test_result.get('passed') or row.test_result.get('head_sha')!=sha:
            raise GateError('没有与此提交绑定的通过测试记录')
        values={'status':{'approve':'approved','reject':'rejected','rollback':'rollback_requested'}[decision],
            'approved_by':operator,'approved_sha':sha,'approved_at':utcnow(),'updated_at':utcnow(),'version':row.version+1}
        changed=db.execute(update(Feedback).where(Feedback.id==job_id,Feedback.status==expected,Feedback.version==row.version).values(**values))
        if changed.rowcount!=1: raise GateError('另一个审批已先处理，请刷新')
        db.add(BotReceipt(event_id=event_id));event(db,job_id,decision,operator,f'绑定提交 {sha}')
        try: db.commit()
        except IntegrityError:
            db.rollback();return '该事件已接收'
    return {'approve':'已批准此提交，发布器将执行备份和健康检查','reject':'已拒绝，当前版本保持不变','rollback':'已接收回滚请求，将恢复上一个运行版本'}[decision]

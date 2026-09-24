"""向相关上级提交评审：员工被岗位权限挡住时，把这件请求交给本店店长或集团管理员。

评审只记录"谁在什么时候请求什么、上级怎么处理"，**从不改变任何权限、也不执行业务动作**：
上级本人在原业务页面办理，这里只留痕。事件表只追加，不修改、不删除。
"""
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow
from .flow_models import Versioned

STATUSES = ('open', 'claimed', 'done', 'rejected', 'cancelled')
# 只解决“权限/额度不够”。业务规则明确禁止的事项在创建时就被拒绝，不能借评审绕过规则。
CATEGORIES = ('authority', 'amount')
STATUS_LABELS = {'open': '待处理', 'claimed': '已接手', 'done': '已办理', 'rejected': '已驳回', 'cancelled': '已撤回'}
CATEGORY_LABELS = {'authority': '岗位权限不足', 'amount': '金额或额度超出'}
TARGET_LABELS = {'manager': '本店店长', 'admin': '集团管理员'}


class Escalation(Versioned, Base):
    __tablename__ = 'escalations'
    requester_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    requester_role: Mapped[str] = mapped_column(String(30))
    target_role: Mapped[str] = mapped_column(String(30))
    subject: Mapped[str] = mapped_column(String(160))
    case_reference: Mapped[str] = mapped_column(String(80), default='')
    operation_id: Mapped[str] = mapped_column(String(200), default='')
    blocked_message: Mapped[str] = mapped_column(Text, default='')
    reason_category: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='open')
    claimed_by_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default='')
    __table_args__ = (
        CheckConstraint('status in (%s)' % ','.join("'%s'" % value for value in STATUSES),
                        name='ck_escalation_status'),
        CheckConstraint('reason_category in (%s)' % ','.join("'%s'" % value for value in CATEGORIES),
                        name='ck_escalation_category'),
        CheckConstraint("target_role in ('manager','admin')", name='ck_escalation_target'),
        Index('ix_escalations_store_status', 'store_id', 'status'),
    )


class EscalationEvent(Base):
    """只追加的处理轨迹：提交、接手、办理、驳回、撤回。"""
    __tablename__ = 'escalation_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    escalation_id: Mapped[int] = mapped_column(ForeignKey('escalations.id'), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

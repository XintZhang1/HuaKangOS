"""Transaction fragments for original return-transit searches and reappearance.

The existing parent/case CAS, tenant authority and request receipt own the
transaction. No fragment here writes stock, money, loss or settlement entries.
"""
from fastapi import HTTPException
from sqlalchemy import select
from .db import today
from .transfer_goods_recovery_models import GoodsRecovery
from .transfer_goods_search_models import GoodsSearch, GoodsSearchReview, GoodsSearchOutcome, GoodsReappearance

ACTIONS = {'trace_open', 'trace_approve', 'trace_reject'}
OUTCOMES = {'review': '双方查找复核中', 'unlocated': '双方已结束本次查找，原物资仍未找到',
    'rejected': '本版结束查找未获同意，继续核对实际到货', 'arrived': '查找期间实际到货，回到原复验流程'}


def _services():
    from . import transfer_goods_recovery_service as goods
    from . import transfer_exception_service as exc
    return goods, exc


def latest(db, row):
    goods, _ = _services()
    return next(iter(reversed(goods.rows(db, GoodsSearch, recovery_id=row.id))), None)


def outcome(db, search):
    if search is None:
        return None
    return db.scalar(select(GoodsSearchOutcome).where(GoodsSearchOutcome.search_id == search.id))


def pending(db, row):
    search = latest(db, row)
    return search if search and outcome(db, search) is None else None


def reviewers(db, row, parent, search):
    """Resolve two distinct, uninvolved actual local managers, or fail closed."""
    goods, exc = _services()
    history = goods.facts(db, row)
    decided = goods.rows(db, GoodsSearchReview, search_id=search.id)
    blocked = {row.requested_by, search.requested_by} | {f.actor_id for f in history} | {r.actor_id for r in decided}
    parties = (parent.from_store_id, parent.to_store_id)
    choices = {}
    for sid in parties:
        if any(r.store_id == sid for r in decided):
            continue
        choices[sid] = [u.id for u in exc.flow.eligible_users(db, 'manager', sid) if u.id not in blocked]
        if not choices[sid]:
            raise HTTPException(409, '请配置未参与本次找到、发运或查找申报的本店主管；两店复核必须由不同人员完成')
    if len(choices) == 2:
        first, second = parties
        for a in choices[first]:
            for b in choices[second]:
                if a != b:
                    return {first: a, second: b}
        raise HTTPException(409, '两店不能由同一个人复核结束查找，请配置另一名独立主管')
    return {sid: ids[0] for sid, ids in choices.items()}


def apply(db, user, row, parent, case, action, values):
    goods, exc = _services()
    sid = case.store_id
    if row.status != 'transit':
        raise HTTPException(409, '仅实际发回且尚未收到的原物资，可以查找或复核；到货与再次找到分别办理')
    history = goods.facts(db, row)
    if not any(f.kind == 'ship' for f in history) or any(f.kind == 'receive' for f in history):
        raise HTTPException(409, '缺少实际原退运或已经到货，不能申报仍未找到')
    exc._proof(db, user, case, values['evidence_id'])
    search = pending(db, row)
    if action == 'trace_open':
        if user.role not in exc.PHYSICAL | exc.MANAGER:
            raise HTTPException(403, '退运查找由本店库管或主管根据实际记录申报')
        if search:
            raise HTTPException(409, '本次退运已有查找复核，请继续原申请')
        search = GoodsSearch(recovery_id=row.id, revision=len(goods.rows(db, GoodsSearch, recovery_id=row.id)) + 1,
            store_id=sid, case_id=case.id, requested_by=user.id, evidence_id=values['evidence_id'],
            reason=values['reason'], business_date=today())
        db.add(search); db.flush()
        reviewers(db, row, parent, search)
        return
    if user.role not in exc.MANAGER:
        raise HTTPException(403, '结束本次查找须由两店主管独立核对')
    if search is None or values['search_id'] != search.id:
        raise HTTPException(409, '查找版本已变化或已经有实际结果，请刷新原记录')
    reviews = goods.rows(db, GoodsSearchReview, search_id=search.id)
    blocked = {row.requested_by, search.requested_by} | {f.actor_id for f in history} | {r.actor_id for r in reviews}
    if user.id in blocked or any(r.store_id == sid for r in reviews):
        raise HTTPException(403, '申报、实际找到、原退运经办人及另一方复核人不能代本店独立复核')
    exc._assert_task(db, user, case, f'transfer_found_{row.id}_trace_review_{search.id}')
    review = GoodsSearchReview(search_id=search.id, store_id=sid, case_id=case.id,
        decision='end_search' if action == 'trace_approve' else 'keep_searching',
        actor_id=user.id, evidence_id=values['evidence_id'], reason=values['reason'], business_date=today())
    db.add(review); db.flush()
    if action == 'trace_reject' or len(reviews) == 1:
        kind = 'rejected' if action == 'trace_reject' else 'unlocated'
        db.add(GoodsSearchOutcome(search_id=search.id, store_id=sid, case_id=case.id,
            kind=kind, review_id=review.id, actor_id=user.id, business_date=today()))
        if kind == 'unlocated':
            row.status = 'unlocated'; row.active_transfer_id = None
        db.flush()


def actual_arrival(db, user, row, parent, case, fact):
    """An actual receipt wins over an unfinished proposal, with original proof."""
    search = pending(db, row)
    if search is not None:
        db.add(GoodsSearchOutcome(search_id=search.id, store_id=case.store_id, case_id=case.id,
            kind='arrived', receive_fact_id=fact.id, actor_id=user.id, business_date=fact.business_date))
        db.flush()


def remaining(db, previous):
    goods, _ = _services()
    links = goods.rows(db, GoodsReappearance, previous_recovery_id=previous.id)
    used = 0
    for link in links:
        child = db.scalar(select(GoodsRecovery).where(GoodsRecovery.id == link.recovery_id))
        if child is None:
            raise HTTPException(409, '原再次找到来源不完整，请核对恢复记录')
        # A child which was sent and then unlocated keeps its branch capacity;
        # descendants must continue that child, not reuse its parent's budget.
        if child.status != 'cancelled':
            used += link.quantity_milli
    available = previous.quantity_milli - used
    if available < 0:
        raise HTTPException(409, '原查找数量已被重复关联，请核对来源')
    return available


def validate_reappearance(db, parent, loss, previous_id, quantity):
    if previous_id is None:
        return None
    previous = db.scalar(select(GoodsRecovery).where(GoodsRecovery.id == previous_id,
        GoodsRecovery.transfer_id == parent.id, GoodsRecovery.loss_id == loss.id))
    if previous is None or previous.status != 'unlocated':
        raise HTTPException(409, '再次找到须明确关联同一原损失下、双方已结束的原退运查找')
    search = latest(db, previous); ended = outcome(db, search)
    if ended is None or ended.kind != 'unlocated' or quantity > remaining(db, previous):
        raise HTTPException(409, '本次找到量超过该次原查找尚未重新找到的数量')
    return previous, search


def attach_reappearance(db, user, row, case, original, evidence_id):
    if original is None:
        return
    previous, search = original
    db.add(GoodsReappearance(previous_recovery_id=previous.id, search_id=search.id, recovery_id=row.id,
        store_id=case.store_id, case_id=case.id, quantity_milli=row.quantity_milli,
        evidence_id=evidence_id, actor_id=user.id, business_date=today()))
    db.flush()


def task_desires(db, row, parent, sid):
    search = pending(db, row)
    if row.status != 'transit' or search is None:
        return {}
    assignments = reviewers(db, row, parent, search)
    if sid not in assignments:
        return {}
    return {f'trace_review_{search.id}': ('独立核对退运查找结果，不重复记损失', 'manager', assignments[sid])}


def append_view(db, user, row, parent, sid, result, assigned):
    goods, exc = _services()
    searches = goods.rows(db, GoodsSearch, recovery_id=row.id)
    result['searches'] = []
    for search in searches:
        end = outcome(db, search)
        item = dict(id=search.id, revision=search.revision, store_id=search.store_id,
            reason=search.reason, business_date=search.business_date.isoformat(),
            status=end.kind if end else 'review', status_label=OUTCOMES[end.kind if end else 'review'],
            evidence_id=search.evidence_id if search.store_id == sid else None,
            reviews=[dict(store_id=r.store_id, is_local=r.store_id==sid, decision=r.decision, reason=r.reason,
                evidence_id=r.evidence_id if r.store_id == sid else None)
                for r in goods.rows(db, GoodsSearchReview, search_id=search.id)])
        result['searches'].append(item)
    link = db.scalar(select(GoodsReappearance).where(GoodsReappearance.recovery_id == row.id))
    result['previous_recovery_id'] = link.previous_recovery_id if link else None
    result['reappearances'] = [dict(recovery_id=l.recovery_id, quantity_milli=l.quantity_milli)
        for l in goods.rows(db, GoodsReappearance, previous_recovery_id=row.id)]
    result['reappearance_remaining_milli'] = remaining(db, row) if row.status == 'unlocated' else 0
    search = pending(db, row)
    if row.status == 'transit':
        if search is None and user.role in exc.PHYSICAL | exc.MANAGER:
            result['actions'].append('trace_open')
        elif search and user.role in exc.MANAGER:
            reviews = goods.rows(db, GoodsSearchReview, search_id=search.id)
            blocked = {row.requested_by, search.requested_by} | {f.actor_id for f in goods.facts(db, row)} | {r.actor_id for r in reviews}
            if user.id not in blocked and not any(r.store_id == sid for r in reviews) and (
                f'transfer_found_{row.id}_trace_review_{search.id}' in assigned):
                result['actions'].extend(('trace_approve', 'trace_reject'))
    if row.status == 'unlocated' and result['reappearance_remaining_milli'] > 0 and user.role in exc.PHYSICAL:
        result['actions'].append('refind')


def prior_searches(db, parent, loss):
    goods, _ = _services()
    return [dict(recovery_id=r.id, available_quantity_milli=remaining(db, r))
        for r in goods.rows(db, GoodsRecovery, transfer_id=parent.id, loss_id=loss.id, status='unlocated')
        if remaining(db, r) > 0]

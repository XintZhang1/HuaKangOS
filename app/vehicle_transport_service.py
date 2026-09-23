"""Guarded single-VIN discrepancies on the original two vehicle transfer cases.

No intermediate commits: parent/custody lock, local evidence, independent tasks,
immutable posting and original request receipt are one transaction.
"""
import copy
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import utcnow, today
from .config import settings
from .flow_models import Case, Task
from .tenancy import single_store
from . import flow_engine as flow
from . import transfer_service as coordination
from . import vehicle_transfer_service as original_service
from .vehicle_transfer_models import VehicleTransfer, VehicleMovement
from .vehicle_transport_models import (VehicleTransportException as ExceptionRow,
    VehicleTransportObservation as Observation, VehicleTransportPlan as Plan,
    VehicleTransportReview as Review, VehicleTransportWithdrawal as Withdrawal,
    VehicleTransportDisposal as Disposal, VehicleTransportFoundUnavailable as FoundUnavailable, VehicleTransportLoss as Loss,
    VehicleTransportLossSettlement as LossSettlement,
    VehicleTransportFoundReceipt as FoundReceipt,
    VehicleTransportFoundSettlement as FoundSettlement,
    VehicleTransportReceipt as Receipt)
from . import vehicle_transport_rules as rules

READ = {'admin', 'manager', 'inventory', 'finance', 'auditor'}
PHYSICAL = {'admin', 'inventory'}
FINANCE = {'admin', 'finance'}
MANAGER = {'admin', 'manager'}
STATUS_LABELS = {'investigating': '双方核对原VIN中', 'review': '待两店独立复核',
    'approved': '方案获准，待实际办理', 'posted': '原车损失已确认',
    'resolved': '差异已解除，仍须真实交接', 'recovered': '原车已实际找回入库'}
OBS_LABELS = {'dispatch_verified': '核对本店原VIN已发出', 'not_located': '核对原VIN仍未找到',
    'original_seen': '核对原VIN实际在场', 'unusable_held': '原VIN在手但已不可用',
    'other_vin_seen': '现场为其他VIN，原车未确认', 'found_usable': '后来找到原VIN且在本店可验收'}


def clean(row):
    return rules.clean({c.name: getattr(row, c.name) for c in row.__table__.columns})


def rows(db, model, **where):
    query = select(model)
    for key, value in where.items(): query = query.where(getattr(model, key) == value)
    result = list(db.scalars(query.order_by(model.id).limit(25001)))
    if len(result) > 25000: raise HTTPException(413, '原车差异来源超过当前上限，不能返回截断结果')
    return result


def one(db, model, key):
    row = db.scalar(select(model).where(model.id == key))
    if row is None: raise HTTPException(404, '本店原整车差异记录不存在')
    return row


def active(db, parent):
    return db.scalar(select(ExceptionRow).where(ExceptionRow.active_transfer_id == parent.id))


def guard_original(db, parent):
    if active(db, parent): raise HTTPException(409, '该原VIN差异尚在核对或已确认损失，请从原差异办理；不能绕过差异普通入库')


def _parent(db, user, key, sid):
    ex = db.scalar(select(ExceptionRow).join(VehicleTransfer, VehicleTransfer.id == ExceptionRow.transfer_id).where(
        ExceptionRow.id == key, or_(VehicleTransfer.from_store_id == sid, VehicleTransfer.to_store_id == sid)))
    if not ex: raise HTTPException(404, '不是当前门店的原整车运输差异')
    parent = original_service.transfer(db, ex.transfer_id, sid)
    original_service.local_case(db, user, parent, sid)
    return ex, parent


def _lock(db, user, parent, sid, version, case_version, ex=None, exception_version=None):
    parent = db.scalar(select(VehicleTransfer).where(VehicleTransfer.id == parent.id).with_for_update())
    case = original_service.local_case(db, user, parent, sid)
    if parent.version != version or case.version != case_version or ex and ex.version != exception_version:
        raise HTTPException(409, '调拨、差异或本店原单已变化，请刷新并核对原请求')
    parent.updated_at = utcnow(); case.updated_at = utcnow()
    if ex: ex.updated_at = utcnow()
    # Every native command and every exception/claim command touches this parent
    # before testing the remaining VIN/cost. SQLite optimistic locks also fail closed.
    db.flush()
    custody = original_service.current_custody(db, parent.vin)
    if not custody: raise HTTPException(409, '原VIN共享保管来源缺失')
    if parent.status != 'recovered' and (custody.pending_transfer_id != parent.id or custody.current_vehicle_id is not None):
        raise HTTPException(409, '原VIN已被交接或不再处于本次独占在途')
    custody.version += 1; db.flush()
    return parent, case, custody


def proof(db, user, case, key, financial=False):
    asset = coordination.evidence(db, user, case, key)
    if asset.generated: raise HTTPException(409, '自动生成草稿不能替代实际核对、处置或财务协议')
    expected = {'receipt', 'procurement_contract'} if financial else {'evidence', 'inspection', 'authorization'}
    if asset.category not in expected:
        raise HTTPException(422, '请上传本店原单的真实财务协议凭据' if financial else '请上传本店原单的实车核对、检测或授权凭据')
    return asset


def _original(db, parent, ex):
    with coordination.coordination_scope(db, parent.from_store_id, (parent.from_store_id, parent.to_store_id)):
        move = one(db, VehicleMovement, ex.original_id)
        if move.transfer_id != parent.id or move.kind != 'dispatch': raise HTTPException(409, '不是本调拨原VIN发出来源')
        return move


def loss_for(db, parent, ex):
    with coordination.coordination_scope(db, parent.from_store_id, (parent.from_store_id, parent.to_store_id)):
        return db.scalar(select(Loss).where(Loss.exception_id == ex.id))


def found_for(db, parent, ex):
    for sid in (parent.from_store_id, parent.to_store_id):
        with coordination.coordination_scope(db, sid, (parent.from_store_id, parent.to_store_id)):
            row = db.scalar(select(FoundReceipt).where(FoundReceipt.exception_id == ex.id))
            if row: return row
    return None


def latest_plan(db, ex):
    all_plans = rows(db, Plan, exception_id=ex.id)
    return all_plans[-1] if all_plans else None


def latest_observations(db, ex):
    return {o.store_id: o for o in rows(db, Observation, exception_id=ex.id) if o.kind != 'found_usable'}


def plan_parts(db, parent, ex, plan):
    source = one(db, Observation, plan.source_observation_id)
    destination = one(db, Observation, plan.destination_observation_id)
    found = one(db, Observation, plan.found_observation_id) if plan.found_observation_id else None
    loss = loss_for(db, parent, ex) if plan.kind == 'found_receive' else None
    original = _original(db, parent, ex)
    try:
        value = rules.validate_plan(clean(parent), clean(ex), clean(original), clean(source), clean(destination), clean(plan),
            clean(found) if found else None, clean(loss) if loss else None, timezone_name=settings.timezone)
    except (ValueError, KeyError, TypeError) as err:
        raise HTTPException(409, str(err))
    return source, destination, found, loss, value


def _reviewer_ids(db, parent, ex, plan):
    source, destination, found, _, _ = plan_parts(db, parent, ex, plan)
    excluded = rules.independent_reviewers(clean(ex), clean(plan), [clean(x) for x in (source, destination, found) if x])
    chosen = {r.store_id: r.actor_id for r in rows(db, Review, plan_id=plan.id) if r.decision == 'approve'}
    for sid in (parent.from_store_id, parent.to_store_id):
        if sid in chosen: continue
        candidates = [u.id for u in flow.eligible_users(db, 'manager', sid) if u.id not in excluded | set(chosen.values())]
        if not candidates: raise HTTPException(409, '两店需要各一名独立主管；不能由申请、原观察、方案经办人或同一人兼任双方复核')
        chosen[sid] = candidates[0]
    return chosen


def _task_key(ex, suffix): return f'vehicle_transport_{ex.id}_{suffix}'


def _task(db, user, case, key):
    coordination.assert_task(db, user, case, key)


def _event(db, user, case, ex, action, values):
    # Local evidence and money stay on the local original case projection.
    detail = {'exception_id': ex.id, 'transfer_id': ex.transfer_id, **rules.clean(values)}
    flow.log_event(db, user, case, 'vehicle_transport_' + action, '整车运输差异追加原事实', detail=detail)


def sync_tasks(db, user, ex, parent):
    observations = latest_observations(db, ex); plan = latest_plan(db, ex)
    reviews = {r.store_id: r for r in rows(db, Review, plan_id=plan.id)} if plan else {}
    reviewers = _reviewer_ids(db, parent, ex, plan) if ex.status == 'review' else {}
    disposed = bool(rows(db, Disposal, exception_id=ex.id))
    sender, receiver = rules.parties(clean(parent), clean(ex))
    terminal = ex.status in {'resolved', 'posted', 'recovered'}
    for sid, cid in ((parent.from_store_id, parent.from_case_id), (parent.to_store_id, parent.to_case_id)):
        with coordination.coordination_scope(db, sid, (parent.from_store_id, parent.to_store_id)):
            case = flow.scoped_get(db, Case, cid); case.updated_at = utcnow(); desired = {}
            if ex.status == 'investigating':
                if sid not in observations or sid == receiver and observations[sid].kind == 'other_vin_seen':
                    desired[_task_key(ex, 'observe')] = ('本人核对本段原VIN的发出、在场或失联', 'inventory', None)
                elif len(observations) == 2 and sid == parent.from_store_id:
                    seen = observations[receiver].kind == 'original_seen'
                    desired[_task_key(ex, 'plan')] = ('按已核对原VIN提出继续交接' if seen else '拟定原车损失及双方原成本承担', 'inventory' if seen else 'finance', None)
            elif ex.status == 'review' and sid not in reviews:
                desired[_task_key(ex, 'review_' + str(plan.id))] = ('独立复核本版原VIN、原成本与两店事实', 'manager', reviewers[sid])
            elif ex.status == 'approved':
                if plan.kind == 'found_receive' and sid == plan.receiving_store_id:
                    desired[_task_key(ex, 'found_receive')] = ('本人再次核对原VIN并实际验收找回车辆', 'inventory', None)
                elif plan.kind == 'loss' and plan.loss_method == 'destroyed' and not disposed and sid == receiver:
                    desired[_task_key(ex, 'dispose')] = ('实际处置在手不可用原VIN，保留销毁凭据', 'inventory', None)
                elif plan.kind == 'loss' and (plan.loss_method == 'missing' or disposed) and sid == parent.from_store_id:
                    desired[_task_key(ex, 'post_loss')] = ('依据双方批准及真实处置确认原在途损失', 'finance', None)
            prefix = _task_key(ex, '')
            for task in list(db.scalars(select(Task).where(Task.case_id == cid, Task.status == 'open'))):
                if task.key.startswith(prefix) and task.key not in desired: flow.finish_task(db, case, task.key, user)
            for key, (label, role, assignee) in desired.items():
                task = flow.ensure_task(db, case, key, label, role, assignee=assignee, reopen=True)
                if ex.status == 'review' and task.assignee_id != assignee: raise HTTPException(409, '当前复核待办负责人不独立，需明确转交')
            if not terminal:
                for key in ('vehicle_receive', 'vehicle_return_ship', 'vehicle_return_receive'): flow.finish_task(db, case, key, user)
                case.state = 'working'; case.completed_date = None
    if ex.status == 'resolved':
        original_service.synchronize(db, user, parent, 'discrepancy_resolved', '两店独立复核已解除差异，实际交接仍单独办理')
    elif ex.status in {'posted', 'recovered'}:
        original_service.synchronize(db, user, parent, 'loss_recorded' if ex.status == 'posted' else 'original_found', '原车损失或实际找回事实已登记，原款及店间清算另行办理')
    from . import vehicle_transport_recovery as claims
    for sid, cid in ((parent.from_store_id, parent.from_case_id), (parent.to_store_id, parent.to_case_id)):
        with coordination.coordination_scope(db, sid, (parent.from_store_id, parent.to_store_id)):
            claims.sync_tasks(db, user, ex, parent, flow.scoped_get(db, Case, cid))


def _project(result, user):
    if user.role in flow.MANAGEMENT: return result
    def strip(v):
        if isinstance(v, list): return [strip(x) for x in v]
        if isinstance(v, dict): return {k: strip(x) for k, x in v.items() if not k.endswith('_cents') and k not in {'claims', 'counterparty_snapshot'}}
        return v
    projected = strip(copy.deepcopy(result))
    projected['can_money'] = False
    for plan in projected.get('plans', []):
        if plan.get('kind') != 'resume':
            plan.pop('reason', None); plan.pop('evidence_id', None)
            for review in plan.get('reviews', []):
                review.pop('reason', None); review.pop('evidence_id', None)
    return projected


def execute(db, user, request_id, action, values, roles, operation):
    try:
        with coordination.authority(db, user, roles) as sid:
            digest = rules.signature({'action': action, 'values': values})
            receipt = db.scalar(select(Receipt).where(Receipt.request_key == request_id))
            if receipt:
                if receipt.actor_id != user.id or receipt.digest != digest: raise HTTPException(409, '该请求编号已用于其他动作或内容')
                return _project(receipt.result, user)
            result = operation(sid)
            db.add(Receipt(request_key=request_id, actor_id=user.id, digest=digest, result=result))
            db.commit(); return result
    except (IntegrityError, OperationalError, StaleDataError):
        db.rollback(); raise HTTPException(409, '原VIN、差异或原款正在变化，请刷新核对原请求，不能重复记账')
    except Exception:
        db.rollback(); raise


def describe(db, user, ex, parent, sid):
    case = original_service.local_case(db, user, parent, sid)
    observations = rows(db, Observation, exception_id=ex.id)
    plans = rows(db, Plan, exception_id=ex.id); plan = plans[-1] if plans else None
    loss = loss_for(db, parent, ex); found = found_for(db, parent, ex)
    result = {'id': ex.id, 'transfer_id': parent.id, 'version': parent.version, 'exception_version': ex.version,
        'case_id': case.id, 'case_version': case.version, 'number': parent.number, 'vin': parent.vin,
        'status': ex.status, 'status_label': STATUS_LABELS[ex.status], 'origin_status': ex.origin_status,
        'kind': ex.kind, 'reason': ex.reason, 'side': 'source' if sid == parent.from_store_id else 'destination',
        'can_money': user.role in flow.MANAGEMENT, 'observations': [], 'plans': [], 'actions': [],
        'loss_recorded': loss is not None, 'found_received': found is not None,
        'unavailable_findings': [{'plan_id':x.plan_id,'observation_id':x.observation_id,'kind':x.kind,'own_store':x.store_id==sid,
            **({'evidence_id':x.evidence_id,'reason':x.reason} if x.store_id==sid else {})} for x in rows(db,FoundUnavailable,exception_id=ex.id)],
        'definition': '观察不等于入库；在途损失不再次出库；找回按原VIN新代次恢复原成本，原赔款与店间实际资金分别处理。'}
    if ex.store_id == sid: result['evidence_id'] = ex.evidence_id
    for obs in observations:
        item = {'id': obs.id, 'kind': obs.kind, 'label': OBS_LABELS[obs.kind], 'vin': obs.vin,
            'own_store': obs.store_id == sid, 'actual_at': obs.actual_at.isoformat(), 'reason': obs.reason}
        if obs.store_id == sid: item['evidence_id'] = obs.evidence_id
        result['observations'].append(item)
    for p in plans:
        reviews = rows(db, Review, plan_id=p.id)
        withdrawn = bool(rows(db, Withdrawal, plan_id=p.id))
        status = 'withdrawn' if withdrawn else 'rejected' if any(r.decision == 'reject' for r in reviews) else 'approved' if len(reviews) == 2 else 'pending'
        item = {'id': p.id, 'revision': p.revision, 'kind': p.kind, 'status': status, 'reason': p.reason,
            'source_observation_id': p.source_observation_id, 'destination_observation_id': p.destination_observation_id,
            'found_observation_id': p.found_observation_id, 'receiving_own_store': p.receiving_store_id == sid,
            'loss_method': p.loss_method, 'reviews': [{'own_store': r.store_id == sid, 'decision': r.decision,
                **({'evidence_id': r.evidence_id, 'reason': r.reason} if r.store_id == sid else {})} for r in reviews]}
        if p.store_id == sid: item['evidence_id'] = p.evidence_id
        if user.role in flow.MANAGEMENT: item.update(source_bearer_cents=p.source_bearer_cents, destination_bearer_cents=p.destination_bearer_cents)
        result['plans'].append(item)
    if loss and user.role in flow.MANAGEMENT:
        result['loss'] = {'id': loss.id, 'value_cents': loss.value_cents, 'source_bearer_cents': loss.source_bearer_cents,
            'destination_bearer_cents': loss.destination_bearer_cents, 'kind': loss.kind, 'business_date': loss.business_date.isoformat()}
    if found:
        result['found'] = {'id': found.id, 'own_store': found.store_id == sid, 'business_date': found.business_date.isoformat()}
        if found.store_id == sid: result['found'].update(vehicle_id=found.vehicle_id, evidence_id=found.evidence_id)
        if user.role in flow.MANAGEMENT: result['found']['value_cents'] = found.value_cents
    if ex.status == 'investigating':
        if user.role in PHYSICAL: result['actions'].append('observe')
        if sid == parent.from_store_id:
            if user.role in PHYSICAL: result['actions'].append('plan_resume')
            if user.role in FINANCE: result['actions'].append('plan_loss')
    elif ex.status == 'review':
        reviews = rows(db, Review, plan_id=plan.id)
        excluded = {ex.requested_by, plan.actor_id} | {o.actor_id for o in observations if o.id in {plan.source_observation_id, plan.destination_observation_id, plan.found_observation_id}}
        if user.role in MANAGER and user.id not in excluded | {r.actor_id for r in reviews} and sid not in {r.store_id for r in reviews}:
            result['actions'] += ['approve', 'reject']
        if user.id == plan.actor_id and sid == plan.store_id: result['actions'].append('withdraw')
    elif ex.status == 'approved':
        if plan.kind == 'found_receive' and plan.receiving_store_id == sid and user.role in PHYSICAL: result['actions'] += ['found_receive', 'found_unavailable']
        elif plan.kind == 'loss':
            disposed = bool(rows(db, Disposal, exception_id=ex.id))
            receiver = rules.parties(clean(parent), clean(ex))[1]
            if plan.loss_method == 'destroyed' and not disposed and sid == receiver and user.role in PHYSICAL: result['actions'].append('dispose')
            if (plan.loss_method == 'missing' or disposed) and sid == parent.from_store_id and user.role in FINANCE: result['actions'].append('post_loss')
        if plan.kind == 'found_receive' and user.id == plan.actor_id and sid == plan.store_id:
            # Revocation is still a new two-party decision; it cannot erase the approved plan.
            result['notice'] = '获准待收期间再次失联，请记录找回接收失败，不得伪造实际入库。'
    elif ex.status == 'posted' and loss and loss.kind == 'missing':
        if user.role in PHYSICAL: result['actions'].append('observe_found')
        if sid == parent.from_store_id and user.role in FINANCE: result['actions'].append('plan_found')
    from . import vehicle_transport_recovery as claims
    result['claims'] = claims.describe(db, user, ex, parent, sid)
    if loss and user.role in FINANCE and claims.burden(db, ex, parent, sid)>0 and not (plan and plan.kind=='found_receive' and ex.status in {'review','approved'}): result['actions'].append('recovery_create')
    return _project(result, user)


def detail(db, user, key):
    with coordination.authority(db, user, READ) as sid:
        ex, parent = _parent(db, user, key, sid)
        return describe(db, user, ex, parent, sid)


def create(db, user, request_id, transfer_id, version, case_version, kind, evidence_id, reason):
    values = dict(transfer_id=transfer_id, version=version, case_version=case_version, kind=kind, evidence_id=evidence_id, reason=reason)
    def operation(sid):
        parent = original_service.transfer(db, transfer_id, sid)
        parent, case, _ = _lock(db, user, parent, sid, version, case_version)
        if parent.status not in rules.ACTIVE_ORIGINS or active(db, parent): raise HTTPException(409, '只对本次尚未入库、尚无在办差异的实车在途登记差异')
        proof(db, user, case, evidence_id)
        with coordination.coordination_scope(db, parent.from_store_id, (parent.from_store_id, parent.to_store_id)):
            original = db.scalar(select(VehicleMovement).where(VehicleMovement.transfer_id == parent.id, VehicleMovement.kind == 'dispatch'))
            if not original: raise HTTPException(409, '原VIN尚无真实发出记录')
        ex = ExceptionRow(transfer_id=parent.id, active_transfer_id=parent.id, original_id=original.id, origin_status=parent.status,
            kind=kind, store_id=sid, requested_by=user.id, evidence_id=evidence_id, reason=reason)
        db.add(ex); db.flush(); _event(db, user, case, ex, 'open', values)
        sync_tasks(db, user, ex, parent); db.flush()
        return describe(db, user, ex, parent, sid)
    return execute(db, user, request_id, 'vehicle_transport:create', values, PHYSICAL, operation)


def _observe(db, user, case, ex, parent, sid, values, found=False):
    if ex.status != ('posted' if found else 'investigating'): raise HTTPException(409, '请先完成当前方案复核；观察不能改写已锁定方案')
    loss = loss_for(db, parent, ex)
    actual = values['actual_at']
    if isinstance(actual, str): actual = datetime.fromisoformat(actual.replace('Z', '+00:00'))
    if actual.tzinfo is None or actual.utcoffset() is None: raise HTTPException(422, '实物核对时间须明确时区')
    actual = actual.astimezone(timezone.utc).replace(tzinfo=None)
    retired = rows(db, FoundUnavailable, exception_id=ex.id) if found else []
    if retired and actual < retired[-1].created_at: raise HTTPException(409, '再次找到须晚于原找回失效事实，不能复用此前在场观察')
    obs = Observation(exception_id=ex.id, store_id=sid, kind='found_usable' if found else values['kind'], vin=values['vin'].upper(),
        actual_at=actual, evidence_id=values['evidence_id'], actor_id=user.id, reason=values['reason'], created_at=utcnow())
    original = _original(db, parent, ex)
    try: rules.validate_observation(clean(parent), clean(ex), clean(obs), clean(original), loss=clean(loss) if loss else None, timezone_name=settings.timezone)
    except (ValueError, TypeError, KeyError) as err: raise HTTPException(409, str(err))
    db.add(obs); db.flush()
    _event(db, user, case, ex, 'observe_found' if found else 'observe', {**values, 'observation_id': obs.id})


def _make_plan(db, user, case, ex, parent, sid, action, values):
    found_kind = action == 'plan_found'; kind = 'found_receive' if found_kind else 'resume' if action == 'plan_resume' else 'loss'
    if sid != parent.from_store_id or ex.status != ('posted' if found_kind else 'investigating'):
        raise HTTPException(409, '仅原资产门店对当前已核对事实提出本版方案')
    observations = latest_observations(db, ex)
    if set(observations) != {parent.from_store_id, parent.to_store_id}: raise HTTPException(409, '须先由两店分别本人核对原VIN')
    source, destination = observations[parent.from_store_id], observations[parent.to_store_id]
    found = one(db, Observation, values['found_observation_id']) if found_kind else None
    loss = loss_for(db, parent, ex) if found_kind else None
    if found and (found.exception_id != ex.id or found.kind != 'found_usable'): raise HTTPException(404, '找回观察不属于本次原失联车辆')
    if found:
        retired = {x.observation_id for x in rows(db, FoundUnavailable, exception_id=ex.id)}
        candidates = [o for o in rows(db, Observation, exception_id=ex.id) if o.kind == 'found_usable' and o.id not in retired]
        if not candidates or candidates[-1].id != found.id: raise HTTPException(409, '请选择最新仍有效的原VIN在场观察；失联或失效的旧发现不能复用')
    original = _original(db, parent, ex)
    plan = Plan(exception_id=ex.id, revision=len(rows(db, Plan, exception_id=ex.id))+1, kind=kind,
        source_observation_id=source.id, destination_observation_id=destination.id,
        found_observation_id=found.id if found else None, receiving_store_id=found.store_id if found else None,
        source_bearer_cents=values.get('source_bearer_cents', 0), destination_bearer_cents=values.get('destination_bearer_cents', 0),
        loss_method=values.get('loss_method', 'none'), store_id=sid, actor_id=user.id, evidence_id=values['evidence_id'],
        reason=values['reason'], created_at=utcnow(), origin_digest=rules.signature(rules.origin_payload(clean(parent), clean(ex), clean(original),
            clean(source), clean(destination), clean(found) if found else None, clean(loss) if loss else None)))
    try: rules.validate_plan(clean(parent), clean(ex), clean(original), clean(source), clean(destination), clean(plan), clean(found) if found else None, clean(loss) if loss else None, timezone_name=settings.timezone)
    except (ValueError, TypeError, KeyError) as err: raise HTTPException(409, str(err))
    db.add(plan); db.flush(); ex.status = 'review'; _reviewer_ids(db, parent, ex, plan)
    _event(db, user, case, ex, action, {**values, 'plan_id': plan.id})


def _review(db, user, case, ex, parent, sid, action, values):
    plan = latest_plan(db, ex)
    if ex.status != 'review' or not plan or plan.id != values['plan_id']: raise HTTPException(409, '只能复核当前尚在两店确认中的原方案')
    parts = plan_parts(db, parent, ex, plan)
    existing = rows(db, Review, plan_id=plan.id)
    if action == 'withdraw':
        if user.id != plan.actor_id or sid != plan.store_id: raise HTTPException(403, '只有本版原经办人可撤回尚未生效方案')
        db.add(Withdrawal(plan_id=plan.id, store_id=sid, evidence_id=values['evidence_id'], actor_id=user.id, reason=values['reason']))
        ex.status = 'posted' if plan.kind == 'found_receive' else 'investigating'
    else:
        excluded = rules.independent_reviewers(clean(ex), clean(plan), [clean(x) for x in parts[:3] if x])
        if user.id in excluded or any(r.actor_id == user.id for r in existing): raise HTTPException(403, '本人不得复核自己参与的原事实，也不能兼任两店复核；管理员不例外')
        if any(r.store_id == sid for r in existing): raise HTTPException(409, '本店已复核本版方案')
        _task(db, user, case, _task_key(ex, 'review_' + str(plan.id)))
        db.add(Review(plan_id=plan.id, store_id=sid, decision=action, evidence_id=values['evidence_id'], actor_id=user.id, reason=values['reason']))
        if action == 'reject': ex.status = 'posted' if plan.kind == 'found_receive' else 'investigating'
        elif len(existing) == 1:
            if plan.kind == 'resume': ex.status = 'resolved'; ex.active_transfer_id = None
            else: ex.status = 'approved'
    _event(db, user, case, ex, action, values)


def _post_loss(db, user, case, ex, parent, sid, values):
    plan = latest_plan(db, ex)
    if ex.status != 'approved' or not plan or plan.kind != 'loss' or sid != parent.from_store_id:
        raise HTTPException(409, '须两店批准当前原车损失，并由原资产门店实际确认')
    _, _, _, _, cost = plan_parts(db, parent, ex, plan)
    if plan.loss_method == 'destroyed' and not rows(db, Disposal, exception_id=ex.id): raise HTTPException(409, '在手不可用原车尚未实际处置，不得先记损失')
    _task(db, user, case, _task_key(ex, 'post_loss'))
    loss = Loss(transfer_id=parent.id, exception_id=ex.id, original_id=ex.original_id, plan_id=plan.id, case_id=case.id,
        value_cents=cost, source_bearer_cents=plan.source_bearer_cents, destination_bearer_cents=plan.destination_bearer_cents,
        kind=plan.loss_method, evidence_id=values['evidence_id'], actor_id=user.id, business_date=today())
    db.add(loss); db.flush()
    amount = plan.destination_bearer_cents
    if amount:
        for party, other, sign in ((parent.from_store_id, parent.to_store_id, 1), (parent.to_store_id, parent.from_store_id, -1)):
            with coordination.coordination_scope(db, party, (parent.from_store_id, parent.to_store_id)):
                db.add(LossSettlement(transfer_id=parent.id, loss_id=loss.id, exception_id=ex.id,
                    counterparty_store_id=other, amount_cents=sign*amount, business_date=today()))
    ex.status = 'posted'; parent.status = 'lost'
    _event(db, user, case, ex, 'post_loss', {**values, 'loss_id': loss.id})


def _dispose(db, user, case, ex, parent, sid, values):
    plan = latest_plan(db, ex)
    receiver = rules.parties(clean(parent), clean(ex))[1]
    if ex.status != 'approved' or not plan or plan.kind != 'loss' or plan.loss_method != 'destroyed' or sid != receiver:
        raise HTTPException(409, '仅获准实际处置在手不可用原车的门店可记录销毁')
    plan_parts(db, parent, ex, plan)
    if values['vin'].upper() != parent.vin: raise HTTPException(409, '实际处置VIN与原车不一致')
    _task(db, user, case, _task_key(ex, 'dispose'))
    db.add(Disposal(exception_id=ex.id, plan_id=plan.id, store_id=sid, vin=parent.vin,
        evidence_id=values['evidence_id'], actor_id=user.id, reason=values['reason'], business_date=today()))
    _event(db, user, case, ex, 'dispose', values)


def _receive_found(db, user, case, ex, parent, custody, sid, values):
    plan = latest_plan(db, ex)
    if ex.status != 'approved' or not plan or plan.kind != 'found_receive' or sid != plan.receiving_store_id or parent.status != 'lost':
        raise HTTPException(409, '仅本版获两店批准的实际找回门店可验收原车')
    _, _, found, loss, cost = plan_parts(db, parent, ex, plan)
    if values['vin'].upper() != parent.vin: raise HTTPException(409, '实际找回VIN与已确认损失原车不一致')
    _task(db, user, case, _task_key(ex, 'found_receive'))
    vehicle = original_service.receipt_vehicle(db, user, parent, custody, values['location_id'], case, values['evidence_id'])
    receipt = FoundReceipt(transfer_id=parent.id, exception_id=ex.id, loss_id=loss.id, plan_id=plan.id, observation_id=found.id,
        vehicle_id=vehicle.id, case_id=case.id, value_cents=cost, location_id=values['location_id'],
        evidence_id=values['evidence_id'], actor_id=user.id, business_date=today())
    db.add(receipt); db.flush()
    amount = rules.found_pair_amount(clean(parent), clean(loss), sid)
    if amount:
        for party, other, sign in ((parent.from_store_id, parent.to_store_id, 1), (parent.to_store_id, parent.from_store_id, -1)):
            with coordination.coordination_scope(db, party, (parent.from_store_id, parent.to_store_id)):
                db.add(FoundSettlement(transfer_id=parent.id, receipt_id=receipt.id, loss_id=loss.id,
                    counterparty_store_id=other, amount_cents=sign*amount, business_date=today()))
    parent.status = 'recovered'; ex.status = 'recovered'; ex.active_transfer_id = None
    _event(db, user, case, ex, 'found_receive', {**values, 'receipt_id': receipt.id, 'vehicle_id': vehicle.id})


def _found_unavailable(db, user, case, ex, parent, sid, values):
    plan = latest_plan(db, ex)
    if ex.status != 'approved' or not plan or plan.kind != 'found_receive' or sid != plan.receiving_store_id:
        raise HTTPException(409, '只能由本版实际接收门店说明尚未入库的原找回车辆不能接收')
    plan_parts(db, parent, ex, plan)
    if values['vin'].upper() != parent.vin: raise HTTPException(409, '无法接收的车辆须核对该原VIN')
    _task(db, user, case, _task_key(ex, 'found_receive'))
    row = FoundUnavailable(exception_id=ex.id, plan_id=plan.id, observation_id=plan.found_observation_id,
        store_id=sid, vin=parent.vin, kind=values['kind'], evidence_id=values['evidence_id'], actor_id=user.id, reason=values['reason'])
    db.add(row); db.flush()
    # Safety withdrawal of this local physical attestation, not unilateral
    # reversal of the two-store original loss or a second loss posting.
    ex.status = 'posted'
    _event(db, user, case, ex, 'found_unavailable', {**values, 'unavailable_id': row.id})
    for other, cid in ((parent.from_store_id, parent.from_case_id), (parent.to_store_id, parent.to_case_id)):
        if other == sid: continue
        with coordination.coordination_scope(db, other, (parent.from_store_id, parent.to_store_id)):
            flow.log_event(db, user, flow.scoped_get(db, Case, cid), 'vehicle_transport_found_notification',
                '对方尚未验收入库，本次找回失效；原损失及原往来继续保留', detail={'exception_id': ex.id, 'plan_id': plan.id})


def command(db, user, key, request_id, version, case_version, exception_version, action, values):
    from . import vehicle_transport_recovery as claims
    roles = (PHYSICAL if action in {'observe', 'observe_found', 'plan_resume', 'dispose', 'found_receive', 'found_unavailable'} else
        FINANCE if action in {'plan_loss', 'plan_found', 'post_loss'} else MANAGER if action in {'approve', 'reject'} else READ - {'auditor'})
    if action in claims.ACTIONS: roles = claims.roles(action)
    payload = dict(version=version, case_version=case_version, exception_version=exception_version, values=values)
    def operation(sid):
        ex, parent = _parent(db, user, key, sid)
        parent, case, custody = _lock(db, user, parent, sid, version, case_version, ex, exception_version)
        if action not in claims.ACTIONS:
            current = latest_plan(db, ex)
            financial = action in {'plan_loss', 'plan_found', 'post_loss'} or action in {'approve', 'reject', 'withdraw'} and current is not None and current.kind != 'resume'
            proof(db, user, case, values['evidence_id'], financial)
        if action in {'observe', 'observe_found'}: _observe(db, user, case, ex, parent, sid, values, action == 'observe_found')
        elif action in {'plan_resume', 'plan_loss', 'plan_found'}: _make_plan(db, user, case, ex, parent, sid, action, values)
        elif action in {'approve', 'reject', 'withdraw'}: _review(db, user, case, ex, parent, sid, action, values)
        elif action == 'dispose': _dispose(db, user, case, ex, parent, sid, values)
        elif action == 'post_loss': _post_loss(db, user, case, ex, parent, sid, values)
        elif action == 'found_receive': _receive_found(db, user, case, ex, parent, custody, sid, values)
        elif action == 'found_unavailable': _found_unavailable(db, user, case, ex, parent, sid, values)
        elif action in claims.ACTIONS: claims.act(db, user, ex, parent, case, sid, action, values)
        else: raise HTTPException(404, '整车差异动作不存在')
        db.flush(); sync_tasks(db, user, ex, parent); db.flush()
        return describe(db, user, ex, parent, sid)
    return execute(db, user, request_id, f'vehicle_transport:{key}:{action}', payload, roles, operation)


def clearing_pause_info(db, user, transfer_id):
    """A known finding freezes new loss payments, not original paid receipts."""
    with coordination.authority(db, user, READ) as sid:
        parent = original_service.transfer(db, transfer_id, sid)
        ex = active(db, parent)
        if not ex: return None
        plan = latest_plan(db, ex)
        return ex.id if plan and plan.kind == 'found_receive' and ex.status in {'review', 'approved'} else None


def lock_clearing_parent(db, user, transfer_id, action):
    # This lock is taken before clearing bucket/account locks, exactly as in
    # the physical command. A later real receipt cannot race a new payout.
    with coordination.authority(db, user, FINANCE | MANAGER) as sid:
        parent = original_service.transfer(db, transfer_id, sid)
        parent = db.scalar(select(VehicleTransfer).where(VehicleTransfer.id == parent.id)
            .with_for_update().execution_options(populate_existing=True))
        parent.updated_at = utcnow(); db.flush()
        if action in {'clearing_create', 'clearing_pay'} and clearing_pause_info(db, user, transfer_id):
            raise HTTPException(409, '原车找回方案在办，暂停新增原损失付款；已付款的原到账确认、未付款撤销及差异记录仍沿原单办理')

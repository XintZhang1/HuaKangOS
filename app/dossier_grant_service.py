"""Named cross-store dossier access, separate from normal source endpoints.

No source write, new cash/inventory event, identity merge or financial clearing
is performed here. Each returned record/file requires a fresh checked grant and
an audit committed before response bytes are released.
"""
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
import json

from fastapi import HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError

from .db import utcnow
from .models import User, Store, Vehicle
from .flow_models import Case, Customer, FileAsset, FlowEvent
from .dossier_grant_models import (DossierGrant, DossierGrantFile, DossierDecision,
                                   DossierAccess, DossierReceipt)
from . import dossier_grant_rules as rules
from . import flow_engine as eng
from .tenancy import single_store, set_scope, role_for_store, project_user
from .flow_documents import can_file
from .file_security import require_usable, is_usable
from .private_files import read_content
from .services import audit

MAX_EVENT_ROWS = 200  # A bounded, explicitly labelled history window, not a claim of all history.


@contextmanager
def authority(db, user, roles=rules.READ):
    sid = single_store(db)
    account = db.scalar(select(User).where(User.id == user.id).execution_options(populate_existing=True))
    store = db.scalar(select(Store).where(Store.id == sid, Store.active.is_(True)))
    role = role_for_store(db, account, sid)
    if not account or not store or role not in roles or role != user.role:
        raise HTTPException(403, '当前门店或岗位不能办理原单档案授权，请重新登录核对权限')
    previous = db.info.get('_dossier_authority')
    db.info['_dossier_authority'] = (user.id, sid)
    try:
        yield sid
    finally:
        if previous is None:
            db.info.pop('_dossier_authority', None)
        else:
            db.info['_dossier_authority'] = previous


@contextmanager
def _source_scope(db, grant):
    """Only after an exact local-party grant was selected; never a write scope."""
    if not db.info.get('_dossier_authority'):
        raise HTTPException(403, '尚未核验原单授权')
    keys = ('store_scope', 'write_store')
    previous = {key: db.info.get(key) for key in keys}
    with db.no_autoflush:
        set_scope(db, [grant.from_store_id], None)
        try:
            yield
        finally:
            for key, value in previous.items():
                if value is None:
                    db.info.pop(key, None)
                else:
                    db.info[key] = value


def _case(db, user, case_id, *, lock=False):
    statement = select(Case).where(Case.id == case_id, Case.store_id == single_store(db))
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(statement)
    if not row or not eng.can_read(db, user, row):
        raise HTTPException(404, '原业务不存在或当前岗位无权查看')
    if not rules.role_allows(db, user.role, row):
        raise HTTPException(403, '该类记录须使用原管理权限，不能通过档案授权扩大访问')
    return row


def _recipient(db, user_id, sid, *, lock=False):
    query = select(User).where(User.id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    user = db.scalar(query)
    role = role_for_store(db, user, sid)
    if not user or not user.active or user.must_change_password or role not in rules.READ:
        raise HTTPException(409, '接收员工尚未启用、未完成首次改密，或没有接收门店的匹配岗位')
    if not db.scalar(select(Store.id).where(Store.id == sid, Store.active.is_(True))):
        raise HTTPException(409, '接收门店已停用')
    return user, role


def _source_allowed(db, user, grant):
    if user.role not in rules.MANAGE | {'auditor'} and (
        user.id != grant.requested_by or user.role != grant.requester_role
        or user.access_version != grant.requester_access_version):
        raise HTTPException(404, '此授权仅对原发起人和原店复核审计岗位可见')
    row = _case(db, user, grant.source_case_id)
    if grant.from_store_id != single_store(db):
        raise HTTPException(404, '当前门店没有该授权')
    return row


def _grant(db, user, key, *, source=False, lock=False):
    sid = single_store(db)
    criterion = DossierGrant.from_store_id == sid if source else or_(
        DossierGrant.from_store_id == sid,
        (DossierGrant.to_store_id == sid) & (DossierGrant.recipient_id == user.id))
    statement = select(DossierGrant).where(DossierGrant.id == key, criterion)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    grant = db.scalar(statement)
    if not grant:
        raise HTTPException(404, '授权不存在或未指定当前门店和员工')
    if grant.from_store_id == sid:
        _source_allowed(db, user, grant)
    return grant


def _files(db, grant):
    rows = list(db.scalars(select(DossierGrantFile).where(
        DossierGrantFile.grant_id == grant.id).order_by(DossierGrantFile.file_id)))
    for row in rows:
        if not isinstance(row.metadata_snapshot, dict) or row.metadata_snapshot.get('id') != row.file_id:
            raise HTTPException(409, '逐件授权编号与批准范围不一致，停止读取')
    return rows


def _scope_check(db, grant):
    files = _files(db, grant)
    try:
        rules.validate_record(grant.record_snapshot, grant.include_record, grant.include_contact, grant.include_financials)
    except ValueError as exc:
        raise HTTPException(409, '原单快照范围不完整或含未批准字段') from exc
    if len(files) > rules.MAX_FILES or not grant.include_record and not files:
        raise HTTPException(409, '档案授权范围不完整')
    expected = rules.digest(rules.scope_payload(grant, [r.metadata_snapshot for r in files]))
    if expected != grant.scope_digest:
        raise HTTPException(409, '授权范围与原始摘要不一致，停止读取')
    if grant.include_record:
        record = grant.record_snapshot
        if (record.get('definition_version') != rules.PROJECTION_VERSION
            or record.get('case', {}).get('id') != grant.source_case_id
            or record.get('case', {}).get('version') != grant.source_case_version):
            raise HTTPException(409, '原单快照版本或来源不一致')
    elif grant.record_snapshot:
        raise HTTPException(409, '仅文件授权不能附带原单内容')
    return files


def _decisions(db, grant):
    rows = list(db.scalars(select(DossierDecision).where(
        DossierDecision.grant_id == grant.id).order_by(DossierDecision.previous_version)))
    state, version, approval = 'pending', 1, None
    for row in rows:
        target = {'approve': 'approved', 'reject': 'rejected', 'cancel': 'cancelled', 'revoke': 'revoked'}.get(row.action)
        if (row.previous_version != version or row.scope_digest != grant.scope_digest
            or row.store_id != grant.from_store_id or not target
            or row.occurred_at < grant.created_at
            or (row.action == 'revoke' and state != 'approved')
            or (row.action != 'revoke' and state != 'pending')):
            raise HTTPException(409, '原店复核与授权状态不一致，停止读取')
        if row.action in {'approve', 'reject'} and (row.actor_id == grant.requested_by or row.actor_role not in rules.MANAGE):
            raise HTTPException(409, '缺少原店不同人员的独立复核')
        if row.action == 'approve':
            if row.occurred_at >= grant.expires_at:
                raise HTTPException(409, '批准发生在授权到期后')
            approval = row
        state, version = target, version + 1
    if state != grant.status or version != grant.version:
        raise HTTPException(409, '授权版本缺少对应的原始决定')
    return rows, approval


def _snapshot(db, row, *, include_contact, include_financials):
    from .flow_specs import flow_spec, STATES
    header = {key: getattr(row, key) for key in ('id', 'store_id', 'number', 'kind', 'flow_version',
                                              'version', 'state', 'title')}
    header.update(kind_label=flow_spec(row.kind, row.flow_version)['label'], state_label=STATES.get(row.state, row.state))
    for key in ('business_date', 'due_date', 'completed_date'):
        value = getattr(row, key)
        header[key] = value.isoformat() if value else None
    header['updated_at'] = rules.iso(row.updated_at)
    info = {'definition_version': rules.PROJECTION_VERSION, 'case': header}
    if row.customer_id:
        customer = db.scalar(select(Customer).where(Customer.id == row.customer_id, Customer.store_id == row.store_id))
        if not customer:
            raise HTTPException(409, '原单客户来源不完整，不能冻结档案')
        # No master ID or master link is exposed. Contact information is opt-in.
        info['customer'] = {'name': customer.name}
        if include_contact:
            info['customer'].update(phone=customer.phone, contact_allowed=customer.contact_allowed)
    if row.vehicle_id:
        vehicle = db.scalar(select(Vehicle).where(Vehicle.id == row.vehicle_id, Vehicle.store_id == row.store_id))
        if not vehicle:
            raise HTTPException(409, '原单车辆来源不完整，不能冻结档案')
        info['vehicle'] = {'vin': vehicle.vin, 'model': vehicle.model, 'color': vehicle.color}
    events = list(db.scalars(select(FlowEvent).where(FlowEvent.case_id == row.id, FlowEvent.store_id == row.store_id)
        .order_by(FlowEvent.id.desc()).limit(MAX_EVENT_ROWS)))
    # Only original action labels and states, NOT unrestricted nested payloads,
    # evidence IDs, accounts, notes, other cases or current source actions.
    info['events'] = [{'id': e.id, 'label': e.label, 'from_state': e.before_state,
                       'to_state': e.after_state, 'occurred_at': rules.iso(e.occurred_at)} for e in reversed(events)]
    total = db.scalar(select(func.count()).select_from(FlowEvent).where(
        FlowEvent.case_id == row.id, FlowEvent.store_id == row.store_id)) or 0
    info['event_total'], info['events_omitted'] = total, max(0, total - len(events))
    if include_financials:
        info['financials'] = {'amount_cents': row.amount_cents, 'paid_cents': eng.paid_amount(db, row),
                              'cost_cents': row.cost_cents, 'basis': '批准前原单记账快照，不是实际资金划付'}
    return info


def _validate_file(db, source, asset, sender, recipient):
    if (not asset or asset.store_id != source.store_id or asset.case_id != source.id
        or not can_file(sender, source, asset) or not can_file(recipient, source, asset)):
        raise HTTPException(403, '文件必须来自本张原单，且原店与接收岗位均可查看该文件类别')
    require_usable(db, asset)


def _principal_bindings(db, grant, approval=None, *, lock=False):
    """Pin both store roles and account generations; re-enabling cannot resurrect."""
    checks = [(grant.requested_by, grant.from_store_id, grant.requester_role, grant.requester_access_version),
              (grant.recipient_id, grant.to_store_id, grant.recipient_role, grant.recipient_access_version)]
    if approval:
        checks.append((approval.actor_id, grant.from_store_id, approval.actor_role, approval.actor_access_version))
    users = {}
    ids = sorted({r[0] for r in checks})
    statement = select(User).where(User.id.in_(ids)).order_by(User.id).execution_options(populate_existing=True)
    if lock:
        statement = statement.with_for_update()
    users = {u.id: u for u in db.scalars(statement)}
    for uid, sid, role, version in checks:
        u = users.get(uid)
        if (not u or not u.active or u.must_change_password or u.access_version != version
            or role_for_store(db, u, sid) != role):
            raise HTTPException(409, '授权相关账号或门店岗位已变化，原授权暂停；请由原店重新核对申请')
    stores = select(Store).where(Store.id.in_([grant.from_store_id, grant.to_store_id])).order_by(Store.id)
    if lock:
        stores = stores.with_for_update()
    values = list(db.scalars(stores.execution_options(populate_existing=True)))
    if len(values) != 2 or any(not s.active for s in values):
        raise HTTPException(409, '授权相关门店已停用，停止读取')
    return users


def _live_access(db, user, grant, *, lock=False):
    if single_store(db) != grant.to_store_id or user.id != grant.recipient_id:
        raise HTTPException(404, '只有授权指定的接收员工可通过此入口读取')
    files = _scope_check(db, grant)
    _, approval = _decisions(db, grant)
    if grant.status != 'approved' or not approval:
        raise HTTPException(403, '原店尚未批准，或此授权已结束')
    if utcnow() >= grant.expires_at:
        raise HTTPException(403, '授权已到期，请由原店重新核对申请')
    users = _principal_bindings(db, grant, approval, lock=lock)
    with _source_scope(db, grant):
        source_query = select(Case).where(Case.id == grant.source_case_id, Case.store_id == grant.from_store_id)
        if lock:
            # Original-case reassignment can change the sender's visibility even
            # when no account role changes. Serialize this check with that write.
            source_query = source_query.with_for_update().execution_options(populate_existing=True)
        source = db.scalar(source_query)
        sender = project_user(users[grant.requested_by], grant.requester_role)
        reviewer = project_user(users[approval.actor_id], approval.actor_role)
        if (not source or not rules.role_allows(db, user.role, source)
            or not eng.can_read(db, sender, source) or not eng.can_read(db, reviewer, source)):
            raise HTTPException(403, '原单或原店授权人员的可读范围已变化，停止读取')
    return files, users


def _safe_status(db, user, grant):
    if grant.status != 'approved':
        return grant.status, rules.STATES[grant.status]
    if utcnow() >= grant.expires_at:
        return 'expired', rules.STATES['expired']
    try:
        _, approval = _decisions(db, grant)
        _principal_bindings(db, grant, approval)
    except HTTPException:
        return 'suspended', rules.STATES['suspended']
    return grant.status, rules.STATES[grant.status]


def _public_file(item):
    meta = item.metadata_snapshot
    return {key: meta[key] for key in ('id', 'name', 'category', 'media_type', 'size', 'sha256', 'created_at')}


def _detail(db, user, grant):
    source_side = grant.from_store_id == single_store(db)
    state, label = _safe_status(db, user, grant)
    if not source_side and state == 'approved':
        try:
            _live_access(db, user, grant)
        except HTTPException:
            state, label = 'suspended', rules.STATES['suspended']
    # On the receiver side, ended/pending/suspended rows carry no source payload,
    # customer, original number, purpose, file name or unapproved file metadata.
    response = {'id': grant.id, 'version': grant.version, 'status': grant.status,
        'effective_status': state, 'status_label': label, 'from_store_id': grant.from_store_id,
        'to_store_id': grant.to_store_id, 'recipient_id': grant.recipient_id,
        'expires_at': rules.iso(grant.expires_at), 'created_at': rules.iso(grant.created_at),
        'source_side': source_side, 'can_read': not source_side and state == 'approved',
        'can_review': source_side and user.role in rules.MANAGE and user.id != grant.requested_by
            and grant.status == 'pending' and utcnow() < grant.expires_at,
        'can_cancel': source_side and grant.status == 'pending'
            and (user.id == grant.requested_by or user.role in rules.MANAGE),
        'can_revoke': source_side and grant.status == 'approved'
            and (user.id == grant.requested_by or user.role in rules.MANAGE)}
    if response['can_read']:
        response.update(include_record=grant.include_record, include_contact=grant.include_contact,
                        include_financials=grant.include_financials)
    for key, sid in [('from_store_name', grant.from_store_id), ('to_store_name', grant.to_store_id)]:
        store = db.scalar(select(Store).where(Store.id == sid))
        response[key] = store.name if store else '已不可用门店'
    if source_side:
        _source_allowed(db, user, grant)
        files = _scope_check(db, grant)
        decisions, _ = _decisions(db, grant)
        receiver = db.scalar(select(User).where(User.id == grant.recipient_id))
        response.update(source_case_id=grant.source_case_id, source_case_version=grant.source_case_version,
            requested_by=grant.requested_by, recipient_name=receiver.display_name if receiver else '',
            recipient_role=grant.recipient_role, purpose=grant.purpose,
            include_record=grant.include_record, include_financials=grant.include_financials,
            include_contact=grant.include_contact, scope_digest=grant.scope_digest,
            preview=grant.record_snapshot, files=[_public_file(f) for f in files],
            decisions=[{'action': d.action, 'actor_id': d.actor_id, 'reason': d.reason,
                        'occurred_at': rules.iso(d.occurred_at)} for d in decisions])
    return response


def detail(db, user, key):
    with authority(db, user):
        return _detail(db, user, _grant(db, user, key))


def listing(db, user, *, box='received', state='', page=1, source_case_id=None):
    with authority(db, user) as sid:
        if box not in {'received', 'sent', 'review'}:
            raise HTTPException(422, '请选择收到的授权、本店发出或待我复核')
        if box == 'received':
            criterion = (DossierGrant.to_store_id == sid) & (DossierGrant.recipient_id == user.id)
        else:
            if box == 'review' and user.role not in rules.MANAGE:
                raise HTTPException(403, '原店复核需要主管岗位')
            visible = eng.case_query(user).with_only_columns(Case.id)
            criterion = (DossierGrant.from_store_id == sid) & (DossierGrant.source_case_id.in_(visible))
            if user.role not in rules.MANAGE | {'auditor'}:
                criterion &= DossierGrant.requested_by == user.id
            if box == 'review':
                criterion &= (DossierGrant.status == 'pending') & (DossierGrant.requested_by != user.id) & (DossierGrant.expires_at > utcnow())
        query = select(DossierGrant).where(criterion)
        if source_case_id is not None:
            if box == 'received':
                raise HTTPException(422, '收到的授权不能按未开放的原单编号筛选')
            _case(db, user, source_case_id)
            query = query.where(DossierGrant.source_case_id == source_case_id)
        if state:
            if state not in rules.STATES or state in {'expired', 'suspended'}:
                raise HTTPException(422, '授权状态筛选无效')
            query = query.where(DossierGrant.status == state)
        if box == 'received':
            count = db.scalar(select(func.count()).select_from(query.subquery()))
            rows = db.scalars(query.order_by(DossierGrant.id.desc()).offset((page - 1) * 30).limit(30))
            items = [_detail(db, user, grant) for grant in rows]
        else:
            # Exact source authorization precedes pagination AND count. The
            # coarse case_query alone cannot disclose even a hidden row count.
            count, items = 0, []
            for grant in db.scalars(query.order_by(DossierGrant.id.desc()).execution_options(yield_per=100)):
                try:
                    _source_allowed(db, user, grant)
                except HTTPException as exc:
                    if exc.status_code in {403, 404}:
                        continue
                    raise
                if (page - 1) * 30 <= count < page * 30:
                    items.append(_detail(db, user, grant))
                count += 1
        return {'items': items, 'total': count, 'page': page, 'page_size': 30}



def source_options(db, user, case_id, to_store_id=None, recipient_id=None):
    with authority(db, user, rules.WRITE) as sid:
        row = _case(db, user, case_id)
        result = {'case': {'id': row.id, 'number': row.number, 'version': row.version},
            'stores': [{'id': s.id, 'label': s.name} for s in db.scalars(select(Store).where(
                Store.active.is_(True), Store.id != sid).order_by(Store.id))], 'recipients': [], 'files': [],
            'can_financials': False, 'max_validity_days': rules.MAX_VALIDITY_DAYS,
            'notice': '指定员工只读批准时的快照和勾选文件；不开放关联单据、全部客户档案或后续新增文件。'}
        if to_store_id is None:
            return result
        if to_store_id == sid or not db.scalar(select(Store.id).where(Store.id == to_store_id, Store.active.is_(True))):
            raise HTTPException(422, '请选择其他启用的直营门店')
        for account in db.scalars(select(User).where(User.id != user.id, User.active.is_(True), User.must_change_password.is_(False)).order_by(User.id)):
            role = role_for_store(db, account, to_store_id)
            if rules.role_allows(db, role, row):
                result['recipients'].append({'id': account.id, 'label': account.display_name, 'role': role})
        if recipient_id is None:
            return result
        receiver, role = _recipient(db, recipient_id, to_store_id)
        if not rules.role_allows(db, role, row):
            raise HTTPException(403, '接收岗位不能查看该类原业务')
        principal = project_user(receiver, role)
        result['can_financials'] = user.role in rules.FINANCIAL and role in rules.FINANCIAL
        result['files'] = [_public_file(SimpleNamespace(metadata_snapshot=rules.file_snapshot(a))) for a in db.scalars(
            select(FileAsset).where(FileAsset.case_id == row.id, FileAsset.store_id == sid).order_by(FileAsset.id))
            if can_file(user, row, a) and can_file(principal, row, a) and is_usable(db, a)]
        return result


def _execute(db, user, request_id, action, payload, operation):
    with authority(db, user, rules.WRITE) as sid:
        request_digest = rules.digest({'action': action, 'payload': payload})
        try:
            old = db.scalar(select(DossierReceipt).where(DossierReceipt.request_key == request_id, DossierReceipt.store_id == sid))
            if old:
                if old.actor_id != user.id or old.digest != request_digest:
                    raise HTTPException(409, '请求编号已用于其他内容或其他经办人')
                grant = _grant(db, user, old.grant_id, source=True)
                if old.scope_digest != grant.scope_digest:
                    raise HTTPException(409, '原请求与冻结范围不一致')
                return {'grant': _detail(db, user, grant), 'replayed': True}
            grant = operation(sid)
            db.flush()
            db.add(DossierReceipt(store_id=sid, request_key=request_id, actor_id=user.id, digest=request_digest,
                action=action, request_data=payload, grant_id=grant.id, scope_digest=grant.scope_digest))
            response = _detail(db, user, grant)
            db.commit()
            return {'grant': response, 'replayed': False}
        except (IntegrityError, OperationalError, StaleDataError) as exc:
            db.rollback()
            raise HTTPException(409, '授权已变化或有同时办理，本次未保存；请刷新核对并保留请求编号') from exc
        except Exception:
            db.rollback()
            raise


def propose(db, user, request_id, values):
    payload = dict(values)
    payload['expires_at'] = rules.iso(values['expires_at'])

    def operation(sid):
        now, expires = utcnow(), rules.timestamp(values['expires_at'])
        if not now < expires <= now + timedelta(days=rules.MAX_VALIDITY_DAYS):
            raise HTTPException(422, '授权期限须在当前时间之后，且不超过一年')
        if values['to_store_id'] == sid:
            raise HTTPException(422, '此入口用于跨店授权，本店请使用原业务权限')
        row = _case(db, user, values['source_case_id'], lock=True)
        if row.version != values['source_case_version']:
            raise HTTPException(409, '原单已变化，请刷新核对后提交')
        receiver, role = _recipient(db, values['recipient_id'], values['to_store_id'], lock=True)
        if receiver.id == user.id:
            raise HTTPException(422, '不能给自己跨店授权；已有多店权限请切换原门店查看')
        if not rules.role_allows(db, role, row):
            raise HTTPException(403, '接收岗位不能查看该类原业务')
        if values['include_financials'] and (user.role not in rules.FINANCIAL or role not in rules.FINANCIAL):
            raise HTTPException(403, '金额成本快照仅可在双方均有财务可读岗位时单独授权')
        if not values['include_record'] and (values['include_financials'] or values['include_contact']):
            raise HTTPException(422, '仅文件授权不能附带原单金额或联系方式')
        files = []
        for file_id in sorted(values['file_ids']):
            asset = db.scalar(select(FileAsset).where(FileAsset.id == file_id, FileAsset.store_id == sid, FileAsset.case_id == row.id))
            _validate_file(db, row, asset, user, project_user(receiver, role))
            files.append(rules.file_snapshot(asset))
        if not values['include_record'] and not files:
            raise HTTPException(422, '请至少选择原单快照或一个具体文件')
        record = _snapshot(db, row, include_contact=values['include_contact'], include_financials=values['include_financials']) if values['include_record'] else {}
        grant = DossierGrant(from_store_id=sid, to_store_id=values['to_store_id'], source_case_id=row.id,
            source_case_version=row.version, recipient_id=receiver.id, recipient_role=role,
            recipient_access_version=receiver.access_version, requested_by=user.id, requester_role=user.role,
            requester_access_version=user.access_version, include_record=values['include_record'],
            include_financials=values['include_financials'], include_contact=values['include_contact'],
            record_snapshot=record, purpose=values['purpose'], expires_at=expires, status='pending',
            created_at=now, updated_at=now, scope_digest='')
        grant.scope_digest = rules.digest(rules.scope_payload(grant, files))
        db.add(grant)
        db.flush()
        db.add_all([DossierGrantFile(grant_id=grant.id, file_id=f['id'], metadata_snapshot=f) for f in files])
        db.flush()
        audit(db, user.id, 'dossier_propose', 'dossier_grant', grant.id,
              reason='提交指定员工的只读档案范围', after={'source_case_id': row.id, 'scope_digest': grant.scope_digest})
        return grant
    return _execute(db, user, request_id, 'propose', payload, operation)


def decide(db, user, request_id, key, version, action, values):
    if action not in {'approve', 'reject', 'cancel', 'revoke'}:
        raise HTTPException(404, '授权办理动作不存在')
    payload = {'grant_id': key, 'version': version, **values}

    def operation(sid):
        grant = _grant(db, user, key, source=True, lock=True)
        if grant.version != version:
            raise HTTPException(409, '授权已由他人办理，请刷新后核对')
        files = _scope_check(db, grant)
        _decisions(db, grant)
        if action in {'approve', 'reject'}:
            if user.role not in rules.MANAGE or user.id == grant.requested_by:
                raise HTTPException(403, '须由原店另一名主管独立复核，不能自行批准')
            if grant.status != 'pending':
                raise HTTPException(409, '只有待复核授权可以批准或拒绝')
        elif action == 'cancel':
            if grant.status != 'pending' or (user.id != grant.requested_by and user.role not in rules.MANAGE):
                raise HTTPException(403, '仅发起人或原店主管可取消待复核授权')
        elif grant.status != 'approved' or (user.id != grant.requested_by and user.role not in rules.MANAGE):
            raise HTTPException(403, '仅发起人或原店主管可撤销已批准授权')
        if action == 'approve':
            if utcnow() >= grant.expires_at:
                raise HTTPException(409, '授权已到期，不能补批')
            users = _principal_bindings(db, grant, lock=True)
            source = _case(db, user, grant.source_case_id, lock=True)
            sender = project_user(users[grant.requested_by], grant.requester_role)
            recipient = project_user(users[grant.recipient_id], grant.recipient_role)
            if not eng.can_read(db, sender, source) or not rules.role_allows(db, recipient.role, source):
                raise HTTPException(409, '原单负责人或接收岗位的范围已变化，请重新申请')
            expected = _snapshot(db, source, include_contact=grant.include_contact, include_financials=grant.include_financials) if grant.include_record else {}
            if source.version != grant.source_case_version or expected != grant.record_snapshot:
                raise HTTPException(409, '原单或快照依赖已变化，不会静默扩大范围；请取消后重新申请')
            for file in files:
                asset = db.scalar(select(FileAsset).where(FileAsset.id == file.file_id, FileAsset.store_id == sid, FileAsset.case_id == source.id))
                _validate_file(db, source, asset, sender, recipient)
                if not can_file(user, source, asset) or rules.file_snapshot(asset) != file.metadata_snapshot:
                    raise HTTPException(409, '文件版本或岗位可读范围已变化，不能批准')
        now = utcnow()
        db.add(DossierDecision(grant_id=grant.id, previous_version=grant.version, action=action,
            actor_id=user.id, actor_role=user.role, actor_access_version=user.access_version,
            store_id=sid, scope_digest=grant.scope_digest, reason=values['reason'], occurred_at=now))
        grant.status = {'approve': 'approved', 'reject': 'rejected', 'cancel': 'cancelled', 'revoke': 'revoked'}[action]
        grant.updated_at = now
        db.flush()
        audit(db, user.id, 'dossier_' + action, 'dossier_grant', grant.id,
              reason=values['reason'], after={'scope_digest': grant.scope_digest})
        return grant
    return _execute(db, user, request_id, action, payload, operation)


def _record_access(db, user, grant, action, file_id=None):
    now = utcnow()
    if now >= grant.expires_at:
        raise HTTPException(403, '授权已到期，停止此次读取')
    db.add(DossierAccess(grant_id=grant.id, grant_version=grant.version, actor_id=user.id,
        actor_role=user.role, actor_access_version=user.access_version, store_id=single_store(db),
        action=action, file_id=file_id, scope_digest=grant.scope_digest, occurred_at=now))
    audit(db, user.id, 'dossier_read_' + action, 'dossier_grant', grant.id,
          reason='按独立批准范围只读', after={'scope_digest': grant.scope_digest, 'file_id': file_id})
    # Both SQLite snapshot races and PostgreSQL serialization conflicts must fail
    # BEFORE JSON/file bytes are returned, not merely leave an audit best effort.
    db.commit()


def read_record(db, user, key):
    with authority(db, user):
        try:
            grant = _grant(db, user, key, lock=True)
            files, _ = _live_access(db, user, grant, lock=True)
            if not grant.include_record:
                raise HTTPException(403, '此授权仅包含指定文件，没有原单快照')
            response = {'grant_id': grant.id, 'scope_digest': grant.scope_digest,
                        'frozen_at': rules.iso(grant.created_at), 'expires_at': rules.iso(grant.expires_at),
                        'record': json.loads(rules.canonical(grant.record_snapshot)),
                        'files': [_public_file(f) for f in files], 'read_only': True}
            _record_access(db, user, grant, 'record')
            return response
        except (IntegrityError, OperationalError, StaleDataError) as exc:
            db.rollback()
            raise HTTPException(409, '授权或账号正在变化，本次未返回档案；请刷新核对') from exc
        except Exception:
            db.rollback()
            raise


def received_files(db, user, key):
    """A file-only grant still checks its full authorization, but exposes no case."""
    with authority(db, user):
        try:
            grant = _grant(db, user, key, lock=True)
            files, _ = _live_access(db, user, grant, lock=True)
            response = {'grant_id': grant.id, 'files': [_public_file(f) for f in files],
                        'include_record': grant.include_record, 'expires_at': rules.iso(grant.expires_at)}
            # Metadata is also an authorized read, not an unaudited cached list.
            _record_access(db, user, grant, 'directory')
            return response
        except (IntegrityError, OperationalError, StaleDataError) as exc:
            db.rollback()
            raise HTTPException(409, '授权或账号正在变化，本次未返回文件目录') from exc
        except Exception:
            db.rollback()
            raise


def download(db, user, key, file_id):
    with authority(db, user):
        try:
            grant = _grant(db, user, key, lock=True)
            items, users = _live_access(db, user, grant, lock=True)
            item = next((r for r in items if r.file_id == file_id), None)
            if not item:
                raise HTTPException(404, '该文件未逐件列入此次授权')
            with _source_scope(db, grant):
                source = db.scalar(select(Case).where(Case.id == grant.source_case_id, Case.store_id == grant.from_store_id))
                asset = db.scalar(select(FileAsset).where(FileAsset.id == file_id,
                    FileAsset.store_id == grant.from_store_id, FileAsset.case_id == grant.source_case_id))
                sender = project_user(users[grant.requested_by], grant.requester_role)
                _validate_file(db, source, asset, sender, user)
                if rules.file_snapshot(asset) != item.metadata_snapshot:
                    raise HTTPException(409, '文件编号、原版本或摘要与批准件不一致，停止读取')
                content = read_content(db, asset)
                name, media_type = asset.name, asset.media_type
            _record_access(db, user, grant, 'file', file_id)
            return content, name, media_type
        except (IntegrityError, OperationalError, StaleDataError) as exc:
            db.rollback()
            raise HTTPException(409, '授权或账号正在变化，本次未返回文件；请刷新核对') from exc
        except Exception:
            db.rollback()
            raise

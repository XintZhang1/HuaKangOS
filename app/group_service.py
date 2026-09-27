"""Explicitly authorized shared identity and principal stored-value operations.

Every command commits once with its immutable receipt; callers must not commit
individual postings. No generic central-data CRUD or tenant-scope escape exists.
"""
from contextlib import contextmanager
import hashlib
import json
import re
import uuid
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today, utcnow
from .models import User, UserStore, Store, CashEntry, Vehicle
from .flow_models import Customer, Reference, Case, Account, FileAsset, PaymentLink, Task
from .tenancy import single_store, role_for_store, account_role
from . import business_entity_service as entities
from .group_models import (GroupIdentity, GroupIdentityLink, GroupMember, GroupEntry,
    GroupReservation, GroupRefundRequest, GroupPaymentLink, GroupSettlementEntry, GroupEvent, GroupReceipt)

READ_ROLES = {'admin', 'manager', 'finance', 'auditor', 'service', 'sales', 'reception', 'customer_service'}
IDENTITY_ROLES = READ_ROLES - {'auditor'}
FINANCE_ROLES = {'admin', 'finance'}
REFUND_REQUEST_ROLES = {'admin', 'finance', 'service', 'customer_service'}
REFUND_REVIEW_ROLES = {'admin', 'manager'}


@contextmanager
def authority(db, user, roles=READ_ROLES):
    """Authority never widens ordinary store scope or enables cross-store writes."""
    store_id = single_store(db)
    active = db.scalar(select(Store.id).where(Store.id == store_id, Store.active.is_(True)))
    assignment = db.scalar(select(UserStore).where(UserStore.user_id == user.id, UserStore.store_id == store_id))
    if not active or not user.active or (account_role(user) != 'admin' and not assignment):
        raise HTTPException(403, '没有当前门店的集团业务权限')
    if role_for_store(db, user, store_id) not in roles:
        raise HTTPException(403, '当前门店岗位不能办理此集团业务')
    previous = db.info.get('_group_authority')
    db.info['_group_authority'] = (user.id, store_id)
    try:
        yield store_id
    finally:
        if previous is None:
            db.info.pop('_group_authority', None)
        else:
            db.info['_group_authority'] = previous


def case_paid_amount(db, case_id):
    return db.scalar(select(func.coalesce(func.sum(GroupPaymentLink.amount_cents), 0))
                     .where(GroupPaymentLink.case_id == case_id)) or 0


def case_reserved_amount(db, case_id):
    return db.scalar(select(func.coalesce(func.sum(GroupReservation.amount_cents), 0))
                     .where(GroupReservation.case_id == case_id, GroupReservation.status == 'reserved')) or 0


def _version(row, version):
    if row.version != version:
        raise HTTPException(409, '记录已变化，请刷新并核对后重新办理；不要盲目换请求编号重试')


def _local(db, model, key, store_id):
    row = db.scalar(select(model).where(model.id == key, model.store_id == store_id))
    if not row:
        raise HTTPException(404, '当前门店记录不存在')
    return row


def _digest(action, payload):
    return hashlib.sha256(json.dumps([action, payload], sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def _execute(db, user, request_id, action, payload, operation, roles):
    with authority(db, user, roles) as store_id:
        digest = _digest(action, payload)
        try:
            receipt = db.scalar(select(GroupReceipt).where(GroupReceipt.store_id == store_id,
                                                           GroupReceipt.request_key == request_id))
            if receipt:
                if receipt.actor_id != user.id or receipt.digest != digest:
                    raise HTTPException(409, '请求编号已被其他操作使用')
                return receipt.result
            result = operation(store_id)
            db.add(GroupReceipt(store_id=store_id, request_key=request_id, actor_id=user.id,
                                digest=digest, result=result))
            db.commit()
            return result
        except (IntegrityError, OperationalError, StaleDataError):
            db.rollback()
            raise HTTPException(409, '数据冲突或同时办理中，请刷新核对；保留原请求编号以确认结果')
        except Exception:
            db.rollback()
            raise


def _phone(value):
    value = re.sub(r'[\s()+-]', '', value)
    if not re.fullmatch(r'\d{7,20}', value):
        raise HTTPException(422, '集团客户识别需要有效的完整联系电话；电话相同仍须人工确认身份')
    return value


def link_identity(db, user, request_id, kind, local_id, identity_id=None, identifier=''):
    def operation(store_id):
        if kind == 'customer':
            row = _local(db, Customer, local_id, store_id)
            if user.role in {'sales', 'reception'} and row.owner_id != user.id:
                raise HTTPException(403, '只能关联自己负责的客户')
            name, search_key = row.name, _phone(row.phone)
            canonical = uuid.uuid4().hex
        elif kind == 'vehicle':
            row = _local(db, Vehicle, local_id, store_id)
            name, search_key = row.model, row.vin.upper()
            if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', search_key):
                raise HTTPException(422, '车辆 VIN 必须为有效的 17 位标识')
            canonical = search_key
        elif kind == 'counterparty':
            row = _local(db, Reference, local_id, store_id)
            if row.category not in {'供应商', '保险公司'} or not row.active:
                raise HTTPException(422, '仅供应商和保险公司档案可以关联往来单位')
            name, search_key = row.name, identifier.upper()
            if not re.fullmatch(r'[A-Z0-9]{18}', search_key):
                raise HTTPException(422, '请录入往来单位的 18 位统一社会信用代码')
            canonical = search_key
        else:
            raise HTTPException(422, '共享身份类型无效')
        existing = db.scalar(select(GroupIdentityLink).where(GroupIdentityLink.store_id == store_id,
            GroupIdentityLink.local_kind == kind, GroupIdentityLink.local_id == local_id))
        if existing:
            raise HTTPException(409, '本地档案已关联集团身份；不能通过覆盖关联合并客户')
        if identity_id:
            identity = db.scalar(select(GroupIdentity).where(GroupIdentity.id == identity_id,
                                                            GroupIdentity.kind == kind))
            if not identity or identity.search_key != search_key or (kind != 'vehicle' and identity.name != name):
                raise HTTPException(409, '身份资料不匹配；请核对本地档案与客户确认结果')
        else:
            identity = GroupIdentity(kind=kind, name=name, search_key=search_key,
                                     canonical_key=canonical, created_by=user.id)
            db.add(identity)
            db.flush()
        link = GroupIdentityLink(store_id=store_id, identity_id=identity.id, local_kind=kind,
                                 local_id=local_id, confirmed_by=user.id)
        db.add(link)
        db.add(GroupEvent(store_id=store_id, actor_id=user.id, action='identity_link',
                          detail={'identity_id': identity.id, 'kind': kind, 'local_id': local_id}))
        db.flush()
        return {'identity_id': identity.id, 'link_id': link.id, 'kind': kind, 'local_id': local_id}
    roles = IDENTITY_ROLES | ({'inventory'} if kind in {'vehicle', 'counterparty'} else set())
    return _execute(db, user, request_id, 'identity_link',
        dict(kind=kind, local_id=local_id, identity_id=identity_id, identifier=identifier), operation, roles)


def search_identities(db, user, kind, query):
    roles = READ_ROLES | ({'inventory'} if kind in {'vehicle', 'counterparty'} else set())
    with authority(db, user, roles) as store_id:
        if kind == 'customer':
            key = _phone(query)
        elif kind == 'vehicle' and re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', query.upper()):
            key = query.upper()
        elif kind == 'counterparty' and re.fullmatch(r'[A-Z0-9]{18}', query.upper()):
            key = query.upper()
        else:
            raise HTTPException(422, '请使用完整电话、VIN 或统一社会信用代码精确查询')
        rows = list(db.scalars(select(GroupIdentity).where(GroupIdentity.kind == kind,
                                                           GroupIdentity.search_key == key).limit(20)))
        items = []
        for row in rows:
            linked = db.scalar(select(GroupIdentityLink.id).where(GroupIdentityLink.store_id == store_id,
                                                                    GroupIdentityLink.identity_id == row.id))
            # A candidate is not an authorization to read its source store's history.
            name = row.name if linked or kind != 'customer' else row.name[:1] + '＊' * max(1, len(row.name)-1)
            items.append({'id': row.id, 'kind': row.kind, 'name': name, 'linked': bool(linked)})
        return {'items': items, 'notice': '匹配仅供提示，关联需人工核实；不提供其他门店业务历史'}


def _member(db, member_id, store_id, version=None):
    relation = select(GroupIdentityLink.identity_id).where(GroupIdentityLink.store_id == store_id,
                                                          GroupIdentityLink.local_kind == 'customer')
    row = db.scalar(select(GroupMember).where(GroupMember.id == member_id,
        GroupMember.identity_id.in_(relation)).with_for_update())
    if not row:
        raise HTTPException(404, '会员不存在或尚未关联当前门店客户')
    if not row.active:
        raise HTTPException(409, '集团会员已停用')
    if version is not None:
        _version(row, version)
    return row


def _wallet(row):
    return {'id': row.id, 'identity_id': row.identity_id, 'number': row.number, 'version': row.version,
            'balance_cents': row.balance_cents, 'reserved_cents': row.reserved_cents,
            'available_cents': row.balance_cents-row.reserved_cents, 'active': row.active}


def _refund_info(row):
    return {'id': row.id, 'version': row.version, 'status': row.status, 'case_id': row.case_id,
            'original_id': row.original_id, 'amount_cents': row.amount_cents, 'requested_by': row.requested_by,
            'approved_by': row.approved_by, 'closed_by': row.closed_by, 'executed_entry_id': row.executed_entry_id,
            'reason': row.reason}


def issue_member(db, user, request_id, identity_id):
    def operation(store_id):
        link = db.scalar(select(GroupIdentityLink).where(GroupIdentityLink.store_id == store_id,
            GroupIdentityLink.identity_id == identity_id, GroupIdentityLink.local_kind == 'customer'))
        if not link:
            raise HTTPException(404, '请先关联本店客户与集团身份')
        customer = _local(db, Customer, link.local_id, store_id)
        if user.role in {'sales', 'reception'} and customer.owner_id != user.id:
            raise HTTPException(403, '只能为自己负责的客户开通会员')
        if db.scalar(select(GroupMember.id).where(GroupMember.identity_id == identity_id)):
            raise HTTPException(409, '该集团客户已开通会员，请查询现有会员')
        member = GroupMember(identity_id=identity_id, number='HK'+uuid.uuid4().hex[:20].upper())
        db.add(member)
        db.flush()
        db.add(GroupEvent(store_id=store_id, actor_id=user.id, member_id=member.id,
                          action='issue', detail={'identity_id': identity_id}))
        return {'member': _wallet(member)}
    return _execute(db, user, request_id, 'issue', {'identity_id': identity_id}, operation, IDENTITY_ROLES)


def member_for_customer(db, user, customer_id):
    with authority(db, user) as store_id:
        customer = _local(db, Customer, customer_id, store_id)
        if user.role in {'sales', 'reception'} and customer.owner_id != user.id:
            raise HTTPException(403, '只能查询自己负责的客户会员')
        link = db.scalar(select(GroupIdentityLink).where(GroupIdentityLink.store_id == store_id,
            GroupIdentityLink.local_kind == 'customer', GroupIdentityLink.local_id == customer_id))
        member = db.scalar(select(GroupMember).where(GroupMember.identity_id == link.identity_id)) if link else None
        return {'identity_id': link.identity_id if link else None, 'member': _wallet(member) if member else None,
                'customer': {'id': customer.id, 'name': customer.name, 'phone': customer.phone}}


def member_detail(db, user, member_id):
    with authority(db, user) as store_id:
        member = _member(db, member_id, store_id)
        if user.role in {'sales', 'reception'}:
            own = db.scalar(select(Customer.id).join(GroupIdentityLink, GroupIdentityLink.local_id == Customer.id)
                .where(Customer.store_id == store_id, Customer.owner_id == user.id,
                       GroupIdentityLink.store_id == store_id, GroupIdentityLink.local_kind == 'customer',
                       GroupIdentityLink.identity_id == member.identity_id))
            if not own:
                raise HTTPException(403, '只能查询自己负责的客户会员')
        entries = list(db.scalars(select(GroupEntry).where(GroupEntry.member_id == member.id,
            GroupEntry.store_id == store_id).order_by(GroupEntry.id.desc()).limit(100)))
        reservations = list(db.scalars(select(GroupReservation).where(GroupReservation.member_id == member.id,
            GroupReservation.store_id == store_id).order_by(GroupReservation.id.desc()).limit(100)))
        refund_requests = list(db.scalars(select(GroupRefundRequest).where(GroupRefundRequest.member_id == member.id,
            GroupRefundRequest.store_id == store_id).order_by(GroupRefundRequest.id.desc()).limit(100)))
        result = {'member': _wallet(member), 'entries': [{'id': e.id, 'case_id': e.case_id, 'purpose': e.purpose,
            'amount_cents': e.amount_cents, 'original_id': e.original_id,
            'occurred_at': e.occurred_at.isoformat()+'Z'} for e in entries],
            'reservations': [{'id': r.id, 'case_id': r.case_id, 'version': r.version,
                'amount_cents': r.amount_cents, 'status': r.status} for r in reservations],
            'refund_requests': [_refund_info(r) for r in refund_requests]}
        if user.role in {'admin', 'manager', 'finance', 'auditor'}:
            by_id = {e.id: e for e in entries}
            for item in result['entries']:
                e = by_id[item['id']]
                item.update(cash_id=e.cash_id, account_id=e.account_id, reference=e.reference,
                            evidence_id=e.evidence_id)
        from .business_finance_stored import effective_group_topup
        from .recharge_bundle_service import guard_principal_refund
        originals={e.id:e for e in entries if e.purpose=='topup'}
        missing={r.original_id for r in refund_requests}-set(originals)
        if missing:originals.update({e.id:e for e in db.scalars(select(GroupEntry).where(GroupEntry.id.in_(missing),GroupEntry.store_id==store_id,GroupEntry.member_id==member.id,GroupEntry.purpose=='topup'))})
        result['effective_topups']=[]
        for original in originals.values():
            current=effective_group_topup(db,original);remaining=max(0,_refund_remaining(db,current))
            direct=True
            try:guard_principal_refund(db,original.id)
            except HTTPException as error:
                if error.status_code!=409:raise
                direct=False
            item={'original_id':original.id,'effective_amount_cents':current.amount_cents,'refundable_cents':remaining,
                'available_refund_cents':min(remaining,member.balance_cents-member.reserved_cents),'corrected':current.cash_id!=original.cash_id,
                'direct_refund_allowed':direct}
            if user.role in {'admin','manager','finance','auditor'}:
                item.update(cash_id=current.cash_id,account_id=current.account_id,reference=current.reference,
                    account_name=_local(db,Account,current.account_id,store_id).name if current.cash_id else None)
            result['effective_topups'].append(item)
        return result


def _case(db, user, member, case_id, version, store_id, service=False):
    row = db.scalar(select(Case).where(Case.id == case_id, Case.store_id == store_id).with_for_update())
    if not row:
        raise HTTPException(404, '当前门店业务不存在')
    from .flow_specs import flow_spec
    from .flow_engine import can_read
    flow_spec(row.kind, row.flow_version)
    if not can_read(db, user, row):
        raise HTTPException(403, '当前岗位不能访问退款或办理凭据的来源业务，请交获权岗位办理')
    from .retail_group_service import guard_legacy_wallet_action
    guard_legacy_wallet_action(db,row)
    _version(row, version)
    linked = db.scalar(select(GroupIdentityLink.id).where(GroupIdentityLink.store_id == store_id,
        GroupIdentityLink.local_kind == 'customer', GroupIdentityLink.local_id == row.customer_id,
        GroupIdentityLink.identity_id == member.identity_id))
    if not linked:
        raise HTTPException(409, '本单客户与集团会员身份不一致')
    if service:
        from .aftercare_service import guard_source_action
        guard_source_action(db,user,row,'group_settlement')
        from .repair_service import is_detailed, customer_due
        if is_detailed(row):customer_due(db,row)
        elif row.kind != 'repair' or row.state not in {'settling', 'credit_open'} or row.data.get('payer') != '客户':
            raise HTTPException(409, '仅客户承担且已质检待结算的维修单可使用集团储值')
    row.updated_at = utcnow()
    return row


GROUP_EVIDENCE_CATEGORIES = ('evidence', 'receipt')


def _evidence(db, row, evidence_id, user):
    asset = db.scalar(select(FileAsset).where(FileAsset.id == evidence_id, FileAsset.case_id == row.id,
                                              FileAsset.store_id == row.store_id))
    if not asset or asset.generated:
        raise HTTPException(422, '请上传本单的实际办理凭据；生成文件不代表已确认')
    if asset.category not in GROUP_EVIDENCE_CATEGORIES:
        # 旧文案写“或客户授权凭据”，但“客户授权”并不在校验接受的类别里，
        # 员工按提示选“客户授权”必然被拒。这里改成与校验一致的说明。
        from .flow_engine import category_requirement_message
        raise HTTPException(422, category_requirement_message(asset.category, GROUP_EVIDENCE_CATEGORIES))
    from .flow_documents import can_file
    if not can_file(user, row, asset):
        raise HTTPException(403, '当前岗位不能使用该类来源凭据，请交获权岗位办理')
    from .file_security import require_usable
    require_usable(db,asset)
    return asset


def _entry(db, user, member, row, purpose, amount, evidence_id, original=None, cash=None, account=None, reference=None):
    entry = GroupEntry(member_id=member.id, store_id=row.store_id, case_id=row.id,
        purpose=purpose, amount_cents=amount, original_id=original.id if original else None,
        cash_id=cash.id if cash else None, account_id=account.id if account else None,
        reference=reference, evidence_id=evidence_id, actor_id=user.id)
    db.add(entry)
    db.flush()
    # Positive: receivable of that party. These are internal clearing facts,
    # never additional cash, revenue or a claim of completed bank settlement.
    db.add_all([GroupSettlementEntry(store_id=row.store_id, entry_id=entry.id, side='center', amount_cents=amount),
                GroupSettlementEntry(store_id=row.store_id, entry_id=entry.id, side='store', amount_cents=-amount)])
    return entry


def _cash(db, user, row, values, direction, original=None):
    account = _local(db, Account, values['account_id'], row.store_id)
    if not account.active:
        raise HTTPException(409, '收退款账户已停用')
    if original and account.id != original.account_id:
        raise HTTPException(409, '本版集团本金退款须退回原收款门店的原账户')
    entities.require_account_entity(db,user,row,account.id,today(),original_cash_id=original.cash_id if original else None)
    reference = values['reference']
    group_used = db.scalar(select(GroupEntry.id).where(GroupEntry.store_id == row.store_id,
        GroupEntry.account_id == account.id, GroupEntry.reference == reference))
    workflow_used = db.scalar(select(PaymentLink.id).where(PaymentLink.store_id == row.store_id,
        PaymentLink.account_id == account.id, PaymentLink.reference == reference))
    cash_used = db.scalar(select(CashEntry.id).where(CashEntry.store_id == row.store_id,
        CashEntry.account == account.name, CashEntry.voucher_no == reference))
    if group_used or workflow_used or cash_used:
        raise HTTPException(409, '该账户的凭证号已记录，请核对实际流水')
    # Lock/touch the shared account as well: simultaneous workflow/group cash
    # reference claims must not both commit on the same account version.
    account.updated_at = utcnow()
    customer = _local(db, Customer, row.customer_id, row.store_id)
    cash = CashEntry(store_id=row.store_id, doc_no='GM-'+uuid.uuid4().hex[:24].upper(),
        business_date=today(), approval_state='approved', created_by=user.id, direction=direction,
        category='group_member_topup' if direction == 'in' else 'group_member_refund',
        amount_cents=values['amount_cents'], account=account.name, counterparty=customer.name,
        payment_method='cash' if account.account_type == 'cash' else 'bank', voucher_no=reference,
        note='集团会员本金；来源业务 '+row.number)
    db.add(cash)
    db.flush()
    entities.record_cash_entity(db,user,row,cash,account.id,original_cash_id=original.cash_id if original else None)
    return cash, account


def _refund_original(db, member, original_id, store_id):
    original = db.scalar(select(GroupEntry).where(GroupEntry.id == original_id,
        GroupEntry.member_id == member.id, GroupEntry.store_id == store_id, GroupEntry.purpose == 'topup'))
    if not original:
        raise HTTPException(404, '当前门店的原集团充值记录不存在')
    from .recharge_bundle_service import guard_principal_refund
    guard_principal_refund(db, original.id)
    from .business_finance_stored import effective_group_topup
    return effective_group_topup(db,original)


def _refund_remaining(db, original):
    returned = db.scalar(select(func.coalesce(func.sum(-GroupEntry.amount_cents), 0)).where(
        GroupEntry.original_id == original.id, GroupEntry.purpose == 'refund')) or 0
    pending = db.scalar(select(func.coalesce(func.sum(GroupRefundRequest.amount_cents), 0)).where(
        GroupRefundRequest.original_id == original.id, GroupRefundRequest.status == 'approved')) or 0
    from .business_finance_stored import pending_group_reduction
    return original.amount_cents-returned-pending-pending_group_reduction(db,original.id)


def _refund_action(db, user, member, action, values, store_id):
    """Original recharge and approved request facts determine the eventual cash."""
    from .flow_engine import ensure_task, finish_task
    entry = None
    if action == 'refund_request':
        original = _refund_original(db, member, values['original_id'], store_id)
        row = _case(db, user, member, original.case_id, values['case_version'], store_id)
        _evidence(db, row, values['evidence_id'], user)
        if values['amount_cents'] > _refund_remaining(db, original):
            raise HTTPException(409, '申请金额超过原充值尚未退款且未批准占额的金额')
        request = GroupRefundRequest(store_id=store_id, member_id=member.id, original_id=original.id,
            case_id=row.id, amount_cents=values['amount_cents'], requested_by=user.id,
            evidence_id=values['evidence_id'], reason=values['reason'])
        db.add(request)
        db.flush()
        ensure_task(db, row, 'group_refund_review_'+str(request.id), '复核集团会员本金退款', 'manager')
        return row, request, entry
    request = db.scalar(select(GroupRefundRequest).where(GroupRefundRequest.id == values['refund_request_id'],
        GroupRefundRequest.member_id == member.id, GroupRefundRequest.store_id == store_id).with_for_update())
    if not request:
        raise HTTPException(404, '当前门店集团退款申请不存在')
    _version(request, values['refund_request_version'])
    if request.status not in {'requested', 'approved'}:
        raise HTTPException(409, '退款申请已结束，不能重复批准、付款或撤销')
    original = _refund_original(db, member, request.original_id, store_id)
    row = _case(db, user, member, request.case_id, values['case_version'], store_id)
    review_key, pay_key = 'group_refund_review_'+str(request.id), 'group_refund_pay_'+str(request.id)
    if action == 'refund_approve':
        if request.status != 'requested':
            raise HTTPException(409, '退款申请已经批准')
        if request.requested_by == user.id and account_role(user) != 'admin':
            raise HTTPException(403, '退款申请人与审批人必须分开；请交其他主管复核')
        if request.amount_cents > _refund_remaining(db, original) or request.amount_cents > member.balance_cents-member.reserved_cents:
            raise HTTPException(409, '退款超过原充值未退金额或集团会员可用本金，请核对其他消费和占额')
        member.reserved_cents += request.amount_cents
        request.status, request.approved_by, request.approved_at = 'approved', user.id, utcnow()
        finish_task(db, row, review_key, user)
        ensure_task(db, row, pay_key, '按原账户执行集团会员本金退款', 'finance')
    elif action in {'refund_reject', 'refund_cancel'}:
        if action == 'refund_cancel' and request.requested_by != user.id and user.role not in REFUND_REVIEW_ROLES:
            raise HTTPException(403, '仅申请人或主管可撤销退款申请')
        if request.status == 'approved':
            member.reserved_cents -= request.amount_cents
        request.status = 'rejected' if action == 'refund_reject' else 'cancelled'
        request.closed_by = user.id
        finish_task(db, row, review_key, user, 'done' if action == 'refund_reject' else 'cancelled')
        finish_task(db, row, pay_key, user, 'cancelled')
    elif action == 'refund':
        if request.status != 'approved':
            raise HTTPException(409, '退款必须先由主管批准并占额，再由财务执行')
        task = db.scalar(select(Task).where(Task.case_id == row.id, Task.key == pay_key, Task.status == 'open'))
        if not task or (task.assignee_id != user.id and account_role(user) != 'admin'):
            raise HTTPException(403, '退款付款任务须由当前接手财务办理')
        _evidence(db, row, values['evidence_id'], user)
        # The approved reservation is included in the member hold. Exclude only
        # this request from the checks, preserving all other stores' holds.
        if _refund_remaining(db, original) < 0:
            raise HTTPException(409, '原充值退款金额与其他批准占额不一致，请核对')
        if request.amount_cents > member.reserved_cents or request.amount_cents > member.balance_cents:
            raise HTTPException(409, '退款占额或本金不一致，请联系管理员核对')
        cash_values = {**values, 'amount_cents': request.amount_cents}
        cash, account = _cash(db, user, row, cash_values, 'out', original)
        member.reserved_cents -= request.amount_cents
        member.balance_cents -= request.amount_cents
        entry = _entry(db, user, member, row, 'refund', -request.amount_cents, values['evidence_id'],
                       original, cash, account, values['reference'])
        request.status, request.closed_by, request.executed_entry_id = 'executed', user.id, entry.id
        finish_task(db, row, pay_key, user)
    else:
        raise HTTPException(404, '集团退款动作不存在')
    return row, request, entry


def member_command(db, user, member_id, request_id, version, action, values):
    def operation(store_id):
        member = _member(db, member_id, store_id, version)
        result = {}
        entry = None
        reservation = None
        refund_request = None
        if action in {'topup', 'reserve'}:
            row = _case(db, user, member, values['case_id'], values['case_version'], store_id, service=action == 'reserve')
            _evidence(db, row, values['evidence_id'], user)
            amount = values['amount_cents']
            if action == 'topup':
                from .flow_specs import TERMINAL
                if row.kind not in {'lead', 'order', 'repair', 'membership'} or row.state in TERMINAL:
                    raise HTTPException(409, '集团充值须关联本客户尚未结束的接待、销售或维修单；不复用本地会员充值单')
                from .membership_service import validate_host
                validate_host(db,user,row,member,action,values)
                cash, account = _cash(db, user, row, values, 'in')
                member.balance_cents += amount
                entry = _entry(db, user, member, row, 'topup', amount, values['evidence_id'],
                               cash=cash, account=account, reference=values['reference'])
            else:
                from .flow_engine import collectable_amount
                from .repair_service import is_detailed, customer_due
                due = customer_due(db,row) if is_detailed(row) else collectable_amount(db,row)
                if amount > member.balance_cents-member.reserved_cents or amount > due:
                    raise HTTPException(409, '金额超过集团会员可用本金或本单尚未占额的未结金额')
                member.reserved_cents += amount
                reservation = GroupReservation(store_id=store_id, member_id=member.id, case_id=row.id,
                    amount_cents=amount, evidence_id=values['evidence_id'], actor_id=user.id)
                db.add(reservation)
        elif action in {'capture', 'release'}:
            reservation = db.scalar(select(GroupReservation).where(GroupReservation.id == values['reservation_id'],
                GroupReservation.store_id == store_id, GroupReservation.member_id == member.id).with_for_update())
            if not reservation:
                raise HTTPException(404, '当前门店占额不存在')
            _version(reservation, values['reservation_version'])
            if reservation.status != 'reserved':
                raise HTTPException(409, '占额已核销或已释放')
            row = _case(db, user, member, reservation.case_id, values['case_version'], store_id, service=action == 'capture')
            member.reserved_cents -= reservation.amount_cents
            if action == 'release':
                reservation.status = 'released'
            else:
                from .flow_engine import paid_amount, finish_task, complete_case
                from .repair_service import is_detailed, customer_due, sync_after_member
                _evidence(db, row, values['evidence_id'], user)
                due=customer_due(db,row,include_reservations=False) if is_detailed(row) else row.amount_cents-paid_amount(db,row)
                if reservation.amount_cents > due:
                    raise HTTPException(409, '本单未结金额已变化，请先释放占额并核对')
                member.balance_cents -= reservation.amount_cents
                reservation.status = 'captured'
                entry = _entry(db, user, member, row, 'capture', -reservation.amount_cents, values['evidence_id'])
                db.add(GroupPaymentLink(store_id=store_id, case_id=row.id, entry_id=entry.id,
                                       reservation_id=reservation.id, amount_cents=reservation.amount_cents))
                db.flush()
                if is_detailed(row):sync_after_member(db,user,row)
                elif paid_amount(db, row) >= row.amount_cents:
                    finish_task(db, row, 'receive', user)
                    if row.state == 'credit_open':
                        complete_case(db, user, row)
        elif action in {'refund_request', 'refund_approve', 'refund_reject', 'refund_cancel', 'refund'}:
            row, refund_request, entry = _refund_action(db, user, member, action, values, store_id)
        elif action == 'reverse':
            original = db.scalar(select(GroupEntry).where(GroupEntry.id == values['original_id'],
                GroupEntry.member_id == member.id, GroupEntry.store_id == store_id))
            if not original or original.purpose != 'capture':
                raise HTTPException(404, '当前门店的原充值或核销记录不存在')
            row = _case(db, user, member, original.case_id, values['case_version'], store_id)
            _evidence(db, row, values['evidence_id'], user)
            amount = values['amount_cents']
            corrected = db.scalar(select(func.coalesce(func.sum(func.abs(GroupEntry.amount_cents)), 0))
                                  .where(GroupEntry.original_id == original.id)) or 0
            if amount > abs(original.amount_cents)-corrected:
                raise HTTPException(409, '金额超过原记录尚未退回或冲正的金额')
            if row.kind != 'repair' or row.state != 'settling' or row.data.get('released_date'):
                raise HTTPException(409, '仅客户接车前的待结算维修单可冲正核销；接车后退款需独立退修流程')
            from .aftercare_service import guard_source_action
            guard_source_action(db,user,row,'group_reverse')
            source = db.scalar(select(GroupPaymentLink).where(GroupPaymentLink.entry_id == original.id,
                                                               GroupPaymentLink.store_id == store_id))
            if not source:
                raise HTTPException(409, '原核销结算关联缺失，请联系管理员核对')
            member.balance_cents += amount
            entry = _entry(db, user, member, row, 'reverse', amount, values['evidence_id'], original)
            db.add(GroupPaymentLink(store_id=store_id, case_id=row.id, entry_id=entry.id,
                                   reservation_id=source.reservation_id, amount_cents=-amount))
            from .flow_engine import ensure_task
            from .repair_service import is_detailed, sync_after_member
            db.flush()
            if is_detailed(row):sync_after_member(db,user,row)
            else:ensure_task(db, row, 'receive', '登记维修款到账', 'finance', reopen=True)
        else:
            raise HTTPException(404, '集团会员动作不存在')
        from .membership_service import complete_host
        complete_host(db,user,row,member,action,values)
        from .invoice_service import sync_source
        sync_source(db,user,row)
        db.flush()
        if entry:
            result['entry_id'] = entry.id
        if reservation:
            result['reservation'] = {'id': reservation.id, 'version': reservation.version,
                'status': reservation.status, 'amount_cents': reservation.amount_cents, 'case_id': reservation.case_id}
        if refund_request:
            result['refund_request'] = _refund_info(refund_request)
        detail = {'case_id': row.id, **result}
        if values.get('reason'):
            detail['reason'] = values['reason']
        db.add(GroupEvent(store_id=store_id, member_id=member.id, actor_id=user.id, action=action, detail=detail))
        from .flow_engine import log_event
        log_event(db, user, row, 'group_'+action, '集团会员'+{
            'topup':'充值确认', 'reserve':'本金占额', 'capture':'本金核销', 'release':'释放占额',
            'refund':'本金退款', 'reverse':'核销冲正', 'refund_request':'退款申请', 'refund_approve':'退款批准占额',
            'refund_reject':'退款退回', 'refund_cancel':'退款撤销'}[action], row.state, detail)
        db.flush()
        return {'member': _wallet(member), 'case_id': row.id, 'case_version': row.version, **result}
    roles = (REFUND_REQUEST_ROLES if action == 'refund_request' else REFUND_REVIEW_ROLES
             if action in {'refund_approve', 'refund_reject'} else REFUND_REQUEST_ROLES | REFUND_REVIEW_ROLES
             if action == 'refund_cancel' else FINANCE_ROLES)
    return _execute(db, user, request_id, 'member_'+action,
                    {'member_id': member_id, 'version': version, 'values': values}, operation, roles)


def reconciliation(db, user):
    with authority(db, user, {'admin', 'manager', 'finance', 'auditor'}) as store_id:
        # Store clearing is not customer revenue and not an additional cash source.
        if db.scalar(select(func.count()).select_from(GroupEntry).where(GroupEntry.store_id == store_id)) > 25000:
            raise HTTPException(422, '对账记录超过本版处理上限，请先升级分页对账；本次未返回截断统计')
        rows = list(db.execute(select(GroupEntry.purpose, func.sum(GroupEntry.amount_cents))
            .where(GroupEntry.store_id == store_id).group_by(GroupEntry.purpose)))
        sides = dict(db.execute(select(GroupSettlementEntry.side, func.sum(GroupSettlementEntry.amount_cents))
            .where(GroupSettlementEntry.store_id == store_id).group_by(GroupSettlementEntry.side)).all())
        entries = list(db.scalars(select(GroupEntry).where(GroupEntry.store_id == store_id).order_by(GroupEntry.id)))
        return {'store_id': store_id, 'purpose_totals_cents': dict(rows),
            'center_receivable_cents': sides.get('center', 0), 'store_receivable_cents': sides.get('store', 0),
            'clearing_sum_cents': sum(sides.values()),
            'rows': [{'id': e.id, 'purpose': e.purpose, 'amount_cents': e.amount_cents,
                'case_id': e.case_id, 'cash_id': e.cash_id, 'original_id': e.original_id} for e in entries]}

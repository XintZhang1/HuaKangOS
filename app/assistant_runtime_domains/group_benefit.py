"""Original member benefit detail, read through current employee/store authority.

The direct member route avoids choosing a linked customer. Wallet, entry and
reservation facts prove existence only, never sufficient credit or settlement.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id, _response_data

BENEFIT_OBJECT_TYPE = 'group_member'
BENEFIT_MEMBERS = 'GET /api/group/benefits/members'
BENEFIT_MEMBER_READ = 'GET /api/group/benefits/members/{member_id}'
BENEFIT_RULES = 'GET /api/group/benefits/rules'
BENEFIT_ACTION = 'POST /api/group/benefits/members/{member_id}/actions/{action}'
BENEFIT_KINDS = ('bonus', 'points', 'coupon', 'package')
BENEFIT_RESULT_OPERATIONS = frozenset({BENEFIT_MEMBERS, BENEFIT_MEMBER_READ, BENEFIT_RULES, BENEFIT_ACTION})
BENEFIT_RECEIPT_OPERATIONS = frozenset({BENEFIT_ACTION})
BENEFIT_FACTS = ('group_benefit.wallet_recorded', 'group_benefit.entry_recorded',
                 'group_benefit.reservation_recorded')
BENEFIT_ACTIONS = ('grant', 'purchase', 'reserve', 'adjust', 'exchange', 'capture', 'release',
                   'reverse', 'refund_request', 'refund_approve', 'refund_reject',
                   'refund_cancel', 'refund')
ENTRY_PURPOSES = ('purchase', 'grant', 'exchange_in', 'reverse', 'capture', 'refund',
                  'adjust', 'exchange_out', 'correction')
HISTORY_LIMIT = 100


def _now():
    return datetime.now(timezone.utc)


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


def _invalid():
    raise HTTPException(502, '原业务返回的权益记录不完整或关联不一致，请重新核对') from None


class GroupBenefitAdapter(FlowCaseAdapter):
    """Exact benefit fact provider; group_principal owns the shared object snapshot."""

    name = 'group_benefit'
    object_types = (BENEFIT_OBJECT_TYPE,)

    def _member_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != BENEFIT_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原集团会员')
        return values

    async def _member_detail(self, principal, ref):
        values = self._member_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(BENEFIT_MEMBER_READ,
                path_args={'member_id':values['id']}, query={}, body=None)
        except HTTPException as exc:
            if exc.status_code in {401,403,404}:
                raise HTTPException(404, '原业务不存在或当前账号不可查看') from None
            raise
        data = _response_data(response)
        member = data.get('member')
        if (type(member) is not dict or member.get('id') != values['id']
                or not _positive_id(member.get('id'))
                or member.get('version') is not None and not _positive_id(member['version'])
                or any(type(data.get(key)) is not list
                       for key in ('wallets','entries','reservations','refunds'))):
            _invalid()
        wallets = data['wallets']
        wallet_ids = set()
        for wallet in wallets:
            if (type(wallet) is not dict or not _positive_id(wallet.get('id'))
                    or wallet['id'] in wallet_ids or not _positive_id(wallet.get('member_id'))
                    or wallet['member_id'] != values['id']
                    or type(wallet.get('rule')) is not dict
                    or wallet['rule'].get('kind') not in BENEFIT_KINDS):
                _invalid()
            wallet_ids.add(wallet['id'])
        for key in ('entries','reservations'):
            seen = set()
            for item in data[key]:
                if (type(item) is not dict or not _positive_id(item.get('id'))
                        or item['id'] in seen or not _positive_id(item.get('wallet_id'))
                        or item['wallet_id'] not in wallet_ids
                        or not _positive_id(item.get('case_id'))):
                    _invalid()
                seen.add(item['id'])
        return data

    @staticmethod
    def _evidence(data):
        member = data['member']
        observed_at = _now()
        ref = BusinessObjectRef(type=BENEFIT_OBJECT_TYPE, id=member['id'])
        source = EvidenceRef(source_type='object', source_id=ref,
            native_version=member.get('version'), observed_at=observed_at)
        return ref, source

    async def read_snapshot(self, principal, ref):
        data = await self._member_detail(principal, ref)
        member_ref, source = self._evidence(data)
        member = data['member']
        return BusinessObjectSnapshot(ref=member_ref, native_version=member.get('version'),
            display_number=member.get('number') if type(member.get('number')) is str else None,
            state=None, tasks=[],
            available_actions=[AvailableAction(action_key=key,availability='unknown')
                for key in BENEFIT_ACTIONS], evidence_refs=[source],
            manual_route='group', observed_at=source.observed_at)

    async def fact_snapshot(self, principal, ref, fact_key):
        self._member_ref(ref)
        if fact_key not in BENEFIT_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='集团权益未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._member_detail(principal, ref)
        _, source = self._evidence(data)
        key, label = {'group_benefit.wallet_recorded':('wallets','权益批次'),
            'group_benefit.entry_recorded':('entries','权益流水'),
            'group_benefit.reservation_recorded':('reservations','权益占用记录')}[fact_key]
        rows = data[key]
        if key == 'entries' and any(item.get('purpose') not in ENTRY_PURPOSES for item in rows):
            return _unknown(fact_key, '原权益流水用途不完整，请到原页面核对')
        if key == 'reservations' and any(item.get('status') not in ('reserved','captured','released')
                                        for item in rows):
            return _unknown(fact_key, '原权益占用状态不完整，请到原页面核对')
        reason = ('已存在原%s；仅证明至少一笔，不代表余额足够或业务已结清' % label
                  if rows else '该会员当前没有原%s' % label)
        if key != 'wallets' and len(rows) >= HISTORY_LIMIT:
            reason += '；原详情最多返回%d条，历史可能截断，不用于总量核对' % HISTORY_LIMIT
        return FactSnapshot(fact_key=fact_key, satisfied=bool(rows),
            evidence_refs=[source], reason=reason)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in BENEFIT_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        if operation_id in {BENEFIT_MEMBERS, BENEFIT_MEMBER_READ, BENEFIT_RULES}:
            return []
        member_id = data.get('member_id')
        if not _positive_id(member_id):
            member = data.get('member') if type(data.get('member')) is dict else {}
            member_id = member.get('id')
        if not _positive_id(member_id):
            return []
        return [BusinessObjectRef(type=BENEFIT_OBJECT_TYPE, id=member_id)]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in BENEFIT_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(502, '原业务返回的权益回执不完整，请稍后重新核对') from None


__all__ = ['BENEFIT_ACTION', 'BENEFIT_FACTS', 'BENEFIT_KINDS', 'BENEFIT_MEMBER_READ', 'BENEFIT_MEMBERS',
           'BENEFIT_OBJECT_TYPE', 'BENEFIT_RECEIPT_OPERATIONS', 'BENEFIT_RESULT_OPERATIONS',
           'BENEFIT_RULES', 'GroupBenefitAdapter']

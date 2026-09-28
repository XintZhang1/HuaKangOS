"""维修领退料与返修（rework_grant）适配器：原责任授权（ReworkSourceGrant）的只读投影。

- 只读 `GET /api/rework-extensions/grants/{key}`（reviewed catalog 内），不调用业务 command。
- 批准、撤销、承接返修是三件不同的事实：**批准历史不证明当前未撤销或尚有可用范围**，
  承接关系（ReworkExtension）无法从该详情证明时返回未知，不猜。
- 责任授权额度（原 `original_liability_limit_cents`）与客户自费部分严格分开：本适配器只投影前者。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

GRANT_OBJECT_TYPE = 'rework_source_grant'
GRANT_READ = 'GET /api/rework-extensions/grants/{key}'
GRANT_CREATE = 'POST /api/rework-extensions/grants'
GRANT_ACTION = 'POST /api/rework-extensions/grants/{key}/actions/{action}'
GRANT_REQUEST = 'POST /api/rework-extensions/requests'
GRANT_QUOTE = 'POST /api/rework-extensions/orders/{key}/quote'
GRANT_ACTIONS = ('approve', 'reject', 'cancel', 'revoke')
GRANT_RESULT_OPERATIONS = frozenset({GRANT_READ, GRANT_CREATE, GRANT_ACTION, GRANT_REQUEST, GRANT_QUOTE})
GRANT_RECEIPT_OPERATIONS = frozenset({GRANT_CREATE, GRANT_ACTION, GRANT_REQUEST, GRANT_QUOTE})
GRANT_FACTS = ('rework.approval_recorded', 'rework.revocation_recorded', 'rework.extension_recorded')
# 原授权状态：只有经 approve 决定后才会离开 pending/rejected。
APPROVED_STATES = ('approved', 'consumed', 'revoked')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的责任授权不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class ReworkGrantAdapter(FlowCaseAdapter):
    """`object_type=rework_source_grant` 的原责任授权。"""

    name = 'rework_grant'
    object_types = (GRANT_OBJECT_TYPE,)

    def _grant_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != GRANT_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原责任授权')
        return values

    async def _grant_detail(self, principal, ref):
        values = self._grant_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(GRANT_READ, path_args={'key': values['id']},
                                                 query={}, body=None)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404}:
                raise HTTPException(404, '原业务不存在或当前账号不可查看') from None
            raise
        if type(response) is not dict or type(response.get('status')) is not int:
            _invalid()
        status = response['status']
        if status in {401, 403, 404}:
            raise HTTPException(404, '原业务不存在或当前账号不可查看')
        if 400 <= status < 500:
            raise HTTPException(status, '原业务暂不能读取此责任授权，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if (not _positive_id(data.get('id')) or data.get('id') != values['id']
                or type(data.get('status')) is not str or not data['status'].strip()):
            _invalid()
        # 跨门店授权按原详情透传：本适配器不补默认门店，也不改写 store_id。
        for key in ('from_store_id', 'to_store_id'):
            if data.get(key) is not None and not _positive_id(data[key]):
                _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._grant_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        grant_ref = BusinessObjectRef(type=GRANT_OBJECT_TYPE, id=data['id'])
        # 只有原详情确实提供的额度才进入快照理由，客户自费部分一律不推断。
        liability = data.get('original_liability_limit_cents')
        reason = None
        if _positive_id(liability):
            reason = '原责任授权额度（分）：' + str(liability)
        try:
            return BusinessObjectSnapshot(
                ref=grant_ref, native_version=version,
                display_number=data.get('source_number') if type(data.get('source_number')) is str else None,
                state=data['status'],
                tasks=[],
                # 原详情不返回动作可用性：不猜。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in GRANT_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=grant_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in GRANT_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='维修领退料与返修未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._grant_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        grant_ref = BusinessObjectRef(type=GRANT_OBJECT_TYPE, id=data['id'])
        from_grant = EvidenceRef(source_type='object', source_id=grant_ref,
                                 native_version=version, observed_at=observed_at)
        status = data['status']

        if fact_key == 'rework.approval_recorded':
            # 只有经过 approve 决定才会离开 pending/rejected；批准不等于当前仍有效。
            if status in APPROVED_STATES:
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_grant],
                                    reason='批准记录存在；当前是否仍有可用范围以原授权状态为准')
            if status == 'rejected':
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_grant],
                                    reason='原责任授权已被拒绝，请到原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_grant],
                                reason='原责任授权尚未有批准决定，请到原页面核对审批进度')

        if fact_key == 'rework.revocation_recorded':
            if status == 'revoked':
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_grant])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_grant],
                                reason='原责任授权当前不是已撤销状态，请在原页面核对')

        # rework.extension_recorded：必须有原 ReworkExtension 确证本授权与承接维修单的关系；
        # 该详情不提供承接关系，故一律未知，绝不用批准历史代替。
        return _unknown(fact_key, '需要原承接维修单关系（ReworkExtension），该详情未提供，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in GRANT_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or type(data.get('status')) is not str or not data['status'].strip()):
            return []
        return [BusinessObjectRef(type=GRANT_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in GRANT_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族 `ReworkGrantReceipt`；派生接待命令仍走 IntakeReceipt（不在本适配器范围内）。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['APPROVED_STATES', 'GRANT_ACTION', 'GRANT_ACTIONS', 'GRANT_CREATE', 'GRANT_FACTS',
           'GRANT_OBJECT_TYPE', 'GRANT_QUOTE', 'GRANT_READ', 'GRANT_RECEIPT_OPERATIONS',
           'GRANT_REQUEST', 'GRANT_RESULT_OPERATIONS', 'ReworkGrantAdapter']

"""卷宗授权（dossier_grant）适配器：原授权单的只读投影 + 当前可读性实测。

- 只读 `GET /api/dossier-grants/{grant_id}` 与 `GET /api/dossier-grants/{grant_id}/record`（均已在
  reviewed catalog 内），不调用业务 command；**key 即原 `DossierGrant.id`**。
- 批准、当前可读、撤回是三件不同的事实：**批准历史不满足当前可读**——当前可读必须由
  **本次原 /record 成功读取同一 grant 的授权摘要**证明；**403/404 无法区分"不存在"与"不可见"时返回未知**。
- 原 native version 取原授权 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

DG_OBJECT_TYPE = 'dossier_grant'
DG_READ = 'GET /api/dossier-grants/{grant_id}'
DG_RECORD = 'GET /api/dossier-grants/{grant_id}/record'
DG_CREATE = 'POST /api/dossier-grants'
DG_ACTION = 'POST /api/dossier-grants/{grant_id}/actions/{action}'
DG_ACTIONS = ('propose', 'decide', 'read_record')
DG_RESULT_OPERATIONS = frozenset({DG_READ, DG_RECORD, DG_CREATE, DG_ACTION})
DG_RECEIPT_OPERATIONS = frozenset({DG_CREATE, DG_ACTION})
DG_FACTS = ('dossier.approval_recorded', 'dossier.record_readable', 'dossier.revocation_recorded')
DECISION_APPROVE = ('approve', 'approved')
DECISION_REVOKE = ('revoke', 'revoked', 'withdraw', 'withdrawn', 'cancel', 'cancelled')
DECISION_KEYS = ('action', 'decision', 'kind')
INDISTINGUISHABLE = ('原接口对该主体返回 403/404：无法区分"授权不存在"与"当前不可见"，'
                     '按合同返回未知，不推断为未授权；批准历史也不满足当前可读')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的卷宗授权不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class DossierGrantAdapter(FlowCaseAdapter):
    """`object_type=dossier_grant` 的原卷宗授权；可读性由本次 /record 实测。"""

    name = 'dossier_grant'
    object_types = (DG_OBJECT_TYPE,)

    def _grant_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != DG_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原卷宗授权')
        return values

    def _store(self, principal):
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        return store_id

    async def _call(self, operation_id, path_args):
        try:
            response = await self._native_reader(operation_id, path_args=path_args, query={}, body=None)
        except HTTPException as exc:
            raise exc
        if type(response) is not dict or type(response.get('status')) is not int:
            _invalid()
        return response

    async def _grant_detail(self, principal, ref):
        values = self._grant_ref(ref)
        self._store(principal)
        response = await self._call(DG_READ, {'grant_id': values['id']})
        status = response['status']
        if status in {403, 404}:
            # 与 /record 同口径：不区分不存在与不可见 → 由事实层给未知；快照层按 404 处理不暴露。
            raise HTTPException(404, '原业务不存在或当前账号不可查看')
        if 400 <= status < 500:
            raise HTTPException(status, '原业务暂不能读取此卷宗授权，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or data['id'] != values['id']):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._grant_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        grant_ref = BusinessObjectRef(type=DG_OBJECT_TYPE, id=data['id'])
        state = data.get('status') or data.get('state')
        try:
            return BusinessObjectSnapshot(
                ref=grant_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=state if type(state) is str else None,
                tasks=[],
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in DG_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=grant_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    @staticmethod
    def _decisions(data):
        value = data.get('decisions')
        if isinstance(value, list):
            return [item for item in value if type(item) is dict]
        return None

    @staticmethod
    def _decision_kind(decision):
        for key in DECISION_KEYS:
            candidate = decision.get(key)
            if type(candidate) is str and candidate.strip():
                return candidate.strip().lower()
        return None

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in DG_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='卷宗授权未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        values = self._grant_ref(ref)
        store_id = self._store(principal)

        if fact_key == 'dossier.record_readable':
            # 必须由本次原 /record 成功读取**同一** grant 的授权摘要证明。
            response = await self._call(DG_RECORD, {'grant_id': values['id']})
            status = response['status']
            if status in {403, 404}:
                return _unknown(fact_key, INDISTINGUISHABLE)
            if 400 <= status < 500:
                raise HTTPException(status, '原业务暂不能读取此授权摘要，请到原页面核对')
            if not 200 <= status < 300:
                raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
            data = response.get('data')
            if type(data) is not dict or data.get('truncated'):
                _invalid()
            summary_grant = data.get('grant_id')
            if summary_grant is not None and summary_grant != values['id']:
                return _unknown(fact_key, '原授权摘要与本授权不一致，按合同返回未知')
            observed_at = _now()
            grant_ref = BusinessObjectRef(type=DG_OBJECT_TYPE, id=values['id'])
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[
                EvidenceRef(source_type='object', source_id=grant_ref, native_version=None,
                            observed_at=observed_at)],
                reason='本次已通过原 /record 成功读取本授权的摘要；'
                       '批准历史不满足当前可读，且该结论以本次读取为准')

        data = await self._grant_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        grant_ref = BusinessObjectRef(type=DG_OBJECT_TYPE, id=data['id'])
        from_grant = EvidenceRef(source_type='object', source_id=grant_ref,
                                 native_version=version, observed_at=observed_at)
        decisions = self._decisions(data)
        if decisions is None:
            return _unknown(fact_key, '原详情未提供原决定明细（DossierDecision），请在原页面核对')

        wanted = DECISION_APPROVE if fact_key == 'dossier.approval_recorded' else DECISION_REVOKE
        identified = 0
        for decision in decisions:
            kind = self._decision_kind(decision)
            if kind is None:
                continue
            identified += 1
            if kind in wanted:
                if fact_key == 'dossier.approval_recorded':
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_grant],
                                        reason='已登记原批准决定；批准历史不满足当前可读')
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_grant])
        if identified == 0:
            if isinstance(data.get('decisions'), list) and not data['decisions']:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_grant],
                                    reason='本授权还没有原' + ('批准' if fact_key == 'dossier.approval_recorded'
                                                              else '撤回/撤销') + '决定，请在原页面核对')
            return _unknown(fact_key, '原决定缺少可识别的动作类型，请在原页面核对')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_grant],
                            reason='本授权还没有原' + ('批准' if fact_key == 'dossier.approval_recorded'
                                                      else '撤回/撤销') + '决定，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in DG_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        if operation_id == DG_RECORD:
            return []
        grant_id = data.get('id') if _positive_id(data.get('id')) else data.get('grant_id')
        if not _positive_id(grant_id):
            return []
        return [BusinessObjectRef(type=DG_OBJECT_TYPE, id=grant_id)]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in DG_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族 `DossierReceipt`；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['DECISION_APPROVE', 'DECISION_KEYS', 'DECISION_REVOKE', 'DG_ACTION', 'DG_ACTIONS',
           'DG_CREATE', 'DG_FACTS', 'DG_OBJECT_TYPE', 'DG_READ', 'DG_RECEIPT_OPERATIONS',
           'DG_RECORD', 'DG_RESULT_OPERATIONS', 'INDISTINGUISHABLE', 'DossierGrantAdapter']

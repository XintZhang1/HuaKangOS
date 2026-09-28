"""调拨货物找回（transfer_goods_recovery）适配器：原找回案的只读投影。

- 只读 `GET /api/transfer-goods-recoveries/{key}`（reviewed catalog 内），不调用业务 command；
  **key 即原 `GoodsRecovery.id`**（与登记的对象类型一致）。
- 匹配、实物接收、损失恢复过账是三件不同的事实：**unlocated 不等于 recovered**，
  **找到/收到不能替代损失恢复过账或赔付退回**；未提供对应事实时一律未知。
- 原 native version 取原案 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

GR_OBJECT_TYPE = 'goods_recovery'
GR_READ = 'GET /api/transfer-goods-recoveries/{key}'
GR_CREATE = 'POST /api/transfer-goods-recoveries'
GR_ACTION = 'POST /api/transfer-goods-recoveries/{key}/actions/{action}'
GR_ORIGINS = 'GET /api/transfer-goods-recoveries/origins/{transfer_id}'
GR_ACTIONS = ('match', 'inspect', 'ship', 'receive', 'plan', 'approve', 'reject', 'dispose',
              'restore', 'finish_bad')
GR_RESULT_OPERATIONS = frozenset({GR_READ, GR_CREATE, GR_ACTION})
GR_RECEIPT_OPERATIONS = frozenset({GR_CREATE, GR_ACTION})
GR_FACTS = ('goods_recovery.match_recorded', 'goods_recovery.receipt_recorded',
            'goods_recovery.restore_posted')
FACT_KINDS = {'goods_recovery.match_recorded': ('match', 'loss_match'),
              'goods_recovery.receipt_recorded': ('receive', 'physical_receive'),
              'goods_recovery.restore_posted': ('restore', 'loss_restore')}
FACT_LABEL = {'goods_recovery.match_recorded': '原损失匹配',
              'goods_recovery.receipt_recorded': '实物接收',
              'goods_recovery.restore_posted': '损失恢复过账'}
NOT_RECOVERED = ('未找回（unlocated）不等于已找回；找到或收到实物也不能替代损失恢复过账或赔付退回')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的找回案不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class TransferGoodsRecoveryAdapter(FlowCaseAdapter):
    """`object_type=goods_recovery` 的原找回案；key 即原案 id。"""

    name = 'transfer_goods_recovery'
    object_types = (GR_OBJECT_TYPE,)

    def _recovery_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != GR_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原找回案')
        return values

    async def _detail(self, principal, ref):
        values = self._recovery_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(GR_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此找回案，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not _positive_id(data.get('transfer_id'))):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        recovery_ref = BusinessObjectRef(type=GR_OBJECT_TYPE, id=data['id'])
        state = data.get('status') or data.get('state')
        try:
            return BusinessObjectSnapshot(
                ref=recovery_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=state if type(state) is str else None,
                tasks=[],
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in GR_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=recovery_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    @staticmethod
    def _matching(data, wanted, keys):
        for container in keys:
            value = data.get(container)
            items = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
            for item in items:
                if type(item) is not dict or not _positive_id(item.get('id')):
                    continue
                kind = None
                for key in ('kind', 'fact', 'action', 'source'):
                    candidate = item.get(key)
                    if type(candidate) is str and candidate.strip():
                        kind = candidate.strip().lower()
                        break
                if kind is not None and kind in wanted:
                    return item
        return None

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in GR_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='调拨货物找回未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        recovery_ref = BusinessObjectRef(type=GR_OBJECT_TYPE, id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=recovery_ref,
                                native_version=version, observed_at=observed_at)
        state = data.get('status') or data.get('state')
        wanted = FACT_KINDS[fact_key]
        containers = (('postings', 'posting') if fact_key == 'goods_recovery.restore_posted'
                      else ('facts', 'fact'))

        found = self._matching(data, wanted, containers)
        if found is not None:
            note = ('；' + NOT_RECOVERED) if fact_key != 'goods_recovery.restore_posted' else \
                '；过账不改变原实物状态'
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                reason='已登记' + FACT_LABEL[fact_key] + '记录' + note)
        provided = any(isinstance(data.get(container), (list, dict)) for container in containers)
        if not provided:
            return _unknown(fact_key, '原详情未提供' + FACT_LABEL[fact_key] + '明细，'
                                      '无法确证，请在原页面核对；' + NOT_RECOVERED)
        if state == 'unlocated':
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='原案状态为未找回（unlocated），' + NOT_RECOVERED)
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                            reason='本单还没有原' + FACT_LABEL[fact_key] + '记录，请在原页面核对；'
                                   + NOT_RECOVERED)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in GR_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id')):
            return []
        return [BusinessObjectRef(type=GR_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in GR_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族 `GoodsReceipt`；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['FACT_KINDS', 'FACT_LABEL', 'GR_ACTION', 'GR_ACTIONS', 'GR_CREATE', 'GR_FACTS',
           'GR_OBJECT_TYPE', 'GR_ORIGINS', 'GR_READ', 'GR_RECEIPT_OPERATIONS',
           'GR_RESULT_OPERATIONS', 'NOT_RECOVERED', 'TransferGoodsRecoveryAdapter']

"""维修套餐（repair_package）适配器：原套餐购买面的受控投影。

**读取维度不匹配（如实登记，不猜内部 ID）**：本项登记的对象类型是 `package_purchase`
（原 `PackagePurchase.id`），但本领域已评审的读取只有
`GET /api/repair-packages/members/{key}/purchases`（**按会员**维度），
不存在按购买 id 的详情读取；仅凭购买 id 无法建立该读取路径，
而助手不得自行拼接会员 ID，也不得改用未评审的查询。

因此本适配器：
- `read_snapshot` 明确报告"无法从该对象建立已评审读取"（503 + 原页面入口），**不发起任何读取**；
- 三条购买事实（issued/capture_recorded/refund_paid）一律未知并说明原因；
- `extract_result` 仍按原写接口响应绑定原 `PackagePurchase` 引用；
- `read_receipt` 由已评审 resolver 绑定，保持冻结 `request_id`。
评审补一条"purchase_id → member_id"的已评审只读映射（或提供按购买 id 的详情读取）后，
本项即可按原 `PackageLot`/`PackageEntry`/`PackageRefund` 实现真实快照与事实。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

PACKAGE_OBJECT_TYPE = 'package_purchase'
PACKAGE_MEMBER_PURCHASES = 'GET /api/repair-packages/members/{key}/purchases'
PACKAGE_RULES = 'GET /api/repair-packages/rules'
PACKAGE_CREATE = 'POST /api/repair-packages/purchases'
PACKAGE_ORDER_CAPTURE = 'POST /api/repair-packages/orders/{key}/capture'
PACKAGE_ORDER_QUOTE = 'POST /api/repair-packages/orders/{key}/quote'
PACKAGE_ACTION = 'POST /api/repair-packages/purchases/{key}/actions/{action}'
PACKAGE_REFUND_ACTION = 'POST /api/repair-packages/refunds/{key}/actions/{action}'
PACKAGE_ACTIONS = ('authorize', 'issue', 'cancel', 'refund_request')
PACKAGE_RESULT_OPERATIONS = frozenset({PACKAGE_CREATE, PACKAGE_ORDER_CAPTURE, PACKAGE_ORDER_QUOTE,
                                       PACKAGE_ACTION, PACKAGE_REFUND_ACTION})
PACKAGE_RECEIPT_OPERATIONS = frozenset({PACKAGE_CREATE, PACKAGE_ORDER_CAPTURE, PACKAGE_ORDER_QUOTE,
                                        PACKAGE_ACTION, PACKAGE_REFUND_ACTION})
PACKAGE_FACTS = ('repair_package.issued', 'repair_package.capture_recorded',
                 'repair_package.refund_paid')
KEY_MISMATCH = ('本领域已评审的读取按会员维度（members/{key}/purchases），'
                '没有按购买 id 的详情读取；不能用 package_purchase id 或自行拼接的会员 ID 代替，'
                '请到原页面核对该购买，或由评审补一条 purchase→member 的只读映射。')


def _now():
    return datetime.now(timezone.utc)


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class RepairPackageAdapter(FlowCaseAdapter):
    """`object_type=package_purchase`；已评审读取按会员维度，故不建立读取路径。"""

    name = 'repair_package'
    object_types = (PACKAGE_OBJECT_TYPE,)

    def _purchase_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != PACKAGE_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原套餐购买记录')
        return values

    async def read_snapshot(self, principal, ref):
        self._purchase_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        # 不发起任何读取：已评审读取需要会员 ID，本项只有购买 ID。
        raise HTTPException(503, KEY_MISMATCH)

    async def fact_snapshot(self, principal, ref, fact_key):
        self._purchase_ref(ref)
        if fact_key not in PACKAGE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='维修套餐未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        # authorize/quote 不满足发行/核销/退款键；在映射补齐前一律未知，不猜。
        return _unknown(fact_key, KEY_MISMATCH)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in PACKAGE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        purchase_id = data.get('purchase_id')
        if not _positive_id(purchase_id):
            purchase = data.get('purchase') if type(data.get('purchase')) is dict else {}
            purchase_id = purchase.get('id') if _positive_id(purchase.get('id')) else data.get('id')
        if not _positive_id(purchase_id):
            return []
        return [BusinessObjectRef(type=PACKAGE_OBJECT_TYPE, id=purchase_id)]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in PACKAGE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(502, '原业务返回的套餐回执不完整，请稍后重新核对') from None


__all__ = ['KEY_MISMATCH', 'PACKAGE_ACTION', 'PACKAGE_ACTIONS', 'PACKAGE_CREATE', 'PACKAGE_FACTS',
           'PACKAGE_MEMBER_PURCHASES', 'PACKAGE_OBJECT_TYPE', 'PACKAGE_ORDER_CAPTURE',
           'PACKAGE_ORDER_QUOTE', 'PACKAGE_RECEIPT_OPERATIONS', 'PACKAGE_REFUND_ACTION',
           'PACKAGE_RESULT_OPERATIONS', 'PACKAGE_RULES', 'RepairPackageAdapter']

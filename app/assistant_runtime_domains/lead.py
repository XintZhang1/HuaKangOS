"""售前接待（lead）适配器：把原 Case 的 lead 能力接到统一快照/结果/事实/回执合同。

- 只读 `GET /api/flow/cases/{case_id}`（M0 reviewed catalog 内），不调用任何业务 command。
- 只登记原 flow_specs 的 lead 事实键；没有原详情的直接证据一律 `satisfied=None`，
  不把状态文字、待办结束或动作可用性当成业务事实。
- 原 native version 取原详情的 `flow_version`/`version`；缺失即 `None`，不造版本。
- 本适配器只声明可准备的原 operation，不执行、不生成卡、不改原状态机。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import BusinessObjectRef, EvidenceRef, FactSnapshot
from .flow_case import (
    FLOW_ACTION, FLOW_CREATE, FLOW_READ, FlowCaseAdapter, _case_ref, _positive_id,
    _record, _response_data,
)

LEAD_KIND = 'lead'
LEAD_ACTIONS = ('assign', 'intent', 'remind', 'follow', 'reserve', 'close', 'reopen')
# 本项登记的三条事实，每条都必须有原详情的直接证据。
LEAD_FACTS = ('lead.customer_linked', 'lead.owner_assigned', 'lead.reserve_recorded')


def _now():
    return datetime.now(timezone.utc)


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class LeadAdapter(FlowCaseAdapter):
    """`kind == 'lead'` 的原 Case；其它 kind 明确拒绝，不越界读取。"""

    name = 'lead'
    object_types = ('case',)

    async def read_snapshot(self, principal, ref):
        # 详情与列表读法不同：对象快照只由原详情建立，且必须是 lead；
        # 单次受控 GET，不额外探测、不读列表。
        record, _ = await self._lead_detail(principal, ref)
        return self.snapshot_from_record(ref, record)

    async def _lead_detail(self, principal, ref):
        """一次受控原身份 GET，返回（已校验记录, 原详情原始数据）。"""
        ref = _case_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        response = await self._native_reader(FLOW_READ, path_args={'case_id': ref.id}, query={}, body=None)
        data = _response_data(response)
        record = _record(data, expected_id=ref.id, expected_store=store_id, observed_at=_now())
        if record['kind'] != LEAD_KIND:
            raise HTTPException(422, '这不是原售前接待记录，请到对应业务页面办理')
        return record, data

    async def fact_snapshot(self, principal, ref, fact_key):
        _case_ref(ref)
        if fact_key not in LEAD_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='售前接待未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        record, data = await self._lead_detail(principal, ref)
        observed_at = _now()
        version = record['version'] if _positive_id(record['version']) else record['flow_version']
        case_ref = BusinessObjectRef(type='case', id=record['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)

        if fact_key == 'lead.customer_linked':
            # 只有原详情确实带本店可读客户引用才算满足；同名客户不默选。
            customer = data.get('customer')
            customer_id = data.get('customer_id')
            if not _positive_id(customer_id) and type(customer) is dict:
                customer_id = customer.get('id')
            if not _positive_id(customer_id):
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[],
                                    reason='原详情没有可读客户引用，请先在原页面关联客户后再继续')
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[
                EvidenceRef(source_type='object', source_id=BusinessObjectRef(type='customer', id=customer_id),
                            native_version=None, observed_at=observed_at),
                from_case,
            ])

        if fact_key == 'lead.owner_assigned':
            # new_case initializes owner_id to the creator *before* reception
            # assignment. Neither that ID nor an arbitrary task assignee proves
            # that the original assign command was performed.
            assignments = [task for task in record['tasks']
                if type(task) is dict and task.get('key') == 'assign'
                and task.get('case_id') == record['id'] and _positive_id(task.get('id'))]
            if len(assignments) != 1:
                return _unknown(fact_key, '未取得明确的原分派记录，请在原单核对')
            assignment = assignments[0]
            if assignment.get('status') == 'open':
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[],
                                    reason='接待尚未分派')
            if (assignment.get('status') != 'done' or not _positive_id(data.get('owner_id'))
                    or record.get('state') == 'unassigned'):
                return _unknown(fact_key, '分派结果与负责人尚未核实，请在原单核对')
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[
                EvidenceRef(source_type='task', source_id=assignment['id'],
                            native_version=assignment.get('version') if _positive_id(assignment.get('version')) else None,
                            observed_at=observed_at),
                from_case,
            ])

        # The original reserve command creates an order whose parent is this
        # lead. case_detail exposes authorized children, not a generic links
        # collection. A loose case ID, state caption or ended task is no proof.
        children = data.get('children')
        if type(children) is not list:
            return _unknown(fact_key, '未取得原关联订单，请在原单核对')
        orders = [child for child in children if type(child) is dict
            and child.get('kind') == 'order' and _positive_id(child.get('id'))
            and type(child.get('parent_id')) is int and child['parent_id'] == record['id']
            and type(child.get('store_id')) is int and child['store_id'] == record['store_id']]
        if not orders:
            # An absent readable child does not prove that another role has no
            # order; leave the missing business fact explicitly unknown.
            return _unknown(fact_key, '未找到可核对的关联车辆订单')
        return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[
            *[EvidenceRef(source_type='object', source_id=BusinessObjectRef(type='case', id=child['id']),
                          native_version=child.get('version') if _positive_id(child.get('version')) else None,
                          observed_at=observed_at) for child in sorted(orders, key=lambda child: child['id'])],
            from_case,
        ])


__all__ = ['FLOW_ACTION', 'FLOW_CREATE', 'FLOW_READ', 'LEAD_ACTIONS',
           'LEAD_FACTS', 'LEAD_KIND', 'LeadAdapter']

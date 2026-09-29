"""助手等待原因的固定中文文案（唯一来源）。

侧栏事项、当前事项面板和计划步骤都显示同一件事的等待原因，因此标签只在这里维护，
不在前端另造一套，也不把 ``employee_continue`` 这类状态机内部标识直接给员工看。

找不到文案时返回 ``None``，由各自的回退文案负责；本模块不猜业务含义。
"""
from __future__ import annotations

# key 是计划步骤与事项投影实际使用的 wait_reason 标识。
WAIT_REASONS = {
    # 等员工本人继续
    'employee_continue': '等你继续办理',
    'employee_input': '等你补充资料',
    'employee_paused': '已暂停跟进',
    # 等原业务事实
    'external_fact': '等原业务结果',
    'native_prerequisite': '等同一原单前序步骤完成',
    'dependency': '等前序步骤完成',
    'not_prepared': '尚未准备这一步',
    'preparation_pending': '正在准备这一步',
    'completion_conditions_missing': '尚未登记这一步的完成条件',
    'completion_evidence_missing': '缺少可核对的完成凭据',
    'explicit_time_missing': '尚未明确约定时间',
    'time_source_missing': '缺少可核对的时间来源',
    # 结果待核对
    'result_unknown': '结果待核对，请不要重复提交',
    'confirmation_in_progress': '确认结果待核对',
    'recheck_required': '需要重新核对这一步',
    'expired': '原草稿已过期，需要重新准备',
    'row_failed': '原业务办理未完成',
    'row_cancelled': '这一步已取消',
    # 不可读
    'source_inaccessible': '当前权限看不到原业务，请核对岗位或门店',
}
_COMPLETION_RECHECK = 'completion_recheck_'
COMPLETION_RECHECK_WAIT = '原完成事实需要重新核对'


def waiting_label(reason):
    """Return the fixed Chinese label for a wait reason, or None when unknown."""
    if type(reason) is not str or not reason:
        return None
    if reason in WAIT_REASONS:
        return WAIT_REASONS[reason]
    if reason.startswith(_COMPLETION_RECHECK):
        return COMPLETION_RECHECK_WAIT
    return None


__all__ = ['COMPLETION_RECHECK_WAIT', 'WAIT_REASONS', 'waiting_label']
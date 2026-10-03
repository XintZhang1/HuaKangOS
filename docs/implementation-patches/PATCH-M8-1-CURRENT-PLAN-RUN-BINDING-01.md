# PATCH-M8-1-CURRENT-PLAN-RUN-BINDING-01

2026-10-03；M8.1 当前原 UI 故障验证接线修复，原授权范围内。

## 原因与范围

实际源码 `businessAssistantSendRuntime` 只提交 request_id/content/thinking；后端既有 RunCreate.plan_id 和 enqueue_run 的本人、门店、会话、active 及 goal_version 守卫因此未被当前计划聊天入口使用。修改 `web/businessassistant.js`、`web/assistantworkspace.js`：仅将已从服务器加载、当前会话列表存在、当前选择一致的 active Plan 在第一次发送时绑定到 request 快照。使用 Workspace 当前 Plan 投影（跟进按钮成功已更新），不使用暂停/恢复后仍旧的 work-status status；snapshot 暴露既有读取中/跟进操作中状态以避免绑定未完成读取。未知结果重试沿用原 plan_id 和 request_id；新会话、未加载、加载失败及 paused 计划不猜绑定。

## 接线与验证范围

修改 `tests/browser_click/run.py`、`fixture_server.py`、`runtime_faults.py`、`runtime_queue_closeout.py`、`scenarios.py` 的显式白名单、固定合成 provider 和原 Web/worker 观察器，登记 CONTEXT / GOAL 独立场景。原摘要窗口和 60 秒查询凭据按真实时钟验证，不改生产期限。9 次杀进程自然租约恢复及 30 分钟自然过期使全量时间超过原 3600 秒限制；运行器总限 9000 秒，现有 CI job 限 165 分钟，单场边界不放宽。异常、失败及不完整执行仍按失败保留。

## 审阅与结果

绑定来自服务器当前选定计划；原后端重新验证权限和状态，不增加自动业务提交。仅前端接入现有合同，不更改业务或 grant 状态机。定向浏览器验证待当前接线完成后执行；静态检查不视作业务验收。

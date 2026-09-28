# M6.5 编码审阅与实测记录（统一交接守卫与“交给助手”入口）

2026-09-28，集中测试阶段。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 唯一交接入口 | `web/assistantworkspace.js` 新增 `requestHandoff({entry_context|reference+intent, prompt?, contextEpoch?, returnRoute?, keepCurrent?})`、`guardHandoff()`、`pendingHandoff()`、`clearHandoff()`、`handoffLabel()`、`buildEntryContext()`、`routeValid()`；新增内存编辑态 `rememberUi()`/`restoreUi()`/`clearUi()`（`uiBySession`） |
| 页面接线 | `web/businessassistant.js`：`new`/`session` 入口改走 `businessAssistantSwitchMatter()`（统一守卫 + 明确二选一）、新增 `businessAssistantNewMatter()`、`businessAssistantHandoffBar()`（交接标签与“留在当前事项 / 保留当前事项并打开 / 取消交接”）、发送时把 `entry_context` 放进 Run 提交体并在服务器接收后清除标签 |
| 未完成原表单 | `web/workforms.js` 新增 `workFormRequestHandoff(dialog,onDiscard)`：提交中拒绝跳转、第二次点击不覆盖待决定意图、只有明确“放弃后打开助手”才清 dirty、关表单并执行一次交接 |
| 流程入口 | `web/workflowguides.js`：`applyWorkflowAssistantIntent()` 不再直接 `session=null`，改为薄包装调用 `requestHandoff`（带 `workflow_id`），交接入口不可用时才退化为只预填草稿 |
| 外部套件 | `V/tests/frontend/test_m6_5.cjs`（11 项）、`V/tests/runtime/test_m6_5.py`（6 项） |
| 边界移动 | M6.2 的提交断言改为“同一 `request_id`、只提交一次、payload 可带 entry_context”；M6.3 的侧栏交接断言改为走唯一入口；M6.3 的导出集合同步扩展 |

## 2. 关键实现点（对应计划 M6.5 具体改法 1—7）

1. 唯一前端函数 `requestHandoff`；`entry_context` 严格产出服务器 DTO（`task`/`object`/`workflow`），意图仅 `query_status`/`explain_prerequisites`/`prepare_action`；三种固定中文模板；`returnRoute` 只保存用于返回原页面、经原路由语法校验，绝不进 `entry_context`。
2. 引用只来自真实记录：侧栏项用 `task_id` 或服务器 `object_ref`；`report_query` 必须是 WorkItem UUID、其余必须是正整数原单 ID（与服务器 `BusinessObjectRef` 一致）；拿不到明确引用就拒绝并提示回原页面办理。携带的任何 `user_id`/`store_id`/`role` 都被丢弃。
3. `workFormRequestHandoff`：`submitting` 直接拒绝；dirty 时插入“继续填写 / 放弃后打开助手”提示，只有一个待决定意图；继续填写移除提示并恢复原焦点；放弃才清 dirty、关闭并执行一次交接（回调自行复核 `contextEpoch`）。
4. `guardHandoff` 覆盖 new/session/history/suggestion/notification 入口：员工自己写的草稿或未确认重试 → 停留原事项并明确提示；待确认/executing/uncertain 卡或运行中 → 明确二选一；选择“保留当前事项并打开”时把草稿/答案/选卡/计划/文件选择存进内存后打开目标，**不 cancel、不重生成卡**。只放过“上一次交接预填且未改动”的草稿，便于员工改交接目标。
5. `uiBySession` 只存内存：草稿、答案、`activeCardId`、`queueFilter`、`workPlanId`、文件选择；临时键 `new`；不跨会话复制、不落浏览器存储；切店/退出 `disposeContext` 清空整个 map；回到旧事项只恢复服务器上仍存在（同一 `proposal_id`）的答案。
6. 流程入口改为薄包装；模块/快捷/流程入口传 workflow 引用、原任务传任务引用、原单传对象引用。
7. 交接只显示上下文标签并预填；`entry_context` 随员工下一次发送提交（Run 提交体），服务器接收后标签清除；`取消交接` 立即清标签；`contextEpoch` 不符时丢弃且不写草稿。

## 3. 实测结论

运行 `20260928T112532Z-571cad4490`：`status=passed`（源码指纹 `81e6abc74ead15aaafbf4cf0a85c2b401e3a2a4b78c77cefeae867873e784802`）。

- `m65-node-workspace-contract`：11 passed。覆盖伪造/自报引用被拒（含 `report_query` 必须 UUID、任务/对象 ID 必须正整数）、三种来源的 DTO 形状、非法意图被拒、`contextEpoch` 过期丢弃、草稿与重试停留、待确认卡/运行中的二选一与保留后打开（含回到原事项草稿仍在）、交接标签与 `returnRoute` 隔离、只恢复同一 `proposal_id` 的答案、dispose 清空内存与待交接、发送携带 `entry_context` 并在接收后清除、五类入口共用守卫、流程入口薄包装与表单保护、交接零业务写入与零浏览器存储。
- `m65-wiring-regression`：6 passed（唯一入口、DTO 形状与身份字段排除、守卫覆盖、内存态与清理、表单保护、流程薄包装、发送时提交）。
- 同指纹回归：M6.1、M6.2、M6.3、M6.4 全部 passed；前端 6 项检查（ux/workspaces/workboard/r3/oneclick）`diagnostic_passed`（`20260928T112614Z-467619481c`）。

## 4. 本轮实测发现并修复的问题

1. **`report_query` 类型与 ID 种类不匹配会被前端接受**：原实现只按“正整数”判定，导致 `{type:'report_query', id:5}` 也能生成 `object_ref`（服务器必然拒绝）。已按服务器合同区分：`report_query` 必须 UUID 字符串，其余必须正整数。
2. **`returnRoute` 未做字符串校验**：交接入口会把 `undefined` 拼成字符串存进标签。已改为只有字符串且通过原路由语法才保存。
3. **二次交接被自家守卫误拦**：员工点第二处“交给助手”时，上一处预填的草稿会被当成“员工自己写的内容”而拒绝。已区分“员工输入”与“本模块上一次预填、未改动”。

## 5. 尚未由运行证据覆盖

- 真实浏览器里未完成原表单的提示插入、焦点恢复、IME 与第二次点击行为：属 M8.4 浏览器验收。
- 通知入口（M6.7）尚未实现，`guardHandoff` 已就绪但该入口尚未接入。
- 原待办/moduleCard/快捷操作/流程文章上的“交给助手”按钮：本轮接入侧栏项、流程入口与 new/session 守卫；其余入口的按钮属 M6.5 剩余 UI 面，按下一轮补齐（未登记为已通过）。

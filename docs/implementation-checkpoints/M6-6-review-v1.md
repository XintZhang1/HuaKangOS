# M6.6 编码审阅与实测记录（每件事的持续跟进与生命周期控制）

2026-09-28，集中测试阶段。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 计划投影与生命周期 | `web/assistantworkspace.js`：新增 `loadPlan(planId)`（GET `/plans/{id}`）、`setFollowup(action)`（POST `/plans/{id}/followup`，只带当前 `expected_version`）、`planHeaderHTML()`、`planStatusText()`/`grantStatusText()`/`followupAllowed()`；当前事项头部显示目标、固定中文状态、`grant.status`/`stop_reason`、共同 steps 的等待原因 |
| 页面接线 | `web/businessassistantwork.js`：确认/取消卡、切换计划后只触发 `bawLoadPlan(planId)` 重新读取（离线单独加载时退化为空操作）；`openItem` 切换事项时读取该事项的 plan |
| 样式 | `web/assistantworkspace.css` 追加 `.ba-plan-*`（只在助手范围内） |
| 外部套件 | `V/tests/frontend/test_m6_6.cjs`（12 项）、`V/tests/runtime/test_m6_6.py`（7 项） |
| 边界移动 | M6.3 的导出合同改为“包含约定集合且无杂项全局”（后续里程碑扩充导出面不再误伤，见 §4） |

## 2. 关键实现点（对应计划 M6.6 具体改法 1—7）

1. `loadPlan` 只读 PlanView；头部显示 goal、`进行中/已暂停/已完成/已取消`、`尚未开启持续跟进/持续跟进中/已暂停跟进/已结束跟进`、`stop_reason` 与前三条 `wait_reason`；未知状态显示「状态待核对」，不直译英文；旧计划缺可验证条件时只显示服务端给出的补齐内容，前端不解析 `wait_for` 自动升级。
2. `setFollowup(action)` 只提交当前 `plan.id` 与当前 `version`；按钮来自 `allowed_actions`；`features.followup !== true` 时只显示状态、不渲染任何可操作按钮，也不提交。
3. enable 前在事项内显示范围说明：目标、门店（只按当前门店权限）、以本人身份查询和准备、实际办理需确认、退出登录后继续、随时暂停或结束；按钮「开启此事项持续跟进」，默认没有预选勾。resume 同样重新展示目标与退出后继续语义。
4. pause 保留已生成卡，状态以返回的 PlanView 为准；revoke 文案「结束这件事」，第一次点击只进入二次确认（明确写出「已生成的卡片和已提交的原业务都不会被取消」），第二次才提交；从不发送 `completed`，也不把结束标成业务完成。
5. 409：不重放动作，读回当前 Plan 并在读回之后仍显示「事项已经变化…请核对目标与权限后再决定」；403/404：收起写控制（清空本地 plan 投影）并提示原业务仍可在原页面办理；其它错误显示原始信息，不伪造授权。
6. 确认/取消卡与切换计划只触发读取；是否继续准备由服务器按 active Grant 决定；UI 无 `setTimeout`/`setInterval`，不自动 retry、不自动成卡。
7. 退出/切店只清前端（`disposeContext` 清 plan 投影），logout 链路不调用 followup；登录后重新读服务器授权与卡片，不使用本地布尔。

## 3. 实测结论

运行 `20260928T115324Z-7f746aa3fb`：`status=passed`（源码指纹 `ac19fbc8d8a1d5df54ba920bc312a61bca5d043cb357d49e7e346791358e5ff3`）。

- `m66-node-workspace-contract`：12 passed。覆盖默认无 Grant 且只读不 POST、状态与等待原因中文化（含未知状态兜底）、仅显式 enable 提交且只带当前版本、开关关闭时无按钮无提交、结束需二次确认且不发送 completed、pause 保留卡并以返回 PlanView 为准、409 不重放并读回、403/404 收起写控制、读取失败不假装已开启、退出只清前端、确认/取消后只读取、中文界面无租约/token/工具调用 ID。
- `m66-wiring-regression`：7 passed。覆盖只读计划投影、动作来自 `allowed_actions` 且带 `expected_version`、范围说明六要素与无预选勾、冲突/权限/读取失败分支、无前端定时器与本地授权、工作台只读、CSS 只在助手范围。
- 同指纹回归：M6.1—M6.5 全部 passed；前端 6 项检查（ux/workspaces/workboard/r3/oneclick）`diagnostic_passed`（`20260928T114923Z-19b5f98c16`）。

## 4. 本轮实测发现并修复的问题

1. **409 提示被随后的成功读回清空**：原实现先写 `planError` 再 `loadPlan`，读回成功即把提示清成空串，员工看不到「已经变化，请重新核对」。已改为读回之后再写提示并直接返回该原因。
2. **导出合同随里程碑扩充反复误伤**：M6.3 的“导出恰好这些名字”在 M6.5/M6.6 各失败一次。已改为“包含约定集合 + 不得出现非函数式命名的杂项全局”，既保留约束也不再因新增导出产生假失败。
3. **多处测试自身缺陷**（非产品）：Harness 每次 `getElementById` 返回新节点导致头部断言读空、`mount()` 会额外产生 `/workspace` 读取、`SOURCE.indexOf('globalThis.AssistantWorkspace')` 命中文档注释而切片为空、正则转义过度导致语法错误。全部按真实语义修正后复跑通过。

## 5. 尚未由运行证据覆盖

- 退出登录后 worker 继续准备、再登录能看到真实待确认卡：需要真实 worker + 会话实例（M8.1/M8.7 环境），本项只验证前端不伪造授权、不自动重试。
- 真实浏览器里 grant 状态变化、暂停/恢复/结束的可见反馈：属 M8.4。
- 通知入口（M6.7）尚未实现。

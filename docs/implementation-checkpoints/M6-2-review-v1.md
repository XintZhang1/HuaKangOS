# M6.2 编码审阅与实测记录（发送、恢复与显式停止接入持久 Run）

2026-09-28，集中测试阶段。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 产品实现 | `web/businessassistant.js`：新增 `businessAssistantSendRuntime()`、`businessAssistantSendLegacy()`（原逻辑原样保留）、`businessAssistantRuntimeFeatures()`、`businessAssistantWatchRuntimeRun()`、`businessAssistantResumeRuntimeRun()`、`businessAssistantReleaseRuntime()`、`businessAssistantStopButtonHTML()`、`businessAssistantRunText()`；改写 `businessAssistantSend()`（按服务端投影分派）、`clearBusinessAssistantSession()`、`businessAssistantRememberSession()`、`businessAssistantWorking()`、`businessAssistantCompose()` 停止按钮、stop 事件分支 |
| 外部套件 | `V/tests/frontend/test_m6_2.cjs`（Node 行为 9 项，经已评审 `tests/m02_node_adapter.py` 运行）、`V/tests/runtime/test_m6_2.py`（接线与边界 7 项） |
| 边界移动（已随本项同步并复跑 M6.1） | `V/tests/runtime/test_m6_1.py` 的"只有客户端自己可以取消/清理"改为允许助手工件页发起显式停止（M6.1 的验收范围本就是"本项不替换员工现用发送按钮"），其余文件仍不得代员工取消 |
| 未改动 | 原确认/批量/卡片有效期/后端接口/迁移/模型合同；`web/businessassistantfiles.js` 仍调用同一个 `businessAssistantSend()` |

## 2. 关键实现点（对应计划 M6.2 具体改法 1—7）

1. `businessAssistantSend()` 先读 `/workspace` 投影：`features.runtime=true` 走 Runtime 路径，否则走原流式路径；**读取失败不得改走另一个入口重发**（`runtimeFeatures=null` 且按旧入口处理）。
2. 只在员工发送时创建缺失的 session；`retry={session_id,request_id,content,thinking}` 在内存保留，`submitRun` 用同一 `request_id`；202 丢失时重试仍用同一 body，不生成新编号、不额外发送 `expected_version`。
3. 202 之后只清除**与已提交内容完全一致**的输入文字；提交记录保留供恢复；刷新后只用 `SessionView.last_request.run_id`，`null` 不创建 Run、不按消息位置猜。
4. 局部发送结束不等于 Run 结束：`businessAssistantWorking()` 在 `runId` 存在时按服务端事件显示阶段/文字，只有服务端终态才收尾；旧卡确认仍走原 `businessAssistantDecide/batch` 包装。
5. 停止按钮文案"停止本次准备"，仅在 `RunView.allowed_actions` 含 `cancel` 时显示；点击用 `cancelRun(id, version)` 提交当前版本，本地显示"正在停止…"；409 只刷新 RunView 不重放；失败保留运行展示与错误，不删除任何卡片。
6. 离开助手页/退出/换店只关闭订阅并 `disposeContext()`（纯本地）；注释已改为"退出登录/换门店只清浏览器状态：不调用 cancel、不撤销 Grant、不删除卡片"。
7. 文件"发送资料并填表"与手工"查询下一步"入口未改，仍复用同一发送函数与只读意图。

## 3. 实测结论

运行 `20260928T105949Z-6203423841（源码指纹 ad4d64645b5375f0c1d3aaeb61c569ebff1f85713adba3b08ebe9f6dc720387a）；M6.1 同一指纹复跑 20260928T105921Z-9b6ab23df4 也 passed`：`status=passed`。

- `m62-node-send-stop-contract`：9 passed（读取本次安全镜像里的真实 `web/businessassistant.js` + `web/assistantruntime.js`）。
  覆盖：runtime 关闭走原入口且不创建 Run；runtime 打开用同一 `request_id` 提交并订阅 202 返回的 Run；
  提交结果未知时保留同一编号与输入；只有 `allowed_actions` 含 cancel 才出现"停止本次准备"并按当前版本调用 cancel；
  终态视图关闭订阅且 `succeeded` 固定显示"本次准备已完成"（不等于业务已完成）；`dispose` 零服务器调用；
  刷新按 `last_request.run_id` 恢复、`null` 不创建 Run；旧确认路径未被替换；切店/退出只清本地。
- `m62-wiring-regression`：7 passed（接线、保留的旧流式路径、版本绑定停止、本地清理、无新增浏览器持久化与第三方协议）。

## 4. 人工审查要点

- 未新增 localStorage/sessionStorage/IndexedDB/EventSource/XHR；无任意外部地址。
- 停止是唯一的取消入口，且必须带服务器版本；`unsubscribe`/`disposeContext`/离开页面都不产生取消。
- 迟到响应按 `businessAssistantAlive(current,generation)`/上下文校验丢弃；输入与卡片选择按 ID 稳定。
- 旧登录/换店清理顺序保持：先 abort 本地控制器，再释放 Runtime 订阅，再重建状态并递增 generation。

## 5. 尚未由运行证据覆盖

- 真实浏览器里的双击发送/断线刷新/切页只出现一个 Run、抽屉与窄屏布局、IME 焦点：属 M6.3/M8.4 浏览器验收。
- Grant 持续跟进在退出登录后由 worker 继续：属 M6.6/M6.7 与 M8 的实例级实测。
- 本项不启动原预览、不调用真实模型、不写公司库。

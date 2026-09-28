# M6.1 编码审阅与实测记录（Run REST/SSE 客户端与纯状态归并）

2026-09-28，集中测试阶段。Astra 批次未开始 M6.1；本轮实现 + 外部实测。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 产品实现 | 新增 `web/assistantruntime.js`（IIFE，唯一出口 `globalThis.AssistantRuntime`，6 个函数）；`web/index.html` 在 `businessassistantfiles.js` 之后、`workflowactions.js` 之前加入 `defer` 标签 |
| 外部套件 | `V/tests/frontend/test_m6_1.cjs`（Node 合同测试 15 项，经已评审的 `tests/m02_node_adapter.py` 事件级证据运行）、`V/tests/runtime/test_m6_1.py`（接线与真实路由形状 7 项） |
| 未改动 | `web/businessassistant.js` 与全部原确认路径（本项不替换员工现用发送按钮）、后端接口、模型/provider、业务 schema、迁移 |

客户端只做四件事：建立/读取 Run、按 `after_seq` 订阅事件、可显式请求停止、只在内存保存状态；
不生成业务动作、不确认业务、不写任何浏览器持久化。

## 2. 实测结论（真实运行）

运行 `20260928T092523Z-1ef70a74e0`：`status=passed`，`phase_complete=true`。

- `m61-node-client-contract`：15 passed（Node，读取本次安全镜像里的真实 `web/assistantruntime.js`）。
  覆盖：唯一出口恰为 6 个函数且无 confirm/followup/EventSource/localStorage/XHR；重复与乱序事件按
  seq 只应用一次；`display` 按 revision 替换而非拼接；序号缺口关闭订阅并以 `after_seq` 补读；
  网络中断保留已知状态并按 1/2/5 秒、之后 15 秒退避重连；半截/非法 JSON 不进入应用状态；
  终态只读回一次 session 并关闭订阅、`unsubscribe` 不发 cancel；显式取消提交当前版本且缺版本拒绝；
  409 先读回 RunView/session；401 清登录上下文、403/404 停止读取且不重连；`submitRun` 复用原请求守卫
  并登记 202 的 run id；`disposeContext` 只清本地并中断读取、零服务器调用；切店后的迟到事件既不应用
  也不推进本地序号；后台标签暂停刷新、回到可见立即重读。
- `m61-wiring-regression`：7 passed。加载顺序（files→runtime→workflowactions，且带 defer）、
  固定路由与认证传输（same-origin + `X-App-Request` + `X-Store-ID` + `text/event-stream`）、
  无浏览器持久化、只有客户端自己调用 cancel/dispose、原发送/确认路径未被替换、
  以及真实服务器接受该路由形状（无会话 401/403；已登录但执行不存在 404/409）。

## 3. 本轮实测发现并修复的缺陷（客户端）

1. **状态失败分支不生效**：`statusFailure()` 原本 `return` 而非 `throw`，导致 409 的"先读回
   RunView/session"、401 清理与 403/404 停止读取在真实分支上都不会触发；Node 合同测试先失败后修复。
2. **陈旧上下文的迟到事件推进本地序号**：`dispatch()` 在验证上下文之前写 `lastAppliedSeq`；
   切店后的迟到事件会让本地序号前进、并可能让后续补读跳过事件。修复为先验证 `alive()` 再应用；
   `applyView()` 同样先验证后写入。
3. **重连退避不收敛**：原实现第三次之后仍是 5 秒；修复为 `attempt < 3 ? RECONNECT_MS[attempt] : 15000`，
   并由测试固定 1/2/5/15 秒序列。

## 4. 人工审查要点

- 传输层复用 `businessAssistantRequest`（同源 Cookie、CSRF、当前门店守卫）；SSE 用 `fetch` +
  `ReadableStream` 并显式带所需请求头，不用无法携带这些头的 `EventSource`；只请求固定
  `/api/business-assistant` 路由，无任意外部地址。
- 状态机：每 run 记录 `{view,lastAppliedSeq,displayRevision,connectionState,controller,contextEpoch}`；
  回调先校验 `businessAssistantContext()`/generation/`storeSwitch`。
- 错误分类：401 清上下文并交原登录流程；403/404 终止读取；409 读回核对；网络/5xx 只显示连接问题，
  绝不伪造 Run 失败；终态 `succeeded` 的固定中文展示为"本次准备已完成"。
- 副作用：`unsubscribe`/`disposeContext` 只关闭本地读取并 abort 请求；不发 cancel、不改授权、不删卡。

## 5. 尚未由运行证据覆盖

- 真实浏览器同源 Cookie/CSRF/CSP 与真实 SSE 连接头（含失效 CSRF 不能创建 Run）：属 M8.4 浏览器验收。
- 发送按钮接入持久 Run、恢复与显式停止（M6.2）；事项侧栏与两列工作台（M6.3）；通知与交接（M6.7）。
- 本项不启动原预览、不调用真实模型、不写公司库。

源码指纹：`ee2752b6bad230d227b4c95cd6d4fedf42da38e3c466690fabc79442851ee2d1`。

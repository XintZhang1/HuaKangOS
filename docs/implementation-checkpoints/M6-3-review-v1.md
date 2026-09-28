# M6.3 编码审阅与实测记录（真实事项侧栏与两列工作台）

2026-09-28，集中测试阶段。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新增实现 | `web/assistantworkspace.js`（IIFE，唯一出口 `globalThis.AssistantWorkspace`：`load` / `mount` / `renderSidebar` / `openItem` / `patchCurrent` / `disposeContext` / `snapshot`）、`web/assistantworkspace.css` |
| 接入 | `web/index.html`：`assistantruntime.js` 之后插入 `assistantworkspace.css` 与 `assistantworkspace.js`（均在原十模块脚本之前） |
| 助手渲染改动 | `web/businessassistant.js`：`businessAssistantWorkspace()` 改为 `.ba-runtime-workspace`（280px 事项栏 + 当前事项）；当前事项固定 `#ba-current-heading` → `#ba-current-plan` → `#business-assistant-messages` → `#business-assistant-cards` → `#business-assistant-form`；工作台（`#business-assistant-workboard`）从卡片队列移入当前事项；新增 `businessAssistantWorkspaceModule()` 薄封装；`bindBusinessAssistantPage()` 挂载、`businessAssistantPage()` 载入、`businessAssistantReleaseRuntime()` 一并 dispose |
| 外部套件 | `V/tests/frontend/test_m6_3.cjs`（10 项）、`V/tests/runtime/test_m6_3.py`（6 项） |
| 未改动 | 原业务 API、任务分派规则、原十模块样式、确认/批量语义、后端接口与迁移 |

## 2. 关键实现点（对应计划 M6.3 具体改法 1—7）

1. 六个函数 + `snapshot()` 齐备；只读 `GET /api/business-assistant/workspace`，**与模型开关无关**：模型未就绪也照样渲染本人待办与原页面链接。
2. 侧栏固定 `attention 待我处理 → following 跟进中 → finished 已结束`，只渲染服务器给的组与项；待我处理组显示分项计数（"业务待办 3、待确认操作 2"），组徽标取服务器 `counts`；**读取失败显示错误行并提示"这不是空列表"**，不冒充零合计。
3. 当前事项结构固定，原卡 ID、组 key、`data-ba-*` 选择器继续有效；确认卡在当前事项流里，逐张导航与同组批量未改。
4. `openItem`：同一会话内直接切换；跨事项先过守卫（未发草稿 / 未确认重试 / 运行中 / 待确认卡 → 拒绝并保留当前页）；`native_task` 只显示摘要与原业务入口 + "交给助手"，**不创建会话、不调用模型**；`proposal`/`plan` 项才 `ChooseSession` 并按 `plan_id` 读回进度。
5. `patchCurrent()` 只替换 `#ba-current-heading` 与 `#ba-current-plan`（保留其中的工作台节点），消息流/卡片/输入区由助手页面自己维护；事件刷新不重建聚焦输入。
6. `.ba-runtime-workspace` 根下 `280px minmax(0,1fr)`；`≤1024px` 事项栏抽屉化（`translateX(-102%)` + 遮罩）、`≤768px` 当前事项单列；输入区 `position:sticky` 固定在工作台底部。
7. 初次进入不自动选卡、不自动发送（无 `businessAssistantSend(`、无 `.click()`）；无当前事项时显示欢迎提示 + 真实侧栏；切店/退出调用两个模块的 dispose 并移除抽屉类；`mount` 用文档级委托监听，`disposeContext` 移除，重复 mount 不重复绑定。

## 3. 实测结论

运行 `20260928T110717Z-0b9a8fa7d6`：`status=passed`。

- `m63-node-workspace-contract`：10 passed（读取本次安全镜像里的真实 `web/assistantworkspace.js`）。
  覆盖：唯一出口与函数集；三组固定顺序 + 服务器计数 + 分项计数；读取失败 ≠ 空列表；翻页按稳定 key 去重追加（同名不同 key 各自成项）；草稿/重试/运行中/待确认卡四类守卫拒绝切换；同一事项内切换放行；
  原生待办不创建会话、计划项才读回会话与进度；`patchCurrent` 保留工作台节点与输入值；抽屉开关 + Escape 关闭 + dispose 移除监听；交给助手只填未发送草稿且无浏览器存储。
- `m63-wiring-regression`：6 passed（接线顺序、固定 DOM 节点与顺序、mount/load/dispose 接线、与模型开关无关、无业务写入、响应式规则）。
- 前端回归（同指纹 `b74d5974…`）：`b03-node-check_assistant_workboard`、`b03-node-check_assistant_r3`、`b03-node-check_ux`、`b04-check_assistant_r3`、`b04-check_assistant_oneclick_integration`、`b04-check_ux` 全部 `diagnostic_passed`（run `20260928T110759Z-85acdf2e93`）。

## 4. 人工审查要点

- 侧栏模块不写业务、不推进 Plan/Task/Proposal、无 `localStorage`/`sessionStorage`/`indexedDB`/`EventSource`/`XMLHttpRequest`，也不绕过 `businessAssistantRequest` 直接 `fetch`。
- 门户仍以员工本人身份读取；无权限项由服务器不返回，前端不自行拼装。
- 抽屉只在窄屏出现；键盘 Escape 关闭并回到切换按钮；遮罩点击关闭。
- 移交（M6.5）尚未实现前的临时边界：`openItem` 已按计划第 4 条拒绝在草稿/重试/运行中/待确认卡时切换，"交给助手"目前只填草稿不发送。

## 5. 尚未由运行证据覆盖

- 真实浏览器的 390/768/1440px 布局、IME 焦点、20 条状态事件下输入不丢、抽屉键盘可达：属 M8.4 浏览器验收。
- 事项栏与 ConfirmBar 的视觉重叠、卡片不遮盖确认区：需真实浏览器截图，属 M8.4。
- Grant 持续跟进与通知分组（M6.6/M6.7）尚未实现，侧栏在此阶段只显示既有投影。
- 本项不启动原预览、不调用真实模型、不写公司库。

# M6.7 编码审阅与实测记录（站内通知、原任务协作和未知结果核对）

2026-09-28，集中测试阶段。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 通知投影与轮询 | `web/assistantworkspace.js`：`loadNotifications({cursor,limit,silent})`（GET `/notifications`，`unread_count` 作入口徽标、稳定 `id` 去重、`next_cursor` 原样透传）、`startNotifications()`/`stopNotifications()`/`pollTick()`/`onVisibility()`/`invalidateNotifications()`（可见页面每 30 秒、隐藏停止、回前台立即读取、既有运行事件只触发一次合并读取） |
| 点击与已读 | `openNotification(id)`：先按引用打开目标（任务走统一守卫 → 会话按引用切换 → 其余只用原 `manual_route`），成功后才显式 `POST /notifications/{id}/read`；失败提示「已打开，已读状态未更新」，未读计数不假装变化；守卫拒绝时不打开也不标记已读 |
| 结果核对 | `checkReceipt(sessionId, proposalId)`：只 `GET /sessions/{id}/proposals/{id}/execution-result`；五种结果固定中文文案；读取失败记为待核对，不重发业务请求、不换 `request_id` |
| 界面与样式 | 事项头部通知入口（未读徽标）+ 面板（`safe_summary`、`created_at`、未读标记、继续加载）；`web/assistantworkspace.css` 追加 `.ba-notice-*` |
| 外部套件 | `V/tests/frontend/test_m6_7.cjs`（11 项）、`V/tests/runtime/test_m6_7.py`（9 项） |
| 边界移动 | M6.6 的“不得有前端定时器”改为“定时器只允许用于通知轮询”（M6.7 计划明列 30 秒轮询）；M6.3/M6.5/M6.6 的 Node 宿主替身改为记录式定时器（避免真实 30 秒定时器占住事件循环） |

## 2. 关键实现点（对应计划 M6.7 具体改法 1—6）

1. 未读计数取 `NotificationList.unread_count`；列表只用 `safe_summary`/`created_at`/授权引用；`next_cursor` 只原样传给下一页；按 `notification.id` 去重；**不根据摘要拼路由**（无引用时只显示摘要、按钮禁用）。
2. 可见页每 30 秒 GET；`visibilitychange`/`focus` 时回到前台立即读取，隐藏时清掉定时器；切店/退出随 `disposeContext` 停轮询并清缓存；既有 `proposal.prepared/plan.updated/run.completed/run.failed/run.cancelled` 只用来触发一次合并读取，未新增事件类型；只在新通知 ID 首次出现时提示一次。
3. 点击通知先打开目标再显式 read；守卫拒绝或读取失败不假称已读；已读失败保留已打开业务；重复 read 只影响未读计数。
4. 协作/转交：只用服务器投影的 `task_id`、`session_id`、`manual_route`；模块内**不出现** `assignDialog`、`state.row` 或任何代理动作，转交必须回到原授权页面由原 `taskList()`/`a==='assign'` 分支处理。
5. `核对办理结果` 按钮只 GET 原 `execution-result`；`confirmed_success` 显示「已找到原业务成功回执，请按原单核对结果」；`not_found/unsupported/inaccessible/mismatch` 分别保留待核对语义，任何路径都不重发业务写、不换 `request_id`、不把卡片改成 succeeded。
6. 评审引导只消费服务端结果字段：模块内无 `permission_hint`、无 `refusal` 自造，页面不对 403 文案做判断；业务成功但通知读取/更新失败只给次级提醒。

## 3. 实测结论

运行 `20260928T121421Z-ba5b526aa9`：`status=passed`（源码指纹 `e04af80248373abb5459737ffd50d5e0bf99f8abc4b780d9583b718d448cc3d6`）。

- `m67-node-workspace-contract`：11 passed。覆盖只读投影（未读计数、去重、游标透传、零 POST）、前台轮询/隐藏停止/回前台立即读取、只提示一次、事件合并读取且无新事件类型、点击先打开后 read（含跨会话按引用切换）、read 失败不假装已读、守卫拒绝时不打开也不已读、无授权引用只显示不拼路由、回执核对只读且五种文案、回执失败保留待核对、退出停轮询并清缓存。
- `m67-wiring-regression`：9 passed。覆盖服务器字段消费与通知函数内的别名排除、可见窗口轮询、首次提示、先打开后 read、协作不自造代理动作、回执只读、拒绝引导只来自服务端、dispose 停止轮询、CSS 只在助手范围。
- 同指纹回归：M6.1—M6.6 全部 passed；前端 4 项检查（workboard/ux/oneclick）`diagnostic_passed`（`20260928T115827Z-343ab43315`）。

## 4. 本轮实测发现并修复的问题

1. **新增轮询把旧套件挂死**：M6.3/M6.5/M6.6 的 Node 宿主替身使用真实 `setTimeout`，`mount()` 装的 30 秒定时器让进程无法退出（适配器超时判失败）。已把三套替身改为记录式定时器（语义不变）。
2. **M6.6 的“禁止前端定时器”与 M6.7 的 30 秒轮询直接冲突**：按计划把该断言收窄为“定时器只能用于通知轮询”，避免用旧约束否定新计划要求。
3. **测试断言误伤与切片错误**：通知别名检查原先扫整个模块（命中侧栏 `item.title`）、`str.lastIndexOf` 应为 `rindex`、`assign(` 命中 `Object.assign(`、拒绝引导断言写错字段名——均按真实语义修正后复跑。

## 5. 尚未由运行证据覆盖

- 真实浏览器里的 30 秒轮询、标签隐藏/恢复、通知点击后的可见反馈：属 M8.4。
- 同事转交的完整链路（原 `assignDialog` 收件岗位校验）：需真实任务分派数据，属 M8.2。
- 通知去重与 resolved 状态在真实事件流下的表现：需 M8.1 故障/恢复演练环境。

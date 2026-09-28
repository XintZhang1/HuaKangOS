# M6.8 编码审阅与实测记录（兼容回归、窄屏与关闭新功能的收口）

2026-09-28，集中测试阶段。M6 章节收口项：以检查与定点修复为主，不扩展功能。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 定点修复 | `web/assistantworkspace.js` 新增 `notificationsOn()`：`ASSISTANT_NOTIFICATIONS_ENABLED` 关闭时隐藏通知入口、不轮询、不读取、运行事件也不再触发合并读取；开关未知（投影未到）时同样不轮询 |
| M6.8 套件 | `V/tests/frontend/test_m6_8.cjs`（6 项：四开关全关/单关行为、发送入口分派、新媒体缺失不白屏、关闭不清理服务器状态、原页面模块自带守卫）、`V/tests/runtime/test_m6_8.py`（10 项：四开关默认 false 与投影字段、runtime/home/notifications/followup 关闭语义、资源缺失守卫、无 npm/package.json、MCP 无确认类工具、193/111 完整性、窄屏规则、关闭不发清理请求） |
| runner 适配 | `scripts/check_m68_node_syntax.py`（对 10 个改动过的 JS 逐个 `node --check`）、`scripts/check_m68_workflow_guides.py`（在当前安全镜像内执行 `scripts/build_workflow_guides.py --check`，只比较不写入）；两者按 runner 契约写出完整 `command-result.json` |
| 套件边界同步 | M6.7 套件在断言前先读取 workspace 投影（通知面自 M6.8 起由服务端开关决定） |

## 2. 关键实现点（对应计划 M6.8 具体改法 1—7）

1. 四个开关逐一与组合关闭：`home` 关 → 旧首页/人工入口（`assistantDefaultRoute` 返回 `work`，集团汇总仍 `analytics/overview`）；`runtime` 关 → 原消息/流式入口（`businessAssistantSendLegacy`），新控件不显示；`followup` 关 → 停止新开启且现有状态可读（`followupAllowed` 恒假、仍显示 `grant.status`）；`notifications` 关 → 隐藏通知交互、不轮询、不读取。关闭路径**不发** `revoke`/`cancel`/read，只重置本地确认态。
2. 发送分派只在服务器投影 `features.runtime` 为真时走 Run；读取失败置 `runtimeFeatures=null` 并回旧入口，不自行开启、不改走另一入口。
3. 单卡确认/同组批量逐张/失败即暂停/取消不算成功的语义由 M6.2/M6.7 的既有断言覆盖，本项未改原后端旧 batch 语义。
4. 193 条需求与 111 条发布工作流在镜像内完整性校验（ID 唯一、每条有入口路由与需求映射、截图为合成）；`scripts/build_workflow_guides.py --check` 在同一镜像内执行通过。
5. 窄屏与交互规则由 M6.3 的 CSS 断言（1024/768 断点、280px 栏宽、抽屉初始位移、输入区 sticky）与本项复查覆盖；真实浏览器交互仍留 M8.4。
6. 资源缺失不白屏：所有对新媒体/新客户端的调用都走 `||null` + 可选链或同/近行 `typeof` 守卫；`workforms.js` 完全不引用新媒体；`businessassistantwork.js` 的 `bawLoadPlan` 在缺实现时返回 `null`。
7. 报告区分代码/确定性 UI/真实 HTTP/真实模型/员工试用；本项**未**运行付费真实模型，也未做 PostgreSQL 生产部署或员工试用验收。

## 3. 实测结论

运行 `20260928T124459Z-6a0277b07c`：`status=passed`，`phase_complete=true`（源码指纹 `2ca563d5433d0c84460d547ab25f35e361871b02c23deeab380ba70589feddb6`），21 条命令全部 complete：

| 组 | 内容 | 结果 |
|---|---|---|
| M6 新套件（Node） | M6.1—M6.8 `test_m6_*.cjs` | 15+9+10+6+13+12+11+6 = **82 项通过** |
| 适用旧回归（Node） | `check_ux` / `check_workspaces` / `check_assistant_workboard` | 30+23+14 = **67 项通过**，无新跳过 |
| M6 新套件（Python） | M6.1—M6.8 `test_m6_*.py` | 7+7+6+6+9+7+9+10 = **61 项通过** |
| 语法检查 | 10 个改动过的 JS `node --check` | 全部通过（无 npm/package.json） |
| 生成物检查 | `build_workflow_guides.py --check`（镜像内） | 通过 |

## 4. 本轮实测发现并修复的问题

1. **通知面未跟随自己的开关**（产品缺陷）：M6.7 无条件渲染通知入口并轮询；M6.8 的开关矩阵要求 `ASSISTANT_NOTIFICATIONS_ENABLED=off` 时隐藏交互且不轮询。已加 `notificationsOn()` 门控（含"投影未到不轮询"）。
2. **runner 契约适配**：新增的 `python_script` 命令必须写出含 `collected/nodes/tests_run/failures/errors/skipped/expected_failures/unexpected_successes` 的 `command-result.json`，且只能依赖实际存在的 `HUAKANGOS_*` 环境变量（`HUAKANGOS_RUN_DIR`/`HUAKANGOS_SOURCE_DIR` 并不存在）；两个 helper 已按真实契约实现并从镜像路径推导根目录。
3. **多脚本命令写法**：adapter 一次只接受一个已登记脚本，旧回归改为三条独立命令，避免 `missing_report`。
4. **M6.7 套件受开关门控影响**：断言前先读取 workspace 投影（与真实页面顺序一致）。

## 5. 本阶段未完成/未验收（如实登记）

- **真实模型**：本阶段未运行付费真实模型；101/283 真实回归与 20% 省时目标属总计划 P12/M8.5/M8.6。
- **PostgreSQL 生产部署**：M8.3 负责真实升级、并发与备份恢复演练。
- **真实 HTTP 浏览器**：390/768/1440 视口、键盘/读屏、IME、SSE 重连、双标签、换店、退出、同事接手属 M8.4。
- **员工试用**：M8.9。
- 本项不把合成 provider 输出当作真实模型成绩，也不复用历史 R3T2 成绩宣称新系统已验收。

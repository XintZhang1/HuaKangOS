# M8.1 前置侦察记录（综合故障与恢复验收，未执行）

2026-09-28，集中测试阶段。M8 组首项。**本文件只记录验收清单、环境事实与下一步，不表示该项已通过。**

## 1. 验收清单原文（5 项，逐条保留，不得降低）

- [ ] 确认前原业务写入 0，资金/库存等重复事实 0。
- [ ] 每个稳定 WorkItem 最多一个对应有效准备版本；批量无遗漏。
- [ ] 旧租约不能覆盖新状态；无授权/撤权不能继续或泄露结果。
- [ ] “业务成功、通知失败”仍呈现真实业务成功；未知写入绝不重放。
- [ ] 故障重复执行能稳定得到同一断言结果。

**允许/禁止（原文）**：允许在**独立子进程**中注入中断、延迟、重复事件和模型协议异常；
**禁止**向生产进程发信号、伪造真实业务回执或**降低断言**。

**目标（原文）**：验证已完成各子系统接在一起后，不重复准备、不越权、不丢批量项，不把未知结果变成自动重试。

## 2. 环境事实（本轮核对）

- `V/validation-manifest.json` **当前没有任何 M8.x 登记**（最新为 `M7.12.3`）→ M8.1 需按既有节奏
  **新登记**：外部套件 + `register_m8_1.py`（含 `minimum_tests`）+ manifest 条目；
- 外部套件目录沿用 `$ValidationRoot/tests/baseline/overlay/tests/runtime_domains/`（既有 M7.x 套件同处）；
- `V/tests/runtime`、`V/tests/integration`、`V/tests/fault` **均不存在** → 故障注入套件需新建，
  且必须按"独立子进程注入"的允许范围实现（不触碰生产进程、不伪造回执）。

## 3. 已清点的运行时面（供下一轮精读定位）

`app/assistant_runtime_*.py` 共 19 个模块。与本项 5 条断言最相关的模块：

| 断言 | 主要相关模块与符号（待精读） |
|---|---|
| ① 确认前零原业务写入 / 无重复资金库存事实 | `assistant_runtime_receipts.py`（`freeze_confirmation`、`frozen_payload`、`_lookup_receipt_once`）、`assistant_runtime_objects.py`（`read_object`、`resolve_result`） |
| ② 每个 WorkItem 至多一个有效准备版本 / 批量无遗漏 | `assistant_runtime_queue.py`（`RunHandle`、`runtime_busy_token`、`_handle`、`_state_event`）、`assistant_runtime_runner.py`（`_work_key`、`ReprepareAuthorization`、`RowResolution`） |
| ③ 旧租约不得覆盖新状态 / 撤权即停 | `assistant_runtime_queue.py`（租约/状态跃迁相关）、`assistant_runtime_principal.py`（`RuntimePrincipal`、`_denied`、`_stopped`）、`assistant_runtime_access_signals.py`（`emit_user_access_changed`/`emit_store_access_changed`） |
| ④ 业务成功但通知失败仍为成功 / 未知写入不重放 | `assistant_runtime_events.py`（`_append`、`_append_queue_transition`、`_committed`）、`assistant_runtime_outbox.py`（`emit_wake_event`、`DispatchResult`、`PollResult`） |
| ⑤ 故障重复执行结果稳定 | 全套件需**确定性**：固定时钟/固定 uuid/固定摘要输入，重复运行得到同一断言结果 |

## 3b. 本轮已逐字确认的两处关键机制（供断言落点）

- **准备键是确定性摘要**：`assistant_runtime_runner._work_key(scope, input_item_id)`
  = `'prepare:' + _digest({**anchor, 'input_item_id': input_item_id, ...})`，其中 `anchor` 取
  `{plan_id, step_key}`（无计划时取 `origin_request_id`）。
  → 直接支撑断言 ②（**同一稳定 WorkItem 至多一个有效准备版本**：同一 scope + 同一输入项得到同一键）
  与断言 ⑤（**重复执行结果稳定**：键为纯函数，不含随机或时钟输入）。
- **队列状态跃迁是带前置状态的事务内追加**：`assistant_runtime_queue._state_event(db, run, previous_status, *, clock)`
  文档串为 “Append only a queue transition **already made in this same transaction**”，内部转
  `assistant_runtime_events._append_queue_transition(..., previous_status=previous_status, ...)`，
  并在 `settings.assistant_notifications_enabled` 为真时另行处理通知。
  → 直接支撑断言 ③（**旧租约不得覆盖新状态**：跃迁必须携带并匹配前置状态）与断言 ④
  （**通知与业务成功解耦**：通知开关只影响通知，不改变已提交的业务状态）。

## 4. 下一步（下一轮第一步，不虚构完成）

1. 精读 `assistant_runtime_queue.py` 的 RunHandle/租约/状态跃迁与 `assistant_runtime_runner.py` 的
   `_work_key`/`_require_authorized`，确认"准备版本唯一性"与"旧租约"的可注入点；
2. 精读 `assistant_runtime_receipts.py` 的冻结确认与一次性回执查找，确认"确认前零写入"与
   "未知写入绝不重放"的可断言面；
3. 在**独立子进程**中注入：重复事件、延迟、中断、模型协议异常（不向生产进程发信号、不伪造回执）；
4. 逐条实现 5 项断言 → 登记 `register_m8_1.py`（`minimum_tests` 与真实用例数一致）→ 运行
   `run_validation.py --milestone M8.1` → 通过后写评审记录并登记 `done`（M8.x 为验收到，不用 `implemented`）；
5. 若某项需真实环境（浏览器/真实模型/PostgreSQL/Linux/员工），**如实登记为待条件项**，不假完成。

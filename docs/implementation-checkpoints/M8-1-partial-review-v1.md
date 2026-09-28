# M8.1 部分验收记录（综合故障与恢复，**尚未完成**）

2026-09-28，集中测试阶段。前置侦察见 `M8-1-recon-note.md`。**本文件是部分证据，M8.1 仍为未完成。**

## 1. 本轮可执行并已通过的部分

外部套件 `$ValidationRoot/tests/runtime_domains/test_m8_1_fault_recovery.py`（7 项通过，
run `20260928T144342Z-875dbfaa7d`，`phase_complete=true`，源码指纹 `9bebdcdcd6a215a4550c4c69b16d21783bf00c047319dd2c36d26263438812b1`）。

| 断言 | 本轮证据 |
|---|---|
| ② 每个稳定 WorkItem 至多一个有效准备版本 | **真实调用** `assistant_runtime_runner._work_key`：同一 scope+输入项恒等、不同输入项/不同 `plan_id`/不同 `step_key` 各不相同、无计划时锚定 `origin_request_id`；`_work_key` 需 `scope.intent_version` 参与摘要（本轮实测发现） |
| ⑤ 故障重复执行结果稳定 | 同一输入重复 20 次仅得 1 个键；`inspect.getsource` 断言源码不含 `now(`/`utcnow`/`random`/`uuid`/`time(` 等非确定输入 |
| ④ 未知写入绝不重放（冻结与防篡改） | **真实构造**确认项并计算 `submission_snapshot_digest`：`_checked_snapshot` 返回快照、`frozen_payload` 返回脱离副本；**篡改 `body.values` 后两者都必须抛错**；非确认项（`kind='result'`/缺 `proposal_id`）必须被拒 |
| ④ 无回执不得猜成功 | 源码逐字断言：`_lookup_receipt_once` 只按"exact, durable confirmation only"读取，且"no HTTP route or background identity bypass" |
| ① 确认前不得发原请求 | 源码逐字断言：`freeze_confirmation` 文档串要求"a new item together with Proposal.status=executing **before sending the native request**"，且"an existing item is never rewritten"、"created=False does not authorize" |
| ③ 旧租约不得覆盖新状态 | 真实读取签名：`_state_event(db, run, previous_status, *, clock)` 的 `previous_status` **无默认值**，并转交 `_append_queue_transition(previous_status=…)`；文档串要求跃迁"already made in this same transaction"；通知分支（`assistant_notifications_enabled`）**不得再改业务状态** |

## 2. 尚未完成、因此 M8.1 不得登记 done 的部分（如实登记）

1. **独立子进程故障注入**：中断、延迟、重复事件、模型协议异常四类注入（清单"允许"范围）尚未实现；
2. **端到端零写入计数**："确认前原业务写入 0、资金/库存等重复事实 0"需完整 DB 与原业务夹具逐笔计数；
3. **批量无遗漏**：真实批量（多行、部分失败即暂停）与"每个稳定 WorkItem 至多一个有效准备版本"的 DB 级核对；
4. **撤权即停**："无授权/撤权不能继续或泄露结果"的会话级演练（含 `access_signals` 事件路径）；
5. **同断言结果稳定性**：同一故障脚本重复运行的**结果级**稳定性（本轮仅覆盖纯函数级稳定性）。

## 3. 本轮实测发现的真实事实（已纳入套件）

- `_work_key` 的 scope 还要求 **`intent_version`**（首轮因缺该键直接 `KeyError`）→ 已写入夹具，
  并说明准备键的摘要输入是 `{plan_id|origin_request_id, step_key, input_item_id, intent_version}`。

## 4. 状态登记

`### M8.1` 登记为 **`in_progress`**（唯一在办项）：已具备可执行的部分证据，但上节 5 项未完成前不得 `done`。

# PATCH-CP-00B-09 — M8.2 归档契约对齐（两处已过时断言）

**状态**：已获业主批准并应用（2026-09-30）。适用里程碑：M0.2.B 与 M8.2。
**范围**：只改 V 侧 overlay 里的两处**归档断言**与 `archive/baseline-restoration.json` 的适配登记；
**未改任何生产代码**，未放宽任何守卫、权限或业务规则。

## 1. 依据

计划 B4 表「已过时测试合同」一行要求：对照当前 AGENTS/业务接口/变更文档给出**精确冲突**、保留原断言，
「A列的两例可迁移，**其他例提交补丁审阅，不能自行放宽**」。本补丁即该审阅的结果，业主于本轮明确批准。
另一条通用规则同样适用：断言文字过时不允许回退正确业务规则。

## 2. 冲突一：`scripts/check_assistant_r3t3.py`

**节点**：`check_assistant_r3t3.StreamRepairs.test_protocol_error_retains_safe_fixed_code`

| 项 | 内容 |
|---|---|
| 原断言 | `self.assertIn('tool finish mismatch', caught.exception.detail)` |
| 实际 | `'回复未完整通过校验，请核对已有卡片。'` |
| 当前依据 | `app/assistant_runtime_provider.py:219` 仍抛 `ValueError('tool finish mismatch')`；`:285-286` 把它包装为 `ModelProtocolError`（内部 `HTTPException(503)`），**内部码不外泄给员工**，与既定方向（内部状态机标识一律改固定中文）一致 |
| 保留的意图 | 断言后半句「不得回显员工原文」**依然强制**；本次改为更强：既断言固定中文，又断言内部码**不得**出现 |

判定：**过时测试合同**（产品行为是刻意变更，不是回归）。

## 3. 冲突二：`tests/test_business_assistant.py`

**节点**：`tests/test_business_assistant.py::test_batch_confirm_reports_one_bad_card_without_blocking_the_rest`

| 项 | 内容 |
|---|---|
| 原断言 | 三张卡中第二张摘要错误时，第一与第三张均为 `succeeded` |
| 实际 | `['succeeded','skipped']`（第三张 `skipped`） |
| 当前依据 | 计划登记的 `PATCH-M8-1-BATCH-01`：**首个失败或不确定结果后停止**，后续 `skipped` 仅为本次批量结果；仓库 `tests/assistant_offline/tests/test_batch_confirmation.py::test_bad_second_digest_pauses_third_without_rolling_back_first` 断言的正是 `['succeeded','refused','skipped']` |
| 归档内部矛盾 | **同一份归档文件**里 `test_batch_confirm_refuses_absurd_or_repeated_selections` 的重复报名断言是**通过**的，与现行「逐张独立校验、首项失败即停」一致；该文件因此自相矛盾，只有这一处是旧口径 |
| 保留的意图 | 「被拒绝的卡绝不到达原业务 API」（`len(calls)==2`）**原文保留**；本次把该断言的说明改为同时覆盖被跳过的卡，并保留第一张独立提交、不回滚、不重放的语义 |

判定：**归档内部自相矛盾的过时合同**。用例名保留不动，以免下游引用失效。

## 4. 实际改动

```
V/tests/baseline/overlay/scripts/check_assistant_r3t3.py   sha256 4a02024a786dd91275c88cc20e3bf378feb1ddd24b301eb99995f39be4ec4a86 (17698 bytes)
V/tests/baseline/overlay/tests/test_business_assistant.py  sha256 bf47b040f869244a821c72fbafbf9a3dedb43b3e53637fafc8966bedd56bfaa9 (58591 bytes)
```

`archive/baseline-restoration.json` 的 `adaptations` 与 `overlay_additions` 已同步新哈希、字节数与补丁号
（`test_business_assistant.py` 的 `patch` 记为 `PATCH-CP-00B-08 PATCH-CP-00B-09`，并保留
`previous_overlay_sha256` 便于追溯）。改动前已备份 `baseline-restoration.json.bak-20260930-pre-cp00b09`
与 `validation-manifest.json.bak-20260930-pre-cp00b09`。

## 5. 例外路径（不得据此放宽的部分）

- 本次**只**处理这两条明确冲突；归档其余失败若出现，仍按 B4 表逐条归因，不得顺手改断言。
- 符号链接 skip（`tests/test_private_files.py::test_symlink_file_and_root_rejected`）属**环境缺口**，
  不因本补丁改变，仍如实记为 skipped。
- 本补丁不放宽任何原业务守卫，也不构成 M8.2 通过：M8.2 仍需在冻结源码上取得有效基线并完成逐项比较。
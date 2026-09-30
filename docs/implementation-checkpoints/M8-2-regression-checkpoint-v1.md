# M8.2 归档基线复跑与归因检查点 v1

2026-09-30；开发候选。**M8.2 保持 `todo`。** 本记录如实登记归档基线（M0.2.B）在本源码上的结果、
三处失败的精确归因、以及一处**必须由业主裁决的测试合同冲突**；不把未通过写成通过。

## 1. 为什么跑 M0.2.B

M8.2 要求「重新执行 M0.2 全部仍适用测试」。归档基线由 V 侧
`run_validation.py --repo E:\HuaKangOS --milestone M0.2 --phase B` 执行：41 条命令、319 个归档文件、
`tests/baseline/applicability.json` 登记的 5 个已废止子系统文件不适用，其余全部适用。

M0.2.B 有**严格参照**门禁：它要求同仓库存在一次通过的 M0.1 全量运行。历史通过运行都在 `f735de2`
（main），与当前特性分支不同指纹。本轮先在当前源码上建立参照：

- `--milestone M0.1` → **passed**，run `20260930T024144Z-e24c65f6db`，`phase_complete=true`；
- 随后 `--milestone M0.2 --phase B` → run `20260930T024201Z-44314a41f0`。

## 2. 本轮结果（**无效证据，须重跑**）

| 项 | 值 |
|---|---|
| 命令 | 41 条全部实际执行 |
| 归档聚合 | **3334 passed / 2 failed / 1 skipped** |
| `inventory_complete` / `coverage_complete` | true / true |
| `status` | failed |
| `incomplete_reasons` | `commands_not_complete`、`inputs_changed`、`baseline_not_successful` |
| `source_unchanged` | **false** |
| `mirror_unchanged` / `overlay_unchanged` / `harness_unchanged` | true / true / true |

**`source_unchanged=false` 的原因是我自己的操作**：运行期间我在工作区提交了验收机制（`test(assistant):
give M8.1 a workspace-local acceptance gate`），而装置在运行前后各做一次源码清单指纹比对。它拍到了
工作树变化，因此**这次运行不构成有效证据**，`3334/2/1` 只能当**指示性**结果，不能写成 M0.2.B 通过。
重跑必须在「运行期间不改动被测源码」的条件下进行。

## 3. 三处失败的精确归因

### 3.1 `b04-check_assistant_r3t3` → 1 failed（**过时测试合同**）

节点：`check_assistant_r3t3.StreamRepairs.test_protocol_error_retains_safe_fixed_code`
（`scripts/check_assistant_r3t3.py:238`，39 项中 1 项失败）

```
self.assertIn('tool finish mismatch', caught.exception.detail)
AssertionError: 'tool finish mismatch' not found in '回复未完整通过校验，请核对已有卡片。'
```

- 内部码仍存在：`app/assistant_runtime_provider.py:219` 抛 `ValueError('tool finish mismatch')`；
- 但 `:285-286` 把它统一包装成 `ModelProtocolError('回复未完整通过校验，请核对已有卡片。')`——即
  **内部错误码不再外泄给员工**，与既定方向（等待原因等内部状态机标识一律改为固定中文）一致；
- 断言的后半句（`assertNotIn('文本', detail)`，即不得回显员工原文）**在当前实现下依然成立**；
- 判定：**过时测试合同**。按计划 B4 表，此类「提交补丁审阅，不能自行放宽」，故本轮**未改动该断言**。

### 3.2 `b05-business-02` → 1 failed（**归档内部自相矛盾的过时合同**）

节点：`tests/test_business_assistant.py::test_batch_confirm_reports_one_bad_card_without_blocking_the_rest`
（161 项中 1 项失败）

```
assert ['succeeded','skipped'] == ['succeeded','succeeded']
```

- 该用例断言「第二张坏卡不得阻塞其余」；
- 但**同一份归档文件**里 `test_batch_confirm_refuses_absurd_or_repeated_selections` 的重复报名断言
  **通过**，即批量确实是「逐张独立校验、首个失败即停」；
- 计划把 `PATCH-M8-1-BATCH-01` 登记的现行标准写为：**首个失败或不确定结果后停止，后续 `skipped`
  仅为本次批量结果**；仓库内 `tests/assistant_offline/tests/test_batch_confirmation.py`
  （`test_bad_second_digest_pauses_third_without_rolling_back_first`）断言的正是
  `['succeeded','refused','skipped']`；
- 判定：**过时测试合同，且与已批准补丁直接冲突**。此类同样「提交补丁审阅，不能自行放宽」，故本轮
  **未改动该断言**。

### 3.3 `b05-business-11` → 1 skipped（**已知环境缺口，非产品缺陷**）

节点：`tests/test_private_files.py::test_symlink_file_and_root_rejected`（105 项中 104 passed、1 skipped）

符号链接权限在 Windows 宿主上的已知缺口，与 `CP-00B-v6` 记录的「唯一 skip 仍是符号链接环境缺口」一致。

## 4. 需要业主裁决的一件事

上述 3.1 与 3.2 都落在计划 B4 表的「已过时测试合同」一行：

> 对照当前AGENTS/业务接口/变更文档给出精确冲突，保留原断言；**A列的两例可迁移，其他例提交补丁审阅，
> 不能自行放宽**

我已给出精确冲突（文件、行号、期望值、实际值、当前正确行为的依据）。**两份归档断言的迁移属计划保留
给业主的裁决**，我未自行修改。可选处置：

1. **批准迁移这两处归档断言**（登记为新补丁 `PATCH-CP-00B-09`，写明精确冲突、当前依据、受影响命令与
   指纹），随后重跑 M0.2.B 取得有效证据；
2. **不迁移**，则 M0.2.B 在本源码上保持 2 failed，M8.2 按计划「不接受未关闭备案」，只能如实记为
   未完成并说明原因；
3. 其他业主指定的口径。

## 5. M8.2 其余完成检查的当前状态

| 完成检查 | 状态 | 证据 |
|---|---|---|
| 基线及新增用例逐项比较，新增/缺失/不适用均有理由 | **未完成** | 需在有效基线上做逐 nodeid 比较（本轮的 per_node 报告在无效运行里，仅可参考） |
| 193 映射与 111 工作流检查通过，原菜单及原名搜索仍可用 | **满足（可复核）** | `tests/assistant_offline/check_m82_contracts.py`：生成物 `--check` 通过、193 项/10 模块、111 工作流、双向映射、生成物与源指纹一致；原名搜索与模块导航由前端 Node 套件（`assistant_render`/`assistant_plan_ui`/`runtime_client`）覆盖 |
| SQLite 当前适用原业务/助手/前端自动回归全部通过 | **满足** | 工作区内同一条命令 **293 项**（后端 224＋前端 55＋页面 14）全绿，两次运行逐套件计数与双指纹一致，`acceptance-M8.2.json` 为 `accepted=true` |
| 旧接口返回合同保留，相同 request_id 不产生第二 Run | **满足** | `test_runtime_integration::test_http_acceptance_and_request_idempotency`、`::test_reused_request_with_changed_content_is_rejected`；归档组 `b04-*` 亦覆盖旧消息/流式/确认 |

## 6. 明确不声称

- 本轮**不**把 M8.2 记为 `done`：归档基线在本源码上仍有 2 项未决合同冲突，且本轮基线运行因源码在
  运行中被改动而无效，须在冻结源码后重跑。
- 归档 3334 项只是**指示性**结果，不计入 M8.2 通过证据。
- 真实模型、PostgreSQL、独立 Windows/Linux 恢复演练与员工试用均未执行。
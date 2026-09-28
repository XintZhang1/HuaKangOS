# PATCH-CP-00B-06：M0.2 基线夹具的 R4 追加列排除（外部测试合同适配）

2026-09-28，集中测试阶段。第一次在合并 `origin/main` 后的候选源码上复跑 M0.2 基线时，
`tests/test_business_assistant_migration.py::test_nonempty_e13r_to_f24s_and_independent_restore_preserve_business_and_assistant_rows`
失败。本补丁记录实测差异、归属判断、精确适配范围与证据指纹；不改产品代码、不改业务断言。

## 1. 实际观测

- 运行：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/runs/20260928T053713Z-aa13ac82c5`
  （`--milestone M0.2 --phase A`），退出码 1，`a3-anonymous-memory-migration` 170 项中 169 passed / 1 failed。
- 失败点：`test_business_assistant_migration.py:64`（表结构对比断言）。
- 定位手段：在外部 overlay 副本内临时打印两侧 `PRAGMA table_info` / `foreign_key_list` / `index_list`
  （`runs/20260928T054156Z-08f55c47d2`），差异只有一处来源——`business_assistant_proposals`：
  - 列：当前 ORM 多一列 `source_work_item_id VARCHAR(36) NULL`；
  - 外键：当前 ORM 多一条 `source_work_item_id -> business_assistant_work_items.id`；
  - 索引：当前 ORM 多一个 `UNIQUE(source_work_item_id)`（SQLite 自动索引）。
  `business_assistant_sessions`、`business_assistant_messages`、`business_assistant_issues`
  三张表的列、外键、索引在两侧完全一致。
- 该列由 R4 的 `h53k_assistant_runtime`（计划 M1.4 明确追加）加入，晚于夹具冻结的
  `f24s_business_assistant`；`source_work_item_id` 是 Runtime 卡片与 WorkItem 的真实绑定
  （`AssistantProposal.source_work_item_id`，M2.4/M5.x 依赖），不是可删的冗余列。

## 2. 归属判断

不属于产品缺陷：迁移链本身自洽（h53k 建列、建唯一约束、建外键），升级后数据与完整性断言
（事实快照、流水/附件保留、计数为 0、`validate_sqlite` integrity）全部继续通过。

属于**过时测试合同**：该断言原本就用"把更晚迁移新增的列排除在 f24s 冻结形状对比之外"的方式
处理 `g35t`（`thinking`）与 `h49g`（`request_id` 等）；R4 的 `h52j/h53k` 是同一类更晚迁移，
合同需要按同一口径扩展。若改成"升级到当前 head 再比对"，会取消这个夹具的冻结语义；
若删除断言，则失去 ORM 漂移探测能力，两者都属降低标准，均未采用。

## 3. 精确适配范围（外部验证根 V，不在仓库）

文件：`V/tests/baseline/overlay/tests/test_business_assistant_migration.py`
（原件保留在 `V/archive/baseline-original/tests/test_business_assistant_migration.py`，
原始 sha256 `90171a4735f8f6f5ee386d98921590f769343cbe7dc51a167bdf0f8319872d0f` 未变；
适配差异另存 `V/tests/baseline/test_business_assistant_migration.py.r4.diff`）。

1. 新增 `LATER_COLUMNS`：`messages:{thinking}`、`proposals:{request_id,step_order,step_label,questions,source_work_item_id}`。
2. 三处比较改为按"更晚迁移新增列"排除：列、外键（按本地列名）、索引（按索引覆盖的列）。
   排除集合之外的所有结构差异仍然必须让断言失败。
3. 业务事实断言（升级保真、流水/附件、外键一致性、备份恢复逐表比对、状态与 digest 校验）
   一条未改、一条未删。

## 4. 复验证据

| 运行 | 内容 | 结果 |
|---|---|---|
| `20260928T053332Z-71aaadb59a` | M0.1 严格自检（合并 main 后） | passed |
| `20260928T053713Z-aa13ac82c5` | M0.2 A（合并 main 后，未适配） | failed：1 项（本补丁目标） |
| `20260928T054156Z-08f55c47d2` | M0.2 A（定位用插桩运行） | failed：同上，差异已打印 |
| `20260928T054432Z-08720019f3` | M0.1 严格自检（适配后） | passed |
| `20260928T054444Z-e30209a495` | M0.2 A（适配后） | **passed**：43 + 39 + 170 全通过 |

源码指纹 `7992141f09f9df57fabf8515aa3c9cd253fda5e559e305bb17e08a02f6f7a4f9`
（`E:\HuakangOSFeature`，feature 分支 `feature/assistant-agent-runtime`，含 origin/main 合并）。
本补丁只改外部测试副本，不改该指纹。

## 5. 边界

- 未触碰公司库、原预览库、真实附件或凭据；未调用真实模型；未改 OS 权限。
- M0.2.B 完整基线仍需在冻结源码上单独执行；本补丁不代替 B 阶段结论。
- 原 `test_symlink_file_and_root_rejected` 待真实符号链接环境执行的条件不变。

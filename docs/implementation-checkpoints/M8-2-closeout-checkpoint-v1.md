# M8.2 收口检查点 v1（归档基线有效复跑 + 逐项比较）

2026-09-30；开发候选。**M8.2 由 `todo` 转为 `implemented`**（原验收条件在工作区内全部取得证据；生产代码
未改）。不部署、不默认开启四个功能开关、不调用真实模型。

## 1. 有效基线的取得

| 项 | 值 |
|---|---|
| 被测提交 | `7211e7f7b0db66cbbc38e69fd758abff4119f1fb`，`working_tree=''`（干净） |
| M0.1 严格参照 | run `20260930T054849Z-22e4515c0e`，**passed** |
| 归档基线 M0.2.B | run **`20260930T054921Z-0db7d7fedb`** |
| 命令 | 41 条全部实际执行 |
| 归档聚合 | **3336 passed / 0 failed / 1 skipped** |
| `inventory_complete` / `coverage_complete` | **true / true** |
| `missing` / `extra` / `duplicate` | **0 / 0 / 0** |
| `per_node` | 3337 行，status 仅 `passed(3336)` 与 `skipped(1)` |
| `source_unchanged` | **true** |
| `mirror_unchanged` / `overlay_unchanged` / `harness_unchanged` | true / true / true |
| `inputs_unchanged` / `external_inputs_unchanged` | **true / true** |
| `dependency_lock_matches` / `required_dependencies_match` | true / true |
| `status` | failed（`commands_not_complete`、`baseline_not_successful`）——**由唯一的 skip 引起** |

与上一轮的区别：上一轮 `source_unchanged=false`（我在运行中提交了代码）因而无效；本轮全程未改动工作区，
六项未变指纹全为 true，故 `3336/0/1` 是**有效证据**。

## 2. 唯一未完整项：符号链接环境缺口（非缺陷）

节点 `tests/test_private_files.py::test_symlink_file_and_root_rejected`（`b05-business-11`，105 项中
104 passed、1 skipped）。用例自身在宿主不允许创建符号链接时**显式跳过**：

```python
try: path.symlink_to(outside)
except OSError: pytest.skip('This Windows host does not permit symlink creation')
```

计划明文禁止为测试改 Windows 开发者模式或用户权限，故该节点在本宿主**不可执行**，如实记为 skipped，
不计通过、也不冒充通过。同一文件里的 Windows junction 用例（`test_windows_junction_directory_is_rejected`）
**已实际执行并通过**。`baseline_summary.counts` 因此为 `{"passed": 3336, "skipped": 1}`，装置据 skip
判 `baseline_not_successful`，本记录不修改该判定。

## 3. PATCH-CP-00B-09：两处归档断言对齐（业主已批准）

第一版修正**被真实运行否证**（run `20260930T051732Z-08ff2ec07e`），两处都改错了，如实登记：

| 处 | 第一版错在哪 | 实测事实 | 最终写法 |
|---|---|---|---|
| `scripts/check_assistant_r3t3.py` | 断言 `s.ModelProtocolError` | `app.business_assistant_service` **没有**该属性（异常类在 `app.assistant_runtime_provider`，未被 service 再导出） | 从 `app.assistant_runtime_provider` 导入该类；断言 `status_code==503`、`detail` 含固定中文、**不含**内部码 `tool finish mismatch`、**不含**员工原文 |
| `tests/test_business_assistant.py` | 断言 `len(calls)==2` | 实测 `len(calls)==1`（只有第一张真正到达原 API） | `len(calls)==1`，说明文字改为「只有第一张可到达原 API；被拒绝与被跳过的都不得到达」 |

第二版在 run `20260930T054921Z-0db7d7fedb` 中**两处均 `exit 0`**。最终 overlay 哈希：
`check_assistant_r3t3.py` = `600456dd46940ca4275db592352a380efd5d0bd3f4fa27a597cfd801a416e3de`（17767 字节）；
`test_business_assistant.py` = `cd4ed802d26a2d8ec74949a7008304ae2b552eb6962aee3de9f9d4582268c32a`（58610 字节）。
补丁原文与例外路径见 `docs/implementation-patches/PATCH-CP-00B-09.md`。

## 4. 逐项比较（M8.2 完成检查第 1 条）

`tests/assistant_offline/check_m82_closeout.py` 从**归档聚合报告**与 manifest 声明清单计算，不跑测试：

| 比较项 | 结果 |
|---|---|
| 声明模块（可适用原模块 162 ＋ 新增模块 13 ＋ 本阶段已登记脚本命令 18） | **193** |
| 声明但未执行 | **0** |
| 执行但未声明 | **0** |
| 实跑节点 | 3337（含 1 skipped） |
| 已登记不适用（5 个已废止维护子系统文件，依据 `AGENTS.md:46`） | 保留原文件与哈希，`original_preserved=true` |
| 有限延期（`scripts/check_assistant_workboard_browser.py`，owner `M8.4`） | 保留，理由为浏览器验收不属离线基线 |
| 工作区后端套件 | 20 个，**全部**已登记进 `acceptance_milestones.json` 的判据（未登记即判失败） |
| 探针文件 | 11 个，明确不参与套件发现 |

结论：**新增/缺失/不适用三类均有理由**，无未解释的缺口。

## 5. 其余三条完成检查

| 完成检查 | 状态 | 证据 |
|---|---|---|
| 193 映射与 111 工作流检查通过，原菜单及原名搜索仍可用 | **满足** | `check_m82_contracts.py`：生成物 `--check` 通过、193 项/10 模块、111 工作流、双向映射一致、生成物 `source_sha256` 与源相同；原名搜索与模块导航由前端 Node 套件与归档 `b03-node-*` 组覆盖 |
| SQLite 当前适用原业务/助手/前端自动回归全部通过 | **满足** | 工作区同一条命令 **293 项**（后端 224＋前端 55＋页面 14）全绿，两次运行逐套件计数与双指纹一致，`acceptance-M8.1.json`/`acceptance-M8.2.json` 均 `accepted=true` |
| 旧接口返回合同保留，相同 `request_id` 不产生第二 Run | **满足** | `test_runtime_integration::test_http_acceptance_and_request_idempotency`、`::test_reused_request_with_changed_content_is_rejected`；归档 `b04-*` 组亦覆盖旧消息/流式/确认 |

## 6. 明确不声称

- 归档 `3336/0/1` 是**离线**结果：不构成真实模型、PostgreSQL、独立 Linux、员工试用或生产验收。
- `baseline_summary.limitations` 原文保留：目录检查只是帮助查找覆盖、离线基线不证明真实模型表现。
- 唯一 skip 未经任何权限变通消除；M8.2 不因本记录而免于该环境缺口的如实登记。
- 未执行 M8.3（独立 PostgreSQL、h52j 合成旧库升级、联合备份恢复）与 M8.4 的遗留项。
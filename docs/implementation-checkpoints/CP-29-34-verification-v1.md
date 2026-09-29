# CP-29—CP-34 里程碑复验与执行器重绑检查点 v1

2026-09-29；开发候选。M8.1 仍为 `in_progress`；不部署、不默认开启四个功能开关、不调用真实模型。

## 1. 为什么先做这一步

计划正文里 M7.9.2—M7.12.3 已经逐项登记为 `implemented（2026-09-28 实现并完成外部实测）`，
但检查点表里 CP-29—CP-34 仍写着 `not_ready / —`，两者不一致。本轮先把这批里程碑在当前源码上
重新实测，确认结论仍然成立，再据实登记，避免用过期指纹的成绩冒充当前状态。

同时发现统一验证执行器绑定的是**已不存在的仓库路径** `E:\HuakangOSFeature`，`binding.json`
指向同一死路径，而 manifest 也是同一个值。也就是说本轮之前，任何
`run_validation.py --milestone Mx.y` 调用都无法验证当前 \(`E:\HuaKangOS`\) 源码。

## 2. 执行器重绑（先决条件）

- 原 `binding.json` 为 `{"schema":1,"repository":"E:\\HuakangOSFeature"}`；`E:\HuakangOSFeature`
  在当前主机上不存在。最早一版备份 `binding.json.bak-20260928` 指向
  `C:\Users\tiefu\.codex\worktrees\edb5\HuaKangOS`（该 worktree 仍存在，但停在旧提交 `f735de2`）。
- 重绑前保留 `binding.json.bak-20260929-edb5`、`validation-manifest.json.bak-20260929-edb5`、
  `archive/baseline-restoration.json.bak-20260929-contract`。
- 首次替换把 `E:\HuaKangOS` 直接写进 JSON 字符串，反斜杠成为非法转义，manifest 解析失败
  （`Invalid \escape`）。已从备份回滚，改用 `json.dumps` 生成合法转义后重写；两个文件均以
  Python `json.load` 复核通过。
- 重绑后 `manifest.repository == binding.repository == 'E:\HuaKangOS'`，64 个已登记里程碑可运行。

## 3. 两处测试合同与真实原接口不一致（已复现）

首轮 18 个里程碑中 16 个 passed，2 个 failed。两者都不是生产源码缺陷，而是**外部合同夹具写了
原业务不可能出现的形状**；但排查过程中发现了一个真实生产缺陷（见第 4 节）。

| 里程碑 | 现象 | 判定 |
|---|---|---|
| M7.10.6 dossier_grant | 夹具缺少原详情始终下发的 `source_side` 标记，被当成接收店处理，两条决定事实返回未知 | 夹具对齐真实形状 |
| M7.12.3 service_order | 提交缺 `case_id`/`line_key`、顶层缺 `results`、`outcome` 用了原约束不允许的 `pending`，且“两次提交”断言与夹具自相矛盾 | 夹具对齐真实形状 |

**合同修改内容（原件保留为 `.bak-20260929-pre-fact-linkage`）**：

- `tests/runtime_domains/test_dossier_grant.py`：发起店夹具补 `'source_side': True`，与原
  `dossier_grant_service._detail` 只在发起店下发 `decisions` 的合同一致。
- `tests/runtime_domains/test_service_order.py`：
  1. `submissions` 逐条补真实列 `case_id` / `quote_id` / `line_key`（原 `_serialize` 会带出这些列）；
  2. 顶层补真实 `results` 集合，覆盖提交的用例同时显式给出 `results=`；
  3. `'outcome': 'pending'` 改为 `'rejected'`——原 `ck_service_external_outcome` 只允许
     `approved/rejected/need_documents`，`pending` 在原业务中不存在；
  4. “旧提交的 approved 不能当当前结果”改为**同一 `line_key` 存在更新提交**（1001 已批准、
     1003 为最新且无结果），否则该断言在原合同下不可能成立；
  5. 结果指向不属于本单的提交，断言改为“提交关联不完整”的未知，而不是“不一致”；
  6. 顶层 `results` 为空列表时，正确结论是“最新提交尚无批准结果”（False），不是未知。

`archive/baseline-restoration.json` 的两条 `overlay_additions` 逐次同步了新 sha256 与字节数；
执行器对这些文件的哈希校验因此通过，且原件与历次差异均可从备份追溯。

## 4. 排查中发现的真实生产缺陷（已修复）

`app/assistant_runtime_domains/service_order.py` 的 `service.external_approved` 判定要求每个
外部结果自带 `case_id`。但原模型 `ServiceExternalResult` **没有** `case_id` 列（只有
`submission_id`，且该列 `unique=True`），`_serialize` 因此永远不带出该键。结论：该事实在真实
数据上**永远不可能为 True**，依赖它的后续条件无法成立。

修复：删除结果上的 `case_id` 要求。结果归属本单由“提交必须属于本单（`case_id == 本单 id`）且
属于当前项目（`line_key` 在当前 `lines` 中）”的 `by_id` 收口，原接口已保证
`ServiceExternalResult.submission_id` 指向本单提交；重复提交关联、重复结果编号、结论缺失仍
一律返回未知。未放宽任何原有防止串单的判定。

## 5. 实测结果

命令：`& $VPython "$V/run_validation.py" --repo "E:\HuaKangOS" --milestone Mx.y"`

| 里程碑 | 状态 | 里程碑 | 状态 |
|---|---|---|---|
| M7.9.2 | passed | M7.10.6 | passed |
| M7.9.3 | passed | M7.11.1 | passed |
| M7.9.4 | passed | M7.11.2 | passed |
| M7.9.5 | passed | M7.11.3 | passed |
| M7.9.6 | passed | M7.11.4 | passed |
| M7.10.1 | passed | M7.12.1 | passed |
| M7.10.2 | passed | M7.12.2 | passed |
| M7.10.3 | passed | M7.12.3 | passed |
| M7.10.4 | passed | | |
| M7.10.5 | passed | | |

**18/18 passed，同一源码指纹 `5e6fce5edcd510c9fcf8a2ab297b264e518c220085503362d7a132e411f24443`**，
全部 `phase_complete=true`、`incomplete_reasons=[]`。首次失败与中间各次失败 run 全部保留在
`V/runs/`，未覆盖。

## 6. 本记录**不**声称的事项

- 这只是把已完成实现的里程碑在当前源码上重新实测并如实登记，**不是**新的业务验收。
- 里程碑状态仍按计划原登记为 `implemented`；`done` 仍需原全部验收条件，本轮不改变它。
- 未执行 PostgreSQL、真实模型、独立 Windows/Linux 恢复演练、指定 MCP 客户端与员工试用。
- 未因本次合同对齐而放宽任何断言；被修改的六处都是夹具与原接口形状不符，另有第 4 节一处
  真实生产缺陷被独立修复并由离线套件覆盖。

## 7. 下一执行点

M7 章节收口后按计划进入 M8.1 剩余清单（会话级撤权、旧租约晚写、确认前原业务写入计数、批量
部分失败即暂停、延迟注入），随后 M8.2；M8.3 起的外部条件项按实际具备程度执行并如实登记。

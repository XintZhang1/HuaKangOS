# M8.1 收口检查点 v1（工作区验收门禁 + 稳定性复跑）

2026-09-30；开发候选。**M8.1 由 `in_progress` 转为 `implemented`**（实现与工作区内实测完成，
集中测试阶段的归档基线另见 §6）。不部署、不默认开启四个功能开关、不调用真实模型。

## 1. 本记录回答的问题

`implementation_plan.md` 给 M8.1 写的命令是 `& $VPython "$V/run_validation.py" --repo "$RepoRoot"
--milestone M8.1`。本轮把「仓库新增套件能不能挂到那条命令下」查到底，结论是**不能**，原因在隔离器
本身，不是配置疏漏：

- `harness/isolation.py` 的 `DENIED` 集合**显式包含 `tests`**，因此 `source_inventory()`（由
  `git ls-files` 驱动）**从不把仓库测试文件放进冻结副本**；
- `harness/baseline.py` 的 `overlay()` 对已存在文件直接 `GuardError('test_overlay_cannot_replace_
  current_source')`，所以 overlay 只能**补**不在镜像里的文件——这正是 overlay 机制存在的原因；
- 于是要让仓库套件在 `--milestone` 下运行，只有两条路：把套件**复制一份**进 `V/tests/baseline/
  overlay`（套件双份、日后必然漂移），或在 V 侧写适配器把活套件同步进冻结副本（需改 manifest 与
  `overlay_additions`，并绕开 `source_not_current_run` 校验）。

按业主要求「就在工作区里用同一个测试文件夹做测试，不用非要分离」，本轮**不碰 V 侧**，改为把工作区内
那条命令做成**自洽的验收门禁**：一次执行产出证据，一条判定出具结论。计划命令字符串的偏离已在
`implementation_plan.md` 的 M8.1 记录中如实登记。

## 2. 门禁的两个部件（都在 `tests/assistant_offline/`）

| 部件 | 作用 |
|---|---|
| `run_browser_pipeline.py` | 产出证据：预检 → 全新外部目录 → 按指定传输执行 → 核对证据（退出码 0/2/3/4） |
| `run_acceptance.py` + `acceptance_milestones.json` | 出具判定：只复核证据、不跑测试、不联网，按里程碑登记断言给出 `accepted` |

判定规则（全部来自配置文件，任一不符即 `accepted=false`）：运行必须 `complete=true`、`scope` 与登记
一致、传输模式与登记一致、总用例数不低于登记下限、**每个登记套件的用例数不低于登记值**、真实模型调用
为 0、页面错误为 0、必须有浏览器证据。判定写入 `<证据目录>/acceptance-<里程碑>.json`。

**判别性已实测**：把 `web/workflow-guides.json` 的源指纹改成占位值后，
`check_m82_contracts.py --skip-generator` 报 `accepted=false` 与
「生成物与构建源不一致」；还原后通过，工作区保持干净（`git status` 无输出）。

## 3. 稳定性复跑（同一源码、两次完整运行）

| 运行 | 用例总数 | 套件数 | 传输 | `complete` | 页面 | 页面错误 | 结论 |
|---|---:|---:|---|---|---:|---:|---|
| `browser-fixture-20260930T021140Z` | 293 | 22 | fixture | true | 14 | 0 | `accepted=true` |
| `browser-fixture-20260930T023020Z` | 293 | 22 | fixture | true | 14 | 0 | `accepted=true` |

**逐套件计数两次完全一致**；源码指纹两次均为 `a7c0cd8f…`，套件指纹两次均为 `9a026c9f…`。
另有第 2 次尝试因工具调用被中断而**未完成**（`complete=false`、计数为空），该不完整运行**未**计入
稳定性证据，已重跑替代。

`native` 与 Linux CI 的独立复跑见 `M8-1-remaining-items-checkpoint-v1.md` §8.2（同源码、293 项、
`verified=true`、`browser_source=playwright-bundled`）。

## 4. M8.1 完成检查逐条判定

| 完成检查 | 判定 | 证据 |
|---|---|---|
| 确认前原业务写入 0，资金/库存等重复事实 0 | **满足** | `test_prepare_zero_write.py`（全库逐表摘要不变）＋`test_runtime_integration` 既有零写入用例 |
| 每个稳定 WorkItem 最多一个对应有效准备版本；批量无遗漏 | **部分满足** | 冻结点唯一约束与重复点击语义见 `m81-freeze-confirmation-db`（19 项）与 `test_runtime_integration::test_employee_confirm_is_idempotent`；「完整批量行逐行不遗漏」的专门断言仍依赖 M0.2 归档组（§6） |
| 旧租约不能覆盖新状态；无授权/撤权不能继续或泄露结果 | **满足** | `test_lease_transition_db.py`（5 项，含真实队列动词）＋`test_revocation_session.py`（5 项）＋`test_access_signals_emit.py`（4 项）＋外部 11+19 项 |
| 「业务成功、通知失败」仍呈现真实业务成功；未知写入绝不重放 | **满足** | `test_batch_confirmation.py`（响应丢失记 `uncertain` 且不重放）＋既有回执用例 |
| 故障重复执行能稳定得到同一断言结果 | **满足** | §3 两次完整运行逐套件计数与双指纹一致 |

## 4.1 证据与运行的落点（2026-09-30 调整）

按业主要求，套件、运行记录与证据统一放在工作区 	ests/assistant_offline/evidence/，
不再散落在仓库之外；evidence/ 由 .gitignore 排除。**唯一留在仓库外的是合成运行时**
（合成库、随机密码、合成助手配置，默认 HuaKangOS-validation/runtime/<运行名>/），因为应用自身的
usiness_assistant_service.load_config 拒绝读取位于本仓库内的助手配置，装置也拒绝把运行时放进源码树。

## 5. 本批实际改动文件

生产代码：**无**。新增 `tests/assistant_offline/run_acceptance.py`、
`tests/assistant_offline/acceptance_milestones.json`、
`tests/assistant_offline/check_m82_contracts.py`；`run_browser_pipeline.py` 的默认证据目录改为
仓库旁的 `HuaKangOS-validation/`（隔离器不允许输出落在被测源码树内，故不能放在仓库里），并支持
`HUAKANGOS_EVIDENCE_ROOT`；`README.md` 记录门禁用法与判定规则；CI 增加工作流生成物一致性步骤。

## 6. 归档基线（M0.2.B）与 M8.2 的关系

`M8.2` 要求「重新执行 M0.2 全部仍适用测试」。该基线由 V 侧 `--milestone M0.2 --phase B` 执行
（41 条命令、归档 overlay 套件、193 项目录检查与 111 条工作流检查）。本轮先在当前源码上建立
**严格参照**（`--milestone M0.1` → `passed`，run `20260930T024144Z-e24c65f6db`），随后执行 M0.2.B；
其失败清单与归因见 `M8-2-regression-checkpoint-v1.md`。该基线的失败**不计入** M8.1 的完成检查。
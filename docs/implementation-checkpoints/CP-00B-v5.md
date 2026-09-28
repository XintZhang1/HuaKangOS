# CP-00B-v5：完整基线结束，剩余符号链接验证条件

结论：**M0.2 为 blocked，CP-00B 保持 changes_requested，不放行 M0.3 或 Runtime**。原 36 个失败已在本轮完整基线逐项通过；唯一剩余是原符号链接安全测试跳过，其关键拒绝断言尚未执行。

验证根为 `V=C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`。E: 历史证据与归档未动，真实模型调用 0，无生产或原预览数据访问。本报告只回填已结束运行的结果，不改变验收标准。

## 实际运行与结果

- strict `20260927T163115Z-f97fd5d948`：18/18，退出 0。
- 第三轮诊断 `20260927T163202Z-1d7da6404c`：55 个 profile 合同及 5 个原子进程测试，共 60/60，退出 0；诊断不构成完整验收，也未复用其通过结果。
- 新完整 B `20260927T163618Z-574f417642`：全部 41 条命令按原顺序实际执行，40 条判定 complete；第十一业务组因 1 项 skipped 不满足通过条件。
- 原 session 63205 自然退出 1，实际工具返回 chunk `bd6016`；退出后查询确认验证 Python 进程为 0，没有重启、提前终止或拼接旧成绩。

| 范围 | 实际结果 |
|---|---|
| pytest | 2781 个唯一节点：2780 passed、1 skipped；0 failed/error/xfail/xpass |
| 其它检查 | 556 passed：目录查询 193、Node 76、unittest 286、工作流生成检查 1 |
| 合计 | **3336 passed、0 failed、1 skipped** |
| 清单完整性 | 无 missing、extra、duplicate、not_run、非终态节点或超时 |

2781 个 pytest 节点等于原 2124 加新增 657；319 份原件保留，13 个新增模块精确登记。目录的 193 项检查仅证明静态帮助查询，不冒充 193 项业务验收。

前完整 B `20260927T140257Z-053b24940f` 的 36 个失败节点，本轮 setup/call/teardown 均 passed。8 项过时合同按 PATCH-05 迁移并保留原件与差异；其余 28 项执行适配问题已关闭。Windows 解释器、只读 URI、浏览器存储初始化和运输节点登记均已在完整运行中验证，不再以局部诊断代替。

## 唯一未满足的条件

节点：`tests/test_private_files.py::test_symlink_file_and_root_rejected`，位于 `b05-business-11`。本轮 setup passed、call skipped、teardown passed。

原测试第 120–121 行创建文件符号链接时进入 OSError/skip 分支，第 122 行的文件链接读取拒绝断言和第 124 行的目录链接根拒绝断言没有执行。本轮报告没有具体 Windows 错误码；此前单独探测的 WinError 1314 不能写成本轮观测。

这是实际符号链接创建条件缺失，不能登记为可延期的产品缺陷，不能改为 passed、不适用或 xfail，也不能用硬链接、目录联接或修改原安全断言替代。之前关于 Windows 开发者模式/符号链接权限的用户选择仍未收到答复；本轮没有修改系统设置。

恢复条件是该 Windows 执行环境能够真实创建文件和目录符号链接，随后通过统一 runner 复验并满足完整基线及 CP 条件。条件未改变前不重复运行相同失败前提的长基线，不启动后续里程碑。

## 指纹、进程与独立审阅

本轮与 strict 的以下五项指纹逐项相同：

| 输入 | SHA-256 |
|---|---|
| 源码 | `e4111599019a443d8babf0be1f633fbc06087d59d6331e677cecc7d254f7eaa9` |
| 执行器 | `e1dca2ca184ed2a48e955cd943eac63bc65501cff21e723cc6c9439b5c780429` |
| 已登记外部输入 | `b47ec10a415bcc59a61f6203ae1cce338d1b8e1bd87649619f64cf18d5a424a2` |
| 依赖锁 | `3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930` |
| 实际安装依赖 | `0c9c6fd3198a051b655f51ee26babe35e42d64dc77b3c0f48bac14ccc9c218a5` |

全部源码/镜像/overlay/执行器/外部输入/manifest/依赖前后标志为 true，依赖前后相同。独立重算 2915 项文件哈希无差异，包括 616 份仓库源码、616 份镜像、31 项执行器输入、659 项外部输入、各 336 份当前及镜像 overlay、319 份原件、manifest 快照和工具链。

证据均位于 `V/review/CP-00B-05/`：

| 证据 | SHA-256 |
|---|---|
| `profile-diagnostic-terminal-review.json` | `baf6d557c4a3aefbeaf5e7ae9ffa8682249ccc0c00eb2fd2f45f84a66bd09a08` |
| `full-B-163618-process-exit.json` | `9e4c443d8c1e3e05331b48cb6961a08b5e4f5fcd7640d0290ddb371727dc029d` |
| `full-B-20260927T163618Z-574f417642-terminal-review.json` | `5506c8bec8b4626fa3a7192bdcaad1ea988587e231b5dda4d3e356ae73df90e1` |
| `full-B-163618-independent-conclusion.json` | `86d576ed1a3fda5d13ba365a9f48a72bfa2bbcc01e159080bc6ac4fb14034879` |

审计脚本退出 0 仅表示证据一致；其 `full_B_acceptance_supported=false`，不能改称完整 B 通过。原运行仍为 `status=failed`、`phase_complete=false`、`milestone_complete=false`。

## 审计后的记录回填

终态审计完成后，仅回填本报告、实施计划当前项/门禁摘要、PATCH-05 验收记录及外部 BASE-001 缺陷记录。BASE-001 按已放行 CP-00A-v3 和本轮原节点三阶段通过改为 resolved，保留旧记录与 resolution 历史；不新增延期豁免。

BASE-001 回填日志和前后副本在 `V/review/CP-00B-05/metadata-fillback-v5/`。缺陷表原 SHA 为 `cbc3e09eda2560400ddd44aa4e0c738d13a7f26ffd2bec714806a59a3edb696c`，回填后为 `08ab2df5423517430d4ddd87208f4de804eafd62b6ae333c6f47f758102cedbc`；原重现信息、旧状态、旧 resolution、旧完整基线说明均保留。

上述回填不重写旧 run、旧报告或冻结哈希，也不声明回填后的整个工作树与本轮快照字节相同。app/web/migrations、测试、执行器和依赖没有因此改动。完整目标仍未完成，下一可执行项仍是解决 M0.2 的符号链接验证条件。

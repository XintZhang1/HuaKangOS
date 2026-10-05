# M8.2 v23 双平台完整回归审阅

2026-10-05。被测提交为 `541a21f16ace85129a7b71e8b110f5c5d9e9c186`，GitHub run [37231094698](https://github.com/XintZhang1/HuaKangOS/actions/runs/37231094698)。本报告只引用本次两个独立环境的完整原件；前次失败、本地符号链接 skip 和单组诊断均保留，不拼接为本轮通过。

外部证据根 `V = C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`。冻结 source-only 胶囊为 asset `610531872`，ZIP SHA `73337ace072740d3bf300c22659c966ce059d5b93e121be259866cd525f35347`，801 个登记输入。原 319 个归档文件、101 条命令、74 个有序数组和已登记平台范围保持。

## 本轮实际结果

| 原平台 | strict / full run | 完整命令 | 真实终态 |
|---|---|---:|---|
| Windows | `20261004T201146Z-f6cdf4b972` / `20261004T201200Z-2e4c1c2fc0` | 101/101，全部 complete | 4248 passed，0 failed，0 skipped |
| Linux | `20261004T201120Z-9a99d21e34` / `20261004T201128Z-25eeb531ff` | 101/101，全部 complete | 4238 passed，10 个原平台不适用 |

strict 分别为 Windows 18、Linux 22 项通过。两平台原 pytest 清单均为 245 文件、3407 节点；Windows 全通过，Linux 为 3397 通过和 10 NA。原 18 套 unittest 的 203 项全部实际执行通过，总 unittest 为 489；Node 158、目录映射 193、发布工作流检查 1 均通过，另记 10 项语法检查。收集次数不计为测试执行，目录映射不计为 193 项业务人工验收。

Linux 10 NA 仅为原 Windows junction 1 项及 PowerShell 启动器 9 项，理由、原文件与 overlay SHA 均逐项核对。原 5 个已废止自动维护、审批和无人部署测试文件继续保留来源 SHA 与不适用理由；可选浏览器脚本单列 M8.4，未冒作本项通过。

Windows 原 business-01 的 153 项、business-11 的 105 项均全通过，包含原迁移异常路径后的后续用例、符号链接和九个 PowerShell 探测。PowerShell 保持原 20 秒限制、命令和断言；九个真实节点的八个阶段均完整，after_commands 为 131—2194 毫秒，pytest 的 current 别名不重复计数。明确加载固定系统模块后的行为已实测通过，旧版本超时具体卡在何条内部调用仍不能从旧日志反推确定。

两平台全部命令 CLI 0，无 timeout；原生命周期记录均 drained=true、cleanup_required=false。原 runner 记录 loopback-only、真实模型调用 0。独审不冒称远端结束后的 OS 进程快照或独立网络抓包。

## 原件与指纹

| 平台 | 官方 artifact / ZIP SHA-256 | 独审报告 SHA-256 |
|---|---|---|
| Windows | `11318158981` / `f7ae4ed788a477df2f5da94c3e75253759fe523f9a595e82c452b12f87340b23` | `8305c6220d7414c9105b2d0f21ac31366ee941204617afcf3cb0d4a883b182e3` |
| Linux | `11316615974` / `71f37d1bd05434975ddaf28c03e552c39574005fdd5984ec156173748fb0370d` | `21b244d88fc2da5833b9758ec01a83e7549a771cd2adb94f86218fda67c30f35` |

Windows 原件在 `V/closeout-20261003/m82-v23-full-windows-37231094698-20261004T234708Z-2358decbd2`，Linux 在 `V/closeout-20261003/m82-v23-linux-20261004T201238Z-ab56ea89d2`；各自 `independent-review.json` 留完整核对过程。官方摘要、ZIP CRC、路径范围及成员均已核。Windows 2062 成员，Linux 2051 成员。

两个原件的 1315 个源码文件逐 Git blob 匹配本次提交，源码映射逐键相同。33 个 harness 与 768 个 external 共 801 输入，除原合同允许的 repository/platform 绑定外与冻结胶囊一致。74 个有序数组、原 203 unittest 的收集与实际执行、3407 pytest union 均核对完整。strict/full 五指纹一致且重算，输入和依赖前后稳定。

| 指纹 | Windows | Linux |
|---|---|---|
| source | `e90ac72d6b0c56404155af4b9044b12554529839cfd0f088aab4789372b541ac` | 同 Windows |
| harness | `63f2a44d2b0fb72f54fefed6eee9afb588d3df57de68589fa1719dc3876b247a` | `830fbba8908be8f94ec344a46e31a172cd9ad647cd7c0656b42fe9dcf04bb870` |
| external inputs | `21388ee73fb777790eebac45b4e732ac00040a294ed192025d97ef5ba001c568` | 同 Windows |
| dependency lock | `3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930` | 同 Windows |
| installed dependencies | `7691ed697a5be82234ae7354411df047378f748c8d46320ee8d72b5c416f1bf9` | `838a854bfb2a520e2dc6025ba1231352479697b8920bda558f5c578eedf161ba` |

远端物理源码镜像与 command-context 文件未附；独审核对的是原报告的完整映射和原 Git blob，不将其写成对远端目录再次实测。

## 原四条完成检查对应

1. **基线及新增逐项比较**：`m82-b00-complete-inventory`、`baseline.json` 的声明及逐节点结果、原 18 套独立 executor 和完整 101 条命令相互对应，missing/extra/duplicate/problems 均空。新增、原不适用和来源变化均有登记。
2. **193/111、原菜单与原名搜索**：当前 capability matrix 原节点、发布生成物逐字节检查、business-21 的全需求双路径/真实截图及负例、原 workspace Node 的十模块/193 搜索/有效工作流 ID 节点全部通过。矩阵仍明确 acceptance unverified、availability unknown、reader unbound，不把静态覆盖改写成业务验收。
3. **当前 SQLite 原业务/助手/前端**：原 21 个 business 组、8 个 runtime/domain 组及 A—F 全部执行；原真实 HTTP 身份、事务、四个 provider、回执、检查点、24 轮恢复与真实 600 秒预算路径，以及原前端和 M6.1—M6.8 Node 全通过。
4. **旧返回合同与 request_id**：`m82-shared-contracts-03` 的 `test_legacy_runs_retry_same_identity_and_changed_body_conflict` 实际核同请求返回同 Run、改内容冲突且图不变、CSRF 拒绝；`test_runtime_enabled_legacy_message_and_stream_share_one_run` 实际核旧消息/流式共用一个 Run、一对消息和一次 provider 请求，断开订阅不取消原 queued Run。原功能关闭路径也在 business-02 保留。

上述证据满足 M8.2 原四条检查；M8.1 已有本轮 done 与原五条完成记录，CP-35 的 M8.1—M8.2 范围因此具备释放依据。正式里程碑与门禁状态以 `implementation_plan.md` 为准。M8.3—M8.10 的 PostgreSQL、原生浏览器/HTTPS/IME、真实模型、独立环境恢复、安全部署条件和交付仍分别验证；员工试用与人工验收保留。

## CI 耗时与执行范围

本轮 Linux job 用时 1 小时 39 分 16 秒，Windows 3 小时 33 分钟；101 命令累计分别为 5895.249 秒、12658.103 秒。两个平台并行，各平台内部按原 101 条命令串行，包含真实 600 秒预算验证。旧原始逐阶段记录显示，每例隔离数据库准备和各组进程启动/导入/收集占有明显累计开销；没有硬件/负载实测，不将差异归因某一种 GitHub 主机原因。

此前同提交的 Windows 定向 CI `37230141852` 实际 105/105 通过，job 4 分 24 秒，只证明该组；本次完整结果来自各自新 full run。长回归为手动入口，普通 push/PR 只按原登记路径触发运维检查。本轮不含 Playwright 或真实模型任务。

本次新增记录是测试结束后的文档变化。以上结果绑定受检提交及五指纹，不声称未来源码改动自动继承通过；既有失败原件与原门槛均保留。

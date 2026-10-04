# M8.2 v22-r2 修复后双平台完整回归

2026-10-05（下述运行时间为 UTC 2026-10-04）。受检提交为 `d79412318adafe2fa4fe139d3c5cb3b27f0c1518`，GitHub run [37214287295](https://github.com/XintZhang1/HuaKangOS/actions/runs/37214287295)。本次重新检查迁移工具异常路径释放修复后的完整源码，不继承旧 bcac118 候选的通过结果。

冻结验证输入仍为 asset `609828442`，ZIP SHA `129115b39864e387a02b3158151b0fb7f82d38cdff7c3141c681a7076c75c382`；801 个输入与前次逐字节一致。源码由本次 Git checkout 提供，repository/platform 按原有限合同独立绑定。Windows 与 Linux 各自执行 strict 和原 101 条完整回归命令；当前 CI 不运行 Playwright 或真实模型。

## Linux 原件审阅完成

job `111471552408` 从 15:47:03 至 17:56:34 自然 success，约 2 小时 10 分钟。strict `20261004T154746Z-623d20ebda` 为 22 passed；full `20261004T154755Z-c77677df58` 的 101 条命令全部执行并 complete，4248 个真实终态为 **4238 passed、10 个已登记 Linux 不适用**。pytest 原有序清单 3407 项，其中 3397 passed、10 NA；unittest 489（含原 18 套 203 项）、Node 158、目录 193、工作流 1 全通过；另有 10 项语法检查。目录映射通过不等于 193 项实际业务验收。

artifact `11311105880`，ZIP SHA `393cf9df693ff53abdfedd4f4eca9e9643c4e7ad4e50b205c5420a59e27c58ad`，3609861 字节、2051 成员、展开 26821480 字节。下载、官方摘要、路径范围、CRC 和成员字节已核；原件在 `V/closeout-20261003/m82-v22-r2-linux-20261004T175953Z-87cbe29688`。独立报告 `independent-review.json` 的 SHA 为 `e997a90bd99def6d0bfa9a69c5d5bd28771aafe5a0d581014787970941e7b23d`。

实际 1313 个源码文件逐 Git blob 匹配 d794123；33 个 harness / 768 个 external 与冻结 801 输入相符，仅原 repository/platform 重绑定。74 个原有序数组、3407 pytest union 和原 203 项 unittest 逐原报告完整核对；strict/full 五指纹相同并重算，前后输入与依赖稳定。

| Linux 指纹 | SHA-256 |
|---|---|
| 源码 | `46bdcd18aedbbc733bc88dc025042bf9c6e4755407da76efa6c4caaec74313a2` |
| harness | `a0fed53b587405ad817f186253a0066a774e5bda45d10afc18e18c4c6d2ec06b` |
| external inputs | `d67ceee33810677d75a09e67d131c90d7a81d366906a985077b3dea3146a0ae5` |
| dependency lock | `3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930` |
| installed dependencies | `838a854bfb2a520e2dc6025ba1231352479697b8920bda558f5c578eedf161ba` |

全部命令 CLI 0、无 timeout，owned lifecycle 均 drained=true、cleanup_required=false；原 runner 记录 loopback-only、真实模型调用 0。没有将未附的远端物理 mirror、command-context 或运行结束后的 OS 进程快照写成独立审阅事实。命令累计 7698.590 秒；最长为原 600 秒预算/取消验证所在组 639.907 秒，后两组分别为 business-17 的 301.276 秒、business-19 的 291.680 秒。

## Windows 与检查点

Windows job `111471552491` 从 15:47:03 至 19:23:11 自然 failure，约 3 小时 36 分钟；回归步骤 19:22:49 结束，artifact 上传于 19:23:03 成功，未触及 300 分钟上限。strict `20261004T154834Z-3882c044a0` 为 18 passed；full `20261004T154849Z-7c0c46250c` 完整执行 101 条命令，**4239 passed、9 call failed**，0 setup/teardown 错误。唯一失败组 business-11 为 96 passed、9 failed，其余 100 条命令 complete。迁移修复后的 business-01 全 153 项和原 18 套 unittest 全 203 项通过，前次 19 个主库占用错误没有出现。

artifact `11312861793` / ZIP SHA `518439c3e76ed8419f739b1311626a290fa1844947498f4abe6b3df38fb072f1`，2047 成员安全解包及 CRC 已核。原件目录为 `V/closeout-20261003/m82-transfer-full-windows-37214287295-20261004T192542Z-18adb94cb7`；独审 SHA `397987cfaf3cef22ba8b78767e06e53eb03ceffd4598cf1cd45459f3fe4e6778`。3407 pytest / 245 文件、74 个有序数组、原 18 collect/execute 的 203 项、旧 286 unittest、Node 158、目录 193、工作流 1 和另记的语法 10 项逐原报告核对。strict/full 五指纹与三文件映射一致，前后输入/依赖不变、真实模型 0、runner 层无超时、进程正常排空。

两平台 1313 个源码映射逐键相同，源码指纹均为 `46bdcd18aedbbc733bc88dc025042bf9c6e4755407da76efa6c4caaec74313a2`。Windows harness 指纹 `dd94562d14f540631ffeb20d95c10e35267d280e9ca78f266036ea3d957d0ce7`，installed dependencies 指纹 `7691ed697a5be82234ae7354411df047378f748c8d46320ee8d72b5c416f1bf9`；external inputs 与 dependency lock 同上表，保留平台之间的真实差异。

九个失败均为原 Windows 预览 PowerShell 探测在 **20 秒**限制内没有完成；stdout 为空，before_source/after_source 均出现，不能解释为 dot-source 未完成。各自真实命令尚未返回 JSON；共同内置模块发现路径只是待验证线索。按 `PATCH-M8-2-WINDOWS-PROBE-01`，先在原 helper 明确加载固定系统内置模块、记录阶段耗时，再通过已有统一入口做原 business-11 整组 CI 定向诊断；保持原 20 秒与全部节点、命令和断言，不改生产启动器。

## 耗时与后续验证

Windows 命令累计从前轮 7618.311 秒增加至 12816.597 秒。逐命令比较原件 `timing-source-comparison.json` SHA `39454f449ebc4233564fc013a82b715da9cde31731305910a65a9092182dc38a`：

| 原命令分组 | v22-r1 秒数（约） | v22-r2 秒数（约） |
|---|---:|---:|
| 主清单收集 | 302 | 646 |
| 原 18 套 unittest 收集 | 368 | 589 |
| 21 个业务组 | 4479 | 7742 |
| 8 个领域/故障组 | 467 | 840 |
| 原 18 套 unittest 执行 | 585 | 1016 |
| 其余 35 条命令 | 1416 | 1983 |

耗时增加分布在多组，其中 21 个业务组约占总增量的 63%；9 次 20 秒超时仅约 180 秒，不能解释全轮新增的约 5198 秒。同期 Linux 命令耗时从 9239.735 降至 7698.590 秒。没有硬件或负载指标，不把这些时间差推定为某一种机器原因、单一生产卡死或新增性能门槛。

M8.2 仍为唯一 in_progress，CP-35 不追加 released。两平台原件已分别完整审阅；当前先处理唯一失败组，再按真实结果决定完整复验。没有启动 PostgreSQL 或后续真实环境验证。

## v23 候选与本地原组结果

候选仅修改外部原 PowerShell helper：明确加载 `$PSHOME` 的 Utility/Management 固定 manifest，核对原 Cmdlet.Source，在 stderr 留八个固定阶段的单调毫秒数。原 commands、九个测试函数及全部原断言、powershell.exe/非交互参数/DEVNULL/20 秒限制和 JSON 返回保持；helper 以外字节相同。候选 SHA `66899db19f96cf4f4662f3a8269e4d48cfa770619c58fde854f6b0436b033131`，独审 SHA `bf56e8d74326141c4af3c15edb412c0ab4b856da99f9943694b2baaadbb18bfb`。根目录为 `V/closeout-20261003/m82-windows-probe-modules-candidate-20261004T193302Z-5683ba2c61`，原 before、精确 diff 和来源记录均保留。

801 输入仅 helper、原 restoration 记录和 manifest 的九个既有 Linux NA overlay SHA 三项变化，798 输入及全部原归档/命令/节点/授权不变。注册独审 SHA `88c88c6a7fa2a598ce037feef17ede0059d51c47696033e611804dd714cdb17f`；新 draft SHA `e1cd8fef64bda7221c64df8c242dc6ef3ddb18ab840b1103a0aea21aa214a169`。新 source-only ZIP 为 asset `610531872` / SHA `73337ace072740d3bf300c22659c966ce059d5b93e121be259866cd525f35347`，3368721 字节、801 源输入，GitHub 官方 digest 相符；仍在原 draft release，未覆盖旧资产或发布正式版本。

现有两个 workflow 只追加固定 Windows diagnostic 模式，必须 Windows-only，先 M0.1 strict，再原 M0.2.B 的 `b05-business-11` 整组；原 prepare/full、双平台全量、并发和超时保持。新增上传只包含该组固定 `probe.stderr.txt`，不扩为整个 fixtures。YAML/参数映射及字节逆向独审 SHA `f3d2b0022ffa11f048c8af040371673a788c120c6ae397bf8fa1942a369fdcce`，不把静态检查写成 Actions 实测。

本地 strict `20261004T194448Z-76dbf2a628`：18 passed。定向 `20261004T194521Z-b908e0a50b`：先完整收集 2781 项，再执行原 business-11 的 105 项，**104 passed、1 skipped**；pytest 退出 0，但原统一入口如实 CLI 1 / diagnostic_failed，phase_complete=false、milestone_complete=false。唯一 skip 为 `test_private_files.py::test_symlink_file_and_root_rejected`，原理由为 `This Windows host does not permit symlink creation`，未更改 OS 或豁免验收。前次九个 PowerShell 节点全部 setup/call/teardown 通过，各 stderr 八阶段完整单调，after_commands 为 90—2168 毫秒；这些实际通过不代替整组通过。

两 run 五指纹、三文件映射及 801 冻结输入相同，源指纹 `ed0c7fc6f3f8e2bee34306e0aaeac47b65b7ff5e065a1d95b4a27b0c81f944c3`，前后输入稳定、无超时、正常排空、模型 0。局部独审 SHA `e86e9c09e6f40ea209980054f6dc271f57fe989d76710d3130bcf89b701c17e7`。下一步在真实 GitHub Windows 对新提交/新胶囊运行相同原组诊断，补其真实符号链接环境及模块阶段证据；本地结果尚不能确认 CI 超时根因，也不释放 M8.2。

完整回归为手动入口；触及原运维 CI 登记路径的 push/PR 执行轻量运维检查，其 10 分钟为超时上限，不是实际耗时。不同候选、不同平台或局部诊断结果不拼接为本次通过；历史失败原件保留。员工试用、人工验收及生产动作仍遵守各自边界。

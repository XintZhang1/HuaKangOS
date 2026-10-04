# PATCH-M8-2-WINDOWS-PROBE-01

2026-10-05，M8.2 唯一进行项。依据业主持续修复及在 GitHub 可运行条件下继续 CI 验证的授权。本补丁不启动 M8.3，不修改生产启动器或业务规则。

## 原始证据

同次 GitHub `37214287295` / main `d79412318adafe2fa4fe139d3c5cb3b27f0c1518`：Linux 完整通过，Windows 自然 failure（15:47:03—19:23:11 UTC），101 条命令全部执行。Windows 原 full `20261004T154849Z-7c0c46250c` 为 4239 passed、9 call failed，0 setup/teardown 错误；唯一失败命令 `m82-b05-business-11` 为 96 passed、9 failed。全部失败来自 `test_preview_runtime.py` 的原 Windows PowerShell 节点：20 秒到期时 stdout 为空，stderr 的 before_source 和 after_source 均已出现，说明 dot-source 已完成。原迁移组 153 项、原 unittest 203 项及其它 100 条命令 complete，先前 19 个数据库占用错误未再发生。

Windows artifact `11312861793` / ZIP SHA `518439c3e76ed8419f739b1311626a290fa1844947498f4abe6b3df38fb072f1`；原件位于 `V/closeout-20261003/m82-transfer-full-windows-37214287295-20261004T192542Z-18adb94cb7`，独审 SHA `397987cfaf3cef22ba8b78767e06e53eb03ceffd4598cf1cd45459f3fe4e6778`。五指纹、原节点与冻结输入一致，原失败保留。报告命令累计 12816.597 秒，collector 645.891 秒、预算/取消组 668.047 秒，多个业务组也较旧轮慢；不能把总耗时都归因于这 9 个超时。

## 诊断判断与精确范围

九个不同决策的共同路径是首次使用 PowerShell 内置 Utility 命令，部分还使用 Management 命令。隔离环境没有继承调用者 PSModulePath，并有独立 profile；当前证据不足以证明模块自动发现就是根因。只在原测试 helper 固定加载当前 `$PSHOME` 下这两个系统内置模块，消除测试对宿主模块发现范围的依赖，同时增加有限阶段观测。此为待真实验证的测试环境候选，不宣称已修复产品。

允许修改：

- `V/tests/baseline/overlay/tests/test_preview_runtime.py` 的 `powershell()` helper。保留 powershell.exe、原非交互参数、DEVNULL、20 秒限制、原 commands 字节与全部业务断言。用 .NET Path 拼接 Utility/Management 两个固定内置 manifest，缺失则真实失败；用原 Import-Module 明确加载并核对 JSON/路径命令来自对应内置模块。stderr 仅增加固定阶段名和 Stopwatch 毫秒数，stdout 仍只承载原 JSON。禁止重试、跳过、改用其它 PowerShell 版本或延长原超时。
- 与该单一 overlay 文件直接关联的外部来源 SHA 登记、原 Linux 九条既有不适用记录的 overlay SHA，以及新的 801 输入冻结清单。原归档文件、节点、有序数组、命令和不适用范围保持；旧胶囊、报告、失败记录不覆盖。
- `.github/workflows/browser-click-checks.yml` 与 `.github/workflows/full-regression-checks.yml`：在原手动入口增设有限的 Windows 预览原组诊断选项，复用 `V/run_validation.py --milestone M0.2 --phase B --diagnostic-command b05-business-11` 和同候选 strict，不新增 runner 或 workflow。原 prepare/full 入口、完整 101 条双平台门槛及取消/并发策略保持；不能让诊断成功冒充完整验收。诊断参数必须在 workflow 内枚举验证，不接受任意 shell/命令。原 artifact 仅额外保留该固定 business-11 夹具下的 `probe.stderr.txt`，使成功节点也有阶段耗时原件；不扩大为上传 fixtures、脚本、数据库、配置或任意文件。
- 本补丁、M8.2 当前执行记录、对应检查点与 architect 当前任务/索引。

不得修改 OS、用户全局模块路径/执行策略、生产 `scripts/preview_launcher.ps1`、原业务守卫或模型授权。所有新运行使用外部独立源码镜像与合成数据。

## 验证与异常处理

先保存 before/candidate 与精确差异，独立审阅 helper 的原 commands/断言及工作流参数映射。经原统一入口本地 strict 和原 business-11 定向检查，再在真实 GitHub Windows 执行同一原组诊断。若仍超时，以最后一个阶段标记定位 Utility、Management 或原命令位置，继续保留失败，不猜改生产或扩大时间。通过后再登记后续完整复验范围；定向结果的 phase_complete/milestone_complete 仍按原 runner 诊断语义保留 false。

M8.2 及 CP-35 在完整当前候选验收前不标 done/released；PostgreSQL、真实 HTTP/HTTPS、模型、员工与生产门槛保持各自边界。

## 实际合入与本地结果

helper 候选 `66899db1…` 已完成字节/AST逆向独审（`bf56e8d7…`），两 workflow 候选完成 YAML、参数/分支和字节逆向独审（`f3d2b002…`）后由 root 合入。801 外部输入仅3项变化、798保持；来源登记独审 `88c88c6a…`，原节点/完整清单和20秒限制不变。新asset `610531872` / SHA `73337ace072740d3bf300c22659c966ce059d5b93e121be259866cd525f35347` 为独立 draft 源码胶囊。

原统一入口本地 strict `20261004T194448Z-76dbf2a628` 18通过；M0.2.B 定向 `20261004T194521Z-b908e0a50b` 为104通过/1原符号链接权限skip，pytest0、统一入口CLI1/diagnostic_failed，不记整组通过。九个PS节点及其八阶段记录均完整通过，原20秒保持；局部独审 `e86e9c09…` 核五指纹与801输入一致、稳定、正常排空、模型0。未更改主机权限；真实GitHub Windows诊断仍待执行。完整证据与SHA见M8-2-v22-review-v2。

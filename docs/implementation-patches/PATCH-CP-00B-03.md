# PATCH-CP-00B-03：用户批准迁移隔离验证根

归属 M0.2.B / R3-20260927。用户明确选择“允许将后续验证根迁到 C:（推荐）”。这是验证环境迁移，不改变产品文件存储规则、业务断言或后续里程碑范围。

## 路径与保留范围

- 新的唯一执行根：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`，NTFS。
- 历史根：`E:/HuaKangOS-agent-validation/runtime-v1`，原 runs、review、归档和环境保留不动，不删除、不移动、不覆盖。
- 固定原始来源仍为 E: 的 cleanup/ui-validation 归档及已登记本地 Git。来源路径是历史事实，不因执行根迁移而改写。
- 仓库绑定保持 `C:/Users/tiefu/.codex/worktrees/edb5/HuaKangOS`；不读真实 `.env`、公司或预览数据库。

## 允许的迁移

1. 复制已冻结的 `run_validation.py`、`validation-manifest.json`、`binding.json`、两份依赖声明、`harness/`、`archive/baseline-original/`、`archive/baseline-restoration.json`、`tests/baseline/`、原 `.venv/` 和必要登记辅助程序。新根标记与环境探测单独保存。不复制旧 runs、业务数据或日志充当新执行结果。
2. 复制前拒绝重解析点及越界路径；禁止覆盖已有目标。记录每个相对路径、大小和 SHA256，原件/副本逐项一致。迁移脚本和完整证据仅在新根 `review/CP-00B-03/`。
3. 克隆 venv 后用新根的明确 Python 路径核对 `sys.executable`、`sys.prefix`、依赖版本和加载位置。不得调用仍可能绑定旧根的激活脚本或 pip 启动器，不升级依赖掩盖差异；如克隆无效，先报告具体原因及等版本修复方案。
4. 仅把外部合同测试的运行根改为优先读取 `HUAKANGOS_VALIDATION_ROOT`，独立开发检查回退到文件所属外部根；登记辅助程序按其实际路径确定根。原断言不变，保留修改前字节和 diff。
5. 登记 PATCH-CP-00B-02 的最终输入哈希：319 原件、11 新增 overlay、41 个 B 命令；预计 2504 个 pytest 节点（2124 原节点 + 380 新合同）。这只是预期，最终以实际完整收集与逐节点报告为准。
6. 同步 AGENTS、规格、架构、实施计划当前执行路径；历史报告和历史 run ID 不改写。不改变 `total_plan.md`。

迁移审阅追加：三份已登记 Node 适配 diff 按原字节补复制，保留可追溯的相对链接；平台元数据从 C: 实际 Python 重新采集。外部 `test_m02_harness_contract.py` 的一项旧审阅负例不得依赖未冻结的 review 目录：将五份原合成报告内嵌为受指纹保护的固定夹具，要求实际存在、内容吻合并断言具体拒绝原因；保留 79 个测试节点及其他断言。禁止用报告缺失笼统满足原“拒绝”断言。

已完成输入复制：4,711 文件、184,846,783 字节，逐文件原件/副本 SHA256 一致。新 C: Python 为 3.11.4，43 个已安装依赖与原锁逐项相等、加载目录均在新 `.venv`，没有重新安装或升级。完整复制记录和路径适配差异保存在新根 `review/CP-00B-03/`。此处仅为迁移开发核验，正式 strict+B 尚待执行。

迁移独立审阅已通过；五份负例内嵌后的 79 个原合同节点纯开发检查全部通过。重新登记后核对 319 原件及 11 份新增 overlay 哈希均正确、B 命令仍 41 个、合同最低数 380；只有 `b05-business-16` 登记原时区脚本的嵌套 Node 例外。完整证据见 `migration-independent-review.json`、`probe-fixture-embedding.json`、`registration-verification.json`。正式执行只使用 C: 明确的 `.venv/Scripts/python.exe`；复制的 console wrapper/激活脚本可能仍指向 E:，不使用它们作为新环境入口。

## 环境探测与异常路径

新根 `environment-probes/ntfs-c3c819718c/result.json` 记录：硬链接和目录联接创建成功；文件、目录符号链接均返回 WinError 1314。未修改 Windows 系统设置或权限；探测创建的链接已逐项清理，仅保留合成目标与报告。

已请求用户自行开启 Windows 开发者模式，或选择保留现状并记录外部阻塞。得到答复后重新实际探测；权限没有满足时不得 mock、删改、排除原安全用例，原测试的 skip 也不能算完整基线通过。复制/哈希/依赖/隔离校验失败则在新根修复明确原因，不向旧根拼接局部成绩。

## 验收

- [ ] 复制完整清单哈希一致，旧 E: 输入和证据保留；当前执行不导入旧 E: harness。
- [x] 新 C: Python/依赖加载路径与锁定版本核验通过。
- [ ] 硬链接、目录联接、符号链接的实际能力全部满足原测试需要。
- [ ] 新根登记后执行新 strict M0.1 和完整 M0.2.B；输入冻结，五类指纹一致，前后无漂移。
- [ ] 原业务、附件、备份、Node 子进程、目录及 workflow 检查均有完整真实结果；失败/skip/超时/缺结果不放行。

M0.2 仍 in_progress，CP-00B 仍 changes_requested。此补丁和用户迁移授权均不等于完整基线通过。

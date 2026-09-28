# CP-00B-v4：定向复验与 Windows 解释器修补

结论：**changes_requested，M0.2 保持 in_progress**。原完整基线及前两轮诊断证据保留于 v3 和外部 run；本报告不放行 CP-00B，不开始 M0.3/Runtime。

验证根 V 为 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`。E: 历史证据未动。真实模型调用仍为 0，未访问生产或原预览数据。

## 第二轮诊断实际结果

- strict `20260927T161006Z-f5b15c9502`：18/18，退出 0。
- 诊断 `20260927T161041Z-076dad3ad0`：已真实结束、退出 1，原 session 62575 已收尾，无验证进程残留。
- 同次完整 collect 为 2772 个唯一节点，原 2124 集合与此前完整 B 逐项相同；诊断实际选中 784 节点，9 个命令全部执行。
- 实际 **778 passed / 5 failed / 1 skipped**，无 setup/teardown 错误、缺节点或超时。648 个合同节点及运输组 109 节点全部通过。
- 原完整 B 的 36 个失败，本轮 31 个真实通过；剩余 5 个恰为已登记的迁移、两项 CLI、两项 preview 子进程节点，均被 `fixture_profile_interpreter_mismatch` 提前拒绝。不能据此宣称其产品断言通过。
- PATCH-04 的 19 个 reporter、7 个业务节点及 1 个解析安全节点，共 27 个精确目标全部通过。此前 Windows 超长环境变量导致的 1 个 teardown 和 268 个 setup 级联失败已关闭。
- 原符号链接节点仍沿 OSError 分支 skipped；本轮报告没有具体 Windows 错误码，不将此前探测的 WinError 1314 写成本轮观测。该项不能计为通过，仍需系统条件满足后实测。
- strict 五项指纹完全一致；全部源码/镜像/overlay/harness/外部输入/manifest/依赖前后检查通过。诊断保持 phase_complete=false、milestone_complete=false，未覆盖 full 指针或生成完整 baseline。

独立终态审阅：`V/review/CP-00B-05/second-diagnostic-terminal-review.json`，SHA `d1544c216d153198831fef8422266e01ef691a084e5c00f7b5059a6a9ed9a15c`。实际进程退出证据：`second-diagnostic-process-exit.json`，SHA `d6f740488c0db0d1a7c1855f9f27456bda72ff87b101ba3546d9db9f4cc6afa1`。

## 已应用的限定修补

固定 C: venv 的只读观测证实：sys.executable/sys.prefix 指向该 venv，而 Windows redirector 的 sys.orig_argv[0] 为解释器自身的基础 Python。修补仅涉及外部 `harness/fixture_profiles.py` 和其现有纯测试模块。

实际 executable/prefix 仍固定 V/.venv；Windows orig_argv[0] 只额外接受自身非空绝对 _base_executable，且其规范父目录与非空绝对 base_prefix 一致、文件名为 python.exe。完整参数、cwd、节点、profile、run、配置及标记守卫保留，不接受任意系统 Python，不读取 pyvenv.cfg，不修改产品测试。

候选 manifest SHA `097c0063ff157d319d0483d83d3ccfc053bb042b5f60be661d1eac2eb6ce6f03`；独立审阅 `windows-interpreter-independent-review.json` SHA `493991bb6a2cbd39f1ce0dfbb1b7242bb24035fdc0031e493aac7d1b4e68c7b0`，无必须修项。两文件已按候选哈希应用。

开发收集 `20260927T162650Z-25ad8854` 实际 258 节点（55 profile、41 URI、129 diagnostic、9 storage、24 registration），旧 249 全部保留、仅增加 9 项 profile 边界回归；未执行测试或导入产品、访问数据库/网络。登记只更新现有 profile addition 的计数/哈希/完整历史和 b01 minimum 648→657。原 319 文件、17 addition、13 新模块及 41 命令其它字段不变。

登记后 manifest SHA `06b3be2e5d547cc4b3fcc2f57fd246fc74316611cf9e8a6c79e056394f119975`；provenance SHA `3a51db12e6de49d2c51947e4426bf2493083c43f65524d4c6370e57882087772`。证据见 `windows-interpreter-application.json`、`windows-interpreter-registration-verification.json`。预计完整 pytest 2781，须由下一正式 run 实际确认。

## 下一验证与门禁

先新 strict，再由原统一 runner 精确执行全部 55 个 profile 合同与原五个子进程节点。这个局部诊断用于验证本轮唯一新增守卫差异；最终完整 B 仍执行全部 41 命令和全部适用节点，不拼接旧通过片段。任何新错误重新分类，符号链接缺项不降低标准或用其它链接代替。满足全部基线及检查点条件前，CP-00B 保持 changes_requested。

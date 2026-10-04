# PATCH-M8-2-TRANSFER-LIFETIME-01

2026-10-04，M8.2 唯一进行项。范围依据业主持续修复与完整技术验收授权；不启动 M8.3。

## 原始失败与原因

GitHub run `37203190639`、main `bcac11837130bf39c10bf02190822dccd41de40c` 的 Windows job `111438900124` 于 14:53:31 UTC 自然失败，101 条命令全部执行。原 full run `20261004T124607Z-71a48b0d65` 为 4229 passed、19 setup error；全部错误集中于 `m82-b05-business-01`，其余 100 条命令 complete。原 ZIP SHA `02247d2485ec3e3f1e7fed716c802307be6244a89d2f73a286372f351e888380`、独审 SHA `b73d4458dbea373901b5e3828fe91f99cda22951119f97a8319645e2c452a7eb` 保留在仓库外，原失败不覆盖。

最后一个成功节点 `tests/test_app.py::test_real_migration_and_database_transfer` 第二次调用 `transfer(source,target)`，实际验证非空目标被拒绝。`scripts/migrate_database.py` 为该调用创建两个独立 engine，但只在成功路径 dispose；目标非空抛出 ValueError 后，事务和 Connection 的 context 正常退出，底层连接仍可保留在这两个 engine 的池中。紧接的 scheduler 节点及随后 18 个节点在 fixture rename 主合成库时遭遇 WinError32，业务 call 均未执行。fixture 只 dispose 应用主 engine，不能管理迁移工具私有池。这是维护工具异常路径的资源缺陷；不把 setup 错误写成业务断言失败，也不改 fixture 绕过。

## 精确允许范围

只改 `scripts/migrate_database.py` 的标准库 `ExitStack` 导入及 `transfer()` 内两个私有 engine 的生命周期。每创建一个 engine 立即登记其 dispose 回调，覆盖第二个 engine 构造失败、迁移失败、非空目标拒绝、文件校验、写入、内容指纹及提交异常；原事务 context 先退出，私有池再释放。源/目标相同的拒绝、原表顺序、会话排除、逐行复制、计数/内容/附件检查和 PostgreSQL 序列处理均保持原语义。不得增加重试、GC、关闭外键、忽略 Windows 或强制关闭其它所有者的连接。

同时允许更新本补丁、M8.2 当前执行记录、当前 architect 任务/索引及对应检查点报告。测试、manifest、runner、原始报告和业务规则不改。

## 审查与验证

候选位于仓库外 `m82-transfer-engine-lifetime-candidate-20261004T150859Z-16685cb92e`。原脚本 SHA `083c872cabe60c62df728c308cd18a81a105a944b58555a2460a0e44f74145e1`，候选 SHA `4c9a523b739209326322b7c4c7a39b714a1800afcb9d68d238e5a0d5da245325`，diff SHA `483760fcacb07d19fd6f6e33e9cd680ef5ad2a9f38c6715025f98eb57c8bea5a`。作者静态逆向整模块 AST 一致，原业务/事务语句未变；root 已逐行审阅作用域与异常退出顺序。尚未写入生产源码、尚未执行候选动态验证。

Windows 本轮已自然结束并完成原件审阅。本地无验证进程后合入；尚在运行的 Linux 使用 GitHub 独立 checkout 与已解包的冻结源码包，其文件不受本地修改影响，继续自然完成并独立保存旧提交结论。先通过现有统一入口运行本地当前 M0.1，再用 M0.2.B 的既有 `b05-business-01` 全命令定向复验，覆盖原迁移成功/非空拒绝及紧邻下一 fixture；最后在旧双平台原件到齐后，以修复提交和同一冻结验证源码包执行 Windows/Linux M8.2 完整回归。通过前不把 M8.2 或 CP-35 记为完成；本补丁不缩短原清单、不拼接不同候选成绩。

## 实际合入与定向结果

root 在核对原字节与本地无验证进程后合入候选。第二位审阅者验证整文件 bytes/AST 逆向精确，且事务先退出、target/source 私有池再依次清理，独审 SHA `ada612a7478f956417323316c79a7159e1e49d68a7a911d878f7705278cc7361`。未改远端 Linux 的冻结副本，未改任何测试、manifest 或 runner。

当前本地 strict `20261004T151601Z-a3424964dd` 为 18 passed；M0.2.B 定向 `20261004T151650Z-196ece1a41` 为 CLI 0 / `diagnostic_passed`，先收集 2781 原节点，再实际执行原 business-01 的全部 153 节点，全部 setup/call/teardown 通过（244.547 秒）。迁移成功的原行数断言与第二次非空目标拒绝保持；紧邻 scheduler 及此前 19 个受阻节点均有实际 call 通过。两 run 五指纹/三文件映射一致、801 登记输入与冻结 r1 源码包逐项相同，前后输入与依赖稳定、无超时、进程正常排空、模型调用 0。定向独审 SHA `e4f4f44c4e458f1442ad19915df655d9517e0b4498206fcb6df9a538136a1cef`，生产源码指纹 `3e94277cdb4ab3e2a555e462f7fa7581fa70e0d093949a4d3f5658465008b701`。诊断 `phase_complete=false`、`milestone_complete=false` 保持；修复提交的同次双平台完整结果仍待。

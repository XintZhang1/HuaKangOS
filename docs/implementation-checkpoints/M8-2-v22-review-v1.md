# M8.2 v22-r1 完整回归与迁移资源修复

2026-10-04。M8.2 仍为唯一 `in_progress`，CP-35 不增加完整验收放行。当前修复属于已观察到的异常路径资源问题，未启动 M8.3，未修改原业务、测试节点或验收条件。

## 双平台原始运行

GitHub run `37203190639`，受检 main `bcac11837130bf39c10bf02190822dccd41de40c`，冻结验证源 asset `609828442` / SHA `129115b39864e387a02b3158151b0fb7f82d38cdff7c3141c681a7076c75c382`。两平台独立、并行运行；各自内部 101 条命令顺序执行，不使用浏览器或真实模型。

| 平台 | 原 full run | 实际结果 | GitHub 自然终态 |
|---|---|---|---|
| Windows | `20261004T124607Z-71a48b0d65` | 101 条执行，100 complete；4229 passed、19 setup error，0 call failure | failure，14:53:31 UTC，约 2 小时 8 分钟 |
| Linux | `20261004T124610Z-33b5cbca08` | 101 条执行，4248 原终态：4238 passed、10 个已登记 Linux 不适用 | success，15:20:30 UTC，约 2 小时 35 分钟 |

Windows artifact `11306686954`，ZIP SHA `02247d2485ec3e3f1e7fed716c802307be6244a89d2f73a286372f351e888380`，3592498 字节、2047 成员；原件与独审在 `V/closeout-20261003/m82-v22-r1-windows-37203190639-20261004T145712Z-178a4f15fc`。独审 SHA `b73d4458dbea373901b5e3828fe91f99cda22951119f97a8319645e2c452a7eb`：3407 pytest、245 文件、74 个有序数组逐原件一致；原 unittest 203、旧 unittest 286、Node 158、目录 193、工作流 1 全通过，独立语法检查 10 项另记。strict 18 与 full 五指纹、三份文件映射一致，前后输入/依赖稳定；全部进程正常排空、无超时、模型调用 0。先前的 PowerShell 超时和原 unittest 失败本次没有出现。

Linux artifact `11306799704`，ZIP SHA `13a223cb69d645a0b41d50ae98661c93e7ef21bb3e7684e82434754dd67297a7`，3607233 字节、2051 成员；原件在 `V/closeout-20261003/m82-v22-r1-linux-20261004T152440Z-487d5d01e4`。完整独审 SHA `25487e29c3d2c91c4097870edb10f66b75514dc1ff04fb099218c17dbbd49409`：官方下载、路径、CRC、成员字节、74 个原有序数组、3407 pytest union 和原 18 套 unittest 203 项均逐原件一致；1311 源码逐 Git blob 匹配受检 bcac118，33 harness / 768 external 与冻结 801 输入一致，仅既定 repository/platform 重绑定。strict 22 与 full 五指纹一致并重算，101 条命令全部正常排空、无清理/超时、CLI 0、模型调用 0；累计命令 9239.735 秒。未将报告未附的远端物理 mirror 或 OS 残留快照写成独审事实。Linux 旧候选的成功不继承给后续生产源码修复。

## Windows 唯一剩余失败

`m82-b05-business-01` 的 153 节点中，134 call 通过，19 节点在 fixture rename 主合成库时遭遇 WinError32，没有执行业务 call。直接前序是已通过的 `test_real_migration_and_database_transfer`：它第二次调用迁移函数，按原合同验证非空目标被拒绝。

`scripts/migrate_database.py:transfer()` 的两个独立 engine 原来只在成功路径 dispose。非空目标 ValueError 退出事务后，Connection 回到独立池中，仍可能持有 Windows 源库文件。应用主 engine 的 dispose 管理不到这些私有池。不能以改 fixture、GC、重试或关闭外键解决此实际维护工具缺陷。

按 `PATCH-M8-2-TRANSFER-LIFETIME-01`，每个 engine 创建后立即在 `ExitStack` 登记释放，保证构造下一 engine、迁移、拒绝目标、复制/校验/提交异常均有相应清理；原数据库上下文先退出，私有池后释放。源/目标拒绝、复制、原值/附件核对和 PostgreSQL 序列算法的 AST 均保持。原脚本 SHA `083c872cabe60c62df728c308cd18a81a105a944b58555a2460a0e44f74145e1`，候选 SHA `4c9a523b739209326322b7c4c7a39b714a1800afcb9d68d238e5a0d5da245325`，独立 bytes/AST 逆向审阅 SHA `ada612a7478f956417323316c79a7159e1e49d68a7a911d878f7705278cc7361`。相应本地验证进程已收尾后才合入；远端旧候选使用其独立 checkout，不受本地修改影响。

## 修复后本地原组复验

当前 strict `20261004T151601Z-a3424964dd`：18 passed。现有 M0.2.B 定向入口 `20261004T151650Z-196ece1a41`：CLI 0 / `diagnostic_passed`；2781 节点仅作收集，随后原 business-01 全部 153 节点实际 setup/call/teardown 通过（244.547 秒）。原迁移成功断言、非空目标拒绝、紧邻 scheduler 及此前 19 个受阻节点均完整执行。

两 run 五指纹及三文件映射相同，源码指纹 `3e94277cdb4ab3e2a555e462f7fa7581fa70e0d093949a4d3f5658465008b701`；801 登记输入逐项等于冻结 r1 源码包，未改测试、manifest 或 runner。前后源码/输入/依赖稳定、无超时、正常排空、模型调用 0。定向独审位于候选外部目录，SHA `e4f4f44c4e458f1442ad19915df655d9517e0b4498206fcb6df9a538136a1cef`。`phase_complete=false`、`milestone_complete=false` 保持，不把诊断写成完整回归通过。

## 下一步与界限

旧双平台原件均已完整审阅，当前唯一生产脚本修复已通过本地原业务组；提交修复与记录后，以修复提交执行同次 Windows/Linux strict/full。验证源码包 801 输入没有变化，可复用同一 asset；生产源码和实际平台身份由 CI 独立绑定并重新检查。全量通过前继续保持 M8.2 未完成；PostgreSQL、HTTP/HTTPS/输入法、真实模型、独立启停/备份及安全部署条件仍按后续各项执行。员工试用与人工验收保留给人员参加，不以技术检查代替。

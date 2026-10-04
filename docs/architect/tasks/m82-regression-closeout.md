# M8.2 当前 main 完整回归

v23 本地验证已结束：strict18；原business-11 104pass/1本机符号链接权限skip，九PS真实全过但整组保留diagnostic_failed。helper/来源登记/workflow及本地结果均独审；root已合入固定模块和固定CI诊断入口，冻结asset610531872/SHA73337ace…。下一步同新提交GitHub Windows原105项诊断，未豁免skip或开启后项；见M8-2-v22-review-v2。

2026-10-05 v22-r2：root 完成同 d794123 双平台原件收口；Linux 4238 passed/10 NA，Windows 4239 passed/9 PowerShell call超时。root 管精确补丁/来源登记/统一入口及合入；day 负责唯一外部 helper 候选，regression_harness 独审其原20秒/命令/断言不变；mobile 负责现有 workflow 的有限 Windows business-11 诊断候选。801 输入仅3项登记变化，其余798保持。当前仍 M8.2，详见 PATCH-M8-2-WINDOWS-PROBE-01 和 M8-2-v22-review-v2；本地 strict/定向和真实 Windows 诊断待执行，未启动 M8.3。

2026-10-04 v22-r1 双平台原件收口：GitHub `37203190639` 的 Windows 为 4229 passed、19 setup error；Linux 为 4238 passed、10 个已登记平台不适用。Windows 唯一失败来自迁移工具拒绝非空目标后未释放私有 engine 的池。按 `PATCH-M8-2-TRANSFER-LIFETIME-01` 修复后，本地 strict `20261004T151601Z-a3424964dd` 18 通过，M0.2.B `20261004T151650Z-196ece1a41` 原 business-01 全部 153 节点通过，含此前 19 个受阻节点的实际 call；五指纹/三文件映射稳定，801 验证输入未改，模型调用 0。详见 `docs/implementation-checkpoints/M8-2-v22-review-v1.md`。诊断不替代完整验收；下一步在修复提交上重新运行双平台全量，M8.2 仍唯一 in_progress，CP-35 不追加完整验收放行。

2026-10-04 v22-r1定向修订完成：新strict `20261004T123410Z-9314a28915` 18通过，M6.8 `20261004T123445Z-da2b05ff37` 完整21/21通过（149 Node、61 Python，另10语法及1生成物检查）；与该strict同五输入且均正常排空。一字符修复已真实复验，前次失败原件保留。此前同v22的M02定向684及M7领域202结果分别留档，不拼成一次全量通过。冻结source-only asset609828442，SHA `129115b39864e387a02b3158151b0fb7f82d38cdff7c3141c681a7076c75c382`（801源输入、3367654字节ZIP，GitHub官方digest相符）；原319归档、101命令及全部原节点保持。下一步新main该同候选双平台strict/full；M8.2仍唯一in_progress，后续真实技术门槛及员工试用/人工验收边界保留。

2026-10-04 v22定向实跑：strict `20261004T120855Z-001d54f089` 18通过；M0.2.B diagnostic `20261004T121130Z-b2b9a85767` 原657合同+27节点=684全过，阶段/里程碑仍false；25个既有M7入口202节点全过，同五输入、正常排空。M6.8 `20261004T120953Z-12bffdc9cc` 执行15/21，149 Node及25 Python通过，1个Python新正则漏转义失败，后6命令未执行。原失败保留；仅补1个反斜杠并双人静审，注册输入仅该源和来源记录变更，799保持。r1 draft SHA `3cb9419482aac8c597167f64b56921f566f38a5e0f8e65279e5343c880a39817`，新strict及M6.8全入口复验待执行；双平台101全量仍待，不混用为整项通过。

2026-10-04 v22候选已实际合入外部注册来源：129个已交叉静审的测试/夹具/执行器源文件，加两份来源登记，共131输入变化、670/801保持原字节；原319归档、全部命令/节点清单保留，9条Linux preview不适用规则仅重绑overlay SHA。合入前实际检查无本地验证进程，v21两平台已自然终局。新draft SHA `8be5fe1a17554916fa34d62c5ae4ff48209ad12b86fd280914d17b65b6b61f23`；下一步统一strict和原定向入口，尚未执行新候选动态检查，不记通过。

2026-10-04 v21两平台均101/101实际执行并自然failure：Linux4151过87错10NA，Windows3473过89错686setup错误。真实3407/203节点完整且输入不变，各自原件独审完成。root负责baseline/original登录、preview helper、文档与来源合入，day负责50项旧领域/UI合同，reg负责18项Node合同及Windows raw SQLite资源生命周期，mobile负责两平台原件和解释器绑定/进度输出。各自在全新外部before/candidate独占文件，不改旧证据；交叉静审后原统一入口定向复验，再同候选完整双平台。详见M8-2-v21-review-v1及两项精确补丁；M8.2唯一in_progress。

2026-10-04 M8.2 v20：CI37183964600双平台自然failure，各strict18/22通过，matrix/A/B/C/D/E/F全部通过，真实600秒预算和取消计数修复本轮完整通过。原18收集得到203节点但执行0；full27/101各750pass/33fail/2624未执行，后续74命令未跑。33失败均为两个旧合成验证夹具遗漏平台文件及完整清单，按PATCH-M8-2-SYNTHETIC-VALIDATION-FIXTURES-01仅修夹具，不改业务/runner/断言。先现有统一M0.2.B诊断后新同候选双平台full；M8.2唯一in_progress，见M8-2-v20-review-v1。

v21夹具修订已通过本地同指纹strict18及原M0.2.B整组657/657定向复验，CLI均0，诊断不记全量通过。冻结source-only asset609410676/SHA54fe594476256e59abe59f4864f8402b73283f01b9e5b6a86fcbd40eb558acd1，3输入变更/798不变；下一步新main同候选双平台strict/full，当前整项仍in_progress。

2026-10-04 M8.2 v19：CI37181959680双平台自然failure，各strict18/22通过，full8/101各125pass/1fail/3281未执行。E7全部通过，Windows实际PID身份及读取恢复修复已动态成立；F10pass/1fail，真实600秒停止已通过，第二模型轮次的已知HTTP计数在父/子取消传递中遗失。按PATCH-M8-2-MODEL-CANCEL-USAGE-01仅修run_once局部safe usage接线，保留全部输入/断言/预算/权限，新同候选完整复验待完成。M8.2唯一in_progress，见M8-2-v19-review-v1。

2026-10-04 M8.2 v18：Windows定向CI37180332868自然failure（Linux未调度）。新增实证锁定启动器PID4272与实际workerPID6344，父PID4272，Run/helper/mode/存活全匹配，仅原严格PID等式失败；尚未到kill/恢复后置断言。按PATCH-M8-2-WINDOWS-DIRECT-WORKER-01直接持有已绑定实际解释器句柄、核实原venv身份，保持原PID及业务/预算守卫；新同候选双平台完整实跑待完成。M8.2唯一in_progress，详见M8-2-v18-review-v1。

2026-10-04 M8.2 v17：CI37178121548两平台自然failure，分别独审strict22/18、full7/101各114pass/1fail/3292未执行。Linux已越过读取写入故障，停于读取观察25vs24；Windows更早停于未保存PID详情的checkpoint身份校验，不能混同根因。按两项精确补丁仅修E完整有序查询断言及有限身份诊断，保严格校验和全部后置业务守卫；新增默认false的Windows定向入口先取证，最终双平台完整门槛保留。生产不变，M8.2唯一in_progress，详见M8-2-v17-review-v1。

负责人 root；当前唯一实施项 M8.2。main 整合和分支清理已经完成，旧工作区的业主界面改动已合入，原脏工作区保留。

2026-10-04 M8.2 v16：CI37176583479双平台自然failure，各自strict Linux22/Windows18，full只7/101、114pass/1fail/3292未执行；准备故障完整回滚断言已通过。唯一读取恢复失败已定位新WorkItem未先flush即关联已有RunItem的写入次序缺口，按PATCH-M8-2-READ-WORK-FLUSH-01最小修复，原v16全部输入/断言/胶囊保持。两平台证据分别独审，详见M8-2-v16-review-v1；新源码完整复跑待执行，M8.2仍唯一in_progress。

以下 v15 为历史进度：

当前 v15 CI37174392421 双平台自然终局 failure：matrix1/A25/B33/C35/D14通过，E5通过/2失败。双平台独审各自确认113pass/2fail、只7/101命令，原203独立节点仍待。当前补丁仅改SAVEPOINT提交观测及原GET故障子进程有限诊断，后者尚无确定根因。day负责两helper外部候选，mobile负责E原单函数外部候选，reg已完成双平台实件独审，root合并/登记/统一执行。详情见M8-2-v15-review-v1；下文v14为历史进度。

2026-10-04：v14 CI37172219196 两平台自然 failure。Windows B32通过/1夹具失败；Linux B33通过，C27通过/8失败。此前快照连接占用已消失；两平台仅执行4/5个命令，其余未执行，不计全量成功。

回执真实账号投影及问卷截断标记两处生产修复完成交叉静审；六处测试函数按原合同修正并由 root 合并，保留全部原节点/权限/撤权/业务零写断言。v15只改变B/C与两份SHA登记，其余797输入保持。下一步执行当前源的双平台完整 strict/full，按真实失败继续修复。M8.3 PG 及后续真实环境门槛只读准备，未并行启动。精确证据与指纹见 `docs/implementation-checkpoints/M8-2-v14-review-v1.md`，里程碑状态仍只维护在实施计划。

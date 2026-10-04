# M8.2 v16 实际结果与读取任务源记录修复

2026-10-04，main `da3b887b78b9edc50685f7ac8750f281a25bb82c`，CI [37176583479](https://github.com/XintZhang1/HuaKangOS/actions/runs/37176583479) 两平台均自然终局 failure，未取消。Linux 04:25:26 UTC、Windows 04:37:49 UTC 完成。输入 capsule asset609102816 / `519e60ee37dfa5df99063db69a43605cd2b0fe9383c56a99b6208f97ededbe79`。

| 平台 | 官方及下载 ZIP SHA | 外部原件目录 |
|---|---|---|
| Linux | `b93122bff9e3c1fd73a51c304534d418e2cb1a6ee0dd138368534278d4c48e01` | V/closeout-20261003/m82-v16-linux-20261004T042809Z-feed0011f4 |
| Windows | `8b60899a5fe97a81b5a0ead7802301d1164c374419e23a637c3287058a56523b` | V/closeout-20261003/m82-v16-windows-20261004T044258Z-b3493ba12c |

Linux 独立实件审阅 `729d00fd2a21d132c0189077cdde510837e708ccc6d343e559895f14f66741d6`：strict22/22、collector3407唯一节点/245文件；matrix1/A25/B33/C35/D14通过，E6通过/1 call失败，所有已执行节点 setup/teardown 通过。只执行7/101命令，114 passed /1 failed /3292 not_run；后94命令及原203独立节点未执行。五输入和三个来源映射在strict/full一致，输入/依赖前后不变；全部实际命令自然退出排空、无超时，真实模型0。

原准备回滚测试的 SAVEPOINT/外层提交分类已通过，且本轮实际执行了其完整回滚快照断言。唯一失败仍是 `test_real_get_result_kill_restores_same_work_and_default_twenty_four_rounds`。两平台已下载有限诊断均为同一 helper SHA、IntegrityError / runner flush位置755、3 succeeded /2 pending /1 running、子进程退出3；唯一 GET 200 是首准备内部目录查询，显式原单 GET 尚未执行。诊断正文不包含原异常文本或 SQL 约束名。

Windows 独立实件审阅 `a88b2989c7c402c6cabb68eb83e2c8c338e63bf138f2ebb1918d363f2963b717`：strict18/18；该平台独立确认full7/101、114 passed /1 failed /3292 not_run，原203独立节点未执行。collector3407唯一/245文件、已执行有序数组与登记全部一致，节点聚合无缺失/多余/重复；strict/full五指纹及三个来源映射一致，全部输入/依赖前后不变，8条实际命令自然排空、无超时或强制清理、无setup/teardown错误或skip，模型0。有限诊断SHA `9e01764148a5874df3a229596c24ab6871d1189bce0341a9d9bd441d359d1f81`，与Linux分别留证，不拼接成绩。

事前范围见 PATCH-M8-2-READ-WORK-FLUSH-01。两名协作者对照调用顺序、全部表约束及 SQLAlchemy 2.0.50 UOW 源码，确定新建读取 WorkItem 未先 flush 即关联已有 RunItem 的缺口。修复仅先写入源行，再设置外键；同一事务中的最终身份/权限/fence 重验、commit及错误整体回滚保持，复用分支不变。这个源码原因与实际观察吻合；新源码的动态恢复结果仍待复验。

原v16全部测试、输入和胶囊保持，用新源码重新执行统一strict/full；原失败不能改写成通过，M8.2仍唯一in_progress。后续PostgreSQL、真实模型、独立环境、员工试用及人工验收分别保留。

生产窄修源SHA `396eb22eaa4a4778ff8e04692374658b1313529a7798021cd2cff6bd16ec381d`，原件及差异在 `V/closeout-20261003/m82-read-work-flush-candidate-20261004T044437Z-e8f5e30a2f`。作者静审 `f3206d5dfd31d506d71d94958403155a79826bc5d1666a21c95bdbd2b41a3952`、独立静审 `19bac5888633f2e89385ec57763fddcc1e374e270e1e3a4d545e7c52e63b13bb` 确认唯一新增行、逆向字节/全模块AST与原件一致、同事务守卫保持。root独审 `50389bb28905a1326d95deb71fc826a242936c7b988375643c4e28d7af121b0c` 核实全部801输入仍为原v16字节。此阶段未导入应用、运行测试或调用模型；新源码动态恢复结果待下轮。

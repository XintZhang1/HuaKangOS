# PATCH-M8-3-DATABASE-CONTRACTS-01

2026-10-05，沿原M8.3四条完成检查继续首探针之后的剩余范围。仍只有M8.3 in_progress；首探针独立通过记录保留，不继承其成绩为新扩展通过。

## 精确范围

- 外部V既有`tests/baseline/overlay/tests/m83_database_probe.py`增加原同次升级/恢复路径之后的有限检查；新增同目录`m83_database_concurrency.py`、`m83_database_refusals.py`。原`m83_owned_postgres.py`及两个已复制M8.2 helper保持原字节。
- `V/validation-manifest.json`仅更新M8.3的精确overlay、固定命令和实际节点登记；`V/archive/baseline-restoration.json`仅更新该probe来源指纹并追加两个新模块。原319归档、其它里程碑及M8.2所有输入不改；不改统一runner、阶段、超时或通用环境框架。
- 仓库只写本补丁、M8.3原项、architect任务/索引和验收小报告。本补丁不批准额外生产改动；实际发现生产缺陷后记录精确修复范围。

## 原合同接线

保留真实员工HTTP、原Worker、非空h52j旧库、h53k升级和独立联合恢复的整条路径，然后在SQLite和已核身份的PG上分别执行：重复升级不改原行、旧engine1无授权计划经三次实际Worker tick不自动启动、不增加卡或确认冻结事实；唯一/CAS、两个独立Worker租约和旧fence拒绝；原事务outbox失败回滚、重试和同事件竞争；原完整性孤儿/跨员工/跨店/循环/JSON拒绝以及缺失/损坏附件、SQLite联合恢复拒绝。

Worker显式绑定传入的真实目标engine，写Session和独立授权读取Session均核同库。为使原员工HTTP和内部读取实际使用同一个PG，只在测试函数的ExitStack内设置原FastAPI `get_db`依赖为该engine的新Session，保留原`get_user`、Cookie、CSRF、门店/岗位和确认接口；不构造假principal，不改主DATABASE_URL/globalengine，不修改业务状态取得成功。并发线程共享一次固定绑定，全部自然收尾后完整恢复原依赖字典。

数据完整性负例只在已验证专用库的事务/SAVEPOINT内变更，一次一个损坏并断言具体拒绝；每例先通过正向完整性检查、检查守卫无写入，最终回滚。PG保持真实FK/CHECK，用真实SQLSTATE区分数据库约束拒绝，不拷贝SQLite关FK做法。对象负例只作用本次合成字节，finally恢复并重新核hash/正向验证；原bundle和来源根不永久破坏。

各模块先外部候选静审再合入；测试与app只通过原`V/run_validation.py`在新镜像、全新合成库/PG集群执行。所有原失败和前候选保留，不片段拼接成绩。最终按实际完整节点、各原门槛报告、五指纹和自然停止原件审阅；脚本通过不自行改runner的milestone_complete语义。外部模型0，四个生产功能开关默认关闭。

## 首轮扩展实际记录

strict `20261005T015350Z-35bdb3a64d` 18通过；完整数据库命令 `20261005T015431Z-7ee005cea8` 实际1节点/1error、exit1、164.719秒自然排空，PG stop成功、原PID/pidfile消失。五指纹相同且全部稳定，source `430bda06aaa2115332c65e9902342e7a8636d2b665bb656c8aa46c63a08ce883`；run.json SHA `f0723ee5a8e18dc07f8bb5fcc63495c70a6e2893dfe01adb5b813e479e3d8ac7`。原两库升级/恢复、SQLite重复head/旧计划三tick、21拒绝路径及租约/outbox/CAS/前三类唯一已实际执行，但本轮失败，不拼成全量通过。

停于SQLite `proposal-work`唯一检查的准备阶段：新WorkItem在one提交时two仍保留读取事务，记录为OperationalError（源模块448行），尚未保存原sqlite数字错误码。仅在此准备提交前结束two读取事务，之后仍用两个独立连接验证原唯一冲突；不改业务代码、锁、WAL、timeout或断言。原probe安全异常摘要同时仅补DBAPI的整数`sqlite_errorcode`（合法范围0—65535），不输出原错误正文/SQL参数。下一次重新strict与整个数据库命令，原失败保留。

第二轮扩展 `20261005T020357Z-95accd942e`（strict `20261005T020311Z-a803f771b1` 18通过）实际1error/exit1，147.453秒自然排空，五指纹一致且未变、PG正常停止；source `0045afd2c5ff16a356aaa68503433d9d01d1fda12a1fb5e9a4623382ec0416ee`。SQLite21拒绝和12并发子阶段均执行，原行与完整性核对完成，最终断言仍有activeGrant而失败。夹具在约束检查前已用原revoke结束计划，随后才加入合成active授权副本；最终再revoke按原“已结束事项幂等”正确不修改。仅将前一次控制动作改为原pause，最后仍本人revoke并要求无活动授权；保留原业务幂等、全部行和断言。PG扩展尚未执行，整轮不计通过。

第三轮完整通过：`20261005T021313Z-4db44dd34a`，strict021219Z-f699b0cc5f 18通过，实际唯一节点pass/exit0/284.797秒自然排空。同五指纹与三文件映射稳定，SQLite21与PG16拒绝、各12并发、各3旧计划tick及原联合恢复全部完成；PG停止和25合成/0真实模型已核，原两次失败仍留档。最终输入probe SHA `7f579e651812b109cabcb0cde16a60dd36766e88003f68d69a65da53e9c8d864`、并发 `fec13b8bc0e75dd97b068fc40fdc663b6f4e36f9039a924ee40307c7dd3369ff`、拒绝 `b06b519295417eb2e557503c3a81da4c5356985d7f1e80122dbaff32e70c8b38`。原四完成检查据此收口，详M8-3-database-closeout-review-v1；未改runner自动milestone语义。

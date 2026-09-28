# M4.8 v1：事实核查与持续跟进编码审阅

日期：2026-09-28。计划R4-20260928，固定补充合同见PATCH-M4-8-01。本报告记录源码实现及待测范围，不代表运行验收或功能启用。

## 已落代码

- plans抽取原完整条件纯读流程，原已领取Run的求值/准备/写入/完成权限保持。新增独立FollowupCheck，必须真实active Grant probe；绑定同Session/Engine、Grant版本、当前Plan/goal和完整Step/WorkItem/卡片/RunItem来源及执行活动，60秒有效、一次消费、同事务末验。凭据不能代替Run lease/fence。
- 批量持久先锁全部Session、全部Plan、再Grant；核对全部来源后才改任何Step。typed last_evidence、状态和next_check_at同事务保存，同Session在这一批计划更新中只加一次版本。完整必要步骤必须非空且都有本轮完成证据；无待确认、缺资料、未知或未执行完整行才完成Plan并撤当前Grant，原WakeEvent同事务。查询完成仍需实际read WorkItem及原GET重验，不能代替实体业务事实。
- 无变化或条件不足只核查，不建新Run。正常补漏5分钟，明确due_at只有通过原员工消息时间验证才提前安排。缺资料、失败、取消、未知和过期卡不能自动复制；完整batch中原合法未准备行仍按已接受清单保留。
- queue新增固定followup resolve/persist/validate；只能消费服务器签发的完整核查凭据，无通用写callback。Plan核查结果和新Run同事务。统一`followup:plan:goal:fingerprint`用于事件和补漏，不含事件ID、观测时间或Grant代次；同事实已有终态Run只复用，不重新开启。当前会话/事项有queued或running、或有效busy租约时不加新后台Run。
- outbox事件链复用上述条件和入队合同，WakeEvent CAS仍同事务。新增单次poll_due_plan和5秒检查常量供M5.6 worker调用；只扫描active Grant的到期/null核查事项，不扫描所有旧会话。权限失效/过期先用原独立控制服务证明后收尾；瞬时失败只能把仍有效且版本匹配的核查时间推迟30秒，不伪造完成或撤销有效授权。
- runner原最终回复事务增加`usage.followup_outcome_v1`固定字段，保存有限原因码及是否需要员工资料，不存文字、推理或异常正文。真正failed或需资料的执行等待同事项/当前goal之后的本人user/manual执行，调度器不解析模型文字；只抑制新模型执行，不阻止完整原事实自然完成事项。

## 审阅边界

作者与root逐段审阅来源、锁序、全部快照先核后写、空完成条件、完整batch、due时间、失败等待和租约边界。独立审阅者核对outbox→plans→queue实参/返回、同Session最终版本、原终态去重和本事务完成/撤Grant后末验；末验读取原已提交授权，不会与本事务待提交更新自冲突。runner收尾摘要经过独立审阅，原progress或release不会覆盖该JSON更新。

一次性凭据的事务弱引用另作窄修：已消费后必须仍有非空同一事务，不允许事务释放后`None is None`误当仍绑定。原signal兼容入口、manual/user队列、M4.6预算及让出逻辑保持。

没有启动worker、模型、浏览器、应用或数据库；没有新增/修改/运行测试或迁移。四个开关默认关闭。状态只在implementation_plan.md维护，CP-10仍须M4.9及该批最终源码审阅。

## 静态指纹

HEAD f735de2d74f5eb37f13addc1353e6a8e435a01c4。外部Python -I -B仅stdlib AST、UTF-8、无U+FFFD和SHA-256，退出0；新增相对导入调用名称与定义静态核对。未执行候选模块。

| 文件 | SHA-256 |
| --- | --- |
| app/assistant_runtime_plans.py | 5bc23c7bb2096330a60e500e6ab95f030ac5adb1ee78c022bc7ddbda8d356b7e |
| app/assistant_runtime_queue.py | c83ed1224face100643be17b011866e04a938bfff0ed466e0dc923c51149d615 |
| app/assistant_runtime_outbox.py | 64f520e38558a798350e46cc99f8c45e2d303313bacca445ba5a6dc98fec74e5 |
| app/assistant_runtime_runner.py | 3a4325bb76a98b42e767c82ba8a621596a6ec2ec87faa390169c58b2643d7b7e |

## 集中测试必须覆盖

20次无变化0模型、新事实最多一次准备、事件/补漏同时到达、同Session多个Plan、完整batch部分已有卡、查询完成例外、空必要集合、业务完成与卡准备区别、合法/伪造due时间、睡眠后一次补查、暂停/恢复/撤权/登出、过期卡不复制、预算失败与本人明确继续、瞬时GET错误退避、source/Grant/goal变化和跨事务凭据重放、事务任一点中断均待DeepSeek实测。静态结论不勾选原验收条件；原业务回归、PostgreSQL与双连接故障条件保留。

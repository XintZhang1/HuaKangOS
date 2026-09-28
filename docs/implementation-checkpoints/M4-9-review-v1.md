# M4.9 v1：未知确认结果恢复源码审阅

2026-09-28，计划R4-20260928，范围补充见PATCH-M4-9-01。仅记录编码与静态审阅，运行验收后移。

独立只读lookup继续只返回ReceiptLookup；新增协调服务以当前Plan完整关联/合法carry行或当前Run完整accepted工具来源定位原卡，只检查原员工冻结confirmation。原actor、store、request key、原生digest、目标原单和当前原GET可见性一致才签发一次性短时来源凭据。读取前后重新核身份与源版本，HTTP请求身份固定为本轮标量，回滚后不依赖旧ORM回执对象。

协调短事务先锁Session、Plan及实际Run/Grant，Run必须有当前lease/fence。凭据绑定Session、Engine、同一principal、完整来源并只消费一次；可靠成功才将Proposal及confirmation置succeeded、WorkItem置settled，追加typed回执观察与真实proposal结果信号。保留原冻结snapshot/digest、原HTTP status/data及原业务记录；不伪造HTTP200、不补POST。not_found、unsupported、mismatch仍待核对；不可见不输出旧内容。

conditions保留原2xx分支，响应丢失分支必须重查原回执并与已保存观察的receipt ID/operation、对象绑定一致；仍对原单当前权限重验。该条件只证明原命令提交，其他实体完成条件继续独立判断。

outbox在本轮所有FollowupCheck签发前完成协调，再重新读取Plan/Grant/原对象；poll重新取控制版本。runner首先校验完整accepted链，然后协调当前Plan前轮遗留卡并去重当前Run旧unbound卡，最后重读全部恢复状态。新的手动Run尚无model记录时也不会漏掉当前Plan未知卡。未解决卡继续needs_input，不解锁依赖。service仅为已绑定原confirmation的确证结果展示固定说明，原HTTP结果不被改写。

作者、root及独立审阅核对上述接口、来源、状态、锁序和只读边界。修正了真实User岗位校验、跨回滚ORM引用、HTTP身份版本固定及当前Plan历史卡恢复入口。没有启动应用、数据库、worker、浏览器或模型；没有新增或执行测试。

## 静态指纹

HEAD f735de2d74f5eb37f13addc1353e6a8e435a01c4。外部Python -I -B仅stdlib AST/UTF-8/无U+FFFD/SHA-256，退出0。

| 文件 | SHA-256 |
| --- | --- |
| app/assistant_runtime_receipts.py | b0b91a29b7040bd64836a715a2384033da887c174e51705dac3a7ae164043106 |
| app/assistant_runtime_runner.py | 3e0ac3d639b06713094e3b57068e1d8fbfb592a3640cca52948da96d71437496 |
| app/assistant_runtime_outbox.py | 104f3ae70feb475a5bad87c124c1763311eb5d78b70bed003ee44451a7481911 |
| app/assistant_runtime_conditions.py | eac0ed8ce985f1982b1aecb53864d796ea612837652583fade1c53986c2252e0 |
| app/assistant_runtime_principal.py | 797cb91f13436e6aa84796fe75cd521070adb37335095b727704c3d9d9ac0eef |
| app/business_assistant_service.py | b3f09b58b2ce390d20674ae24545f393549eff4cd0deab6e20c9d98dbf8a1420 |

## 集中测试

原业务成功但结果丢失、原API仅一次、迟到回执、任意次数not_found不POST、旧无快照、伪造/不匹配回执、原对象撤权、角色/权限版本变化、跨连接源变更、过期worker与Grant撤销、协调并发/中断/幂等、同Session多Plan凭据顺序、前轮Plan卡及未绑定历史卡、冻结内容无改写、GET无状态变更、非2xx真实回执解锁而实体事实未完成、结果视图均待DeepSeek。通知落地属于M5.4，当前未声称已通知员工。

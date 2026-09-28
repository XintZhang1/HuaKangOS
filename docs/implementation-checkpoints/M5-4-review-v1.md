# M5.4 v1：站内提醒及协作隐私编码审阅

2026-09-28，计划R4-20260928及PATCH-M5-4-01。编码和源码交叉审阅完成，原测试未执行。

通知只绑定真实Proposal、Plan或原Task。摘要为固定安全文案，不摘取聊天、目标、原单明细或模型回复。生成时读取真实员工、当前门店岗位及私有Session权限快照；原任务交接只交Task和原Case引用，通知没有前手私聊/计划/卡。原单可见性沿原Case查询与can_read，不借管理员、登录Cookie或Grant扩大访问。

新增卡、原卡真实结果、原任务实际分派/变化、Plan实际状态变化及关联Run收尾均有同事务来源信号。新卡及复用卡按真实版本去重；任务提醒不随每个FlowEvent重复；Plan排除next_check、observed_at及心跳，真实失败/补充阻断按同目标的blocking Run ID去重。Plan事项列表同步显示这种真实Run阻断，不将执行失败写成某个业务步骤失败。只有同目标的本人真实继续才能解除旧阻断。未知确认按原严格三分钟规则读取，首次executing信号延至三分钟加一微秒；不会重POST或改变卡状态。

分发门禁为(Runtime且followup)或notifications。提醒可独立开启，notifications分支不获取Grant或启动Run/模型；两个分支的实际开关在读写及提交前核对。固定事件凭据绑定同Session/Engine及来源，先完成独立回执协调再解析通知，短事务保存跟进结果、通知和Wake完成CAS；通知分类取本事务的当前源，提交前独立核权限与原已提交来源。失败回滚分发，保留原退避，不改变已成功业务。重复事件不把已读重置未读。

通知GET只读，重验当前来源，权限过滤后计数分页；失权、已不适用的旧提醒不混入未读数。POST read严格本人原Cookie/CSRF和精确路由，只做unread→read，重复和已resolved不改，版本/锁冲突409。resolved只能由实际结束来源产生；结束Plan只解决纯Plan提醒，不能清掉同Plan仍待确认的原卡提醒。接口不接受额外身份、任意来源表或正文参数。

本阶段通知的业务引用可见性实现为当前原Case读取；新建草稿无原单时仍可凭本人真实卡/Session产生固定提醒。未注册或非Case引用安全不产引用提醒，不能当作业务完成。M7引入相应非Case适配时还须补其固定原只读可见性接线，并联合验证；当前结果不代表所有未来领域已覆盖。

作者、root与独立审阅核对了生产者、来源校验、事务、互斥、状态、HTTP隐私及去重。已修复到期边界漏提醒、执行窗口内过早报未知、Plan结束误清原卡提醒、同Run因Step刷新反复提醒、初始结构化条件缺口未提示以及已读flush冲突映射。没有改原业务规则、原确认、默认开关或新迁移。

## 静态指纹

外部Python -I -B只用stdlib核AST、UTF-8、无U+FFFD和SHA-256，退出0；未导入应用。配置文件核对四开关默认false。

| 文件 | SHA-256 |
| --- | --- |
| app/assistant_runtime_workspace.py | d04c4c3f49d89eb939693fa169c551b03886e1b9d2b30994c3ba48a2dda7f8c5 |
| app/assistant_runtime_api.py | 73eac65a443350602810b22c6e5383668cd15f21ec42920e49fde4034c533bbf |
| app/assistant_runtime_outbox.py | 5bcffdd5a8838501851365cb45c21f1306f63faa69d161405dcbcd8852def68b |
| app/business_assistant_service.py | 87545c410def2df9a6df2c06893017fbab65fabdf690d11add13d0f0b0f0f4ec |
| app/assistant_runtime_plans.py | a4b4041ce6690fa476b7c1b1ed019ccdc7571de0b9b5e8169d4d460281e1a9b5 |
| app/assistant_runtime_runner.py | d36e63b40d580b507aa853c3c52796ce5f3e12bd2f1722af8747317b1c598c88 |
| app/assistant_runtime_queue.py | 850d54c9ccc02df5eeeb0798ffd7e056522ac37aef5df993d7b51e18f3b8c89b |
| app/flow_engine.py | 2cb1ea6610518743f34c6f23124d6afc8d82e72ea35254170d25c1b8e6eaf1b0 |
| app/flow_api.py | fff97088ebf2bdc6346ba360181bbd76f48dac029b0f3caa2375a2734afd3a70 |

## 待集中验证

两员工交接、转岗撤店/停用/恢复、原单权限丢失、本人私聊保护、重复/乱序Wake、实际源回滚、同源并发插入、原任务重新分派、Plan与卡分别结束、同Run无重复提醒、真实login继续、原卡三分钟前/恰好边界/之后、提交进程中断、回执迟到、runtime=false通知独立运行、通知失败不改业务结果、同事务跟进推进及通知来源比较、Cookie/CSRF/额外正文拒绝、只读GET、已读幂等/锁冲突、分页及未读计数、无变化零模型/零新提醒、非Case领域后续接线均待DeepSeek实测。没有新增/运行测试、数据库、迁移、应用、worker或模型，没有本批进程句柄。

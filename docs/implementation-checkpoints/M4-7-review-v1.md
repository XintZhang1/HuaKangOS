# M4.7 v1：事务信号与逐事件分发编码审阅

日期：2026-09-28。计划R4-20260928，范围补齐见PATCH-M4-7-01，生产者及原提交位置见M4-7-source-map-v1。用户持续授权下实施；本报告只记录编码，不代替运行验收。

## 实现与审阅

- FlowEvent、实际任务转交、卡片终态、原Grant生命周期、账号授权修改、管理员重置密码和门店启停均引用真实记录，在原事务内写最小WakeEvent；原owner提交，不新增业务commit。Runtime关闭时新增hook提前返回。专用业务直接插入FlowEvent的其他路径留给M7精确接入，不声称全部领域已覆盖。
- 全局权限事务只调用固定receipt/audit来源helper，自行推导实际相关门店；不改store_scope/write_store，不接任意SQL/表名或外部指定门店。历史reset审计没有before/after，不虚构字段；延迟权限事件按历史来源验证，当前权限另行复验。
- 有效Grant可签发只读probe，真实owner/store/原Session岗位与access_version、Plan/goal和Grant版本每次原GET前后重验。没有Run、lease、fence、登录凭据，不能用于模型循环、准备、计划保存或员工确认。
- dispatcher逐条选择到期pending事件；源记录、门店、key及版本由固定映射核验。只按typed对象、任务、卡片、Plan引用匹配；业务对象仍经过本人原GET。一次事件的全部Run、最小Run事件和dispatched CAS同事务；失败整体回滚，再以原事件版本CAS保持pending，30/120/600秒封顶退避。没有最大ID游标，不丢晚提交的小ID。
- queue拆成同Session/Engine、60秒、一次性resolve/persist/final-validate；先锁所有Session，再所有Plan，同Session只触碰一次，避免多个Plan批量分发自冲突。旧单signal入口保留兼容语义，manual/user/领取/预算不改。
- 作者、root与独立审阅者核对事务、权限、来源、批量和旧入口。修复两处漏匹配：任务条件通过真实同店Task.case_id匹配flow事件；卡片匹配复用完整当前manifest投影，接受合法carry_forward旧intent卡，不广收历史卡。条件满足、事实指纹和无变化零调用由紧邻M4.8接入；本项只完成候选分发，不启动worker，不把信号当完成依据。

完成卡片投影接线后，独立末核发现fresh reader缺少单店scope会触发原owned_session守卫；已在真实probe之后为该reader设置原单店范围，末核闭合。初始跨店调度扫描不借此扩大员工读取权限。

## 静态证据

HEAD f735de2d74f5eb37f13addc1353e6a8e435a01c4。外部Python -I -B只用stdlib读取下表源码，AST/UTF-8/无U+FFFD及SHA-256检查退出0；没有执行候选模块。

| 文件 | SHA-256 |
| --- | --- |
| app/assistant_runtime_outbox.py | 4a11251644d0f391ba4e149567423b192a1a26a54a0aed3bbc6f500661eeb590 |
| app/assistant_runtime_queue.py | 4aea5083a2daebc9071debdd8dbfac5334b3a0e8d4ba23b76e955240bef1168c |
| app/assistant_runtime_principal.py | 4039a3bc33378bb245c92af4ac9d3f9c9fae42f820380428c22fe141aa615660 |
| app/assistant_runtime_access_signals.py | 4c1641475edebb9eea842f6e99dfa654cf13b71518867bf6211437b5eab2df63 |
| app/flow_engine.py | 4fa7f512399b5af2a74cdfa20302349d975f5c568064c6da10154ae0f2cea3f2 |
| app/flow_api.py | 3ac7483e5aa12bfc84b7abcf0a6f962bb08eb98f4a245ebe433b30efc8cae6fd |
| app/business_assistant_service.py | 5d96f2e2b6ab936a7162322c2e0bd9751ca1d221737494a8b4ebf51e919f2ee7 |
| app/assistant_runtime_plans.py（沿用） | 66d4ca0026cc16639f2d211c3f92f281a53fcb95b81d66114954eae35dba2123 |
| app/user_access_service.py | 34edda137dabb428e636e823c1a4d80431ae39fe4386481dac45c4fbb581bf77 |
| app/main.py | 0f319441bed474cde826947ac95a78b5433a4af4bec86fc45e6394be7321e13d |

## 集中验证待办

原hook事务回滚、同request幂等、Runtime关闭旧schema、跨店权限扇出、task-only条件、carry_forward卡、grant probe失效、逐事件并发重复/小ID晚提交、同Session多Plan批量、部分入队失败、最终授权变化及30/120/600退避均待DeepSeek实际验证。原验收全部未勾选。

没有新增或运行测试，没有导入app、访问数据库、调用模型、迁移或启动业务/浏览器服务；没有本批待收尾进程。编码审阅结论与单项状态只在implementation_plan.md登记；CP-10须待M4.8/M4.9编码完成，正式验收仍后移。

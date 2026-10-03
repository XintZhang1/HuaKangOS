# PATCH-M8-1-FOLLOWUP-CLOSEOUT-01

2026-10-03，当前唯一M8.1；按业主收口至待人工验收授权，补 `M8-1-virtual-delivery-gaps-v1.md` 表9/11/12可合成路径。不得把未执行或局部覆盖写为全表、全M8或生产通过。

允许仅新增 `tests/browser_click/runtime_followup_closeout.py` 及独立任务记录；原生产、共享provider/fixture/入口不改。主代理集成该文件导出的合成provider扩展、只读观察器、有限场景三元组及独立LONG场景。所有应用导入只发生在官方隔离实例安装contextmanager时，模块导入无应用/库/服务副作用。

全部前置接待由原管理员页面创建，原Case/Task ID来自实际201及读取，不复用已消费的lead_plan。唯一命名原员工输入明确两张Case、Task和接手员工，合成模型只返回原save_work_plan/prepare_business_form；后台按原Grant、真实条件和原身份判断，不提交业务。本人另一个真实登录页确认第一卡后，原登出会话的active Grant准备唯一后继且后继未自动办理；以真实worker.tick和条件求值中的原GET分别留证，20次空poll不能写成20次事实重读。

在途revoke固定边界：只对唯一输入的首个Grant准备响应，在外部文件声明实际Run/Grant/Plan身份后有界等待；本人原跟进UI结束后放行原合成prepare响应，核旧Grant/Run停止且无新卡、Work准备或业务变化。不能通过SQL、时钟、期限或伪造原回执制造结果；心跳抢先中断须记录失败，不算迟到prepare已经返回。

取消/过期：原pending卡原UI取消，核原业务零变、依赖不继续及无新卡。自然过期独立场景按原expires_at实际等待30分钟，原UI显示已过期并禁用确认，原身份Cookie/CSRF补充HTTP确认拒绝独立记证，核无原业务变化、无自动补卡与依赖阻塞；不改生产deadline，不以Run stop/Grant过期或HK099替代。该LONG场需主代理调整实际runner/CI工作量预算，完整入口最终真实执行后才记通过。

观测仅写本次外部evidence，按PID独立日志记录tick、计划事实求值和原GET方法/状态，不保存凭据、模型原始推理或完整响应。剩余表10 source-map各hook回滚/乱序、表13真实摘要/60秒凭据/goal结构及管理员撤权不得从这些局部结果推定，后续精确增量另登记。

2026-10-03 `closeout-contracts-03` 失败保留后的装置修正：原首卡commit不等于准备Run终态；先由真实RunItem映射等待同Plan Grant Run的succeeded/nullerror及原worker tick，再刷新原UI busy。logout后继也由两张真实卡映射等待两准备Run终态，再严格核全部Grant Run恰为这两条、卡恰为两张。该轮logout故障截图UTC04:08:27.5758499，第二Run实际finished_at为04:08:27.806353，约230ms后才完成；实际仅两Run/两卡，不能把此前即时计数误报成真实重复准备。cancel与goal原控件disabled同属刷新早于首Run终态的装置窗口。本人在途revoke场该轮通过；以上修正尚待全新镜像复验，不改原生产或断言标准。

`closeout-contracts-04` 原失败保留：logout第二Run已真实成功，但通知由后续outbox独立tick保存；截图UTC04:31:05.437303，后继proposal_ready实际04:31:07.301581、对应Wake分发04:31:07.302583，通知最终全集唯一。现额外等待该后继真实proposal_ready耐久，再核完整通知唯一，不把Run终态等同通知事务完成。summary最终原UI结束第一次点击被“正在核对，请稍后再操作”guard拒绝；现所有共用结束前从原刷新入口完整重读，只读等待同Plan及work/plan loading和Run/busy全部结束，再原两点击，不改或绕过二次确认守卫。原UI读取开始未立即重绘按钮和同scope GET清arm的源码竞争风险已单独报root，生产不在本子任务修改范围。

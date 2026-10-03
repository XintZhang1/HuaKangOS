# PATCH-M8-1-SOURCE-HOOKS-CLOSEOUT-01

2026-10-03 原入口故障判定接线追加：09 在七类 source 与无Grant事项关闭的8次实际事务中逐次取得原HTTP500、唯一真实注入、业务/Runtime/登录整行回滚，末尾仍被 `scenarios.py` 的普通零5xx全局守卫判失败。允许该固定故障场景在每次完整断言成立后登记精确 method/path/status/注入scope/kind；入口只接纳8个不同scope、七类生产者及plan_close全部齐全、全部回滚已证、与原生响应500多重集完全相等。其他场景继续禁止任何5xx，额外或缺失响应均失败，不只按URL白名单忽略，不跳过原事务/唯一/全行/hash断言。允许修改本脚本登记及 `scenarios.py` 此窄全局分支；09原失败证据保留，修后待独立审阅和新候选实跑。

2026-10-03，当前唯一M8.1表10，按原 `M4-7-source-map-v1.md` 七类实际生产者逐项留事务证据。仅新增 `tests/browser_click/runtime_source_hooks_closeout.py` 与独立任务；root另轮集成固定contextmanager、provider（若必要）、白名单及场景，不改已冻结四模块、生产、共享入口或计划。

各原来源只从原页面产生：原Flow create、原主管Task交接、pending卡原UI取消、本人Grant enable及无Grant Plan close、原管理员对独立新员工授权修改/密码重置、仅独立新店active改变。固定装置只在该原事务实际调用的emit_wake_event或权限Core `_emit` 已插入真实signal后抛一次RuntimeError；匹配原实际source/owner/store，不SQL插入或更新业务/source/Wake，不更改Clock/deadline，不在模型返回任意写入。每项须实际装置账本及同事务源行/信号已flush，HTTP原失败、所有原业务hash与原登录会话hash完整回滚、同范围既有Wake及新Wake完整回滚。后续解除该scope后只按原页面重新核对；不把失败请求未知结果盲重放，也不掩盖原已提交业务的独立助手结果保存边界。

重复与后到source使用实际原FlowEvent和原自然dispatcher退避：对首个原Flow来源固定一次分发失败，原native201保留；随后原页面创建第二真实来源，使后者在先者自然30秒退避期间先分发，后者的真实created_at晚且dispatched_at早；先者自然恢复独立分发，实际通知唯一、Task仍open。实际同signal重复emit只复用原生产者此次真实source，验证原signal_key返回同ID且既有状态/attempt/next_at不变，不造来源或改调度，不将其推定成所有原业务幂等路径已验收。已读不复活须通过原本人通知打开/已读路径及真实重复来源保持验证；无法得到对应真实通知时明确失败，不用空通知推定。

本补丁覆盖七类source-map实际函数和明确原动作，不推定其它领域旁路、所有Proposal结果/自然过期分支或所有grant生命周期。新增文件仍须root全新隔离入口动态验证，局部静态检查不写passed。

恢复后的静态审阅补齐原 create 响应到 Case 页面实际渲染的等待，再点击该原 Task；新员工事项共用上述已登记的原管理员 Task 转交前序，解决原按最少待办分派可能交给另一接待的实际权限边界。没有 SQL 改归属或伪造原读取结果。固定 producer 装置仍只在原 source 已变化、原 Wake 已 flush 后抛错，同范围原业务、登录会话及全部新旧 Wake/Run/Step/通知均须完整回滚。

contracts07 的原 500 表单 close 只触发 `workforms.js` 未保存内容确认；脚本现按原控件明确放弃填写后才导航，并严格核丢草稿业务不变。原 notice/read 422 暴露前端 `{}` 与后端空请求体合同矛盾，由 root 修生产前端，本模块记录真实响应、保持 HTTP 200 和真实持久 read/任务未完成断言，并核确无请求内容。原失败外部证据保留；这些修复尚待新镜像实测。

contracts08 四场正常收尾、两通过两失败；source-map 仅 Grant 和额外无 Grant Plan close 的实际 HTTP 500/原业务与登录及完整新旧 Runtime 行回滚通过，后六类尚未到达。原 plan_close 500 截图仍为“确认结束这件事”；脚本在浏览器 catch/finally 尚未结算时立即 refresh，原同 scope 读取保留了此前 arm，动作“第一次核对”实际发送一次关闭 POST 200，下一点击再找已禁用/销毁按钮超时。不是后台撤权或第二次事务回滚失效。只在本模块 `_arm_original_end` 补原前端结算及两次读态等待：刷新前必须同事项且空闲、未 arm、原“结束这件事”可点击；刷新后再次核同态；第一次核对后须同事项已 arm、空闲、确认按钮可点击。仅观察原 Workspace 状态和原控件，不改状态、不强制点击、不重放；原 500、唯一故障账本和全部回滚 hash 断言保持。late-source 本轮空体已真实发出，但原全局 JSON Content-Type 守卫返回 415，由 root 保留空体并恢复原类型头，不改后端守卫。修改前登记，旧失败全部保留，待新镜像复验。

contracts09 已实际完成八次原 source/业务/login/新旧 Runtime 全行回滚，但原共享零 5xx 汇总门禁使该场失败；root 另登记只允许此固定场景八个已证明 scope/kind、与实际响应 Counter 完全相等的精确期望故障接线，其他场景仍零 5xx。contracts10 仅前两回滚通过，后续刷新前等待未 arm 20 秒失败；第二次 500 后仍有同 Plan GET 200 晚返回，没有新的员工点击，旧 `loadPlan` 可用启动时捕获的 arm 恢复已清意图。网络未直接记录 JS clear→restore 赋值，结论是时序与源码推断，root 另修生产读取成功时必须当前 arm 仍存在。这里仅在 `_arm_original_end` 三个原等待超时分支追加纯读 Workspace/按钮及同 Plan/Grant 最终状态和原员工页面截图，诊断失败单独记录且原超时原样 rethrow。等待条件、20 秒、500/唯一注入/hash 与成功边界均不改；不补发动作或修改任何状态。修改前登记，原失败不改写，新指纹由 root 复验。

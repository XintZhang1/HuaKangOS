# PATCH-M8-1-EMBEDDED-WORKER-LOOP-01

2026-10-01，M8.1 当前实现缺陷修正；前序三个验证run全部结束，原Python/监听均不存在。

## 真实失败及判断边界

reports04 员工管理的错误旧密码负例真实发送原同源POST，30秒未收到响应。员工原两会话保留，无改密审计；worker心跳同秒停止，服务日志4条SQLite BUSY，最终provider文件缺失，停止请求15秒后被执行器收尾。正确改密前序已通过，不替代该负例。

静态实际代码中，`Worker.start()`把 `_serve` 直接放在Web事件循环；worker claim/recover/heartbeat以及异步outbox/runner内同步数据库阶段可能等SQLite写锁。原写入口在认证前取得writer时，事件循环同步锁等待可能阻止依赖退出释放writer。这是与本次观察一致且源码确定存在的阻塞机制；日志不含栈，不能把每条BUSY硬指到某调用。禁止延长测试超时、重试、关闭worker或取消错误密码负例求通过。

## 精确允许范围

只允许 `app/assistant_worker.py` 的嵌入生命周期：`start()`沿既有 `run()` 在独立线程及其自身asyncio循环执行完整worker，所有Session仍在该worker线程内创建/结束；记录真实所属循环/serve任务以供跨线程取消。`stop()`保留先停领取、原超时、已领取Run安全边界及收尾，超时时向worker所属循环调度原serve任务取消，等待实际结束后才清除代理任务。禁止仅取消线程代理而把仍运行的worker记 stopped；重复start仍不产生双worker。

既有独立进程入口、单执行槽、租约、调度/去重、事件/计划/通知/模型合同、本人重验权限、原业务禁止自动确认、原短事务、默认关闭开关不改；不改Web auth接口、数据库等待时长、runner、outbox或fixture，测试原400/422/30秒谓词保持。必要docstring同步实际生命周期，不新增平台或依赖。

## 复核与验证

独立代码审阅聚焦thread内Session、stop先置Event、真实serve取消、完成等待、start竞争和原standalone行为；AST及差异核对后，全新员工管理负例和报表闭包，以及当前原9助手/安全场景和最终全53实际复验。动态前仍pending；不宣称PG、独立Linux进程故障恢复或生产验收。原失败/缺少最终provider证据保留。

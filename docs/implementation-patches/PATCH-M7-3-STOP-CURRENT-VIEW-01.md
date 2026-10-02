# PATCH-M7-3-STOP-CURRENT-VIEW-01

2026-10-02，业主虚拟数据优化后交付授权，当前仍只M8.1在办。原inflight-stop33已真实通过，但普通在途停止首次从创建时queued旧view版本提交固定出现409，原UI重读后员工再次点击才200；这是保护性冲突，原版本守卫正确。根核assistantruntime SSE只在流结束重读RunView，准备中按钮使用旧version，因此本项优化员工停止的一次点击路径，不把原409改称业务失败。

精确生产范围仅web/businessassistant.js的data-ba-action=stop/current.runId分支。员工原明确点击后先用原runtime.getRun(runId)获取服务器当前受授权RunView，捕获原runId/generation、await后重验原businessAssistantAlive和当前runId相同；若已终态/已请求停止则沿原view/SSE终态，不再发取消；只有原queued/running、allowed_actions含cancel及原安全整数version才调用原cancelRun(runId,version)。不猜版本、不改Run/权限/时钟、不自动确认业务、不调用模型、不由打开页面自动取消。

GET与cancel间仍可能真实变更，原expected_version/409及员工核对后再点击合同保留；catch与409重读均使用捕获的原runId并受同generation/user/store/run守卫，切店、登出或新会话迟到不污染或提交旧Run。原legacy停止等待分支、批量/单张业务确认及其他模块完全不改。runflags默认关闭、源输出外置与原正式门槛保持。

之前33是优化前真实证据，生产改后不能继承为当前源码通过。静态JS及独立审阅后，新全新镜像定向原在途停止、同候选关键故障重复与最终完整点击CI验证。测试保留保护性409分支，不为了追求HTTP200删除版本断言；不开真实模型、真人或生产。本轮必要补丁不使M7.3/M8.1正式状态假done。

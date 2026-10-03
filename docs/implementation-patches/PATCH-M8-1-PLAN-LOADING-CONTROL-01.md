# PATCH-M8-1-PLAN-LOADING-CONTROL-01

2026-10-03 10收尾竞态修复：source Plan close 原POST500后的未arm结算等待20秒超时，期间无员工点击，原Plan整行仍active/version2/goal1，已有同Plan GET200晚返回；原件不改通过。静态定位 `loadPlan` 在开始时捕获 armed=true 后，只核同scope/goal/status/grant，即使 `setFollowup` 错误处理已清确认意图，迟到GET也可恢复true。新增成功保留条件 `state.revokeArmed === true`：只保留此刻仍存在的原确认意图，清掉的不会因旧GET复活。原serial/context/id/goal/status/grant/allowed_actions及原POST核验、无重放合同保留。网络未跟踪JS两次赋值，因果为原GET时序与源码推断，下一实际失败额外纯读状态取证；不声称已直接追踪clear→restore。原500与整行回滚断言、未arm等待不降标准。

2026-10-03；当前 M8.1 实测修复。允许修改 `web/assistantworkspace.js` 的 `loadPlan` 开始读取时展示刷新状态，以及当前浏览器验证等待该原状态的范围。

外部 `closeout-contracts-04` 摘要窗口场景的失败截图显示“正在核对，请稍后再操作”，未发送 revoke POST。实际 `loadPlan` 已设置 `planLoading=true`，但相同 Plan 分支直到 GET 完成才重绘，旧按钮仍可点。开始 GET 前立即调用既有 `patchCurrent()`，让原按钮按既有 loading 合同禁用；不增加重试，不替换服务器版本，不改变二次确认、来源变化清确认或权限守卫。

手工审阅：相同选择和新选择均立即显示 loading；原 serial/身份上下文阻止迟到响应；失败/结束沿原分支重绘。Node 静态语法检查及浏览器定向复验另记实际结果；本记录不表示业务验收通过。

2026-10-03 后续实证 `closeout-contracts-05`：outbox 自然恢复、唯一后继及通知断言通过后，第一次结束点击已显示“确认结束这件事”；第二次没有 followup POST，期间原后台刷新读取相同 Plan。源码确认成功的任意 Plan GET 无条件清除二次确认，进度刷新可让已开始的结束操作回到首次点击。补齐同函数范围：只有同一 Plan、相同整数 goal_version、相同 status、完全相同服务器 grant 以及当前仍允许 revoke 时保留原确认意图；任何身份/选择/来源错误、目标/授权/可撤销范围变化仍清除。仅后台进度 version 更新可保留意图，实际 POST 仍由原 setFollowup 再次 GET 比较目标/grant/action 并使用服务器最新 version，CAS 409 不重放。

`closeout-contracts-06` 三场完整执行，CAS/notice 两场通过，logout 在合法 409 后的二次核对断言失败；服务 0/forced=false，日志无 SQLite 锁错误。原因是新的同范围 GET 保留了 catch409 之前的确认意图。补齐 `setFollowup` 同一错误出口：仅当前有效请求进入 catch 时立即清除 revokeArmed，之后沿原 409 重读/403与404收起/其他失败提示路径。所有失败均需员工重新核对，普通成功后台刷新保留意图；不改原 409 断言、不重放请求或伪造成功。原失败证据保留。

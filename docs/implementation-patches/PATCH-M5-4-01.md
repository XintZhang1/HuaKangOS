# PATCH-M5-4-01：站内提醒的真实来源生产接线

2026-09-28，配套M5.4。依据用户“后续授权不用再问，都默认允许”的持续范围授权，在原workspace/outbox/API允许文件之外补齐以下固定生产者。只接真实事务内来源，不改业务状态、权限或确认。

## 精确补充范围

- `app/business_assistant_service.py`：共用卡片持久化在flush后发真实pending卡信号；原卡结果信号门禁接受Runtime或notifications任一开启。原提交、版本、确认、回执及事务所有者不改。
- `app/assistant_runtime_plans.py`：新增仅flush的固定Plan信号助手；实际保存Plan、条件状态/等待原因变化和定时核查语义变化后调用。单纯next_check_at、observed_at或证据刷新不制造提醒；原Grant生命周期信号保留。
- `app/assistant_runtime_runner.py`：原准备结果使Step/Plan实际变化时追加Plan信号，仍在原fence事务内；新卡由共用service生产，不重复建设来源。
- `app/flow_engine.py`：原FlowEvent信号门禁接受Runtime或notifications；ensure_task既有flush后，仅新任务、重开、接手人或到期日实际变化发真实Task版本信号。原分配和业务规则不变。
- `app/flow_api.py`：既有真实任务转交信号同样允许notifications独立开启，不改变原权限、版本或接口返回。
- `app/assistant_runtime_queue.py`：仅`_state_event`在真实生命周期事件落盘后，为有真实Plan的终态Run及本人login的queued继续动作追加固定来源信号。覆盖正常收尾、无最终回复的失败、lease回收及真实重新继续，不改租约、重试、状态机或入队规则。
- `assistant_runtime_workspace.py`允许在当前Plan条目层叠加固定Run阻断投影并供通知复用：严格同owner/store/session/plan/goal，按原`_followup_activity`的真实login继续条件计算；仅Plan item显示failed/needs_input，不伪造Step或业务状态，不展示usage或回复内容。相同标量纳入来源复验。

新Plan信号为topic=`plan`、source_ref.type=`plan`、signal_key=`plan:<id>:<version>:<status>`，只含真实门店及Plan引用。新卡沿用topic=`proposal`、signal_key=`proposal:<id>:<version>:pending`。Task沿原`task:<id>:<version>`；Flow沿原`flow:<event_id>`。outbox保留原grant/plan来源兼容，派发只依据当前真实源，不能用旧信号恢复旧状态。

补充Run来源为topic=`plan`、source_ref.type=`run`、signal_key=`run:<id>:<version>:<status>`，refs只真实store/plan及Run来源。消费须验证真实Run与Plan所有者、门店、会话，且阻断只对当前goal_version生效；通知以真实blocking Run ID去重，心跳与重复核查不重提醒。取消本次执行不能被文案称为原事项已结束。

原确认首次进入executing的事务额外记录`proposal:<id>:<version>:executing`，首次next_attempt_at为原started_at后三分钟再加一微秒，匹配原“严格早于now减三分钟”判定，防止恰好边界消费后漏提醒；复用事件不重置调度。届时只核当前真实状态；仍executing才按原有效uncertain语义提示，已终态则投影当前结果。该延期不调用原提交、不改变卡状态、不影响已经持久化的冻结提交。此窄点也纳入service允许范围及outbox固定source状态校验。

## 状态及异常路径

生产者与原源同事务，只flush不自提交；原事务回滚时信号也回滚。后续通知分发失败只留下pending重试，不反向更改已成功业务。重复来源不重置已派发事件或已读通知。notifications可以独立于Runtime/跟进开启；关闭Runtime不因此调用模型、创建Run或授权，两个相关功能均关闭时不访问新信号表。

通知的source_key按真实源及当前需处理状态去重：Task不按FlowEvent数量重复提醒，Plan不按调度心跳版本重复提醒。转交或撤权只过滤原收件人的不可见内容；不能因此宣称原任务完成。原卡过期/取消与业务成功分开。背景生成不伪造登录、Grant或管理员身份，不发外部消息。

本轮只实现并源码审阅，AST/UTF-8可静态检查；真实去重、回滚、并发、故障恢复、权限、三分钟未知结果和幂等已读的运行验证仍交DeepSeek，不扩展通用通知平台。

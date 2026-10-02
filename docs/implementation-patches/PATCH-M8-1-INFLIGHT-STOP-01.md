# PATCH-M8-1-INFLIGHT-STOP-01

2026-10-02，沿业主持续交付授权，仍只在M8.1补原在途取消故障。preparation-crash30/31原单场已真实完成，同候选故障恢复重复核对另记；相关本地进程与服务已终局。原CI53属于9a6505b，不继承为当前测试全量结果。

当前停止按钮`data-ba-action=stop`调用原POST `/api/business-assistant/runs/{id}/cancel`，现有慢速退出只测两秒查询，跟进撤销发生在后继卡准备后；缺真实点击停止在途准备的证据。精确允许：`tests/browser_click/provider.py`仅新合成`浏览器客户cancel_`名字第二轮准备响应的固定有界阶段/释放标记；`runtime_faults.py`只追加该原生点击场景，复用原外部原子JSON/readonly证据，不改既有崩溃断言或控制器；`scenarios.py`注册第55场，原54全部保留；README、当前M8.1/原任务/递增检查点维护。run.py、fixture、生产代码不变。

从实际Chrome本人本店新客户指令进入原inspect成功，再暂停合成第二轮准备工具响应；阶段保存本轮run/session/本人门店/唯一阶段标记，配置与证据全部外部。浏览器实际点击“停止本次准备”，保留原Cookie/CSRF/expected_version/实际200及原Run stop_requested。running取消200仅请求停止，不直接视作terminal；随后仅外部释放合成响应，不改数据库、时钟、租约、原Run或业务API，不重发聊天。

必须明确证实returned_after_stop：原响应在已置停止后确实返回，最终原Run cancelled、busy/lease释放、原request_id/fence/attempt保持；本session新卡/prepare WorkItem/确认0，原inspect工具整行不变，无新prepare工具执行/成功回复/重排与proposal.prepared/run.completed事件，seq连续至run.cancelled。全原业务表hash不变，真实页面终态“本次准备已停止”且刷新仍无卡。原20秒心跳保持；若心跳先取消合成task另记heartbeat_aborted，它不满足迟到返回子项，不假计passed。

固定阶段有界超时即失败，不能无限等待或吞取消。若原取消409，只允许保留真实冲突、原UI明确重读后最多一次员工点击，禁止循环重放；测试不能通过SQL伪造取消或卡。两个全新隔离实例按相同最终源码/测试/依赖指纹重复；provider合成发起/返回/取消分别留证，真实模型/外部0，正常服务收尾及CLI退出按真实证据记录。此项不代Grant在途撤权、卡到期/取消、双活晚写、批量每行/未知后停、发件箱/通知及后续原环境/人员条件。

首场inflight-stop32已真实终局failed（场景1/宿主CLI3、服务0/forced=false），15秒门控超时，无停止POST，原证据保留。根源码和网络核对确认执行器误等：assistantruntime的原SSE在流结束后才getRun，页面视图可保持提交时queued但取消按钮有效；原服务端阶段实际running/version19、inspect succeeded已真实成立。原页面不保证在门控结束前snapshot.view.status=running。仍仅本函数前置改为接受原queued或running视图并实际cancel可用；不改生产、不发GET/fetch桥接、不放松服务端running/本人门店/原busylease/真实取消200与迟到响应的严格断言。首次409仍依原UI自动重读并最多一次明确员工点击。原32关联进程及52476端口已停止，之后新目录重测，不复用旧阶段。

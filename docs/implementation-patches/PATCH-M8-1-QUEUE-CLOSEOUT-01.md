# PATCH-M8-1-QUEUE-CLOSEOUT-01

2026-10-03 core07 定向复验：双实际存活 CLI、原90/30秒恢复、新fence/完整lease与busy保护、迟到旧写409及三卡数据库断言通过后，末尾DOM count0失败。独立截图/网络审阅确认正确页面只渲染当前选择的一张卡，原选择框有完整A/B/C三个真实ID，GET均200；测试错误要求三卡同时render。仅 `_three_cards` 核原选择框完整ID集合，再按每张真实ID原生选卡，保留逐张唯一显示和待确认断言，整组事务/九kill/租约/业务零变合同不变。原失败保留，不改变产品展示规则或增加提交重试。

2026-10-03；当前 M8.1 收口。范围仅为 `tests/browser_click/runtime_queue_closeout.py`、本补丁与 `docs/architect/tasks/runtime-queue-closeout.md`；生产源码只读。共享入口/provider/fixture 注册由 root 单独集成。

依据 `M8-1-virtual-delivery-gaps-v1.md` 第 1/2/3/14 项及 Runtime 原队列、90 秒租约、30 秒恢复退避、统一批量准备事务、流协议合同。既有单卡 commit 后 kill 不覆盖旧进程存活晚写、三行未提交事务回滚、重复 tool ID 和没有 DONE 的真实截断。

装置只在 run.py 仓库外全新镜像实例使用。数据库证据 SELECT-only；固定子进程启动前设置原隔离环境并保持禁止外网。所有准备均员工原 UI 登录/发送；HTTP 请求去重与原 emitter 合同分别标识为独立 API/内部合同证据。只重用真实已提交 WakeEvent 的原 source/key/refs，不伪造业务来源；不得 SQL 改事实、缩短租约、期限或回放确认。

实际 Worker 调用原 runner 时默认 `stream=False`，并不走模型 SSE。协议补测使用既有 `Worker(runner=...)` 依赖注入，仅在两条精确 `队列流协议 duplicate/truncated_<本次随机标记>` 的原 UI Run 中调用原 `run_once(stream=True)`，经原 provider SSE 解析器与原事务守卫验证；其余调用保持原 JSON 模式。这是明确的隔离适配器 SSE 执行面，不能写成生产 Worker 默认使用 SSE。root 已审阅认可该接线，生产默认不修改。

固定故障点为准备保存前、三行各自原 `_prepare_row` 前/后、统一 `_finish_write` 前、整组 `_save_preparations` 真 commit 返回后。未提交边界 kill 必须整组三卡/Work/映射回滚、先前 durable manifest/children 保持；提交后必须三原卡整体保持。另一场将旧进程同步阻塞在写事务前，原心跳自然停止，第二原 CLI 自然回收租约，完成原 Run 后放行旧进程，核旧 fence 无法写回或释放新 busy。

异常路径：阶段/PID/Run/owner/store/fence 不匹配即停止；命令文件只寻址装置拥有 PID；未命中指定边界、进程未真实退出、自然恢复超时、原状态变化或协议后产生完整准备均失败。网络失败/子进程账本/完整场景执行由外部证据保留；没有运行不登记 passed/done。

当前记录：装置实现已落盘并完成静态人工审阅、AST parse 与限定 diff whitespace 检查；本子任务没有启动服务、浏览器或动态验证，不登记通过。旧租约窗口另外将第二原 CLI 暂停在其原三卡统一 commit 后、Run 尚 running 且 busy 持有时，释放旧 CLI 保存调用，实际旧 fence 409 后逐行核完整状态与 busy 未变，再释放第二 CLI 正常收尾。固定外部控制仅作用于各自 Popen 身份、精确 stage 与原 Run，不暴露任意 PID/路径/SQL 控制。root 集成后在同最终指纹的新实例实际执行，原正式模型、PostgreSQL、员工试用及生产条件仍另留门槛。

2026-10-03 装置归因与修正：root 的外部 `browser-click/closeout-contracts-02` 已结束，`run-summary.json` 记录服务正常退出 0、`forced=false`；旧实例与失败证据只读保留。`runtime-duplicate-request-wake` 的原 UI 请求去重已取得 202 同 Run 与 409 内容冲突，但随后 sales 本人 Run `73b229ab-d8d1-4c59-a4ce-1ef927830449` 的 `save_work_plan` RunItem `71c5feb3-b65c-465c-8433-3d6453186ff4` 实际为 `failed/not_found`，真实 Plan 数为 0。夹具计划引用原 admin 创建、未分配的 case 81/82 和 task 192/193，sales 并非 owner/created_by/assignee；`flow_engine.can_read` 的原守卫正确拒绝。reception 同样受本人范围约束，不能换成该岗位绕过。模型后的“事项已准备”及 Run 的 succeeded 不能证明保存计划成功，本装置的真实 Plan 断言正确失败。

本次修正只改变独立场景的原 UI 登录为夹具已有 manager 本人：其当前门店原岗位允许读取该原单及分派接待；全场请求、Cookie/CSRF、会话、Run 与 Plan 均保持同一本人。额外核保存计划的原 tool 真实成功以及 Plan 的 owner/store/session/engine_version，明确记录真实原单与待办来源；不删减唯一 Plan/真实分发/重复 Wake 的断言，不写 SQL 制造 Plan，不改变原权限或生产代码。该修正需 root 在新外部实例按最终指纹复验，旧失败不改称通过。

长故障启动前静态审计另发现控制器接续缺陷：独立 QueueCloseoutController 的 arm 正常 stop 原控制器拥有的 Gen1/Gen2 后，其并行原 serve_commands 仍只接受已记录 killed 的 current 退出，会正确报非预期退出并取消 queue 控制；这是装置没有显式交接原控制监视器，尚无此路径动态结果。修正仅在独立控制器增加一次精确内部退役：arm 先记录原 monitor 与所拥有 current 身份，主动取消该原 monitor，再逐个正常停止其拥有 Popen 并核退出 0；外层仅接受这次明确主动取消，继续监督 queue。原首次 armed Gen1、原 kill/restart、原 nonzero/normal 退出区别及共享控制器源码保持；没有任意 PID 或生产进程停止入口。

双 worker 比较窗口经原 `_RunHeartbeat` 与 Worker `_beat_loop` 源码核对，两者实际都在该 worker 同一事件循环；rival 在原统一 commit 后同步固定阻塞，其合法心跳不能在此窗口更新 Run 的 lease_until 或 Session 的 busy_until。装置保留完整逐行比较，不排除租约列；额外核真实 `held_after_commit`、未收到 release、原新 fence/lease owner、原准确 busy token 与两个期限尚在未来。释放 rival 的控制器即时调用其所拥有 Popen.poll，核真实 alive，读取同一新 fence/原 lease/busy 后先留 `queue_rival_release_requested` 证据再发精确释放；场景再核该证据与完整比较行的关键列一致。固定 hold 最长 55 秒，小于新90秒租约；它是外部比较窗口界限，不改变 Run 的原180秒验证配置或 lease/deadline。超时、进程退出、期限丢失及恢复失败仍如实失败。

2026-10-03 控制确认等待审阅：已先只读核对外部 `closeout-contracts-03/evidence/run-summary.json`，其场景退出 1、complete/passed 均 false；服务收尾 returncode 0 且 forced=false。旧失败原件保留。静态核独立 idle 控制路径在两个 owned Popen 存活时，各自正常 stop 的上界 12 秒，加原常规 CLI 启动等待 25 秒，顺序理论上界为 49 秒；此前 `_command` 的确认等待 40 秒会先于正常控制路径上界结束。root 授权只将独立 `_command` ack 等待改为 55 秒，覆盖该装置控制上界并留 6 秒调度余量；不改固定故障 stage 等待、场景总限、原90秒租约/30秒退避/180秒 Run 配置或生产代码。该上界来自装置源码审阅，尚无长场超时动态事实，不能写成已验证通过。

# 任务：Runtime 队列与流协议收口

**任务 id 与负责人**：runtime-queue-closeout；子代理 queue_faults，向 root 报告；共享索引由 root 维护。

**目标与交付结果**：以固定仓库外装置补齐 M8.1 缺口表 1/2/3/14 的可执行代表路径，原 UI 准备与独立 HTTP/emitter 合同证据明确分开。

**架构依据与决定**：PATCH-M8-1-QUEUE-CLOSEOUT-01；原 `_save_preparations` 统一 commit，原 90 秒租约与 30 秒退避自然恢复。所有模型响应离线，不更改生产合同、时间、SQL 事实或原确认路径。

实际 Worker 默认模型 JSON；两条精确协议输入经既有 runner 依赖注入选择原 `run_once(stream=True)`，明确为隔离适配器 SSE 执行面，生产默认 False 保持。root 审阅认可；其他准备与查询响应遵守原 stream 参数。

**代码快照与影响范围**：HEAD `7a4f8722bc66029d69cdf2b35b872c85f35f0d59`，开始工作树干净；仅独立模块及本补丁/任务记录。run.py、scenarios.py、provider.py、fixture_server.py 由 root 集成。

**已完成与当前位置**：原队列、runner、worker、emitter 与既有进程控制审计完成；独立模块已落盘。提供 4 个场景：原 UI 发出后的同 request_id HTTP/真实 Plan 唤醒去重、存活旧租约晚写、9 个三行事务边界真实 kill/自然恢复、重复 tool ID 与无 DONE 早 EOF 的实际 SSE。新 owner 在原三卡统一 commit 后仍持 busy 时固定暂停，释放旧 owner 的原保存函数，核实际 409 且完整 Run/items/events/session/busy 无变化后再正常完成新 owner。

**下一步**：root 注册 4 场与镜像白名单，fixture 组合 extend_provider/queue_emitter_control/QueueCloseoutController；embedded Worker 和原 runtime_faults 子进程增加 queue_stream_runner 既有注入，原子进程 provider 组合 extend_provider。先定向动态验证，再依最终指纹执行完整注册入口。共享入口由 root 修改，本子任务不写它们。

自有 CLI 已叠加 receipt/followup provider 与 fault/observer，原常规 idle CLI 也保留这些扩展；观察器采用每 PID 外部文件，由对应负责人维护共享格式。9 处场景间通过原 UI 明确选择“保留当前事项并打开”，保留所有待确认卡；不用直接抹前端状态或取消旧卡来绕开守卫。

**验证与实际阻塞**：已执行 Python AST parse（通过）、限定文件 diff whitespace 检查（退出 0），未导入 app、未启动服务/浏览器、未动态执行。人工审阅已核对真实表名、prepare_inputs manifest 结构、Run 202 原入口、CSRF、整组 commit 与恢复原 input/children ID 合同；修正了 kill 后 rival 启动、旧 owner/new busy 的真实窗口和全 owned PID 异常清理。没有动态成绩；状态仍待 root 集成复验。9 处 kill 均保留原 90 秒租约及 30 秒首次退避，整场需约 20 分钟，外层总超时由 root 结合全套耗时设置。

**首轮动态后的装置修正**：root 已运行 `closeout-contracts-02` 并正常关闭服务（退出 0、无 forced）；流协议场由 root 报告 passed，不能因此登记整套通过。去重场已取得同 request_id 202 及异内容 409，随后原 UI sales 保存接待计划的真实 tool 却为 failed/not_found，库中无 Plan，故严格断言失败。只读原数据库与当前权限代码确认 admin-owned 未分配原单不在 sales/reception 本人范围；这是装置选择身份错误，权限拒绝正确。先登记该归因，再只修独立场景从原登录表单使用当前门店合法 manager 本人，并核 tool 成功、Plan 本人/门店/会话/结构版本。旧失败证据保持，真实 Plan/唯一分发/重复信号断言全部保留；无 SQL 写入、权限改动或共享文件变更。修正后静态检查与新实例动态复验另记，不把模型文字当事实。

修正后模块 SHA-256 `06a63526c6ee16adca20c139b46b69aca11a4bb645b23bce7fab7396e19acb64`；仅 AST parse 与限定 diff whitespace 检查通过。另以旧合成数据库 SELECT-only 核对现有成功 Plan 的原 tool 状态确为 succeeded、error_code null、engine_version 2，新增断言符合实际表结构；没有导入 app 或启动动态路径。本次场景实际结果仍待 root 在新外部实例执行。

**长故障前控制交接审计**：原 current 被 queue arm 正常停止时，原并行 serve_commands 只接受其已登记 killed 身份，会正确拒绝正常退出并连带取消新 queue 控制。先登记装置原因，再在独立控制器显式一次退役原 monitor，正常 stop 所拥有原 Popen 并核 exit0，外层继续监督 queue；不改共享控制器、不伪记 killed、不改原首次 Gen1 故障顺序。此路径仍未动态执行，须新镜像长故障验证。

**本次冻结**：root 已为自有 CLI 接线 context/goal/outbox；独立修正完成 monitor 明确退役及双worker持有窗口证据。原心跳在同步 rival gate 内实际停调度，故完整 Run/Session 比较保留全部列；核新 fence/owner、精确 busy token、两期限未来、无提前释放，并由控制器所拥有 Popen 的真实 alive 与释放前同列证据佐证。模块 SHA-256 `216e81ae41566c04fe1760370cc4e6a0269a99b68e4aed6edc4ca9907108ad6c`；AST parse、9固定边界/2 process场静态字面读取、限定 diff whitespace 均退出0。一次附加 AST 诊断的错误属性访问曾退出1，随后仅修诊断命令并重做退出0；无应用导入或动态运行。新故障动态、后继正常 idle 的实际可用性及全套最终指纹仍待 root 验证。

**控制确认上界修订**：先核 `closeout-contracts-03/evidence/run-summary.json`：场景退出1、complete/passed false，服务退出0、forced=false；未继承该失败为通过。root 授权修独立 `_command` ack40→55秒：两个 owned Popen 的原正常 stop 上界各12秒，原常规 CLI 启动等待25秒，顺序理论49秒超过原ack40；55秒仅为外部控制确认窗口。阶段与场景总限保持，原90/30/180秒合同及生产源码保持。先登记静态原因后实施，本次没有启动任何验证服务，长场动态证据仍待 root 执行。

该修订后模块 SHA-256 `7fef91e77e82618bfc63dd2090e59a1ddac20e843df375637d291c39f5e97875`；AST parse 与限定文件 diff whitespace 均退出0。除这一个等待常量及上述记录外未变更本次冻结模块；没有动态通过结论。

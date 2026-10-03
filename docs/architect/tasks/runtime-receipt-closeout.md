# Runtime 回执与确认故障收口

负责人：receipt_closeout，向 root 报告。2026-10-03，当前唯一里程碑 M8.1。

目标：补原14组缺口的4/5/6/7/8组，独立模块提供有限合成provider、固定故障contextmanager与五个注册场景。生产及共享文件只读；root负责共享接线、动态验证和计划状态。

依据：implementation_plan.md M8.1原故障步骤和五项完成检查；M8-1-virtual-delivery-gaps-v1第4—8行；PATCH-M8-1-RECEIPT-CLOSEOUT-01。原三个确认事务边界、可靠Flow回执、协调器与只读lookup分开验证，不将Master unsupported或UI逐张确认继承成Flow/batch覆盖。

当前：独立实现已落盘并完成静态源码审阅。root 已执行外部 closeout-contracts-02：冻结前原调用失败及两 backend batch 通过，两恢复场失败，整批未完成；原失败归档保留。该实施者未启动应用、浏览器、验证或真实模型，未写业务SQL，未commit/push。修订候选尚待 root 动态复验。

产物为 `runtime_receipt_closeout.py`，导入零app副作用。`receipt_faults(manifest)`只安装在外部镜像app导入后，沿真实确认函数的ContextVar限定原Session，在原gateway和原commit拦一次指定故障；恢复原函数并严格核已消费arm终局。`extend_provider(provider)`只处理完整员工事实的三种固定请求及已明确授权的后继准备，未命中请求沿既有合成provider，外网仍由原网络guard阻断。五场的Flow/客户都是独立原UI创建，不复用lead_plan。

共享接线由root维护：SCRIPT_FILES加本模块；scenarios导入并合并RECEIPT_SCENARIOS；fixture生命周期在 `provider.installed()`之前进入 `extend_provider(provider)`，并嵌套 `receipt_faults(manifest)`。子进程模式的provider也须进入相同extension。五场放原业务长链/主体策略初始化之前：严格Flow断言原六表各追加1，不把后来已启用EntityPolicy引发的额外冻结上下文当成无关差异忽略。

2026-10-03静态审阅：核原确认三段事务、规范Flow native digest、原read-only execution-result、条件proposal_succeeded、当前Plan成员及协调器不可重放路径。发现并修复装置两个静态缺口：Python Playwright无Page.wait_for_response，用原response监听Future；计划首项只挂真实proposal，避免两个同form_ref导致原_bind_preparations唯一步骤守卫拒绝。Python AST及git diff --check退出0，均不等于动态验收。

末轮静态审阅进一步精确核lookup返回的唯一原receipt ID、原operation、case ID及原case.version，两个evidence须绑定同次checked_at；恢复后由员工点击原待确认过滤页再核后继，避免先前attention过滤状态隐藏卡。4处outbox SQLite锁补丁只读窄审阅：新写保留均在独立读取/native await/rollback之后，原权限/版本/CAS再验之前，未把网络或模型搬入锁；PostgreSQL不变。此为源码结论，竞争失败及完整场景仍由root动态核对。

root必须动态核：原Flow六表精确追加与全部旧行保持；已观察success但result_persisted=false的实际页面/HTTP字段；后台协调result引用原confirmation/receipt且snapshot全字段不变；真实GET source变化mismatch；后继唯一pending且原业务零变；两backend batch三行完整与C整行保持。任何固定hook未命中/身份或payload不符/重复目标/超时都留原失败。

2026-10-03 closeout-contracts-02 只读诊断：两恢复场的首卡、WorkItem、既有确认已由原协调器核对并保存成功，首步骤实际 completed；后继因装置未登记 completion_conditions 转为 needs_input / completion_conditions_missing，未创建后台 Grant Run。这是合成计划合同缺项，原生产守卫正确阻止，无生产改动。修订只在每场原 UI 先建立独立接待后继，读取真实 case/number/version、assign task 与本店销售员工，再把原首卡成功及原 assign 动作可用设为准备条件、该真实 assign task done 设为完成条件。第一原卡故障的六表基线取在这个明确记录的原 UI 前置之后；不称整场零写入。后台仍只准备该原单的分派卡，原单/Task/receipt不变且无后继确认。provider 额外核原真实 Grant Run、首步骤 completed、原首卡 succeeded 和后继原单/任务当前事实，不通过重试、加长等待或虚构来源求通过。该修订的 AST/diff 检查是静态证据，未继承原三场通过为修订完整成绩。

2026-10-03 core03 前置失败保留：root 确认本轮 15 场全部正常退出，CLI 1、服务 0、forced=false，8 通过、7 失败；该实施者没有启动验证。storage 场的独立原接待 created_by=11、本人本店、state=unassigned 和姓名均正确，但原 assign Task 合法自动分派给接待 4，装置误假定其必为创建员工 11。lost-response 场轮转恰好分派本人而通过，不能据此认为前置可靠。按原 `flow_api.assign_task` 合同补最小经理原 UI 转交：仅实际任务不是本人时使用原表单、明确员工选择及原因，观测真实 Cookie/CSRF POST 200 和原单 GET；核原 Task 同 ID/版本递增及单次原 reassign Event，Case/Customer 创建与归属事实保持。经理退出后由接待重新登录原助手，重新读取实际任务与 Case 版本，之后才保存本人事项及取六表基线。未修改生产分派规则或降低原后台权限断言。修订后的 AST/diff 仅为静态证据，动态结果留待 root 新候选复验。

2026-10-03 root 静态复审修正：本前置 `key=assign` 的原转交只改变 Task.assignee_id，`flow_engine.log_event` 追加 Event/Audit/Wake，不修改 Case 字段；ORM version_id_col 仅随实际 UPDATE 增加版本。上一候选误断言 Case.version 增加，现严格断言 Case.version 保持、Task.version 恰好加 1，不改生产行为或放宽任务版本。仍保留前述失败，无服务或动态验证运行。
